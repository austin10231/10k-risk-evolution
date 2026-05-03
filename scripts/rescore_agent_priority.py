"""Re-score agent priority (RPI) for every risks JSON under ``10k_filings/``
in S3 — without re-extracting risks.

For each ``10k_filings/<industry>/<company_dir>/<year>_10K_risks.json`` we
re-run the priority pipeline (three-dimensional LLM scoring + agent report)
and overwrite ``result["agent_report"]`` in place. The ``risks`` array,
``company_overview``, and HTML are **not** touched.

This script is **fully self-contained** — it talks to S3 and Bedrock
directly via boto3 and does **not** import ``agentcore_deploy/`` or its
``agent`` shim. That avoids the ``ModuleNotFoundError: No module named
'agent'`` you hit when ``agentcore_deploy/main.py`` lazily imports
``agent`` from the deployment-specific sys.path. The scoring logic
(prompt, three-dim weights, batch size, threshold buckets, output schema)
is replicated here and must be kept in sync with
``agentcore_deploy/agent.py``. See PROJECT_CHANGELOG_CN.md entries 26 / 27
/ 32 for the canonical algorithm.

Usage::

    # 1. Plan only — prints what would happen, no S3 writes, no Bedrock cost.
    python scripts/rescore_agent_priority.py --dry-run

    # 2. Real run. AWS + Bedrock credentials must be in env.
    python scripts/rescore_agent_priority.py --write

    # Filter to one industry / one ticker for partial roll-outs.
    python scripts/rescore_agent_priority.py --write --industry Technology
    python scripts/rescore_agent_priority.py --write --ticker AAPL

    # Skip records that already carry a successful agent_report (resume after
    # a partial failure or re-run only the records that originally errored).
    python scripts/rescore_agent_priority.py --write --skip-already-scored

    # Cap the run at N records (handy on Railway one-offs to bound cost).
    python scripts/rescore_agent_priority.py --write --limit 5
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import boto3

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.industry_mapping import COMPANIES  # noqa: E402  — repo-root injected above

JSON_KEY_RE = re.compile(
    r"^10k_filings/(?P<industry>[^/]+)/(?P<dir>[^/]+)/(?P<year>\d{4})_10K_risks\.json$"
)


# ══════════════════════════════════════════════════════════════════════════════
#  Bedrock + S3 clients (self-contained, no agentcore_deploy dependency)
# ══════════════════════════════════════════════════════════════════════════════


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default)


EXTRACTION_MODEL_ID = (
    _env("BEDROCK_EXTRACTION_MODEL_ID", "us.amazon.nova-pro-v1:0").strip()
    or "us.amazon.nova-pro-v1:0"
)
BEDROCK_REGION = (_env("BEDROCK_REGION") or _env("AWS_REGION", "us-west-2")).strip() or "us-west-2"
S3_REGION = _env("AWS_REGION", "us-west-1").strip() or "us-west-1"


def _s3_bucket() -> str:
    bucket = _env("S3_BUCKET").strip()
    if not bucket:
        raise RuntimeError("S3_BUCKET env var is required.")
    return bucket


def _client_kwargs(region: str) -> dict:
    kwargs: dict = {"region_name": region}
    access_key = _env("AWS_ACCESS_KEY_ID")
    secret_key = _env("AWS_SECRET_ACCESS_KEY")
    session_token = _env("AWS_SESSION_TOKEN")
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token
    return kwargs


_S3_CLIENT = None
_BEDROCK_CLIENT = None


def _s3_client():
    global _S3_CLIENT
    if _S3_CLIENT is None:
        _S3_CLIENT = boto3.client("s3", **_client_kwargs(S3_REGION))
    return _S3_CLIENT


def _bedrock_client():
    global _BEDROCK_CLIENT
    if _BEDROCK_CLIENT is None:
        _BEDROCK_CLIENT = boto3.client("bedrock-runtime", **_client_kwargs(BEDROCK_REGION))
    return _BEDROCK_CLIENT


def _get_bytes(key: str) -> Optional[bytes]:
    try:
        obj = _s3_client().get_object(Bucket=_s3_bucket(), Key=key)
        return obj["Body"].read()
    except Exception:
        return None


def _put_bytes(key: str, data: bytes, content_type: Optional[str] = None) -> None:
    kwargs: dict = {"Bucket": _s3_bucket(), "Key": key, "Body": data}
    if content_type:
        kwargs["ContentType"] = content_type
    _s3_client().put_object(**kwargs)


def _invoke_extraction(prompt: str, max_tokens: int = 2048) -> str:
    """Bedrock Converse call against the extraction model. No retry / no
    SigV4 fallback — this script always runs in an env where boto3 works
    (Railway one-off, dev shell, AgentCore container)."""
    response = _bedrock_client().converse(
        modelId=EXTRACTION_MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0, "topP": 1.0},
    )
    return response["output"]["message"]["content"][0]["text"].strip()


# ══════════════════════════════════════════════════════════════════════════════
#  RPI scoring (mirrors agentcore_deploy/agent.py — keep in sync!)
# ══════════════════════════════════════════════════════════════════════════════


# Score thresholds + weights duplicated from agent.py PRIORITY_* constants.
# RPI is computed deterministically in Python from three LLM-provided dims so
# the LLM cannot return a score↔priority contradiction.
_PRIORITY_HIGH_THRESHOLD = 7.0
_PRIORITY_MEDIUM_THRESHOLD = 4.0
_PRIORITY_DIM_WEIGHTS = (0.4, 0.35, 0.25)  # financial_impact, likelihood, urgency
_PRIORITY_BATCH_SIZE = 40


def _strip_json_fences(text: str) -> str:
    return re.sub(r"```json|```", "", str(text or "")).strip()


# ── JSON repair / retry / raw-response logging ────────────────────────────────
# Nova Pro on Bedrock occasionally hits the maxTokens limit mid-stream and
# returns a JSON document that is missing its closing brackets, has an open
# string, or trails a partial element after the last comma. We try a series
# of best-effort repairs (longest balanced prefix → truncate-at-last-top-comma
# → LIFO close → empty container) before falling back to a single retry with
# a stricter prompt suffix and a larger token budget. Every parse failure is
# logged to stderr so operators can see Nova Pro's literal output.

_RETRY_TOKEN_MULTIPLIER = 2  # max_tokens for the retry call
_RETRY_PROMPT_SUFFIX_ARRAY = (
    "\n\nCRITICAL: Output ONE complete JSON array only — no preamble, no "
    "markdown fences, no commentary. Keep every `reasoning` field under 60 "
    "characters so the array closes within the response window."
)
_RETRY_PROMPT_SUFFIX_OBJECT = (
    "\n\nCRITICAL: Output ONE complete JSON object only — no preamble, no "
    "markdown fences, no commentary. Keep every list entry under 80 "
    "characters so the object closes within the response window."
)
_RAW_LOG_MAX_CHARS = 2000


def _repair_candidates(s: str) -> list[str]:
    """Generate candidate repaired versions of a possibly-truncated JSON
    document, ordered most-data-preserving → least. Caller tries each in
    order and returns the first that parses. Strategies:

      1. Longest prefix where the outermost container balances.
      2. Truncate at the last top-level comma + close root container
         (drops only the partially-emitted last element).
      3. LIFO close any open string + open containers (handles deeply
         nested truncations where the outer container never closed).
      4. Empty container fallback (preserves shape, loses all data).
    """
    s = (s or "").strip()
    if not s or s[0] not in "{[":
        return [s]

    open_close = {"{": "}", "[": "]"}
    stack: list[str] = [s[0]]
    in_string = False
    escape = False
    last_balanced_end = -1
    last_top_level_comma = -1

    for i in range(1, len(s)):
        ch = s[i]
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack and open_close[stack[-1]] == ch:
                stack.pop()
                if not stack:
                    last_balanced_end = i
            # else: unbalanced close — ignored, will be picked up by repair below
        elif ch == "," and len(stack) == 1:
            last_top_level_comma = i

    candidates: list[str] = []

    if last_balanced_end >= 0:
        candidates.append(s[: last_balanced_end + 1])

    if last_top_level_comma > 0:
        candidates.append(s[:last_top_level_comma] + open_close[s[0]])

    repaired = s
    if in_string:
        repaired += '"'
    while stack:
        repaired += open_close[stack.pop()]
    candidates.append(repaired)

    candidates.append("[]" if s[0] == "[" else "{}")

    seen: set[str] = set()
    out: list[str] = []
    for cand in candidates:
        if cand and cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out


def _parse_json_with_repair(raw: str):
    """Try parsing `raw` as JSON; on failure, attempt every repair strategy
    in order. Returns ``(parsed_or_None, repair_used, error_str)``. On
    success ``error_str`` is empty; on total failure ``parsed`` is None and
    ``error_str`` describes what broke."""
    s = (raw or "").strip()
    if not s:
        return None, False, "empty response"

    s_clean = _strip_json_fences(s)
    if not s_clean:
        return None, False, "empty after fence strip"

    for i, ch in enumerate(s_clean):
        if ch in "{[":
            s_clean = s_clean[i:]
            break
    else:
        return None, False, "no_json_root_found"

    try:
        return json.loads(s_clean), False, ""
    except json.JSONDecodeError as exc:
        first_err = f"{type(exc).__name__}: {exc}"

    last_err = first_err
    for cand in _repair_candidates(s_clean):
        try:
            return json.loads(cand), True, ""
        except json.JSONDecodeError as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            continue

    return None, False, f"all_repair_strategies_failed (last={last_err}; first={first_err})"


def _log_raw_response(label: str, raw: str) -> None:
    """Print the raw LLM response to stderr so operators can inspect what
    Nova Pro emitted when JSON parsing fails. Truncated to keep stderr
    readable."""
    snippet = str(raw or "")
    truncated_note = ""
    if len(snippet) > _RAW_LOG_MAX_CHARS:
        truncated_note = f" [truncated; total {len(snippet)} chars]"
        snippet = snippet[:_RAW_LOG_MAX_CHARS]
    print(
        f"  · {label}: raw_response{truncated_note}={snippet!r}",
        file=sys.stderr,
        flush=True,
    )


def _invoke_with_json_retry(
    prompt: str,
    max_tokens: int,
    *,
    expect: str,                   # "array" or "object"
    label: str,                    # for stderr logging context
):
    """Call ``_invoke_extraction``, parse the response as JSON of the shape
    given by ``expect``, retry once on failure.

    Returns ``(parsed_or_None, raw_text_of_last_attempt)``. On both attempts
    failing the raw response is dumped to stderr (truncated to 2 KB)."""
    expected_type = list if expect == "array" else dict

    raw1 = _invoke_extraction(prompt, max_tokens=max_tokens)
    parsed1, repaired1, err1 = _parse_json_with_repair(raw1)
    if isinstance(parsed1, expected_type):
        if repaired1:
            print(
                f"  · {label}: parsed via JSON repair (Bedrock returned malformed/truncated)",
                file=sys.stderr,
                flush=True,
            )
        return parsed1, raw1

    print(
        f"  · {label}: attempt-1 JSON parse failed ({err1}); retrying once with stricter prompt",
        file=sys.stderr,
        flush=True,
    )
    _log_raw_response(f"{label} attempt-1", raw1)

    suffix = _RETRY_PROMPT_SUFFIX_ARRAY if expect == "array" else _RETRY_PROMPT_SUFFIX_OBJECT
    retry_max_tokens = int(max_tokens * _RETRY_TOKEN_MULTIPLIER)
    try:
        raw2 = _invoke_extraction(prompt + suffix, max_tokens=retry_max_tokens)
    except Exception as exc:
        print(
            f"  · {label}: attempt-2 Bedrock call raised {type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return None, raw1

    parsed2, repaired2, err2 = _parse_json_with_repair(raw2)
    if isinstance(parsed2, expected_type):
        if repaired2:
            print(
                f"  · {label}: attempt-2 parsed via JSON repair",
                file=sys.stderr,
                flush=True,
            )
        return parsed2, raw2

    print(
        f"  · {label}: attempt-2 also failed ({err2}); giving up",
        file=sys.stderr,
        flush=True,
    )
    _log_raw_response(f"{label} attempt-2", raw2)
    return None, raw2


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
        fi * _PRIORITY_DIM_WEIGHTS[0]
        + lk * _PRIORITY_DIM_WEIGHTS[1]
        + ur * _PRIORITY_DIM_WEIGHTS[2]
    )
    return round(float(raw), 2)


def _priority_from_score(score: float) -> str:
    s = float(score or 0.0)
    if s >= _PRIORITY_HIGH_THRESHOLD:
        return "High"
    if s >= _PRIORITY_MEDIUM_THRESHOLD:
        return "Medium"
    return "Low"


def _score_one_batch(
    batch: list,
    company: str,
    year: int,
    batch_index: int,
    batch_total: int,
) -> dict:
    """Score one ≤_PRIORITY_BATCH_SIZE batch. Returns ``{local_id: raw_dict}``;
    on any LLM/parse error returns ``{}`` so the caller can mark the entire
    batch unscored instead of inventing Medium=5.0 defaults."""
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
        parsed, _raw = _invoke_with_json_retry(
            prompt,
            max_tokens=2048,
            expect="array",
            label=f"batch {batch_index}/{batch_total}",
        )
    except Exception as exc:
        print(
            f"  · batch {batch_index}/{batch_total} Bedrock call failed: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return {}
    if not isinstance(parsed, list):
        return {}
    return {
        int(item["id"]): item
        for item in parsed
        if isinstance(item, dict) and "id" in item
    }


def _prioritize_risks(
    risks: list,
    company: str,
    year: int,
    progress_steps: Optional[list] = None,
) -> list:
    flat_risks = []
    for cat_block in risks if isinstance(risks, list) else []:
        if not isinstance(cat_block, dict):
            continue
        category = cat_block.get("category", "Unknown")
        for sub_risk in cat_block.get("sub_risks", []) or []:
            if isinstance(sub_risk, dict):
                title = str(sub_risk.get("title", "") or "")
                labels = sub_risk.get("labels", []) if isinstance(sub_risk.get("labels"), list) else []
                tags = sub_risk.get("tags", []) if isinstance(sub_risk.get("tags"), list) else []
            else:
                title = str(sub_risk or "")
                labels = []
                tags = []
            flat_risks.append({"category": category, "title": title, "labels": labels, "tags": tags})

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
            fi = _clamp_int_1_10(raw_score.get("financial_impact"), 5)
            lk = _clamp_int_1_10(raw_score.get("likelihood"), 5)
            ur = _clamp_int_1_10(raw_score.get("urgency"), 5)
            score: Optional[float] = _compute_score_from_dims(fi, lk, ur)
            priority: Optional[str] = _priority_from_score(score)
            reasoning = str(raw_score.get("reasoning", "") or "")
        else:
            # Item not scored (batch failure or partial response). Keep dimensions
            # at neutral 5 for display, but score=None / priority=None so the
            # downstream RPI computation flags it as unscored rather than
            # silently substituting Medium=5.0.
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
        category_map.setdefault(risk["category"], []).append(risk)
    return [{"category": c, "sub_risks": s} for c, s in category_map.items()]


def _build_priority_lists(enriched_risks: list):
    high, medium, low, unscored = [], [], [], []
    for cat_block in enriched_risks if isinstance(enriched_risks, list) else []:
        if not isinstance(cat_block, dict):
            continue
        for sr in cat_block.get("sub_risks", []) or []:
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


def _generate_agent_report(company: str, year: int, enriched_risks: list) -> dict:
    high, medium, low, unscored = _build_priority_lists(enriched_risks)
    top_high = json.dumps(high[:5], ensure_ascii=False)
    top_medium = json.dumps(medium[:3], ensure_ascii=False)

    prompt = f"""You are a senior financial risk intelligence analyst. Generate a structured risk report for {company} ({year} 10-K filing).

