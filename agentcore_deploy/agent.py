"""Risk agent for AgentCore deployment (boto3-only, no Strands)."""

from __future__ import annotations

import json
import os
import re
import hmac
import hashlib
from datetime import datetime, timezone
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


# Dual-model configuration:
#   * EXTRACTION_MODEL_ID — risk extraction, 9-bucket classification, RPI
#     three-dimensional scoring, and the agent priority report (executive
#     summary / themes). Defaults to Amazon Nova Pro because the Converse
#     API tool-use schema and the structured JSON output we depend on are
#     stable on it.
#   * AGENT_MODEL_ID — interactive Q&A only (chat_agent answers, follow-up
#     polishing, "what model are you" identity replies). Defaults to
#     DeepSeek V3.2 since chat doesn't need forced tool output.
# Both can be overridden via env. The legacy ``MODEL_ID`` constant is kept
# as an alias for AGENT_MODEL_ID so external imports keep returning the
# same kind of model historically associated with this module's _invoke
# (which used to back chat).
EXTRACTION_MODEL_ID = (os.getenv("BEDROCK_EXTRACTION_MODEL_ID") or "amazon.nova-pro-v1:0").strip() or "amazon.nova-pro-v1:0"
AGENT_MODEL_ID = (os.getenv("BEDROCK_AGENT_MODEL_ID") or "deepseek.v3.2").strip() or "deepseek.v3.2"
MODEL_ID = AGENT_MODEL_ID
# Back-compat alias. Anything still referencing this name will get the agent
# model, which is what historical callers of ``MODEL_ID`` actually wanted.
BEDROCK_CLAUDE_OPUS_47_MODEL_ID = AGENT_MODEL_ID

# Priority scoring is computed in Python from three LLM-provided dimensions; the
# weights and thresholds are duplicated in the LLM prompt for transparency, but
# Python is the single source of truth — the LLM's own `score`/`priority` fields
# are intentionally ignored to prevent score↔priority contradictions.
PRIORITY_HIGH_THRESHOLD = 7.0
PRIORITY_MEDIUM_THRESHOLD = 4.0
PRIORITY_DIM_WEIGHTS = (0.4, 0.35, 0.25)  # financial_impact, likelihood, urgency
_PRIORITY_BATCH_SIZE = 40


def _clamp_int_1_10(value, default: int = 5) -> int:
    try:
        n = int(round(float(value)))
    except Exception:
        n = default
    return max(1, min(10, n))


def _compute_score_from_dims(financial_impact, likelihood, urgency) -> float:
    fi = _clamp_int_1_10(financial_impact)
    lk = _clamp_int_1_10(likelihood)
    ur = _clamp_int_1_10(urgency)
    raw = (
        fi * PRIORITY_DIM_WEIGHTS[0]
        + lk * PRIORITY_DIM_WEIGHTS[1]
        + ur * PRIORITY_DIM_WEIGHTS[2]
    )
    return round(float(raw), 2)


