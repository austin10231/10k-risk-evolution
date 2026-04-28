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


MODEL_ID = "us.amazon.nova-pro-v1:0"


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


def _invoke(prompt: str, max_tokens: int = 2048) -> str:
    body_obj = {
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": 0.0,
            "topP": 1.0,
        },
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
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
        response = client.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=body_json,
        )
        result = json.loads(response["body"].read())
        return result["output"]["message"]["content"][0]["text"].strip()
    except Exception as exc:
        boto3_error = exc

    # Fallback: direct SigV4 HTTP request without boto3 dependency.
    try:
        region = _env("BEDROCK_REGION", "us-west-2")
        service = "bedrock-runtime"
        encoded_model_id = quote(MODEL_ID, safe="")
        endpoint = f"https://bedrock-runtime.{region}.amazonaws.com/model/{encoded_model_id}/invoke"
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
            f"Bedrock invoke failed (boto3={repr(boto3_error)}, sigv4={repr(sigv4_error)})"
        ) from sigv4_error


def invoke_llm_text(prompt: str, max_tokens: int = 1200) -> str:
    """Public helper for other runtime modules that need direct LLM text responses."""
    return _invoke(prompt, max_tokens=max_tokens)


def get_model_id() -> str:
    return MODEL_ID


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
        },
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
    high, medium, low = [], [], []
    for cat_block in enriched_risks:
        for sr in cat_block.get("sub_risks", []):
            if not isinstance(sr, dict):
                continue
            entry = {
                "category": cat_block.get("category", ""),
                "title": sr.get("title", ""),
                "score": sr.get("score", 5.0),
                "reasoning": sr.get("reasoning", ""),
            }
            priority = sr.get("priority", "Medium")
            if priority == "High":
                high.append(entry)
            elif priority == "Low":
                low.append(entry)
            else:
                medium.append(entry)

    high.sort(key=lambda x: x["score"], reverse=True)
    medium.sort(key=lambda x: x["score"], reverse=True)
    low.sort(key=lambda x: x["score"], reverse=True)
    return high, medium, low


def _prioritize_risks_impl(risks: list, company: str, year: int) -> list:
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

    batch = flat_risks[:40]
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

Score each risk below on three dimensions (1-10 each):
1. financial_impact — potential dollar/earnings impact if the risk materializes
2. likelihood — probability of occurrence in the next 12 months
3. urgency — how soon action or attention is needed

Then compute: score = (financial_impact * 0.4) + (likelihood * 0.35) + (urgency * 0.25)
Assign priority: High if score >= 7, Medium if score >= 4, Low otherwise.

Risks to evaluate:
{risks_json}

Return ONLY a JSON array, one object per risk, in this exact format:
[
  {{
    "id": 0,
    "financial_impact": 8,
    "likelihood": 6,
    "urgency": 7,
    "score": 7.15,
    "priority": "High",
    "reasoning": "One sentence explaining the priority."
  }},
  ...
]
No preamble, no markdown, only the JSON array."""

    try:
        raw = _invoke(prompt, max_tokens=2048)
        raw = _strip_json_fences(raw)
        scored = json.loads(raw)
        score_map = {item["id"]: item for item in scored}
    except Exception:
        score_map = {}

    enriched_flat = []
    for i, risk in enumerate(batch):
        score = score_map.get(i, {})
        enriched_flat.append({
            "category": risk["category"],
            "title": risk["title"],
            "labels": risk["labels"],
            "tags": risk.get("tags", []),
            "priority": score.get("priority", "Medium"),
            "score": round(float(score.get("score", 5.0)), 2),
            "financial_impact": score.get("financial_impact", 5),
            "likelihood": score.get("likelihood", 5),
            "urgency": score.get("urgency", 5),
            "reasoning": score.get("reasoning", ""),
        })

    category_map = {}
    for risk in enriched_flat:
        category = risk["category"]
        if category not in category_map:
            category_map[category] = []
        category_map[category].append(risk)

    return [{"category": category, "sub_risks": sub_risks} for category, sub_risks in category_map.items()]


def _generate_agent_report_impl(
    company: str,
    year: int,
    enriched_risks: list,
    compare_data: dict | None = None,
    user_query: str = "",
) -> dict:
    high, medium, low = _build_priority_lists(enriched_risks)
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
        raw = _invoke(prompt, max_tokens=1500)
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

    return {
        "company": company,
        "year": year,
        "user_query": user_query,
        "priority_matrix": {
            "high": {"count": len(high), "top": high[:5]},
            "medium": {"count": len(medium), "top": medium[:3]},
            "low": {"count": len(low), "top": low[:3]},
        },
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
        out = _extract_json_obj(_invoke(prompt, max_tokens=1000)) or {}
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
    })
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
        enriched_risks = _prioritize_risks_impl(risks, company, year)
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
