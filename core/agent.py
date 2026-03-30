"""
core/agent.py
Risk Agent implemented with Strands SDK (strands-agents).

This module keeps the same public API:
  run_agent(user_query, company, year, risks, compare_data=None) -> dict

Internally:
  - Tool 3: prioritize_risks (risk scoring + priority assignment)
  - Tool 4: generate_agent_report (structured report generation)
Both tools are registered via @tool and orchestrated by strands.Agent.
"""

from __future__ import annotations

import json
import re

import boto3
import streamlit as st

try:
    from strands import Agent, tool
    from strands.models import BedrockModel
    _STRANDS_AVAILABLE = True
    _STRANDS_IMPORT_ERROR = ""
except Exception as e:  # pragma: no cover - import guard for local env mismatch
    Agent = None
    BedrockModel = None
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
    s = re.sub(r"```json|```", "", str(text or "")).strip()
    return s


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


def _response_to_text(response) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return json.dumps(response, ensure_ascii=False)

    for attr in ("message", "output_text", "text"):
        val = getattr(response, attr, None)
        if isinstance(val, str):
            return val

    content = getattr(response, "content", None)
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item["text"]))
                elif "json" in item:
                    parts.append(json.dumps(item["json"], ensure_ascii=False))
        if parts:
            return "\n".join(parts)

    return str(response)


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
    # Flatten to individual sub-risks for scoring
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
    for r in enriched_flat:
        cat = r["category"]
        if cat not in cat_map:
            cat_map[cat] = []
        cat_map[cat].append(r)

    return [{"category": cat, "sub_risks": subs} for cat, subs in cat_map.items()]


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
        new_r = compare_data.get("new_risks", [])[:5]
        removed_r = compare_data.get("removed_risks", [])[:5]
        compare_context = f"""
Year-over-year comparison context:
- New risks (emerged): {json.dumps([r.get('title','')[:100] for r in new_r], ensure_ascii=False)}
- Removed risks (resolved/dropped): {json.dumps([r.get('title','')[:100] for r in removed_r], ensure_ascii=False)}
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


class _RiskTools:
    """Stateful tool holder for a single run_agent invocation."""

    def __init__(self, company: str, year: int, risks: list, compare_data: dict | None, user_query: str):
        self.company = company
        self.year = year
        self.risks = risks
        self.compare_data = compare_data
        self.user_query = user_query

        self.enriched_risks: list | None = None
        self.report: dict | None = None
        self.steps = ["🔍 Interpreting query..."]

    @tool
    def prioritize_risks(self) -> dict:
        """Tool 3: score and prioritize current filing risks."""
        if self.enriched_risks is None:
            total = sum(len(c.get("sub_risks", [])) for c in self.risks)
            self.steps.append(f"⚙️ Tool 3: Scoring and prioritizing {total} risk factors...")
            self.enriched_risks = _prioritize_risks_impl(self.risks, self.company, self.year)
            self.steps.append("✅ Risk prioritization complete.")

        high, medium, low = _build_priority_lists(self.enriched_risks)
        return {
            "status": "ok",
            "high_count": len(high),
            "medium_count": len(medium),
            "low_count": len(low),
        }

    @tool
    def generate_agent_report(self) -> dict:
        """Tool 4: generate a structured risk report from prioritized risks."""
        if self.enriched_risks is None:
            self.prioritize_risks()

        if self.report is None:
            self.steps.append("📝 Tool 4: Generating structured risk intelligence report...")
            self.report = _generate_agent_report_impl(
                company=self.company,
                year=self.year,
                enriched_risks=self.enriched_risks or [],
                compare_data=self.compare_data,
                user_query=self.user_query,
            )
            self.steps.append("✅ Report generation complete.")

        out = dict(self.report)
        out["enriched_risks"] = self.enriched_risks or []
        out["agent_steps"] = list(self.steps)
        return out


def _build_strands_agent(tools: _RiskTools):
    if not _STRANDS_AVAILABLE:
        raise RuntimeError(f"strands-agents not available: {_STRANDS_IMPORT_ERROR}")

    session = boto3.Session(
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=st.secrets["BEDROCK_REGION"],
    )
    model = BedrockModel(
        model_id=MODEL_ID,
        boto_session=session,
        temperature=0.0,
        top_p=1.0,
        max_tokens=2048,
        streaming=False,
    )

    return Agent(
        model=model,
        tools=[tools.prioritize_risks, tools.generate_agent_report],
        system_prompt=(
            "You are a risk-analysis orchestrator. "
            "You must use tools to complete the task. "
            "Always call prioritize_risks before generate_agent_report. "
            "After tool calls, return only the final JSON object."
        ),
    )


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
    out["enriched_risks"] = out.get("enriched_risks", tools.enriched_risks or [])
    out["agent_steps"] = out.get("agent_steps", tools.steps)
    return out


def run_agent(
    user_query: str,
    company: str,
    year: int,
    risks: list,
    compare_data: dict = None,
) -> dict:
    """
    Main agent entry point.
    Uses Strands Agent to orchestrate Tool 3 + Tool 4.
    """
    tools = _RiskTools(
        company=company,
        year=year,
        risks=risks,
        compare_data=compare_data,
        user_query=user_query,
    )

    if not _STRANDS_AVAILABLE:
        try:
            tools.steps.append(f"ℹ️ Strands SDK unavailable: {_STRANDS_IMPORT_ERROR}")
            tools.steps.append("↩️ Falling back to direct tool execution (Tool 3 -> Tool 4).")
            tools.prioritize_risks()
            rep = tools.generate_agent_report()
            return _normalize_report(rep, company, year, user_query, tools)
        except Exception as e:
            return _fallback_report(
                company=company,
                year=year,
                user_query=user_query,
                error=f"Agent failed: {str(e)}",
            )

    try:
        agent = _build_strands_agent(tools)
        prompt = (
            f"Analyze {company} ({year}) 10-K risks.\n"
            f"User query: {user_query or '(none)'}\n\n"
            "Execution policy:\n"
            "1) Call prioritize_risks.\n"
            "2) Call generate_agent_report.\n"
            "3) Return ONLY the JSON object from generate_agent_report."
        )
        response = agent(prompt)
        parsed = _extract_json_obj(_response_to_text(response))
        if isinstance(parsed, dict) and "priority_matrix" in parsed:
            return _normalize_report(parsed, company, year, user_query, tools)

        # If model response isn't parseable, use tool state generated during execution.
        if tools.report is not None:
            return _normalize_report(tools.generate_agent_report(), company, year, user_query, tools)

        # Last fallback in the same run: execute tools directly.
        tools.prioritize_risks()
        return _normalize_report(tools.generate_agent_report(), company, year, user_query, tools)

    except Exception as e:
        # Graceful fallback to deterministic tool execution.
        try:
            tools.prioritize_risks()
            rep = tools.generate_agent_report()
            rep = _normalize_report(rep, company, year, user_query, tools)
            rep["agent_steps"] = rep.get("agent_steps", []) + [f"ℹ️ Strands fallback path: {str(e)}"]
            return rep
        except Exception as inner:
            return _fallback_report(
                company=company,
                year=year,
                user_query=user_query,
                error=f"Agent failed: {str(inner)}",
            )