Priority matrix summary:
- HIGH priority risks ({len(high)} total): {top_high}
- MEDIUM priority risks ({len(medium)} total): {top_medium}
- LOW priority risks: {len(low)} total

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
        parsed, _raw = _invoke_with_json_retry(
            prompt,
            max_tokens=1500,
            expect="object",
            label=f"agent_report({company} {year})",
        )
    except Exception as exc:
        parsed = None
        print(
            f"  · agent_report({company} {year}) Bedrock call failed: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )
    if isinstance(parsed, dict):
        report_content = parsed
    else:
        report_content = {
            "executive_summary": "Report generation failed: JSON parse error after retry (see stderr for raw Nova Pro response).",
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
        "user_query": "",
        "priority_matrix": {
            "high": {"count": len(high), "top": high[:5]},
            "medium": {"count": len(medium), "top": medium[:3]},
            "low": {"count": len(low), "top": low[:3]},
            "unscored": {"count": len(unscored), "top": unscored[:3]},
        },
        "scoring_status": scoring_status,
        **report_content,
    }


def _normalize_report(
    report: dict,
    company: str,
    year: int,
    enriched_risks: list,
    steps: list,
) -> dict:
    out = dict(report or {})
    out.setdefault("company", company)
    out.setdefault("year", year)
    out.setdefault("user_query", "")
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
    # The chat-side fields stay empty here — rescore never has a user_query
    # so we cannot synthesize an answer; the live runtime will fill these in
    # the next time someone asks an interactive question.
    out.setdefault("direct_answer", "")
    out.setdefault("evidence", [])
    out.setdefault("follow_up_questions", [])
    out["enriched_risks"] = out.get("enriched_risks", enriched_risks)
    out["agent_steps"] = out.get("agent_steps", steps)
    return out


def _build_agent_priority_report(company: str, year: int, risks: list) -> dict:
    """Re-implementation of ``agentcore_deploy.agent.run_agent`` minus the
    ``_answer_user_query_impl`` step (we have no user query during a rescore).
    Returns the same ``agent_report`` shape ``main.py`` and the dashboard
    expect."""
    steps = [f"🔁 Rescore: starting for {company} ({year})"]
    total = sum(
        len(c.get("sub_risks", []) or [])
        for c in (risks or [])
        if isinstance(c, dict)
    )
    steps.append(f"⚙️ Tool 3: Scoring and prioritizing {total} risk factors...")
    enriched = _prioritize_risks(risks, company, year, progress_steps=steps)
    steps.append("✅ Risk prioritization complete.")
    steps.append("📝 Tool 4: Generating structured risk intelligence report...")
    rep = _generate_agent_report(company, year, enriched)
    steps.append("✅ Report generation complete.")
    return _normalize_report(rep, company, year, enriched, steps)


# ══════════════════════════════════════════════════════════════════════════════
#  Driver
# ══════════════════════════════════════════════════════════════════════════════


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _list_risks_json_keys() -> list[str]:
    keys: list[str] = []
    paginator = _s3_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_s3_bucket(), Prefix="10k_filings/"):
        for obj in page.get("Contents", []) or []:
            k = str(obj.get("Key") or "")
            if JSON_KEY_RE.match(k):
                keys.append(k)
    return sorted(keys)


