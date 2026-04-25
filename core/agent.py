"""
core/agent.py
Dynamic Risk Agent with query planning, tool routing, and structured outputs.

Public API remains:
  run_agent(user_query, company, year, risks, compare_data=None) -> dict
"""

from __future__ import annotations

import json
import re
from typing import Any

import boto3
import streamlit as st

try:
    from strands import tool
    _STRANDS_AVAILABLE = True
    _STRANDS_IMPORT_ERROR = ""
except Exception as e:  # pragma: no cover
    _STRANDS_AVAILABLE = False
    _STRANDS_IMPORT_ERROR = str(e)

    def tool(func=None, **_kwargs):
        """No-op fallback decorator when strands-agents is unavailable."""
        if func is None:
            def _decorator(f):
                return f
            return _decorator
        return func


MODEL_ID = "us.amazon.nova-pro-v1:0"


def _get_bedrock():
    return boto3.client(
        "bedrock-runtime",
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=st.secrets["BEDROCK_REGION"],
    )


def _invoke(prompt: str, max_tokens: int = 2048) -> str:
    client = _get_bedrock()
    body = json.dumps({
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": 0.0,
            "topP": 1.0,
        },
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
    })
    response = client.invoke_model(
        modelId=MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    return result["output"]["message"]["content"][0]["text"].strip()


def _strip_json_fences(text: str) -> str:
    return re.sub(r"```json|```", "", str(text or "")).strip()


def _extract_json_obj(text: str):
    s = _strip_json_fences(text)
    try:
        return json.loads(s)
    except Exception:
        pass

    l = s.find("{")
    r = s.rfind("}")
    if l >= 0 and r > l:
        try:
            return json.loads(s[l:r + 1])
        except Exception:
            return None
    return None


def _extract_json_arr(text: str):
    s = _strip_json_fences(text)
    try:
        arr = json.loads(s)
        return arr if isinstance(arr, list) else None
    except Exception:
        pass

    l = s.find("[")
    r = s.rfind("]")
    if l >= 0 and r > l:
        try:
            arr = json.loads(s[l:r + 1])
            return arr if isinstance(arr, list) else None
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
        "answer_mode": "fallback",
        "planning": {
            "intent": "error",
            "tool_sequence": [],
            "reason": error,
            "source": "fallback",
        },
        "tool_trace": [],
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
            p = sr.get("priority", "Medium")
            if p == "High":
                high.append(entry)
            elif p == "Low":
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
        cat = cat_block.get("category", "Unknown")
        for sr in cat_block.get("sub_risks", []):
            if isinstance(sr, dict):
                title = sr.get("title", "")
                labels = sr.get("labels", [])
                tags = sr.get("tags", [])
            else:
                title = str(sr)
                labels = []
                tags = []
            flat_risks.append({
                "category": cat,
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
                "title": r["title"][:220],
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
  }}
]
No preamble, no markdown."""

    score_map = {}
    try:
        scored = _extract_json_arr(_invoke(prompt, max_tokens=2200)) or []
        score_map = {int(item.get("id")): item for item in scored if isinstance(item, dict)}
    except Exception:
        score_map = {}

    enriched_flat = []
    for i, r in enumerate(batch):
        s = score_map.get(i, {})
        enriched_flat.append({
            "category": r["category"],
            "title": r["title"],
            "labels": r["labels"],
            "tags": r.get("tags", []),
            "priority": s.get("priority", "Medium"),
            "score": round(float(s.get("score", 5.0)), 2),
            "financial_impact": s.get("financial_impact", 5),
            "likelihood": s.get("likelihood", 5),
            "urgency": s.get("urgency", 5),
            "reasoning": s.get("reasoning", ""),
        })

    cat_map = {}
    for row in enriched_flat:
        cat_map.setdefault(row["category"], []).append(row)

    return [{"category": cat, "sub_risks": subs} for cat, subs in cat_map.items()]


def _compare_insights_impl(
    company: str,
    year: int,
    user_query: str,
    compare_data: dict | None,
) -> dict:
    if not isinstance(compare_data, dict):
        return {
            "compare_insights": "",
            "new_count": 0,
            "removed_count": 0,
            "new_top": [],
            "removed_top": [],
        }

    new_r = compare_data.get("new_risks", []) if isinstance(compare_data.get("new_risks"), list) else []
    removed_r = compare_data.get("removed_risks", []) if isinstance(compare_data.get("removed_risks"), list) else []
    new_titles = [str(r.get("title", "") if isinstance(r, dict) else r)[:140] for r in new_r[:6]]
    removed_titles = [str(r.get("title", "") if isinstance(r, dict) else r)[:140] for r in removed_r[:6]]

    prompt = f"""You are a risk analyst. Compare risk changes for {company} ({year}).

