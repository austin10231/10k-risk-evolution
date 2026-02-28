"""AWS Bedrock — risk classification, summarization, change analysis."""

import json
import streamlit as st
import boto3

MODEL_ID = "us.amazon.nova-lite-v1:0"

RISK_CATEGORIES = [
    "cybersecurity", "regulatory", "supply_chain", "geopolitical",
    "competition", "macroeconomic", "financial", "environmental",
    "litigation", "talent", "technology", "reputational", "operational",
]


def _get_bedrock():
    return boto3.client(
        "bedrock-runtime",
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=st.secrets["BEDROCK_REGION"],
    )


def _invoke(prompt, max_tokens=1024):
    client = _get_bedrock()
    body = json.dumps({
        "inferenceConfig": {"maxTokens": max_tokens},
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


def classify_risks(risks):
    categories_str = ", ".join(RISK_CATEGORIES)
    classified = []
    for cat_block in risks:
        cat_name = cat_block.get("category", "Unknown")
        new_sub_risks = []
        for title in cat_block.get("sub_risks", []):
            text = title[:500] if len(title) > 500 else title
            prompt = f"""Classify this SEC 10-K risk factor into 1-2 categories from this list:
{categories_str}

Risk text: "{text}"

Return ONLY a JSON array of 1-2 category strings, nothing else. Example: ["regulatory", "litigation"]"""
            try:
                raw = _invoke(prompt, max_tokens=50).strip()
                if raw.startswith("["):
                    labels = json.loads(raw)
                    labels = [l for l in labels if l in RISK_CATEGORIES]
                    if not labels:
                        labels = ["other"]
                else:
                    labels = ["other"]
            except Exception:
                labels = ["other"]
            new_sub_risks.append({"title": title, "labels": labels})
        classified.append({"category": cat_name, "sub_risks": new_sub_risks})
    return classified


def generate_summary(company, year, risks):
    risk_lines = []
    for cat_block in risks:
        cat = cat_block.get("category", "")
        subs = cat_block.get("sub_risks", [])
        if isinstance(subs, list) and subs:
            if isinstance(subs[0], dict):
                titles = [s.get("title", "")[:100] for s in subs]
            else:
                titles = [s[:100] for s in subs]
            risk_lines.append(f"{cat}: {'; '.join(titles)}")
    risk_text = "\n".join(risk_lines)
    prompt = f"""You are a financial analyst. Based on the following risk factors from {company}'s {year} 10-K filing, write a concise executive summary in 3-5 sentences.

Focus on: the most critical risks, notable themes, and anything unusual compared to typical 10-K filings.

Risk factors:
{risk_text}

Write the summary directly, no headers or bullet points."""
    try:
        return _invoke(prompt, max_tokens=500)
    except Exception as e:
        return f"(Summary generation failed: {str(e)})"


def analyze_changes(subject, label_b, label_a, new_risks, removed_risks, mode="yoy"):
    new_titles = [r.get("title", "")[:120] for r in new_risks]
    removed_titles = [r.get("title", "")[:120] for r in removed_risks]

    if mode == "yoy":
        prompt = f"""You are a financial analyst comparing {subject}'s 10-K risk factors between {label_a} and {label_b}.

Risks that appeared in {label_b} (not in {label_a}):
{chr(10).join(f'- {t}' for t in new_titles) if new_titles else '- None'}

Risks that disappeared from {label_b} (were in {label_a}):
{chr(10).join(f'- {t}' for t in removed_titles) if removed_titles else '- None'}

Write a concise 3-5 sentence analysis covering:
1. What major risk themes emerged or disappeared
2. Likely business or macro reasons behind these shifts
3. What this signals about the company's evolving risk landscape

Write directly and concisely, no headers or bullet points."""
    else:
        prompt = f"""You are a financial analyst comparing the 10-K risk factors of two different companies or filings: {label_a} and {label_b}.

Risks unique to {label_b} (not found in {label_a}):
{chr(10).join(f'- {t}' for t in new_titles) if new_titles else '- None'}

Risks unique to {label_a} (not found in {label_b}):
{chr(10).join(f'- {t}' for t in removed_titles) if removed_titles else '- None'}

Write a concise 3-5 sentence analysis covering:
1. Key differences in risk profiles between the two companies or periods
2. What these differences suggest about each company's business model, industry position, or strategic focus
3. Any notable risks that one company faces but the other does not, and why that might be

Write directly and concisely, no headers or bullet points."""

    try:
        return _invoke(prompt, max_tokens=500)
    except Exception as e:
        return f"(Change analysis failed: {str(e)})"
