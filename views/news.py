"""News page — company news stream with risk-linked AI summary."""

from __future__ import annotations

import json
import html
import ssl
import re
import math
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.parse import urlparse

import streamlit as st
import yfinance as yf

from core.bedrock import _invoke
from core.global_context import get_global_context, render_current_config_box, sync_widget_from_context
from storage.store import get_company_ticker, get_result, load_agent_reports, load_index, upsert_company_ticker


def _secret_get(key: str, default: str = "") -> str:
    try:
        val = st.secrets.get(key, default)
    except Exception:
        val = default
    return str(val or "").strip()


def _news_ssl_context():
    """Use certifi bundle first to avoid local cert-chain issues."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _iso_to_local(iso_text: str) -> str:
    raw = str(iso_text or "").strip()
    if not raw:
        return "Unknown time"
    try:
        if raw.endswith("Z"):
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return raw


def _to_float(v):
    try:
        return float(v)
    except Exception:
        return None


def _normalize_company_tokens(name: str):
    raw = re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()
    stop = {
        "inc", "incorporated", "corp", "corporation", "co", "company", "plc",
        "ltd", "limited", "class", "common", "stock", "holdings", "group", "the",
    }
    return {tok for tok in raw.split() if len(tok) > 1 and tok not in stop}


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_ticker_profile_name(ticker: str) -> str:
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return ""
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        return ""
    for k in ("longName", "shortName", "displayName"):
        v = str(info.get(k, "") or "").strip()
        if v:
            return v
    return ""


def _ticker_matches_company(company: str, ticker: str):
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return False, "", "Ticker is empty."
    profile_name = _fetch_ticker_profile_name(symbol)
    if not profile_name:
        return False, "", f"Could not verify ticker `{symbol}` from market profile."
    company_tokens = _normalize_company_tokens(company)
    profile_tokens = _normalize_company_tokens(profile_name)
    if company_tokens and profile_tokens and company_tokens.intersection(profile_tokens):
        return True, profile_name, ""
    return False, profile_name, (
        f"Ticker `{symbol}` appears to map to `{profile_name}`, which does not match selected company `{company}`."
    )


def _article_sentiment(article: dict, ticker: str = ""):
    entities = article.get("entities", [])
    if not isinstance(entities, list):
        return None, "Unknown", "#94a3b8"

    target = str(ticker or "").strip().upper()
    picked = []
    fallback = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        sc = _to_float(ent.get("sentiment_score"))
        if sc is None:
            continue
        sym = str(ent.get("symbol", "") or "").strip().upper()
        fallback.append(sc)
        if target and sym == target:
            picked.append(sc)

    scores = picked if picked else fallback
    if not scores:
        return None, "Unknown", "#94a3b8"

    avg = sum(scores) / len(scores)
    if avg > 0.15:
        return avg, "Positive", "#16a34a"
    if avg < -0.15:
        return avg, "Negative", "#ef4444"
    return avg, "Neutral", "#f59e0b"


def _parse_iso_datetime(iso_text: str):
    raw = str(iso_text or "").strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _safe_external_url(raw: str) -> str:
    link = str(raw or "").strip()
    if not link:
        return ""
    try:
        p = urlparse(link)
        if p.scheme in {"http", "https"} and p.netloc:
            return link
    except Exception:
        return ""
    return ""


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_marketaux_news(
    api_token: str,
    company: str,
    ticker: str,
    days: int,
    desired_count: int,
    refresh_nonce: int = 0,
):
    del refresh_nonce
    base_url = "https://api.marketaux.com/v1/news/all"
    per_page = 3
    max_pages = 6
    published_after = (datetime.utcnow() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d")

    seen = set()
    rows = []
    for page in range(1, max_pages + 1):
        params = {
            "api_token": api_token,
            "language": "en",
            "limit": per_page,
            "page": page,
            "sort": "published_desc",
            "published_after": published_after,
        }
        symbol = str(ticker or "").strip().upper()
        query_company = str(company or "").strip()
        if symbol:
            params["symbols"] = symbol
        elif query_company:
            params["search"] = query_company

        req = Request(
            f"{base_url}?{urlencode(params)}",
            headers={"User-Agent": "RiskLens App contact@risklens.com"},
            method="GET",
        )
        try:
            with urlopen(req, timeout=25, context=_news_ssl_context()) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8")
            except Exception:
                detail = str(e)
            return [], f"News API request failed ({e.code}): {detail}"
        except URLError as e:
            return [], f"News API network error: {e}"
        except Exception as e:
            return [], f"News API request failed: {e}"

        if not isinstance(payload, dict):
            return [], "News API returned an unexpected payload format."

        data = payload.get("data")
        if not isinstance(data, list):
            err = payload.get("error") or payload.get("message")
            if err:
                return [], f"News API error: {err}"
            return [], "News API returned an invalid response payload."

        if not data:
            break

        for item in data:
            if not isinstance(item, dict):
                continue
            uid = str(item.get("uuid") or item.get("url") or item.get("title") or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            title = str(item.get("title", "") or "").strip()
            if not title:
                continue

            source = item.get("source")
            if isinstance(source, dict):
                source_name = str(source.get("name") or source.get("domain") or "").strip()
            else:
                source_name = str(source or "").strip()
            if not source_name:
                source_name = str(item.get("source_name") or "Unknown Source")

            summary = (
                str(item.get("description") or "").strip()
                or str(item.get("snippet") or "").strip()
                or "No summary available."
            )
            published_at = str(item.get("published_at") or item.get("publishedAt") or "").strip()
            link = _safe_external_url(item.get("url") or item.get("link") or "")

            rows.append(
                {
                    "title": title,
                    "summary": summary,
                    "published_at": published_at,
                    "source": source_name,
                    "url": link,
                    "raw": item,
                }
            )
            if len(rows) >= int(desired_count):
                break
        if len(rows) >= int(desired_count):
            break

        if len(data) < per_page:
            break

    return rows, ""


def _fetch_news_with_fallback(api_token: str, company: str, ticker: str, days: int, desired_count: int, refresh_nonce: int):
    """Try ticker query first; if empty, fallback to company-text search."""
    rows, err = _fetch_marketaux_news(
        api_token=api_token,
        company=company,
        ticker=ticker,
        days=days,
        desired_count=desired_count,
        refresh_nonce=refresh_nonce,
    )
    if err:
        return rows, err, ""
    if rows:
        return rows, "", "ticker"
    if not ticker:
        return rows, "", "company"

    # fallback: many empty responses are due to stale/wrong ticker mappings
    rows2, err2 = _fetch_marketaux_news(
        api_token=api_token,
        company=company,
        ticker="",
        days=days,
        desired_count=desired_count,
        refresh_nonce=refresh_nonce + 100000,
    )
    if err2:
        return rows2, err2, "company"
    if rows2:
        return rows2, "", "company_fallback"
    return rows2, "", "none"


@st.cache_data(ttl=300, show_spinner=False)
def _company_list():
    idx = load_index()
    out = []
    seen = set()
    for r in idx:
        c = str(r.get("company", "")).strip()
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return sorted(out)


@st.cache_data(ttl=86400, show_spinner=False)
def _guess_ticker_from_company(company: str) -> str:
    """Best-effort ticker lookup when no saved mapping exists."""
    query = str(company or "").strip()
    if not query:
        return ""
    try:
        result = yf.Search(query, max_results=8)
        quotes = getattr(result, "quotes", []) or []
    except Exception:
        return ""

    fallback = ""
    q0 = query.lower()
    for item in quotes:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "") or "").strip().upper()
        if not symbol:
            continue
        quote_type = str(item.get("quoteType", "") or "").strip().upper()
        if quote_type and quote_type != "EQUITY":
            continue
        name = str(
            item.get("shortname")
            or item.get("longname")
            or item.get("name")
            or ""
        ).strip().lower()
        if not fallback:
            fallback = symbol
        if name and q0 in name:
            return symbol
    return fallback


@st.cache_data(ttl=300, show_spinner=False)
def _latest_company_risk_snapshot(company: str):
    target = str(company or "").strip()
    if not target:
        return None

    idx = load_index()
    recs = [r for r in idx if str(r.get("company", "")).strip() == target]
    if not recs:
        return None
    recs.sort(key=lambda r: int(r.get("year", 0) or 0), reverse=True)
    for rec in recs:
        result = get_result(rec.get("record_id", ""))
        if not result:
            continue
        risks = result.get("risks", [])
        if not isinstance(risks, list) or not risks:
            continue
        categories = []
        titles = []
        category_risk_titles = {}
        for cat in risks:
            if not isinstance(cat, dict):
                continue
            cname = str(cat.get("category", "")).strip()
            if cname:
                categories.append(cname)
                category_risk_titles.setdefault(cname, [])
            for sr in cat.get("sub_risks", [])[:6]:
                if isinstance(sr, dict):
                    t = str(sr.get("title", "")).strip()
                else:
                    t = str(sr).strip()
                if t:
                    titles.append(t)
                    if cname and len(category_risk_titles.get(cname, [])) < 8:
                        category_risk_titles[cname].append(t)
                if len(titles) >= 10:
                    break
            if len(titles) >= 10:
                break
        if categories or titles:
            return {
                "year": int(rec.get("year", 0) or 0),
                "categories": categories[:8],
                "titles": titles[:10],
                "category_risk_titles": category_risk_titles,
            }
    return None


@st.cache_data(ttl=300, show_spinner=False)
def _latest_agent_rating(company: str):
    target = str(company or "").strip()
    if not target:
        return "", 0
    reports = load_agent_reports()
    best = None
    for rp in reports:
        if str(rp.get("company", "")).strip() != target:
            continue
        y = int(rp.get("year", 0) or 0)
        if best is None or y > int(best.get("year", 0) or 0):
            best = rp
    if not best:
        return "", 0
    return str(best.get("overall_risk_rating", "") or "").strip(), int(best.get("year", 0) or 0)


def _sentiment_badge(score, label: str, color: str):
    if score is None:
        score_text = "N/A"
    else:
        score_text = f"{score:+.2f}"
    return (
        f'<span style="display:inline-flex; align-items:center; gap:0.32rem; padding:0.17rem 0.5rem; '
        f'border-radius:999px; border:1px solid {color}40; background:{color}18; color:{color}; '
        f'font-size:0.72rem; font-weight:700;">{label} · {score_text}</span>'
    )


def _article_image_url(article: dict) -> str:
    """Return a safe best-effort cover image URL from Marketaux payload."""
    raw = article.get("raw", {})
    if not isinstance(raw, dict):
        raw = {}

    source_obj = raw.get("source", {})
    if not isinstance(source_obj, dict):
        source_obj = {}

    candidates = [
        raw.get("image_url"),
        raw.get("image"),
        raw.get("imageUrl"),
        raw.get("thumbnail"),
        raw.get("thumbnail_url"),
        source_obj.get("logo_url"),
        source_obj.get("favicon"),
    ]
    for c in candidates:
        link = _safe_external_url(c)
        if link:
            return link
    return ""


def _risk_tag_chip(text: str):
    safe = html.escape(str(text or "").strip())
    if not safe:
        return ""
    return (
        '<span style="display:inline-flex; align-items:center; padding:0.16rem 0.52rem; '
        'border-radius:999px; background:#eef2ff; border:1px solid #c7d2fe; '
        'color:#3730a3; font-size:0.7rem; font-weight:650;">'
        f'{safe}</span>'
    )


def _pressure_badge(score: int, label: str):
    score_i = int(max(0, min(100, score or 0)))
    if score_i >= 70:
        color = "#dc2626"
        bg = "#fee2e2"
        border = "#fecaca"
    elif score_i >= 45:
        color = "#b45309"
        bg = "#fef3c7"
        border = "#fde68a"
    else:
        color = "#166534"
        bg = "#dcfce7"
        border = "#bbf7d0"
    return (
        f'<span style="display:inline-flex; align-items:center; gap:0.3rem; padding:0.18rem 0.56rem; '
        f'border-radius:999px; background:{bg}; border:1px solid {border}; color:{color}; '
        f'font-size:0.72rem; font-weight:700;">{html.escape(label)} · {score_i}</span>'
    )


def _render_compact_metric(label: str, value: str, accent: str = "#0f172a"):
    safe_label = html.escape(str(label or ""))
    safe_value = html.escape(str(value or "N/A"))
    safe_title = html.escape(str(value or "N/A"), quote=True)
    st.markdown(
        (
            '<div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; '
            'padding:0.45rem 0.62rem; min-height:68px;">'
            f'<div style="font-size:0.73rem; color:#64748b; line-height:1.1; margin-bottom:0.24rem;">{safe_label}</div>'
            f'<div title="{safe_title}" style="font-size:1.06rem; font-weight:760; color:{accent}; '
            'line-height:1.2; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">'
            f'{safe_value}</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )


def _category_keywords(category_name: str):
    c = str(category_name or "").lower()
    if "macro" in c or "industry" in c:
        return {
            "inflation", "interest", "rates", "recession", "gdp", "tariff", "macro",
            "consumer", "demand", "economy", "geopolitical", "trade", "currency",
        }
    if "regulatory" in c or "legal" in c or "compliance" in c:
        return {
            "regulation", "regulatory", "lawsuit", "litigation", "antitrust", "fine",
            "penalty", "compliance", "privacy", "investigation", "government", "sec",
        }
    if "financial" in c:
        return {
            "revenue", "profit", "margin", "cash flow", "earnings", "debt", "liquidity",
            "guidance", "cost", "expense", "impairment",
        }
    if "contingenc" in c:
        return {
            "disruption", "outage", "incident", "recall", "natural disaster", "earthquake",
            "flood", "war", "strike", "supply interruption", "force majeure",
        }
    if "business" in c:
        return {
            "competition", "customer", "market share", "product", "supply chain",
            "vendor", "partner", "execution", "strategy", "pricing", "demand",
        }
    if "general" in c:
        return {"risk", "uncertainty", "headwind", "challenge"}
    return {
        "risk", "regulation", "competition", "supply", "demand", "security",
        "cost", "revenue", "growth", "volatility",
    }


def _title_tokens(text: str):
    stop = {
        "the", "and", "for", "with", "that", "from", "into", "this", "will", "have",
        "has", "are", "was", "were", "its", "their", "about", "after", "before",
        "inc", "corp", "company", "stock", "shares", "today",
    }
    toks = re.findall(r"[a-z0-9]{3,}", str(text or "").lower())
    return {t for t in toks if t not in stop}


def _source_quality_weight(source_name: str, url: str):
    text = f"{str(source_name or '').lower()} {str(url or '').lower()}"
    high = ("reuters", "bloomberg", "wsj", "ft.com", "apnews", "cnbc", "forbes", "marketwatch")
    medium = ("yahoo", "benzinga", "businessinsider", "seekingalpha", "investopedia")
    if any(k in text for k in high):
        return 1.0
    if any(k in text for k in medium):
        return 0.82
    return 0.72


def _infer_risk_tags(article: dict, snapshot: dict | None):
    text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    categories = list((snapshot or {}).get("categories", []) or [])
    if not categories:
        categories = ["Business Risks", "Financial Risks", "Legal and Regulatory Compliance Risks"]

    score_map = {c: 0.0 for c in categories}
    for c in categories:
        for kw in _category_keywords(c):
            if kw and kw in text:
                score_map[c] += 1.0

    category_risk_titles = (snapshot or {}).get("category_risk_titles", {}) or {}
    if isinstance(category_risk_titles, dict):
        for c, title_list in category_risk_titles.items():
            if c not in score_map:
                continue
            if not isinstance(title_list, list):
                continue
            for t in title_list[:8]:
                for tok in list(_title_tokens(t))[:6]:
                    if tok in text:
                        score_map[c] += 0.6

    ranked = sorted(score_map.items(), key=lambda kv: (-kv[1], kv[0]))
    tags = [c for c, sc in ranked if sc >= 1.0][:3]
    if not tags and ranked:
        tags = [ranked[0][0]]
    return tags


def _compute_duplicate_penalties(news_rows: list[dict]):
    token_sets = [_title_tokens(r.get("title", "")) for r in news_rows]
    penalties = [0.0 for _ in news_rows]
    for i in range(len(news_rows)):
        a = token_sets[i]
        if not a:
            continue
        best = 0.0
        for j in range(len(news_rows)):
            if i == j:
                continue
            b = token_sets[j]
            if not b:
                continue
            inter = len(a.intersection(b))
            union = len(a.union(b))
            if union <= 0:
                continue
            sim = inter / union
            if sim > best:
                best = sim
        penalties[i] = best
    return penalties


def _article_pressure_score(article: dict, sentiment_score, duplicate_penalty: float):
    if sentiment_score is None:
        sentiment_risk = 0.55
    else:
        sentiment_risk = max(0.0, min(1.0, (0.5 - 0.5 * float(sentiment_score))))

    pub_dt = _parse_iso_datetime(article.get("published_at", ""))
    if pub_dt is None:
        recency = 0.55
    else:
        age_hours = max(0.0, (datetime.now(timezone.utc) - pub_dt.astimezone(timezone.utc)).total_seconds() / 3600.0)
        recency = math.exp(-age_hours / 96.0)

    source_weight = _source_quality_weight(article.get("source", ""), article.get("url", ""))
    base = 0.55 * sentiment_risk + 0.25 * recency + 0.20 * source_weight
    penalized = base * (1.0 - 0.30 * max(0.0, min(1.0, float(duplicate_penalty or 0.0))))
    score = int(round(max(0.0, min(1.0, penalized)) * 100))
    if score >= 70:
        label = "High Pressure"
    elif score >= 45:
        label = "Moderate Pressure"
    else:
        label = "Low Pressure"
    return score, label


def _enrich_news_rows(news_rows: list[dict], snapshot: dict | None, ticker: str):
    penalties = _compute_duplicate_penalties(news_rows)
    out = []
    for i, row in enumerate(news_rows):
        score, s_label, s_color = _article_sentiment(row.get("raw", {}), ticker=ticker)
        pressure_score, pressure_label = _article_pressure_score(
            row,
            sentiment_score=score,
            duplicate_penalty=penalties[i] if i < len(penalties) else 0.0,
        )
        tags = _infer_risk_tags(row, snapshot)
        new_row = dict(row)
        new_row.update(
            {
                "_sentiment_score": score,
                "_sentiment_label": s_label,
                "_sentiment_color": s_color,
                "pressure_score": pressure_score,
                "pressure_label": pressure_label,
                "risk_tags": tags,
            }
        )
        out.append(new_row)
    return out


def _sort_news_rows_for_display(news_rows: list[dict]):
    def _key(row: dict):
        p = int(row.get("pressure_score", 0) or 0)
        dt = _parse_iso_datetime(row.get("published_at", ""))
        ts = dt.timestamp() if dt else 0.0
        return (-p, -ts)
    return sorted(news_rows, key=_key)


def _render_negative_evidence(news_rows: list[dict]):
    top = [r for r in news_rows if int(r.get("pressure_score", 0) or 0) >= 45][:3]
    st.markdown('<div class="section-header">⚠️ Top 3 Negative Evidence</div>', unsafe_allow_html=True)
    if not top:
        st.info("No strong negative-pressure headline found in current window.")
        return
    for i, row in enumerate(top, start=1):
        title = html.escape(str(row.get("title", "") or "Untitled"))
        when = html.escape(_iso_to_local(row.get("published_at", "")))
        src = html.escape(str(row.get("source", "") or "Unknown Source"))
        tags = row.get("risk_tags", []) or []
        tag_html = "".join(_risk_tag_chip(t) for t in tags[:3]) or _risk_tag_chip("General Risks")
        st.markdown(
            (
                '<div style="background:#fff; border:1px solid #fde68a; border-left:4px solid #f59e0b; '
                'border-radius:10px; padding:0.75rem 0.85rem; margin-bottom:0.45rem;">'
                '<div style="display:flex; justify-content:space-between; gap:0.8rem; align-items:center;">'
                f'<div style="font-size:0.88rem; font-weight:700; color:#111827;">{i}. {title}</div>'
                f'{_pressure_badge(int(row.get("pressure_score", 0) or 0), str(row.get("pressure_label", "Pressure")))}'
                '</div>'
                f'<div style="margin-top:0.32rem; font-size:0.76rem; color:#64748b;">{src} · {when}</div>'
                f'<div style="display:flex; gap:0.35rem; flex-wrap:wrap; margin-top:0.38rem;">{tag_html}</div>'
                '</div>'
            ),
            unsafe_allow_html=True,
        )


def _render_news_card(article: dict, ticker: str, card_key: str):
    del card_key  # reserved for future per-card interactions
    title = html.escape(str(article.get("title", "") or "Untitled"))
    summary = html.escape(str(article.get("summary", "") or "No summary available."))
    source = html.escape(str(article.get("source", "") or "Unknown Source"))
    published_local = html.escape(_iso_to_local(article.get("published_at", "")))
    link = _safe_external_url(article.get("url", "") or "")
    image_url = _article_image_url(article)
    sentiment_score = article.get("_sentiment_score", None)
    sentiment_label = str(article.get("_sentiment_label", "") or "")
    sentiment_color = str(article.get("_sentiment_color", "") or "")
    if not sentiment_label or not sentiment_color:
        sentiment_score, sentiment_label, sentiment_color = _article_sentiment(article.get("raw", {}), ticker=ticker)
    pressure_score = int(article.get("pressure_score", 0) or 0)
    pressure_label = str(article.get("pressure_label", "") or "Pressure")
    tags = article.get("risk_tags", []) or []
    tag_html = "".join(_risk_tag_chip(t) for t in tags[:3]) or _risk_tag_chip("General Risks")

    media_block = ""
    if image_url:
        media_block = (
            '<div style="height:158px; border-radius:10px; overflow:hidden; border:1px solid #e2e8f0; margin-bottom:0.78rem;">'
            f'<img src="{html.escape(image_url, quote=True)}" alt="news cover" '
            'style="width:100%; height:100%; object-fit:cover; display:block;" loading="lazy" />'
            '</div>'
        )
    else:
        media_block = (
            '<div style="height:158px; border-radius:10px; margin-bottom:0.78rem; '
            'border:1px dashed #cbd5e1; background:linear-gradient(135deg,#f8fbff 0%,#eef2ff 100%); '
            'display:flex; align-items:center; justify-content:center; color:#64748b; font-size:0.8rem; '
            'font-weight:600;">No Cover Image</div>'
        )

    st.markdown(
        (
            '<div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; '
            'padding:0.95rem 1rem; height:392px; box-shadow:0 4px 16px rgba(15,23,42,0.06); overflow:hidden;">'
            f'{media_block}'
            '<div style="display:flex; justify-content:space-between; align-items:flex-start; gap:0.55rem;">'
            f'<span class="badge badge-gray">{source}</span>'
            '<div style="display:flex; align-items:center; gap:0.3rem; flex-wrap:wrap; justify-content:flex-end;">'
            f'{_sentiment_badge(sentiment_score, sentiment_label, sentiment_color)}'
            f'{_pressure_badge(pressure_score, pressure_label)}'
            '</div>'
            '</div>'
            f'<p style="margin:0.7rem 0 0.45rem; font-size:1rem; font-weight:700; color:#0f172a; line-height:1.35; '
            'display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">'
            f'{title}</p>'
            f'<p style="margin:0 0 0.55rem; font-size:0.84rem; color:#475569; line-height:1.5; '
            'display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;">'
            f'{summary}</p>'
            f'<div style="display:flex; gap:0.35rem; flex-wrap:nowrap; overflow:hidden; margin:0 0 0.55rem;">{tag_html}</div>'
            f'<p style="margin:0; font-size:0.73rem; color:#94a3b8;">{published_local}</p>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )
    if link:
        safe_link = html.escape(link, quote=True)
        st.markdown(
            (
                '<a href="{href}" target="_blank" rel="noopener noreferrer" '
                'style="display:block; width:100%; text-align:center; text-decoration:none; '
                'padding:0.48rem 0.7rem; border-radius:8px; '
                'background:#ffffff; border:1px solid #e2e8f0; color:#374151; '
                'font-weight:500; font-size:0.84rem;">Open Source →</a>'
            ).format(href=safe_link),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            (
                '<div style="display:block; width:100%; text-align:center; '
                'padding:0.48rem 0.7rem; border-radius:8px; '
                'background:#f8fafc; border:1px solid #e2e8f0; color:#94a3b8; '
                'font-weight:500; font-size:0.84rem;">Open Source →</div>'
            ),
            unsafe_allow_html=True,
        )


def _build_risk_linked_summary(company: str, ticker: str, news_rows: list[dict]):
    snapshot = _latest_company_risk_snapshot(company)
    if not snapshot:
        return "No risk analysis available for this company yet. Go to Upload/Analyze first, then run this summary again."

    lines = []
    for i, row in enumerate(news_rows[:8], start=1):
        pscore = int(row.get("pressure_score", 0) or 0)
        rtags = ", ".join(row.get("risk_tags", [])[:3]) or "General Risks"
        lines.append(
            f"{i}. {row.get('title', '')} | {row.get('source', '')} | {row.get('published_at', '')} "
            f"| pressure={pscore} | tags={rtags}"
        )
    prompt = f"""