User question:
{user_query or '(none)'}

New risks:
{json.dumps(new_titles, ensure_ascii=False)}

Removed risks:
{json.dumps(removed_titles, ensure_ascii=False)}

Return ONLY JSON in this shape:
{{
  "compare_insights": "2-4 sentence concise explanation of the most important changes.",
  "risk_shift": "risk-increasing | mixed | risk-decreasing"
}}"""

    summary = ""
    shift = "mixed"
    try:
        parsed = _extract_json_obj(_invoke(prompt, max_tokens=600)) or {}
        if isinstance(parsed, dict):
            summary = str(parsed.get("compare_insights", "") or "").strip()
            shift = str(parsed.get("risk_shift", "mixed") or "mixed")
    except Exception:
        summary = ""

    if not summary:
        if len(new_titles) > len(removed_titles):
            summary = (
                "Compared with the baseline filing, the latest filing introduces more new risks than it removes, "
                "suggesting a net increase in risk surface that should be monitored closely."
            )
            shift = "risk-increasing"
        elif len(new_titles) < len(removed_titles):
            summary = (
                "Compared with the baseline filing, more previously disclosed risks were removed than newly introduced, "
                "suggesting partial risk normalization."
            )
            shift = "risk-decreasing"
        else:
            summary = (
                "The filing shows a mixed risk shift with both new and removed items, "
                "indicating rotation in risk focus rather than a one-direction change."
            )
            shift = "mixed"

    return {
        "compare_insights": summary,
        "risk_shift": shift,
        "new_count": len(new_r),
        "removed_count": len(removed_r),
        "new_top": new_titles,
        "removed_top": removed_titles,
    }


def _generate_agent_report_impl(
    company: str,
    year: int,
    enriched_risks: list,
    user_query: str = "",
    intent: str = "general_risk_review",
    compare_insights: str = "",
) -> dict:
    high, medium, low = _build_priority_lists(enriched_risks)

    context = {
        "high_top": high[:5],
        "medium_top": medium[:3],
        "low_count": len(low),
        "intent": intent,
        "user_query": user_query,
        "compare_insights": compare_insights,
    }

    prompt = f"""You are a senior financial risk intelligence analyst. Build a structured report for {company} ({year} 10-K).

Execution intent: {intent}
User query: {user_query or '(none)'}

Risk context JSON:
{json.dumps(context, ensure_ascii=False)}

Return ONLY JSON with this exact structure:
{{
  "executive_summary": "3-4 sentence overview aligned to user intent and top risks.",
  "key_findings": ["...", "...", "..."],
  "recommendations": ["...", "...", "..."],
  "risk_themes": ["theme1", "theme2", "theme3"],
  "overall_risk_rating": "High | Medium-High | Medium | Medium-Low | Low",
  "compare_insights": "Keep concise compare insight if available, else empty string."
}}"""

    try:
        report_content = _extract_json_obj(_invoke(prompt, max_tokens=1500)) or {}
    except Exception:
        report_content = {}

    if not isinstance(report_content, dict):
        report_content = {}

    if compare_insights and not str(report_content.get("compare_insights", "") or "").strip():
        report_content["compare_insights"] = compare_insights

    report_content.setdefault(
        "executive_summary",
        "The current filing indicates a mixed but material risk profile with concentration in high-priority items.",
    )
    report_content.setdefault("key_findings", [])
    report_content.setdefault("recommendations", [])
    report_content.setdefault("risk_themes", [])
    report_content.setdefault("overall_risk_rating", "Unknown")
    report_content.setdefault("compare_insights", compare_insights or "")

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
    compare_summary: str,
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

    prompt = f"""You are a risk intelligence assistant. Answer the user question with evidence.

Company: {company}
Year: {year}
Question: {q}
Executive summary: {summary}
Top high-priority risks: {json.dumps(high_top, ensure_ascii=False)}
Key findings: {json.dumps(key_findings, ensure_ascii=False)}
Compare insights: {compare_summary}

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
        out = _extract_json_obj(_invoke(prompt, max_tokens=1200)) or {}
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
    if compare_summary:
        evidence = [*evidence, f"Comparison signal: {compare_summary[:180]}"][:6]

    follow_ups = [str(x).strip() for x in follow_ups if str(x).strip()][:3]

    return {
        "direct_answer": direct_answer,
        "evidence": evidence,
        "follow_up_questions": follow_ups,
    }


