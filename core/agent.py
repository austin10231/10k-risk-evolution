"""
core/agent.py
Risk Agent — Tool 3 (Risk Prioritization) + Tool 4 (Report Generation)
Uses Amazon Bedrock Nova Lite via the existing _invoke pattern.
Implements a lightweight Strands-style tool registry without external SDK dependency.
"""

import json
import re
import streamlit as st
import boto3

MODEL_ID = "us.amazon.nova-lite-v1:0"

# ── Bedrock client (reuses same pattern as bedrock.py) ───────────────────────

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


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 3 — Risk Prioritization
# Input:  list of risk dicts (category, title, labels)
# Output: same list enriched with priority + score + reasoning
# ══════════════════════════════════════════════════════════════════════════════

def prioritize_risks(risks: list, company: str, year: int) -> list:
    """
    Tool 3: Score and prioritize each risk factor.
    Returns the input risk list with added fields:
      - priority: "High" | "Medium" | "Low"
      - score: float 0-10
      - reasoning: one-sentence rationale
    """
    # Flatten to individual sub-risks for scoring
    flat_risks = []
    for cat_block in risks:
        cat = cat_block.get("category", "Unknown")
        for sr in cat_block.get("sub_risks", []):
            if isinstance(sr, dict):
                title = sr.get("title", "")
                labels = sr.get("labels", [])
            else:
                title = str(sr)
                labels = []
            flat_risks.append({
                "category": cat,
                "title": title,
                "labels": labels,
            })

    if not flat_risks:
        return risks

    # Build a batch prompt to score all risks at once (up to 40)
    batch = flat_risks[:40]
    risks_json = json.dumps(
        [{"id": i, "title": r["title"][:200], "labels": r["labels"]} for i, r in enumerate(batch)],
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
        # Strip any accidental markdown fences
        raw = re.sub(r"```json|```", "", raw).strip()
        scored = json.loads(raw)
        score_map = {item["id"]: item for item in scored}
    except Exception:
        # Fallback: assign Medium to all
        score_map = {}

    # Enrich the original flat_risks
    enriched_flat = []
    for i, r in enumerate(batch):
        s = score_map.get(i, {})
        enriched_flat.append({
            "category": r["category"],
            "title": r["title"],
            "labels": r["labels"],
            "priority": s.get("priority", "Medium"),
            "score": round(float(s.get("score", 5.0)), 2),
            "financial_impact": s.get("financial_impact", 5),
            "likelihood": s.get("likelihood", 5),
            "urgency": s.get("urgency", 5),
            "reasoning": s.get("reasoning", ""),
        })

    # Rebuild category structure with enriched sub_risks
    cat_map = {}
    for r in enriched_flat:
        cat = r["category"]
        if cat not in cat_map:
            cat_map[cat] = []
        cat_map[cat].append(r)

    enriched_risks = [
        {"category": cat, "sub_risks": subs}
        for cat, subs in cat_map.items()
    ]

    return enriched_risks


# ══════════════════════════════════════════════════════════════════════════════
# TOOL 4 — Structured Agent Report Generation
# Input:  enriched risks, company metadata, optional compare data
# Output: structured report dict
# ══════════════════════════════════════════════════════════════════════════════

def generate_agent_report(
    company: str,
    year: int,
    enriched_risks: list,
    compare_data: dict = None,
    user_query: str = "",
) -> dict:
    """
    Tool 4: Generate a structured risk intelligence report.
    Returns a report dict with sections:
      - executive_summary
      - priority_matrix (High/Medium/Low counts + top items)
      - key_findings (list of insights)
      - recommendations (list)
      - compare_insights (if compare_data provided)
    """
    # Build priority matrix from enriched risks
    high, medium, low = [], [], []
    for cat_block in enriched_risks:
        for sr in cat_block.get("sub_risks", []):
            if not isinstance(sr, dict):
                continue
            p = sr.get("priority", "Medium")
            entry = {
                "category": cat_block.get("category", ""),
                "title": sr.get("title", "")[:150],
                "score": sr.get("score", 5.0),
                "reasoning": sr.get("reasoning", ""),
            }
            if p == "High":
                high.append(entry)
            elif p == "Low":
                low.append(entry)
            else:
                medium.append(entry)

    # Sort by score descending
    high.sort(key=lambda x: x["score"], reverse=True)
    medium.sort(key=lambda x: x["score"], reverse=True)
    low.sort(key=lambda x: x["score"], reverse=True)

    # Build prompt context
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
        raw = re.sub(r"```json|```", "", raw).strip()
        report_content = json.loads(raw)
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


# ══════════════════════════════════════════════════════════════════════════════
# AGENT ORCHESTRATOR
# Parses user query → decides which tools to call → returns final report
# ══════════════════════════════════════════════════════════════════════════════

def run_agent(
    user_query: str,
    company: str,
    year: int,
    risks: list,
    compare_data: dict = None,
) -> dict:
    """
    Main agent entry point.
    Orchestrates Tool 3 + Tool 4 based on user query and available data.
    Returns a complete agent report dict.
    """
    steps = []

    # Step 1: Interpret the query
    steps.append("🔍 Interpreting query...")

    # Step 2: Tool 3 — Prioritize risks
    steps.append(f"⚙️ Tool 3: Scoring and prioritizing {sum(len(c.get('sub_risks',[])) for c in risks)} risk factors...")
    enriched = prioritize_risks(risks, company, year)
    steps.append("✅ Risk prioritization complete.")

    # Step 3: Tool 4 — Generate report
    steps.append("📝 Tool 4: Generating structured risk intelligence report...")
    report = generate_agent_report(
        company=company,
        year=year,
        enriched_risks=enriched,
        compare_data=compare_data,
        user_query=user_query,
    )
    steps.append("✅ Report generation complete.")

    report["agent_steps"] = steps
    report["enriched_risks"] = enriched

    return report
