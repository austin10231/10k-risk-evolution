"""Backfill financial table extraction for existing 10-K records.

This script scans the current records index, finds existing 10-K company-year
records, and extracts/saves financial statement tables for records that do not
already have a saved table payload.

Safety:
* Dry-run by default. Use ``--execute`` to write table JSON/CSV into S3.
* Existing table results are skipped unless ``--force`` is provided.
* HTML/iXBRL extraction is preferred by default because it preserves sanitized
  as-filed table HTML for product display; PDF/Textract is used as fallback.

Examples:
    python scripts/backfill_10k_financial_tables.py --limit 10
    python scripts/backfill_10k_financial_tables.py --execute --limit 5
    python scripts/backfill_10k_financial_tables.py --execute --ticker AAPL --year 2024
    python scripts/backfill_10k_financial_tables.py --execute --direct --ticker AAPL --year 2024 --company Apple
    python scripts/backfill_10k_financial_tables.py --execute --api-base https://api.risklensai.org --direct --ticker AAPL --year 2024 --company Apple
    python scripts/backfill_10k_financial_tables.py --execute --force --company Microsoft
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentcore_deploy import main as backend  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _norm_company(value: Any) -> str:
    return str(value or "").strip()


def _norm_ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _norm_industry(value: Any) -> str:
    return str(value or "Other").strip() or "Other"


def _norm_filing_type(value: Any) -> str:
    txt = str(value or "").strip().upper().replace(" ", "")
    if txt in {"10-K", "10K"}:
        return "10-K"
    if txt in {"10-Q", "10Q"}:
        return "10-Q"
    return str(value or "").strip() or "10-K"


def _api_base_url(value: Any) -> str:
    return str(value or "").strip().rstrip("/")


def _api_json_request(
    api_base: str,
    path: str,
    *,
    method: str = "GET",
    body: Optional[dict] = None,
    timeout: int = 90,
) -> dict:
    base = _api_base_url(api_base)
    if not base:
        raise RuntimeError("api_base is required")
    url = f"{base}{path}"
    data = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "RiskLensAI-table-backfill/1.0",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(req, timeout=max(1, int(timeout))) as resp:
            raw = resp.read()
    except (ssl.SSLCertVerificationError, URLError) as exc:
        msg = str(exc).lower()
        if "certificate" not in msg and "ssl" not in msg:
            raise
        with urlopen(req, timeout=max(1, int(timeout)), context=ssl._create_unverified_context()) as resp:
            raw = resp.read()

    try:
        parsed = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception as exc:
        raise RuntimeError(f"API returned non-JSON response from {url}: {type(exc).__name__}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"API returned invalid JSON shape from {url}")
    return parsed


def _load_records_from_api(api_base: str) -> List[dict]:
    payload = _api_json_request(api_base, "/api/records?include_result=0")
    records = payload.get("items")
    if not isinstance(records, list):
        records = payload.get("records")
    if not isinstance(records, list):
        records = payload.get("data")
    return [r for r in records if isinstance(r, dict)] if isinstance(records, list) else []


@dataclass(frozen=True)
class TableBackfillTarget:
    record_id: str
    company: str
    ticker: str
    industry: str
    year: int
    filing_type: str = "10-K"
    created_at: str = ""


def _target_key(target: TableBackfillTarget) -> Tuple[str, int]:
    # Prefer ticker identity when present so duplicate company labels do not
    # trigger duplicate table writes for the same underlying issuer/year.
    identity = f"tk:{target.ticker}" if target.ticker else f"co:{target.company.lower()}"
    return identity, int(target.year)


def _collect_targets(records: List[dict]) -> List[TableBackfillTarget]:
    targets_by_key: Dict[Tuple[str, int], TableBackfillTarget] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        filing_type = _norm_filing_type(rec.get("filing_type"))
        if filing_type != "10-K":
            continue
        company = _norm_company(rec.get("company"))
        year = _to_int(rec.get("year"), 0)
        if not company or year <= 0:
            continue
        target = TableBackfillTarget(
            record_id=str(rec.get("record_id", "") or "").strip(),
            company=company,
            ticker=_norm_ticker(rec.get("ticker")),
            industry=_norm_industry(rec.get("industry")),
            year=year,
            filing_type="10-K",
            created_at=str(rec.get("created_at", "") or ""),
        )
        key = _target_key(target)
        previous = targets_by_key.get(key)
        if previous is None:
            targets_by_key[key] = target
            continue
        # Keep the richer company label/ticker metadata, then latest created_at.
        previous_rank = (1 if previous.ticker else 0, len(previous.company), previous.created_at)
        target_rank = (1 if target.ticker else 0, len(target.company), target.created_at)
        if target_rank > previous_rank:
            targets_by_key[key] = target

    return sorted(targets_by_key.values(), key=lambda t: (t.company.lower(), t.year))


def _filter_targets(targets: List[TableBackfillTarget], args: argparse.Namespace) -> List[TableBackfillTarget]:
    out: List[TableBackfillTarget] = []
    company_filter = str(args.company or "").strip().lower()
    ticker_filter = str(args.ticker or "").strip().upper()
    industry_filter = str(args.industry or "").strip().lower()
    year_filter = _to_int(args.year, 0)
    start_year = _to_int(args.start_year, 0)
    end_year = _to_int(args.end_year, 0)

    for target in targets:
        if company_filter and company_filter not in target.company.lower():
            continue
        if ticker_filter and target.ticker != ticker_filter:
            continue
        if industry_filter and industry_filter not in target.industry.lower():
            continue
        if year_filter > 0 and target.year != year_filter:
            continue
        if start_year > 0 and target.year < start_year:
            continue
        if end_year > 0 and target.year > end_year:
            continue
        out.append(target)

    if args.limit and args.limit > 0:
        out = out[: int(args.limit)]
    return out


def _direct_target_from_args(args: argparse.Namespace) -> Optional[TableBackfillTarget]:
    """Build a single target without reading the records index.

    This is useful for local smoke tests when the runtime records index is only
    available in production, but AWS/S3 credentials are available locally.
    """
    year = _to_int(args.year, 0)
    if year <= 0:
        return None
    ticker = _norm_ticker(args.ticker)
    company = _norm_company(args.company)
    if not company:
        company = ticker
    if not company:
        return None
    return TableBackfillTarget(
        record_id=f"direct_{ticker or company}_{year}_10K",
        company=company,
        ticker=ticker,
        industry=_norm_industry(args.industry),
        year=year,
        filing_type="10-K",
        created_at=_now_iso(),
    )


def _load_existing_table(target: TableBackfillTarget, args: argparse.Namespace) -> Optional[dict]:
    api_base = _api_base_url(getattr(args, "api_base", ""))
    if api_base:
        try:
            query = urlencode(
                {
                    "company": target.company,
                    "year": str(target.year),
                    "filing_type": target.filing_type,
                }
            )
            payload = _api_json_request(api_base, f"/api/tables/result?{query}")
            result = payload.get("result") if isinstance(payload, dict) else None
            return result if isinstance(result, dict) else None
        except Exception:
            return None

    try:
        payload = backend._load_table_result(target.company, target.year, target.filing_type)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _count_found_tables(payload: dict) -> int:
    try:
        return int(backend._count_found_tables(payload))
    except Exception:
        count = 0
        for key in ("income_statement", "balance_sheet", "cash_flow", "comprehensive_income", "shareholders_equity"):
            if isinstance(payload.get(key), dict) and payload.get(key, {}).get("found"):
                count += 1
        return count


def _extract_html(target: TableBackfillTarget) -> Tuple[Optional[dict], str, str, dict]:
    downloader = getattr(backend, "download_10k_html_for_company_year", None)
    if not callable(downloader):
        return None, "", "SEC 10-K HTML downloader is unavailable.", {"format": "html"}

    try:
        html_bytes, meta, sec_err = downloader(
            company_name=target.company,
            year=target.year,
            ticker=target.ticker,
        )
    except Exception as exc:
        return None, "", f"SEC HTML request failed: {type(exc).__name__}: {exc}", {"format": "html"}

    build_url = getattr(backend, "build_filing_html_url", None)
    filing_url = build_url(meta) if callable(build_url) and isinstance(meta, dict) else ""
    if not html_bytes:
        return None, "", sec_err or "Could not download SEC filing HTML.", {"format": "html", "filing_url": filing_url}

    extractor = getattr(backend, "_extract_tables_for_html", None)
    if not callable(extractor):
        return None, "", "HTML table extractor is unavailable.", {"format": "html", "filing_url": filing_url}

    result, table_key, err = extractor(
        html_bytes=html_bytes,
        company=target.company,
        industry=target.industry,
        year=target.year,
        filing_type=target.filing_type,
        source="tables_backfill_sec_html",
        filing_url=filing_url,
    )
    return result, table_key, err, {"format": "html", "filing_url": filing_url}


def _extract_pdf(target: TableBackfillTarget) -> Tuple[Optional[dict], str, str, dict]:
    downloader = getattr(backend, "download_10k_pdf_for_company_year", None)
    if not callable(downloader):
        return None, "", "SEC 10-K PDF downloader is unavailable.", {"format": "pdf"}

    try:
        pdf_bytes, meta, sec_err = downloader(
            company_name=target.company,
            year=target.year,
            ticker=target.ticker,
        )
    except Exception as exc:
        return None, "", f"SEC PDF request failed: {type(exc).__name__}: {exc}", {"format": "pdf"}

    build_url = getattr(backend, "build_filing_html_url", None)
    filing_url = build_url(meta) if callable(build_url) and isinstance(meta, dict) else ""
    if not pdf_bytes:
        return None, "", sec_err or "Could not download SEC filing PDF.", {"format": "pdf", "filing_url": filing_url}

    extractor = getattr(backend, "_extract_tables_for_pdf", None)
    if not callable(extractor):
        return None, "", "PDF/Textract table extractor is unavailable.", {"format": "pdf", "filing_url": filing_url}

    result, table_key, err = extractor(
        pdf_bytes=pdf_bytes,
        company=target.company,
        industry=target.industry,
        year=target.year,
        filing_type=target.filing_type,
        source="tables_backfill_sec_pdf",
    )
    return result, table_key, err, {"format": "pdf", "filing_url": filing_url}


def _download_html_for_api(target: TableBackfillTarget) -> Tuple[Optional[bytes], str, str]:
    downloader = getattr(backend, "download_10k_html_for_company_year", None)
    if not callable(downloader):
        return None, "", "SEC 10-K HTML downloader is unavailable."

    try:
        html_bytes, meta, sec_err = downloader(
            company_name=target.company,
            year=target.year,
            ticker=target.ticker,
        )
    except Exception as exc:
        return None, "", f"SEC HTML request failed: {type(exc).__name__}: {exc}"

    build_url = getattr(backend, "build_filing_html_url", None)
    filing_url = build_url(meta) if callable(build_url) and isinstance(meta, dict) else ""
    if not html_bytes:
        return None, filing_url, sec_err or "Could not download SEC filing HTML."
    return html_bytes, filing_url, ""


def _extract_html_via_api(target: TableBackfillTarget, args: argparse.Namespace) -> dict:
    html_bytes, filing_url, err = _download_html_for_api(target)
    if not html_bytes:
        return {
            "status": "failed",
            "target": asdict(target),
            "error": err or "Could not download SEC filing HTML.",
            "attempts": [{"format": "html", "reason": err or "Could not download SEC filing HTML.", "filing_url": filing_url}],
            "api_base": _api_base_url(args.api_base),
        }

    file_name = filing_url.rsplit("/", 1)[-1] if filing_url else f"{target.ticker or target.company}_{target.year}.htm"
    payload = _api_json_request(
        _api_base_url(args.api_base),
        "/api/tables/extract/manual",
        method="POST",
        timeout=int(getattr(args, "api_timeout", 180) or 180),
        body={
            "company": target.company,
            "ticker": target.ticker,
            "industry": target.industry,
            "filing_type": target.filing_type,
            "year": target.year,
            "file_name": file_name,
            "file_b64": base64.b64encode(html_bytes).decode("ascii"),
        },
    )
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    if payload.get("ok") and result:
        return {
            "status": "ok",
            "target": asdict(target),
            "table_key": payload.get("table_key", ""),
            "tables_found": _count_found_tables(result),
            "source": result.get("source"),
            "source_format": result.get("source_format"),
            "attempts": [{"format": "html", "ok": True, "source": result.get("source"), "filing_url": filing_url}],
            "api_base": _api_base_url(args.api_base),
        }
    return {
        "status": "failed",
        "target": asdict(target),
        "error": payload.get("error") or "API HTML extraction failed.",
        "attempts": [{"format": "html", "reason": payload.get("error") or "API HTML extraction failed.", "filing_url": filing_url}],
        "api_base": _api_base_url(args.api_base),
    }


def _extract_via_api(target: TableBackfillTarget, args: argparse.Namespace) -> dict:
    api_base = _api_base_url(args.api_base)
    payload = _api_json_request(
        api_base,
        "/api/tables/extract/auto-fetch",
        method="POST",
        timeout=int(getattr(args, "api_timeout", 180) or 180),
        body={
            "company": target.company,
            "ticker": target.ticker,
            "industry": target.industry,
            "filing_type": target.filing_type,
            "start_year": target.year,
            "end_year": target.year,
        },
    )
    successes = payload.get("successes") if isinstance(payload.get("successes"), list) else []
    skipped = payload.get("skipped") if isinstance(payload.get("skipped"), list) else []
    if successes:
        first = successes[0] if isinstance(successes[0], dict) else {}
        result = first.get("result") if isinstance(first.get("result"), dict) else {}
        return {
            "status": "ok",
            "target": asdict(target),
            "table_key": first.get("table_key", ""),
            "tables_found": _count_found_tables(result),
            "source": result.get("source"),
            "source_format": result.get("source_format"),
            "attempts": first.get("attempts", []),
            "api_base": api_base,
        }
    return {
        "status": "failed",
        "target": asdict(target),
        "error": payload.get("error") or "; ".join(str(s.get("reason", "")) for s in skipped if isinstance(s, dict)) or "API extraction failed.",
        "skipped": skipped,
        "api_base": api_base,
    }


def _extract_for_target(target: TableBackfillTarget, args: argparse.Namespace) -> dict:
    existing = _load_existing_table(target, args)
    if existing and not args.force:
        return {
            "status": "skipped_existing",
            "target": asdict(target),
            "tables_found": _count_found_tables(existing),
            "source": existing.get("source"),
            "source_format": existing.get("source_format"),
        }

    if not args.execute:
        return {
            "status": "planned",
            "target": asdict(target),
            "would_replace_existing": bool(existing),
            "prefer_format": args.prefer_format,
        }

    attempts: List[dict] = []
    order = ["html", "pdf"] if args.prefer_format == "html" else ["pdf", "html"]
    if args.no_fallback:
        order = order[:1]

    if _api_base_url(getattr(args, "api_base", "")):
        for fmt in order:
            result = _extract_html_via_api(target, args) if fmt == "html" else _extract_via_api(target, args)
            attempts.extend(result.get("attempts", []))
            if result.get("status") == "ok":
                result["attempts"] = attempts
                return result
        return {
            "status": "failed",
            "target": asdict(target),
            "attempts": attempts,
            "error": "; ".join(str(a.get("reason", "")) for a in attempts if a.get("reason")) or "API extraction failed.",
            "api_base": _api_base_url(args.api_base),
        }

    for fmt in order:
        if fmt == "html":
            result, table_key, err, meta = _extract_html(target)
        else:
            result, table_key, err, meta = _extract_pdf(target)

        attempt = {**meta, "ok": bool(result), "reason": err or ""}
        attempts.append(attempt)
        if isinstance(result, dict):
            return {
                "status": "ok",
                "target": asdict(target),
                "table_key": table_key,
                "tables_found": _count_found_tables(result),
                "source": result.get("source"),
                "source_format": result.get("source_format"),
                "attempts": attempts,
            }

    return {
        "status": "failed",
        "target": asdict(target),
        "attempts": attempts,
        "error": "; ".join(a.get("reason", "") for a in attempts if a.get("reason")) or "Extraction failed.",
    }


def _write_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill 10-K financial tables for existing records.")
    parser.add_argument("--execute", action="store_true", help="Write extracted table results to S3. Default is dry-run.")
    parser.add_argument(
        "--api-base",
        default="",
        help="Use a deployed RiskLens API base URL instead of local AWS/S3 helpers, e.g. https://api.risklensai.org.",
    )
    parser.add_argument(
        "--api-timeout",
        type=int,
        default=180,
        help="Seconds to wait for each deployed API extraction request.",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Do not read records index; process one target from --company/--ticker/--year.",
    )
    parser.add_argument("--force", action="store_true", help="Replace existing table results.")
    parser.add_argument("--prefer-format", choices=("html", "pdf"), default="html", help="Preferred extraction format.")
    parser.add_argument("--no-fallback", action="store_true", help="Do not try the secondary extraction format.")
    parser.add_argument("--limit", type=int, default=0, help="Maximum targets to process after filtering.")
    parser.add_argument("--company", default="", help="Case-insensitive company name substring filter.")
    parser.add_argument("--ticker", default="", help="Ticker filter, e.g. AAPL.")
    parser.add_argument("--industry", default="", help="Case-insensitive industry substring filter.")
    parser.add_argument("--year", type=int, default=0, help="Single filing year filter.")
    parser.add_argument("--start-year", type=int, default=0, help="Minimum filing year.")
    parser.add_argument("--end-year", type=int, default=0, help="Maximum filing year.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between execute jobs.")
    parser.add_argument("--max-failures", type=int, default=0, help="Stop after N failures in execute mode. 0 = unlimited.")
    parser.add_argument(
        "--report-path",
        default=str(ROOT / "scripts" / "backfill_10k_financial_tables.report.json"),
        help="Path for JSON run report.",
    )
    args = parser.parse_args()
    api_base = _api_base_url(args.api_base)

    if args.execute and not api_base and not os.getenv("S3_BUCKET"):
        print(
            "[error] S3_BUCKET is not configured locally. Either export production AWS/S3 env vars, "
            "run this as a Railway one-off, or use --api-base https://api.risklensai.org."
        )
        return 1

    if args.direct:
        direct_target = _direct_target_from_args(args)
        if direct_target is None:
            print("[error] --direct requires --year plus --company or --ticker.")
            return 1
        all_targets = [direct_target]
        targets = [direct_target]
    else:
        if api_base:
            try:
                records = _load_records_from_api(api_base)
            except Exception as exc:
                print(f"[error] could not load records from API: {type(exc).__name__}: {exc}")
                return 1
        else:
            try:
                records = backend._load_index()
            except Exception as exc:
                print(f"[error] could not load records index: {type(exc).__name__}: {exc}")
                return 1

        if not isinstance(records, list) or not records:
            print(
                "[error] no records found in index. Make sure this runs in an environment "
                "with S3_BUCKET and AWS credentials configured, such as a Railway one-off. "
                "For one-company local tests, use --api-base https://api.risklensai.org "
                "--direct --ticker AAPL --year 2024."
            )
            return 1

        all_targets = _collect_targets(records)
        targets = _filter_targets(all_targets, args)
    mode = "execute" if args.execute else "dry-run"
    print(
        f"[plan] mode={mode} targets={len(targets)} eligible_10k_targets={len(all_targets)} "
        f"prefer={args.prefer_format} force={bool(args.force)}"
    )

    report: dict = {
        "ok": True,
        "started_at": _now_iso(),
        "finished_at": "",
        "mode": mode,
        "api_base": api_base,
        "prefer_format": args.prefer_format,
        "force": bool(args.force),
        "filters": {
            "api_base": api_base,
            "direct": bool(args.direct),
            "company": args.company,
            "ticker": args.ticker,
            "industry": args.industry,
            "year": args.year,
            "start_year": args.start_year,
            "end_year": args.end_year,
            "limit": args.limit,
        },
        "eligible_targets": len(all_targets),
        "selected_targets": len(targets),
        "summary": {},
        "items": [],
    }

    failures = 0
    for idx, target in enumerate(targets, start=1):
        label = f"{target.company} {target.year} {target.filing_type}"
        try:
            item = _extract_for_target(target, args)
        except Exception as exc:
            item = {
                "status": "failed",
                "target": asdict(target),
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(),
            }

        status = str(item.get("status", "unknown"))
        report["items"].append(item)
        if status == "failed":
            failures += 1
        extra = ""
        if item.get("tables_found") is not None:
            extra = f" tables={item.get('tables_found')}"
        print(f"[{idx}/{len(targets)}] {status}: {label}{extra}")

        if args.execute and args.max_failures and failures >= int(args.max_failures):
            print(f"[stop] max failures reached: {failures}")
            break
        if args.execute and args.sleep and idx < len(targets):
            time.sleep(float(args.sleep))

    summary: Dict[str, int] = {}
    for item in report["items"]:
        status = str(item.get("status", "unknown"))
        summary[status] = summary.get(status, 0) + 1
    report["summary"] = summary
    report["finished_at"] = _now_iso()
    report["ok"] = failures == 0

    report_path = Path(args.report_path).expanduser()
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    _write_report(report_path, report)
    print(f"[report] {report_path}")
    return 0 if report["ok"] or not args.execute else 2


if __name__ == "__main__":
    raise SystemExit(main())