def _fallback_plan(user_query: str, compare_data: dict | None) -> dict:
    q = str(user_query or "").lower()
    has_compare = isinstance(compare_data, dict)

    wants_compare = any(k in q for k in (
        "compare", "vs", "versus", "year over year", "yoy", "changed", "change", "difference"
    ))
    wants_market = any(k in q for k in (
        "stock", "share", "market", "price", "drawdown", "volatility", "return", "spy"
    )) or "[market context]" in q
    wants_priority = any(k in q for k in (
        "top", "critical", "priorit", "urgent", "greatest", "highest", "immediate"
    ))

    if wants_compare and has_compare:
        intent = "comparison"
    elif wants_market:
        intent = "market_overlay"
    elif wants_priority:
        intent = "prioritization"
    else:
        intent = "general_risk_review"

    sequence = ["prioritize_risks"]
    if intent == "comparison" and has_compare:
        sequence.append("analyze_compare_changes")
    sequence.append("generate_agent_report")
    if str(user_query or "").strip():
        sequence.append("answer_user_query")

    return {
        "intent": intent,
        "tool_sequence": sequence,
        "reason": "Keyword-based fallback planner.",
        "source": "fallback",
    }


def _sanitize_tool_sequence(seq: list[Any], has_compare: bool, has_query: bool) -> list[str]:
    allowed = [
        "prioritize_risks",
        "analyze_compare_changes",
        "generate_agent_report",
        "answer_user_query",
    ]
    out: list[str] = []
    for item in seq:
        name = str(item or "").strip()
        if name in allowed and name not in out:
            out.append(name)

    if "prioritize_risks" not in out:
        out.insert(0, "prioritize_risks")

    if not has_compare and "analyze_compare_changes" in out:
        out = [x for x in out if x != "analyze_compare_changes"]

    if "generate_agent_report" not in out:
        out.append("generate_agent_report")

    if has_query and "answer_user_query" not in out:
        out.append("answer_user_query")

    # ensure ordering constraints
    def _move_after(name: str, after: str):
        if name in out and after in out:
            out.remove(name)
            idx = out.index(after)
            out.insert(idx + 1, name)

    _move_after("generate_agent_report", "prioritize_risks")
    if "analyze_compare_changes" in out and "generate_agent_report" in out:
        out.remove("analyze_compare_changes")
        idx = out.index("generate_agent_report")
        out.insert(idx, "analyze_compare_changes")
    if "answer_user_query" in out and out[-1] != "answer_user_query":
        out.remove("answer_user_query")
        out.append("answer_user_query")

    return out


def _plan_execution(user_query: str, compare_data: dict | None) -> dict:
    fallback = _fallback_plan(user_query=user_query, compare_data=compare_data)
    has_compare = isinstance(compare_data, dict)
    has_query = bool(str(user_query or "").strip())

    q = str(user_query or "").strip()
    if not q:
        fallback["tool_sequence"] = _sanitize_tool_sequence(
            fallback.get("tool_sequence", []),
            has_compare=has_compare,
            has_query=has_query,
        )
        return fallback

    prompt = f"""You are a planning module for a risk-analysis agent.

User query:
{q}

Whether compare data is available: {has_compare}

Return ONLY JSON with this schema:
{{
  "intent": "comparison | prioritization | market_overlay | general_risk_review | impact_assessment | mitigation_planning",
  "tool_sequence": ["prioritize_risks", "analyze_compare_changes", "generate_agent_report", "answer_user_query"],
  "reason": "one sentence"
}}

Rules:
- Use only tool names from the allowed set.
- If compare data is unavailable, do not include analyze_compare_changes.
- Always include prioritize_risks before generate_agent_report.
- Put answer_user_query last when the user asks a specific question.
- Output JSON only."""

    try:
        raw = _invoke(prompt, max_tokens=350)
        parsed = _extract_json_obj(raw)
        if isinstance(parsed, dict):
            plan = {
                "intent": str(parsed.get("intent", "") or "").strip() or fallback["intent"],
                "tool_sequence": _sanitize_tool_sequence(
                    parsed.get("tool_sequence", []),
                    has_compare=has_compare,
                    has_query=has_query,
                ),
                "reason": str(parsed.get("reason", "") or "").strip() or "LLM planner",
                "source": "llm",
            }
            if plan["tool_sequence"]:
                return plan
    except Exception:
        pass

    fallback["tool_sequence"] = _sanitize_tool_sequence(
        fallback.get("tool_sequence", []),
        has_compare=has_compare,
        has_query=has_query,
    )
    return fallback