def _priority_from_score(score: float) -> str:
    s = float(score or 0.0)
    if s >= PRIORITY_HIGH_THRESHOLD:
        return "High"
    if s >= PRIORITY_MEDIUM_THRESHOLD:
        return "Medium"
    return "Low"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _signature_key(secret_key: str, date_stamp: str, region: str, service: str) -> bytes:
    k_date = _sign(("AWS4" + secret_key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region)
    k_service = _sign(k_region, service)
    return _sign(k_service, "aws4_request")


def _resolve_credentials() -> tuple[str, str, str | None]:
    access_key = _env("AWS_ACCESS_KEY_ID")
    secret_key = _env("AWS_SECRET_ACCESS_KEY")
    session_token = _env("AWS_SESSION_TOKEN")

    if access_key and secret_key:
        return access_key, secret_key, session_token

    # Try ECS/managed-runtime credential endpoint when static env creds are absent.
    rel_uri = _env("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
    full_uri = _env("AWS_CONTAINER_CREDENTIALS_FULL_URI")
    cred_url = None
    if rel_uri:
        cred_url = "http://169.254.170.2" + rel_uri
    elif full_uri:
        cred_url = full_uri

    if cred_url:
        req = Request(cred_url, method="GET")
        with urlopen(req, timeout=3) as resp:
            creds = json.loads(resp.read().decode("utf-8", errors="ignore"))
        access_key = creds.get("AccessKeyId") or creds.get("accessKeyId")
        secret_key = creds.get("SecretAccessKey") or creds.get("secretAccessKey")
        session_token = creds.get("Token") or creds.get("SessionToken")
        if access_key and secret_key:
            return access_key, secret_key, session_token

    raise RuntimeError("AWS credentials not found in environment or container credentials endpoint")


def _invoke(prompt: str, max_tokens: int = 2048, *, model_id: str | None = None) -> str:
    """Invoke a Bedrock Converse model and return the assistant's text. The
    explicit ``model_id`` arg is what enables this module's dual-model split
    (extraction vs agent). Callers should prefer the named wrappers
    ``_invoke_extraction`` / ``_invoke_agent``."""
    selected_model_id = (model_id or AGENT_MODEL_ID).strip() or AGENT_MODEL_ID
    body_obj = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": 0.0,
            "topP": 1.0,
        },
    }
    body_json = json.dumps(body_obj, ensure_ascii=False)

    boto3_error = None
    try:
        import boto3  # Optional in runtime; fallback path below if unavailable.

        region = _env("BEDROCK_REGION", "us-west-2")
        kwargs = {"region_name": region}
        access_key = _env("AWS_ACCESS_KEY_ID")
        secret_key = _env("AWS_SECRET_ACCESS_KEY")
        session_token = _env("AWS_SESSION_TOKEN")
        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
            if session_token:
                kwargs["aws_session_token"] = session_token

        client = boto3.client("bedrock-runtime", **kwargs)
        response = client.converse(
            modelId=selected_model_id,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0, "topP": 1.0},
        )
        return response["output"]["message"]["content"][0]["text"].strip()
    except Exception as exc:
        boto3_error = exc

    # Fallback: direct SigV4 HTTP request without boto3 dependency.
    try:
        region = _env("BEDROCK_REGION", "us-west-2")
        service = "bedrock-runtime"
        encoded_model_id = quote(selected_model_id, safe="")
        endpoint = f"https://bedrock-runtime.{region}.amazonaws.com/model/{encoded_model_id}/converse"
        parsed = urlparse(endpoint)
        host = parsed.netloc
        canonical_uri = parsed.path
        body = body_json.encode("utf-8")

        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()

        access_key, secret_key, session_token = _resolve_credentials()

        canonical_headers = (
            f"content-type:application/json\n"
            f"host:{host}\n"
            f"x-amz-content-sha256:{payload_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
        if session_token:
            canonical_headers += f"x-amz-security-token:{session_token}\n"
            signed_headers += ";x-amz-security-token"

        canonical_request = (
            "POST\n"
            f"{canonical_uri}\n"
            "\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{payload_hash}"
        )
        credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
        string_to_sign = (
            "AWS4-HMAC-SHA256\n"
            f"{amz_date}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        signing_key = _signature_key(secret_key, date_stamp, region, service)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Host": host,
            "X-Amz-Date": amz_date,
            "X-Amz-Content-Sha256": payload_hash,
            "Authorization": authorization,
        }
        if session_token:
            headers["X-Amz-Security-Token"] = session_token

        req = Request(endpoint, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return result["output"]["message"]["content"][0]["text"].strip()
    except Exception as sigv4_error:
        raise RuntimeError(
            f"Bedrock converse failed (boto3={repr(boto3_error)}, sigv4={repr(sigv4_error)})"
        ) from sigv4_error


def _invoke_extraction(prompt: str, max_tokens: int = 2048) -> str:
    """Bedrock invocation for the extraction path: risk extraction, 9-bucket
    classification, RPI three-dim scoring, and the agent priority report.
    Goes through the EXTRACTION_MODEL_ID (Nova Pro by default)."""
    return _invoke(prompt, max_tokens=max_tokens, model_id=EXTRACTION_MODEL_ID)


def _invoke_agent(prompt: str, max_tokens: int = 2048) -> str:
    """Bedrock invocation for the chat agent: user Q&A and reply polishing.
    Goes through the AGENT_MODEL_ID (DeepSeek V3.2 by default)."""
    return _invoke(prompt, max_tokens=max_tokens, model_id=AGENT_MODEL_ID)


def invoke_llm_text(prompt: str, max_tokens: int = 1200) -> str:
    """Public helper for chat-agent callers (Q&A, language polish, identity
    replies). Routes to AGENT_MODEL_ID by default."""
    return _invoke(prompt, max_tokens=max_tokens, model_id=AGENT_MODEL_ID)


def invoke_llm_extraction(prompt: str, max_tokens: int = 1200) -> str:
    """Public helper for extraction-side callers in main.py (e.g. the
    dashboard 9-bucket classification fallback). Routes to
    EXTRACTION_MODEL_ID."""
    return _invoke(prompt, max_tokens=max_tokens, model_id=EXTRACTION_MODEL_ID)


def get_model_id() -> str:
    """Public model id for chat-context display ("what model are you")."""
    return AGENT_MODEL_ID


def get_extraction_model_id() -> str:
    """Public model id for extraction-side reporting (e.g. /health probe)."""
    return EXTRACTION_MODEL_ID


def _strip_json_fences(text: str) -> str:
    return re.sub(r"```json|```", "", str(text or "")).strip()


def _extract_json_obj(text: str):
    s = _strip_json_fences(text)
    try:
        return json.loads(s)
    except Exception:
        pass
    left = s.find("{")
    right = s.rfind("}")
    if left >= 0 and right > left:
        try:
            return json.loads(s[left : right + 1])
        except Exception:
            return None
    return None


def _fallback_report(company: str, year: int, user_query: str, error: str) -> dict:
    return {
        "company": company,
        "year": year,
        "user_query": user_query,
        "priority_matrix": {
            "high": {"count": 0, "top": []},
            "medium": {"count": 0, "top": []},
            "low": {"count": 0, "top": []},
            "unscored": {"count": 0, "top": []},
        },
        "scoring_status": "failed",
        "executive_summary": f"Report generation encountered an error: {error}",
        "key_findings": [],
        "recommendations": [],
        "risk_themes": [],
        "overall_risk_rating": "Unknown",
        "compare_insights": "",
        "direct_answer": "",
        "evidence": [],
        "follow_up_questions": [],
        "agent_steps": [f"❌ {error}"],
        "enriched_risks": [],
    }


def _build_priority_lists(enriched_risks: list):
    """Bucket enriched risks into (high, medium, low, unscored).

    A sub_risk with priority=None / score=None lands in `unscored` — the agent
    layer keeps these visible so downstream code (main.py) can mark RPI as
    "scoring failed" instead of silently defaulting them to Medium=5.0.
    """
    high, medium, low, unscored = [], [], [], []
    for cat_block in enriched_risks:
        for sr in cat_block.get("sub_risks", []):
            if not isinstance(sr, dict):
                continue
            entry = {
                "category": cat_block.get("category", ""),
                "title": sr.get("title", ""),
                "score": sr.get("score"),
                "reasoning": sr.get("reasoning", ""),
            }
            priority = sr.get("priority")
            if priority == "High":
                high.append(entry)
            elif priority == "Low":
                low.append(entry)
            elif priority == "Medium":
                medium.append(entry)
            else:
                unscored.append(entry)

    def _sort_key(x):
        s = x.get("score")
        return -1.0 if s is None else float(s)

    high.sort(key=_sort_key, reverse=True)
    medium.sort(key=_sort_key, reverse=True)
    low.sort(key=_sort_key, reverse=True)
    return high, medium, low, unscored


def _score_one_batch(
    batch: list,
    company: str,
    year: int,
    batch_index: int,
    batch_total: int,
) -> dict:
    """Score one ≤_PRIORITY_BATCH_SIZE batch via Bedrock.

    Returns {local_id: raw_llm_dict}. On any LLM/parse error returns {} —
    the caller treats every item in this batch as "unscored" instead of
    quietly substituting Medium=5.0.
    """
    risks_json = json.dumps(
        [
            {
                "id": i,
                "title": r["title"][:200],
                "labels": r["labels"],
                "tags": r.get("tags", [])[:6],
            }
            for i, r in enumerate(batch)
        ],
        ensure_ascii=False,
    )

    prompt = f"""You are a senior financial risk analyst evaluating SEC 10-K risk factors for {company} ({year}).

This is batch {batch_index} of {batch_total} for the same filing. Score risks 1-10 in three dimensions:
1. financial_impact — potential dollar/earnings impact if the risk materializes
2. likelihood — probability of occurrence in the next 12 months
3. urgency — how soon action or attention is needed

Risks to evaluate:
{risks_json}

Return ONLY a JSON array, one object per risk, in this exact format:
[
  {{
    "id": 0,
    "financial_impact": 8,
    "likelihood": 6,
    "urgency": 7,
    "reasoning": "One sentence explaining the priority."
  }}
]
Do NOT include `score` or `priority` — they are computed deterministically downstream
from financial_impact/likelihood/urgency. No preamble, no markdown."""

    try:
        raw = _invoke_extraction(prompt, max_tokens=2048)
        raw = _strip_json_fences(raw)
        scored = json.loads(raw)
        if not isinstance(scored, list):
            return {}
        return {
            int(item["id"]): item
            for item in scored
            if isinstance(item, dict) and "id" in item
        }
    except Exception:
        return {}


def _prioritize_risks_impl(
    risks: list,
    company: str,
    year: int,
    progress_steps: list | None = None,
) -> list:
    flat_risks = []
    for cat_block in risks:
        category = cat_block.get("category", "Unknown")
        for sub_risk in cat_block.get("sub_risks", []):
            if isinstance(sub_risk, dict):
                title = sub_risk.get("title", "")
                labels = sub_risk.get("labels", [])
                tags = sub_risk.get("tags", [])
            else:
                title = str(sub_risk)
                labels = []
                tags = []
            flat_risks.append({
                "category": category,
                "title": title,
                "labels": labels,
                "tags": tags,
            })

    if not flat_risks:
        return risks

    total = len(flat_risks)
    batches: list[list[dict]] = [
        flat_risks[i : i + _PRIORITY_BATCH_SIZE]
        for i in range(0, total, _PRIORITY_BATCH_SIZE)
    ]

    score_map_global: dict = {}
    for b_idx, batch in enumerate(batches, start=1):
        local_scores = _score_one_batch(
            batch=batch,
            company=company,
            year=year,
            batch_index=b_idx,
            batch_total=len(batches),
        )
        offset = (b_idx - 1) * _PRIORITY_BATCH_SIZE
        for local_id, item in local_scores.items():
            score_map_global[offset + int(local_id)] = item

    if isinstance(progress_steps, list):
        progress_steps.append(
            f"⚙️ Tool 3a: scored {len(score_map_global)}/{total} risks across {len(batches)} batches"
        )

    enriched_flat = []
    for i, risk in enumerate(flat_risks):
        raw_score = score_map_global.get(i)
        if isinstance(raw_score, dict):
            # Trust only the three LLM-provided dimensions; recompute
            # score+priority deterministically so the LLM cannot return a
            # contradiction such as score=2 + priority="High".
            fi = _clamp_int_1_10(raw_score.get("financial_impact"), default=5)
            lk = _clamp_int_1_10(raw_score.get("likelihood"), default=5)
            ur = _clamp_int_1_10(raw_score.get("urgency"), default=5)
            score: float | None = _compute_score_from_dims(fi, lk, ur)
            priority: str | None = _priority_from_score(score)
            reasoning = str(raw_score.get("reasoning", "") or "")
        else:
            # LLM did not score this item (batch failure or partial response).
            # Mark it explicitly unscored — main.py uses this to flag the whole
            # record's RPI as "scoring failed" instead of faking Medium=5.0.
            fi, lk, ur = 5, 5, 5
            score = None
            priority = None
            reasoning = ""

        enriched_flat.append({
            "category": risk["category"],
            "title": risk["title"],
            "labels": risk["labels"],
            "tags": risk.get("tags", []),
            "priority": priority,
            "score": score,
            "financial_impact": fi,
            "likelihood": lk,
            "urgency": ur,
            "reasoning": reasoning,
        })

    category_map: dict = {}
    for risk in enriched_flat:
        category = risk["category"]
        category_map.setdefault(category, []).append(risk)

    return [{"category": category, "sub_risks": sub_risks} for category, sub_risks in category_map.items()]


def _generate_agent_report_impl(
    company: str,
    year: int,
    enriched_risks: list,
    compare_data: dict | None = None,
    user_query: str = "",
) -> dict:
    high, medium, low, unscored = _build_priority_lists(enriched_risks)
    top_high = json.dumps(high[:5], ensure_ascii=False)
    top_medium = json.dumps(medium[:3], ensure_ascii=False)

    compare_context = ""
    if compare_data:
        new_risks = compare_data.get("new_risks", [])[:5]
        removed_risks = compare_data.get("removed_risks", [])[:5]
        compare_context = f"""
Year-over-year comparison context:
- New risks (emerged): {json.dumps([r.get('title', '')[:100] for r in new_risks], ensure_ascii=False)}
- Removed risks (resolved/dropped): {json.dumps([r.get('title', '')[:100] for r in removed_risks], ensure_ascii=False)}
"""

    query_context = f"\nUser's specific question: {user_query}" if user_query else ""

    prompt = f"""You are a senior financial risk intelligence analyst. Generate a structured risk report for {company} ({year} 10-K filing).

Priority matrix summary:
- HIGH priority risks ({len(high)} total): {top_high}
- MEDIUM priority risks ({len(medium)} total): {top_medium}
- LOW priority risks: {len(low)} total
{compare_context}{query_context}

Generate a JSON report with exactly this structure:
{{
  "executive_summary": "3-4 sentence overview of the company's overall risk profile and most critical concerns.",
  "key_findings": [
    "Finding 1 — specific insight about a high-priority risk",
    "Finding 2 — pattern or theme across multiple risks",
    "Finding 3 — notable change or emerging risk",
    "Finding 4 — industry-specific concern",
    "Finding 5 — any unusual or standout risk"
  ],
  "recommendations": [
    "Recommendation 1 — actionable step for the highest priority risk",
    "Recommendation 2 — monitoring suggestion",
    "Recommendation 3 — strategic implication for investors/analysts"
  ],
  "risk_themes": ["theme1", "theme2", "theme3"],
  "overall_risk_rating": "High | Medium-High | Medium | Medium-Low | Low",
  "compare_insights": "2-3 sentences on YoY or cross-company changes, or empty string if no compare data."
}}

Return ONLY the JSON object, no preamble, no markdown fences."""

    try:
        raw = _invoke_extraction(prompt, max_tokens=1500)
        report_content = json.loads(_strip_json_fences(raw))
    except Exception as e:
        report_content = {
            "executive_summary": f"Report generation encountered an error: {str(e)}",
            "key_findings": [],
            "recommendations": [],
            "risk_themes": [],
            "overall_risk_rating": "Unknown",
            "compare_insights": "",
        }

    scored_total = len(high) + len(medium) + len(low)
    if scored_total == 0 and len(unscored) > 0:
        scoring_status = "failed"
    elif len(unscored) > 0:
        scoring_status = "partial"
    else:
        scoring_status = "ok"

    return {
        "company": company,
        "year": year,
        "user_query": user_query,
        "priority_matrix": {
            "high": {"count": len(high), "top": high[:5]},
            "medium": {"count": len(medium), "top": medium[:3]},
            "low": {"count": len(low), "top": low[:3]},
            "unscored": {"count": len(unscored), "top": unscored[:3]},
        },
        "scoring_status": scoring_status,
        **report_content,
    }


def _answer_user_query_impl(
    user_query: str,
    company: str,
    year: int,
    report: dict,
) -> dict:
    q = str(user_query or "").strip()
    if not q:
        return {
            "direct_answer": "",
            "evidence": [],
            "follow_up_questions": [],
        }

    priority_matrix = report.get("priority_matrix", {}) if isinstance(report, dict) else {}
    high_top = priority_matrix.get("high", {}).get("top", [])[:5]
    key_findings = report.get("key_findings", [])[:5] if isinstance(report, dict) else []
    summary = str(report.get("executive_summary", "") if isinstance(report, dict) else "")
    compare_insights = str(report.get("compare_insights", "") if isinstance(report, dict) else "")

    prompt = f"""You are a risk intelligence assistant. Answer the user question with concise evidence.

Company: {company}
Year: {year}
Question: {q}
Executive summary: {summary}
Top high-priority risks: {json.dumps(high_top, ensure_ascii=False)}
Key findings: {json.dumps(key_findings, ensure_ascii=False)}
Compare insights: {compare_insights}

Return ONLY JSON:
{{
  "direct_answer": "4-7 sentence direct answer to the question.",
  "evidence": [
    "Evidence bullet 1 tied to top risk or compare signal",
    "Evidence bullet 2",
    "Evidence bullet 3"
  ],
  "follow_up_questions": [
    "Optional follow-up 1",
    "Optional follow-up 2"
  ]
}}"""

    try:
        out = _extract_json_obj(_invoke_agent(prompt, max_tokens=1000)) or {}
        if not isinstance(out, dict):
            out = {}
    except Exception:
        out = {}

    direct_answer = str(out.get("direct_answer", "") or "").strip()
    evidence = out.get("evidence", []) if isinstance(out.get("evidence"), list) else []
    follow_ups = out.get("follow_up_questions", []) if isinstance(out.get("follow_up_questions"), list) else []

    if not direct_answer:
        top_titles = [str(x.get("title", "") or "") for x in high_top[:3] if isinstance(x, dict)]
        direct_answer = summary or "Available risk data is limited; please refine the question or provide more context."
        if top_titles:
            direct_answer += " Key high-priority risks include: " + "; ".join(top_titles) + "."

    evidence = [str(e).strip() for e in evidence if str(e).strip()][:5]
    if not evidence and high_top:
        evidence = [
            f"High-priority: {str(x.get('title', ''))[:160]}"
            for x in high_top[:3]
            if isinstance(x, dict)
        ]
    if compare_insights:
        evidence = [*evidence, f"Comparison signal: {compare_insights[:180]}"][:6]

    follow_ups = [str(x).strip() for x in follow_ups if str(x).strip()][:3]

    return {
        "direct_answer": direct_answer,
        "evidence": evidence,
        "follow_up_questions": follow_ups,
    }


def _normalize_report(report: dict, company: str, year: int, user_query: str, enriched_risks: list, steps: list) -> dict:
    out = dict(report or {})
    out.setdefault("company", company)
    out.setdefault("year", year)
    out.setdefault("user_query", user_query)
    out.setdefault("priority_matrix", {
        "high": {"count": 0, "top": []},
        "medium": {"count": 0, "top": []},
        "low": {"count": 0, "top": []},
        "unscored": {"count": 0, "top": []},
    })
    out.setdefault("scoring_status", "missing")
    out.setdefault("executive_summary", "")
    out.setdefault("key_findings", [])
    out.setdefault("recommendations", [])
    out.setdefault("risk_themes", [])
    out.setdefault("overall_risk_rating", "Unknown")
    out.setdefault("compare_insights", "")
    out.setdefault("direct_answer", "")
    out.setdefault("evidence", [])
    out.setdefault("follow_up_questions", [])
    out["enriched_risks"] = out.get("enriched_risks", enriched_risks)
    out["agent_steps"] = out.get("agent_steps", steps)
    return out


def run_agent(
    user_query: str,
    company: str,
    year: int,
    risks: list,
    compare_data: dict = None,
) -> dict:
    """Main agent entrypoint using direct Bedrock calls (no Strands)."""
    steps = ["🔍 Interpreting query..."]

    try:
        total = sum(len(c.get("sub_risks", [])) for c in risks)
        steps.append(f"⚙️ Tool 3: Scoring and prioritizing {total} risk factors...")
        enriched_risks = _prioritize_risks_impl(risks, company, year, progress_steps=steps)
        steps.append("✅ Risk prioritization complete.")

        steps.append("📝 Tool 4: Generating structured risk intelligence report...")
        report = _generate_agent_report_impl(
            company=company,
            year=year,
            enriched_risks=enriched_risks,
            compare_data=compare_data,
            user_query=user_query,
        )
        steps.append("✅ Report generation complete.")
        if str(user_query or "").strip():
            steps.append("💬 Tool 5: Building direct answer to the user question...")
            answer_payload = _answer_user_query_impl(
                user_query=user_query,
                company=company,
                year=year,
                report=report,
            )
            report["direct_answer"] = str(answer_payload.get("direct_answer", "") or "")
            report["evidence"] = answer_payload.get("evidence", [])
            report["follow_up_questions"] = answer_payload.get("follow_up_questions", [])
            steps.append("✅ Direct answer complete.")

        return _normalize_report(report, company, year, user_query, enriched_risks, steps)
    except Exception as exc:
        fallback = _fallback_report(
            company=company,
            year=year,
            user_query=user_query,
            error=f"Agent failed: {str(exc)}",
        )
        fallback["agent_steps"] = steps + [f"❌ Agent failed: {str(exc)}"]
        return fallback