You are a senior risk analyst.

Company: {company}
Ticker: {ticker or "N/A"}
Risk analysis snapshot year: {snapshot.get("year")}
Known risk categories:
{", ".join(snapshot.get("categories", []))}

Known high-level risk items:
{chr(10).join(f"- {t}" for t in snapshot.get("titles", []))}

Recent company news:
{chr(10).join(lines)}

Task:
Write a concise analyst note in 5-7 sentences that includes:
1) which risk categories are likely impacted by recent news,
2) direction of impact (higher pressure / lower pressure / unclear),
3) two concrete monitoring actions.

Use plain business English and keep it concise.
"""
    try:
        return _invoke(prompt, max_tokens=500)
    except Exception as e:
        return f"(Risk-linked summary generation failed: {e})"


def render():
    header_left, header_right = st.columns([2.35, 2.65], gap="medium")
    with header_left:
        st.markdown(
            """
            <div class="page-header">
                <div class="page-header-left">
                    <span class="page-icon">📰</span>
                    <div>
                        <p class="page-title">News</p>
                        <p class="page-subtitle">Track recent company headlines with optional risk-linked AI summary</p>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with header_right:
        render_current_config_box(
            key_prefix="ctx_news",
            year_options=list(range(2025, 2009, -1)),
        )

    api_token = _secret_get("MARKETAUX_API_TOKEN")
    if not api_token:
        st.error("Marketaux API token not configured. Please set `MARKETAUX_API_TOKEN` in `.streamlit/secrets.toml`.")
        return

    companies = _company_list()
    if not companies:
        st.info("No analyzed companies found yet. You can still query by ticker below.")
        companies = ["(Manual input)"]

    ctx = get_global_context()
    ctx_company = str(ctx.get("company", "") or "").strip()
    if ctx_company and ctx_company not in companies:
        companies = [ctx_company] + [c for c in companies if c != "(Manual input)"] + ["(Manual input)"]
    elif "(Manual input)" not in companies:
        companies = companies + ["(Manual input)"]

    sync_widget_from_context("news_company", "company", options=companies)
    sync_widget_from_context("news_ticker", "ticker", allow_empty=True)

    if "news_refresh_nonce" not in st.session_state:
        st.session_state["news_refresh_nonce"] = 0
    if "news_show_count" not in st.session_state:
        st.session_state["news_show_count"] = 6
    if "news_manual_company" not in st.session_state:
        st.session_state["news_manual_company"] = ""
    if "news_ticker_company" not in st.session_state:
        st.session_state["news_ticker_company"] = ""
    if "news_ticker_hint" not in st.session_state:
        st.session_state["news_ticker_hint"] = ""
    if "news_ticker_validated_pair" not in st.session_state:
        st.session_state["news_ticker_validated_pair"] = ""

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([2.2, 1.5, 1.2, 1.1], gap="small")
    with filter_col1:
        selected_company = st.selectbox("Company", companies, key="news_company")
    with filter_col2:
        if selected_company != st.session_state.get("news_ticker_company", ""):
            st.session_state["news_ticker_company"] = selected_company
            if selected_company and selected_company != "(Manual input)":
                mapped = str(get_company_ticker(selected_company, "") or "").strip().upper()
                source_label = ""
                mapped_invalid = False
                corrected_from = ""
                if mapped:
                    ok, _, _ = _ticker_matches_company(selected_company, mapped)
                    if ok:
                        auto_ticker = mapped
                        source_label = "saved mapping"
                    else:
                        mapped_invalid = True
                        corrected_from = mapped
                        auto_ticker = _guess_ticker_from_company(selected_company)
                        source_label = "auto-corrected mapping"
                        if auto_ticker:
                            try:
                                upsert_company_ticker(selected_company, auto_ticker)
                            except Exception:
                                pass
                else:
                    auto_ticker = _guess_ticker_from_company(selected_company)
                    source_label = "auto lookup"
                    if auto_ticker:
                        try:
                            upsert_company_ticker(selected_company, auto_ticker)
                        except Exception:
                            pass
                st.session_state["news_ticker"] = auto_ticker
                if auto_ticker and source_label:
                    if mapped_invalid:
                        st.session_state["news_ticker_hint"] = (
                            f"Saved mapping `{corrected_from}` did not match {selected_company}; "
                            f"auto-corrected to `{auto_ticker}`."
                        )
                    else:
                        st.session_state["news_ticker_hint"] = f"Auto-filled from {source_label}."
                else:
                    st.session_state["news_ticker_hint"] = "No ticker found automatically. You can type one manually."
            else:
                st.session_state["news_ticker"] = ""
                st.session_state["news_ticker_hint"] = ""
        elif selected_company and selected_company != "(Manual input)":
            # Safety net: correct stale wrong ticker even if company selection did not change.
            current_ticker = str(st.session_state.get("news_ticker", "") or "").strip().upper()
            pair = f"{selected_company}::{current_ticker}"
            if current_ticker and st.session_state.get("news_ticker_validated_pair") != pair:
                ok, _, _ = _ticker_matches_company(selected_company, current_ticker)
                if not ok:
                    guessed = _guess_ticker_from_company(selected_company)
                    if guessed and guessed != current_ticker:
                        st.session_state["news_ticker"] = guessed
                        st.session_state["news_ticker_hint"] = (
                            f"Detected mismatch `{current_ticker}` for {selected_company}; "
                            f"auto-corrected to `{guessed}`."
                        )
                        try:
                            upsert_company_ticker(selected_company, guessed)
                        except Exception:
                            pass
                        st.session_state["news_ticker_validated_pair"] = f"{selected_company}::{guessed}"
                    else:
                        st.session_state["news_ticker_validated_pair"] = pair
                else:
                    st.session_state["news_ticker_validated_pair"] = pair
        ticker = st.text_input("Ticker", key="news_ticker", placeholder="e.g. AAPL").strip().upper()
        ticker_hint = str(st.session_state.get("news_ticker_hint", "") or "").strip()
        if ticker_hint:
            st.caption(ticker_hint)
    with filter_col3:
        time_window = st.segmented_control(
            "Window",
            options=["7D", "30D"],
            default="7D",
            key="news_window",
        )
    with filter_col4:
        st.markdown("<div style='height:1.75rem;'></div>", unsafe_allow_html=True)
        if st.button("Refresh", key="news_refresh_btn", use_container_width=True):
            st.session_state["news_refresh_nonce"] = int(st.session_state.get("news_refresh_nonce", 0) or 0) + 1

    manual_company = ""
    if selected_company == "(Manual input)":
        manual_company = st.text_input(
            "Manual Company Name",
            key="news_manual_company",
            placeholder="e.g. Apple",
        ).strip()

    query_company = manual_company if selected_company == "(Manual input)" else selected_company
    window_days = 30 if time_window == "30D" else 7

    desired_count = st.session_state.get("news_show_count", 6)
    with st.spinner("Loading latest company news…"):
        news_rows, err, news_mode = _fetch_news_with_fallback(
            api_token=api_token,
            company=query_company,
            ticker=ticker,
            days=window_days,
            desired_count=desired_count,
            refresh_nonce=int(st.session_state.get("news_refresh_nonce", 0) or 0),
        )

    if err:
        st.error(err)
        return
    if news_mode == "company_fallback":
        st.info(
            "No results were returned for the current ticker in this window. "
            "Showing company-name search results instead (ticker mapping may be incorrect)."
        )

    snapshot_company = query_company if query_company != "(Manual input)" else manual_company
    risk_snapshot = _latest_company_risk_snapshot(snapshot_company)
    news_rows = _enrich_news_rows(news_rows, snapshot=risk_snapshot, ticker=ticker)
    display_rows = _sort_news_rows_for_display(news_rows)

    rating, rating_year = _latest_agent_rating(snapshot_company)
    avg_pressure = int(round(sum(int(r.get("pressure_score", 0) or 0) for r in news_rows) / max(1, len(news_rows))))
    metric_c1, metric_c2, metric_c3, metric_c4, metric_c5 = st.columns(5, gap="small")
    with metric_c1:
        _render_compact_metric("Articles Loaded", str(len(news_rows)))
    with metric_c2:
        _render_compact_metric("Time Window", f"{window_days} days")
    with metric_c3:
        latest_dt = None
        for row in news_rows:
            dt = _parse_iso_datetime(row.get("published_at", ""))
            if dt and (latest_dt is None or dt > latest_dt):
                latest_dt = dt
        latest_time = latest_dt.astimezone().strftime("%Y-%m-%d %H:%M") if latest_dt else "N/A"
        _render_compact_metric("Latest Headline", latest_time)
    with metric_c4:
        risk_text = f"{rating} ({rating_year})" if rating else "No agent rating"
        _render_compact_metric("Risk Rating", risk_text, accent="#b45309" if rating else "#0f172a")
    with metric_c5:
        pressure_color = "#dc2626" if avg_pressure >= 70 else "#b45309" if avg_pressure >= 45 else "#166534"
        _render_compact_metric("Avg News Pressure", f"{avg_pressure}/100", accent=pressure_color)

    if not news_rows:
        st.info("No recent news found for this company/ticker in the selected window.")
        return

    st.markdown("<div style='height:0.2rem;'></div>", unsafe_allow_html=True)
    for row_start in range(0, len(display_rows), 2):
        row_cols = st.columns(2, gap="large")
        for offset, col in enumerate(row_cols):
            idx = row_start + offset
            if idx >= len(display_rows):
                continue
            with col:
                _render_news_card(display_rows[idx], ticker=ticker, card_key=f"{query_company}_{idx}")
        st.markdown("<div style='height:0.35rem;'></div>", unsafe_allow_html=True)

    controls_c1, controls_c2 = st.columns([1, 2], gap="small")
    with controls_c1:
        if len(news_rows) >= desired_count and st.button("Load More", key="news_load_more", use_container_width=True):
            st.session_state["news_show_count"] = int(st.session_state.get("news_show_count", 6) or 6) + 6
            st.rerun()
    with controls_c2:
        st.caption("Marketaux Free tier may return up to 3 articles per request. The page auto-combines pages to show more.")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<div class="section-header">🔎 Risk-Linked News Summary</div>',
        unsafe_allow_html=True,
    )
    if st.button("Generate AI Risk-Linked Summary", key="news_ai_summary_btn", type="primary"):
        with st.spinner("Analyzing headlines against your existing risk profile…"):
            note = _build_risk_linked_summary(query_company, ticker, news_rows)
        st.session_state["news_ai_note"] = note

    if "news_ai_note" in st.session_state:
        st.markdown(
            (
                '<div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px; '
                'padding:1rem 1.1rem; box-shadow:0 1px 3px rgba(15,23,42,0.04);">'
                f'<p style="margin:0; color:#1f2937; font-size:0.93rem; line-height:1.6;">{html.escape(st.session_state["news_ai_note"])}</p>'
                "</div>"
            ),
            unsafe_allow_html=True,
        )