class _RiskTools:
    """Stateful tool holder for one run_agent invocation."""

    def __init__(self, company: str, year: int, risks: list, compare_data: dict | None, user_query: str):
        self.company = company
        self.year = year
        self.risks = risks if isinstance(risks, list) else []
        self.compare_data = compare_data if isinstance(compare_data, dict) else None
        self.user_query = str(user_query or "")

        self.plan: dict = {}
        self.enriched_risks: list | None = None
        self.report: dict | None = None
        self.compare_meta: dict | None = None
        self.answer_payload: dict | None = None

        self.steps: list[str] = ["🔍 Interpreting query..."]
        self.tool_trace: list[dict] = []

    def set_plan(self, plan: dict):
        self.plan = dict(plan or {})

    def _trace(self, tool_name: str, status: str, note: str = "", payload: dict | None = None):
        self.tool_trace.append({
            "tool": tool_name,
            "status": status,
            "note": note,
            "payload": payload or {},
        })

    @tool
    def prioritize_risks(self) -> dict:
        """Score and prioritize current filing risks."""
        if self.enriched_risks is None:
            total = sum(len(c.get("sub_risks", [])) for c in self.risks if isinstance(c, dict))
            self.steps.append(f"⚙️ Tool: prioritize_risks on {total} risk factors...")
            self.enriched_risks = _prioritize_risks_impl(self.risks, self.company, self.year)
            self.steps.append("✅ Risk prioritization complete.")

        high, medium, low = _build_priority_lists(self.enriched_risks)
        out = {
            "status": "ok",
            "high_count": len(high),
            "medium_count": len(medium),
            "low_count": len(low),
        }
        self._trace("prioritize_risks", "ok", "Prioritized risk items.", out)
        return out

    @tool
    def analyze_compare_changes(self) -> dict:
        """Analyze risk changes from provided compare_data."""
        if not self.compare_data:
            out = {
                "status": "skipped",
                "reason": "No compare_data available.",
            }
            self._trace("analyze_compare_changes", "skipped", out["reason"], out)
            return out

        self.steps.append("🔁 Tool: analyze_compare_changes on comparison context...")
        meta = _compare_insights_impl(
            company=self.company,
            year=self.year,
            user_query=self.user_query,
            compare_data=self.compare_data,
        )
        self.compare_meta = meta
        self.steps.append("✅ Comparison analysis complete.")

        out = {
            "status": "ok",
            "new_count": int(meta.get("new_count", 0)),
            "removed_count": int(meta.get("removed_count", 0)),
            "risk_shift": str(meta.get("risk_shift", "mixed")),
        }
        self._trace("analyze_compare_changes", "ok", "Generated compare insights.", out)
        return out

    @tool
    def generate_agent_report(self) -> dict:
        """Generate structured risk report from prioritized risks and plan intent."""
        if self.enriched_risks is None:
            self.prioritize_risks()

        if self.report is None:
            self.steps.append("📝 Tool: generate_agent_report..." )
            intent = str(self.plan.get("intent", "general_risk_review") or "general_risk_review")
            compare_text = ""
            if isinstance(self.compare_meta, dict):
                compare_text = str(self.compare_meta.get("compare_insights", "") or "")
            self.report = _generate_agent_report_impl(
                company=self.company,
                year=self.year,
                enriched_risks=self.enriched_risks or [],
                user_query=self.user_query,
                intent=intent,
                compare_insights=compare_text,
            )
            self.steps.append("✅ Report generation complete.")

        out = dict(self.report)
        out["enriched_risks"] = self.enriched_risks or []
        out["agent_steps"] = list(self.steps)
        self._trace("generate_agent_report", "ok", "Built structured report.", {
            "overall_risk_rating": out.get("overall_risk_rating", "Unknown"),
        })
        return out

    @tool
    def answer_user_query(self) -> dict:
        """Produce direct answer + evidence for the specific user question."""
        if self.report is None:
            self.generate_agent_report()

        if self.answer_payload is None:
            compare_summary = ""
            if isinstance(self.compare_meta, dict):
                compare_summary = str(self.compare_meta.get("compare_insights", "") or "")

            self.steps.append("💬 Tool: answer_user_query with evidence..." )
            self.answer_payload = _answer_user_query_impl(
                user_query=self.user_query,
                company=self.company,
                year=self.year,
                report=self.report or {},
                compare_summary=compare_summary,
            )
            self.steps.append("✅ Question-focused answer complete.")

        out = dict(self.answer_payload)
        self._trace("answer_user_query", "ok", "Generated direct answer and evidence.", {
            "evidence_count": len(out.get("evidence", [])),
        })
        return out