def _resolve_company_name(company_dir: str, result: dict) -> str:
    if isinstance(result, dict):
        overview = result.get("company_overview") if isinstance(result.get("company_overview"), dict) else {}
        name = str((overview or {}).get("company") or "").strip()
        if name:
            return name
    for ticker, meta in COMPANIES.items():
        if str(meta.get("dir") or "").lower() == company_dir.lower():
            return str(meta.get("name") or ticker)
    return company_dir.replace("_", " ")


def _ticker_for_company_dir(company_dir: str) -> Optional[str]:
    for ticker, meta in COMPANIES.items():
        if str(meta.get("dir") or "").lower() == company_dir.lower():
            return ticker
    return None


def _has_successful_agent_report(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    rep = result.get("agent_report") if isinstance(result.get("agent_report"), dict) else None
    if not rep:
        return False
    status = str(rep.get("scoring_status") or "").lower()
    if status in ("ok", "partial"):
        return True
    pm = rep.get("priority_matrix")
    return isinstance(pm, dict) and bool(pm)


def rescore(
    *,
    write: bool,
    industry_filter: str = "",
    ticker_filter: str = "",
    skip_already_scored: bool = False,
    limit: int = 0,
) -> dict:
    started = _now_iso()
    keys = _list_risks_json_keys()
    print(f"[plan] found {len(keys)} risks JSON objects under 10k_filings/", flush=True)
    print(
        f"[plan] BEDROCK_REGION={BEDROCK_REGION}  S3_REGION={S3_REGION}  "
        f"EXTRACTION_MODEL_ID={EXTRACTION_MODEL_ID}",
        flush=True,
    )

    if not write:
        print("[plan] DRY RUN — no S3 writes, no Bedrock invocations", flush=True)

    report: dict = {
        "started_at": started,
        "ended_at": None,
        "total": len(keys),
        "ok": [],
        "skipped": [],
        "failed": [],
        "write": bool(write),
        "industry_filter": industry_filter,
        "ticker_filter": ticker_filter,
        "skip_already_scored": bool(skip_already_scored),
        "limit": int(limit or 0),
        "extraction_model_id": EXTRACTION_MODEL_ID,
        "bedrock_region": BEDROCK_REGION,
    }

    processed = 0
    for idx, key in enumerate(keys, start=1):
        m = JSON_KEY_RE.match(key)
        if not m:
            continue
        industry = m.group("industry")
        company_dir = m.group("dir")
        year = int(m.group("year"))

        if industry_filter and industry != industry_filter:
            continue
        if ticker_filter:
            ticker = _ticker_for_company_dir(company_dir)
            if not ticker or ticker.upper() != ticker_filter.upper():
                continue
        if limit and processed >= limit:
            break
        processed += 1

        t0 = time.time()
        try:
            raw = _get_bytes(key)
            if not raw:
                raise RuntimeError("empty body")
            try:
                result = json.loads(raw.decode("utf-8", errors="ignore"))
            except Exception as exc:
                raise RuntimeError(f"could not parse JSON: {exc}") from exc
            if not isinstance(result, dict):
                raise RuntimeError(f"json root is {type(result).__name__}, not dict")

            if skip_already_scored and _has_successful_agent_report(result):
                duration = time.time() - t0
                print(
                    f"[{idx}/{len(keys)}] SKIP {key} reason=already_scored {duration:.1f}s",
                    flush=True,
                )
                report["skipped"].append({"key": key, "reason": "already_scored"})
                continue

            risks = result.get("risks", []) if isinstance(result.get("risks"), list) else []
            sub_risk_count = sum(
                len(b.get("sub_risks", []) or [])
                for b in (risks if isinstance(risks, list) else [])
                if isinstance(b, dict)
            )
            if not risks or sub_risk_count == 0:
                print(
                    f"[{idx}/{len(keys)}] SKIP {key} reason=no_risks_in_json",
                    flush=True,
                )
                report["skipped"].append({"key": key, "reason": "no_risks"})
                continue

            company = _resolve_company_name(company_dir, result)

            if not write:
                print(
                    f"[{idx}/{len(keys)}] PLAN {key}  company={company} year={year} sub_risks={sub_risk_count}",
                    flush=True,
                )
                report["ok"].append({
                    "key": key,
                    "industry": industry,
                    "company_dir": company_dir,
                    "year": year,
                    "sub_risk_count": sub_risk_count,
                    "planned": True,
                })
                continue

            # Real write below.
            agent_report = _build_agent_priority_report(company, year, risks)
            if not isinstance(agent_report, dict):
                raise RuntimeError("agent_priority returned non-dict")

            result["agent_report"] = agent_report
            result.pop("agent_report_error", None)
            result["agent_report_rescored_at"] = _now_iso()

            payload = json.dumps(result, indent=2, ensure_ascii=False, default=str).encode("utf-8")
            _put_bytes(key, payload, content_type="application/json")

            duration = time.time() - t0
            status = str(agent_report.get("scoring_status") or "ok")
            scored = 0
            try:
                pm = agent_report.get("priority_matrix") if isinstance(agent_report, dict) else {}
                if isinstance(pm, dict):
                    for bucket in ("high", "medium", "low"):
                        bucket_obj = pm.get(bucket) if isinstance(pm.get(bucket), dict) else {}
                        scored += int((bucket_obj or {}).get("count") or 0)
            except Exception:
                pass
            print(
                f"[{idx}/{len(keys)}] OK   {industry}/{company_dir}/{year}  "
                f"status={status} scored={scored}/{sub_risk_count}  {duration:.1f}s",
                flush=True,
            )
            report["ok"].append({
                "key": key,
                "industry": industry,
                "company_dir": company_dir,
                "year": year,
                "sub_risk_count": sub_risk_count,
                "scored_count": scored,
                "scoring_status": status,
                "duration_s": round(duration, 2),
            })

        except Exception as exc:
            duration = time.time() - t0
            tb = traceback.format_exc()
            print(
                f"[{idx}/{len(keys)}] FAIL {key}  reason={type(exc).__name__}:{exc}  {duration:.1f}s",
                flush=True,
            )
            print(tb, flush=True)
            report["failed"].append({
                "key": key,
                "reason": f"{type(exc).__name__}: {exc}",
                "duration_s": round(duration, 2),
            })

    report["ended_at"] = _now_iso()
    print(
        f"[done] ok={len(report['ok'])} skipped={len(report['skipped'])} failed={len(report['failed'])}",
        flush=True,
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-score agent priority (RPI) for every risks JSON under "
            "10k_filings/ in S3 without re-extracting risks. Self-contained: "
            "uses boto3 directly, no agentcore_deploy / agent module imports."
        ),
    )
    parser.add_argument("--dry-run", dest="write", action="store_false",
                        help="Default. Print the rescoring plan; no S3 writes, no Bedrock invocations.")
    parser.add_argument("--write", dest="write", action="store_true",
                        help="Actually invoke Bedrock and write updated JSON back to S3.")
    parser.add_argument("--industry", default="",
                        help="Only rescore one industry directory (e.g., Technology).")
    parser.add_argument("--ticker", default="",
                        help="Only rescore one ticker (e.g., AAPL).")
    parser.add_argument("--skip-already-scored", action="store_true",
                        help="Skip records whose agent_report already has scoring_status in {ok, partial}.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after processing N records (0 = no limit).")
    parser.add_argument("--report", default=str(ROOT / "scripts" / "rescore_agent_priority.report.json"),
                        help="Where to write the run report JSON.")
    parser.set_defaults(write=False)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        _s3_bucket()
    except RuntimeError as exc:
        print(f"[fatal] {exc}", file=sys.stderr)
        return 2

    report = rescore(
        write=args.write,
        industry_filter=args.industry,
        ticker_filter=args.ticker,
        skip_already_scored=args.skip_already_scored,
        limit=args.limit,
    )

    try:
        Path(args.report).write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"[report] wrote {args.report}", flush=True)
    except Exception as exc:
        print(f"[report] could not write {args.report}: {exc}", file=sys.stderr)

    return 0 if not report.get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