def _normalize_report(
    report: dict,
    company: str,
    year: int,
    user_query: str,
    tools: _RiskTools,
) -> dict:
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

    if isinstance(tools.compare_meta, dict) and not str(out.get("compare_insights", "") or "").strip():
        out["compare_insights"] = str(tools.compare_meta.get("compare_insights", "") or "")

    if isinstance(tools.answer_payload, dict):
        out["direct_answer"] = str(tools.answer_payload.get("direct_answer", "") or "")
        out["evidence"] = tools.answer_payload.get("evidence", [])
        out["follow_up_questions"] = tools.answer_payload.get("follow_up_questions", [])
    else:
        out.setdefault("direct_answer", "")
        out.setdefault("evidence", [])
        out.setdefault("follow_up_questions", [])

    out["enriched_risks"] = out.get("enriched_risks", tools.enriched_risks or [])
    out["agent_steps"] = out.get("agent_steps", tools.steps)
    out["planning"] = dict(tools.plan or {})
    out["tool_trace"] = list(tools.tool_trace)
    out["answer_mode"] = "query_focused" if str(user_query or "").strip() else "report"
    out["runtime"] = {
        "strands_available": _STRANDS_AVAILABLE,
        "strands_import_error": _STRANDS_IMPORT_ERROR if not _STRANDS_AVAILABLE else "",
        "orchestration": "local_planner",
    }
    return out


def run_agent(
    user_query: str,
    company: str,
    year: int,
    risks: list,
    compare_data: dict = None,
) -> dict:
    """Main agent entry point with dynamic planning and tool routing."""
    tools = _RiskTools(
        company=company,
        year=year,
        risks=risks,
        compare_data=compare_data,
        user_query=user_query,
    )

    try:
        plan = _plan_execution(user_query=user_query, compare_data=compare_data)
        tools.set_plan(plan)
        tools.steps.append(
            f"🧭 Planner intent: {plan.get('intent', 'general_risk_review')} "
            f"(source: {plan.get('source', 'fallback')})"
        )
        tools.steps.append(f"🧰 Planned tools: {' -> '.join(plan.get('tool_sequence', []))}")

        tool_map = {
            "prioritize_risks": tools.prioritize_risks,
            "analyze_compare_changes": tools.analyze_compare_changes,
            "generate_agent_report": tools.generate_agent_report,
            "answer_user_query": tools.answer_user_query,
        }

        for tool_name in plan.get("tool_sequence", []):
            fn = tool_map.get(tool_name)
            if fn is None:
                tools._trace(tool_name, "skipped", "Unknown tool name from planner.", {})
                continue
            try:
                fn()
            except Exception as e:
                msg = f"Tool {tool_name} failed: {str(e)}"
                tools.steps.append(f"⚠️ {msg}")
                tools._trace(tool_name, "error", msg, {})
                if tool_name == "prioritize_risks":
                    raise

        if tools.report is None:
            tools.generate_agent_report()

        if str(user_query or "").strip() and tools.answer_payload is None:
            # Best-effort fill if planner omitted answer tool.
            tools.answer_user_query()

        final_report = _normalize_report(
            report=tools.report or {},
            company=company,
            year=year,
            user_query=user_query,
            tools=tools,
        )
        return final_report

    except Exception as e:
        try:
            # deterministic fallback path
            tools.steps.append(f"↩️ Planner fallback: {str(e)}")
            tools.prioritize_risks()
            rep = tools.generate_agent_report()
            if str(user_query or "").strip():
                tools.answer_user_query()
            rep = _normalize_report(rep, company, year, user_query, tools)
            rep["agent_steps"] = rep.get("agent_steps", []) + [f"ℹ️ Fallback path due to: {str(e)}"]
            rep["planning"] = {
                "intent": "fallback",
                "tool_sequence": ["prioritize_risks", "generate_agent_report", "answer_user_query"],
                "reason": str(e),
                "source": "fallback",
            }
            return rep
        except Exception as inner:
            return _fallback_report(
                company=company,
                year=year,
                user_query=user_query,
                error=f"Agent failed: {str(inner)}",
            )
