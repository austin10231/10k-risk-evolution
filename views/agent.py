"""Agent page — clean chat-first risk assistant (English UI, multilingual Q&A)."""

from __future__ import annotations

import copy
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime

import boto3
import streamlit as st
from botocore.config import Config

from core.auto_bootstrap import bootstrap_company_year_10k
from core.comparator import compare_risks
from storage.store import (
    get_result,
    load_company_ticker_map,
    load_index,
    save_agent_report,
)

SUGGESTED_QUERIES = [
    "What are NVIDIA's top risks in 2024?",
    "Compare Apple and Microsoft risk profiles in 2024.",
    "How did Tesla's risk profile change year-over-year?",
    "Summarize the most urgent risks for Airbus in 2024.",
    "Which company looks riskier in 2024: Amazon or Meta?",
]

COMPARE_HINTS = (
    "compare", "vs", "versus", "difference", "different", "contrast", "对比", "比较", "区别",
)
YOY_HINTS = (
    "year-over-year", "year over year", "yoy", "last year", "previous year", "同比", "去年",
)


@dataclass
class FilingContext:
    company: str
    year: int
    result: dict
    source: str


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

        :root {
          --bg: #f7fafc;
          --card: #ffffff;
          --line: #dbe7f3;
          --text: #1b2a3a;
          --muted: #5b728a;
          --primary: #2b6cb0;
          --soft: #edf5ff;
          --shadow: 0 10px 28px rgba(33, 73, 112, 0.08);
        }

        [data-testid="stAppViewContainer"] {
          background:
            radial-gradient(900px 360px at 8% -10%, #eaf4ff, transparent 62%),
            linear-gradient(180deg, #f9fcff 0%, var(--bg) 70%);
        }

        .block-container {
          max-width: 980px;
          padding-top: 1rem;
          padding-bottom: 3.6rem;
        }

        .rl-hero {
          border: 1px solid var(--line);
          background: linear-gradient(180deg, #ffffff 0%, #f9fcff 100%);
          border-radius: 16px;
          padding: 1rem 1.05rem 0.95rem;
          box-shadow: var(--shadow);
          margin-bottom: .8rem;
        }

        .rl-title {
          margin: 0;
          color: var(--text);
          font-family: "Manrope", sans-serif;
          font-size: 1.75rem;
          line-height: 1.2;
          font-weight: 800;
          letter-spacing: -.015em;
        }

        .rl-subtitle {
          margin: .35rem 0 0;
          color: var(--muted);
          font-family: "Manrope", sans-serif;
          font-size: .98rem;
          line-height: 1.6;
        }

        .rl-tag {
          display: inline-flex;
          align-items: center;
          border-radius: 999px;
          border: 1px solid #cde0f5;
          background: var(--soft);
          color: #2b5c92;
          padding: .18rem .62rem;
          font-size: .75rem;
          font-weight: 700;
          margin-bottom: .55rem;
          font-family: "Manrope", sans-serif;
        }

        .rl-warning {
          margin-top: .7rem;
          border: 1px solid #fecaca;
          background: #fff4f4;
          border-radius: 10px;
          color: #b91c1c;
          padding: .5rem .65rem;
          font-size: .84rem;
          font-weight: 600;
          font-family: "Manrope", sans-serif;
        }

        .rl-section {
          margin: .75rem 0 .45rem;
          font-family: "Manrope", sans-serif;
          font-size: .74rem;
          letter-spacing: .08em;
          text-transform: uppercase;
          color: #6f879b;
          font-weight: 800;
        }

        .stButton > button {
          border-radius: 11px;
          border: 1px solid var(--line);
          background: #ffffff;
          color: #24415e;
          font-family: "Manrope", sans-serif;
          font-weight: 700;
          box-shadow: 0 5px 14px rgba(33,73,112,.06);
          transition: all .16s ease;
        }

        .stButton > button:hover {
          transform: translateY(-1px);
          background: #f7fbff;
          border-color: #c7dcf1;
          box-shadow: 0 9px 20px rgba(33,73,112,.1);
        }

        [data-testid="stChatMessage"] {
          border: 1px solid var(--line);
          border-radius: 12px;
          background: var(--card);
          padding: .5rem .42rem;
          box-shadow: 0 6px 16px rgba(33,73,112,.06);
          margin-bottom: .58rem;
        }

        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li {
          font-family: "Manrope", sans-serif;
          color: #20384f;
          line-height: 1.62;
          font-size: .965rem;
        }

        [data-testid="stChatInput"] textarea {
          border: 1px solid #cfe0ef !important;
          background: #ffffff !important;
          border-radius: 12px !important;
          color: #1f3448 !important;
          font-family: "Manrope", sans-serif !important;
          box-shadow: 0 8px 20px rgba(33,73,112,.08);
        }

        [data-testid="stChatInput"] button {
          border-radius: 10px !important;
          background: linear-gradient(135deg, #2b6cb0, #3182ce) !important;
          border: 0 !important;
          color: #fff !important;
          font-weight: 700 !important;
        }

        .rl-context {
          border: 1px dashed #cfe0ef;
          background: #f7fbff;
          border-radius: 9px;
          color: #35516c;
          padding: .44rem .58rem;
          font-size: .81rem;
          margin-bottom: .38rem;
          font-family: "Manrope", sans-serif;
        }

        .rl-metric-row {
          display: grid;
          grid-template-columns: repeat(4, minmax(0,1fr));
          gap: .48rem;
          margin-top: .2rem;
        }

        .rl-metric {
          border: 1px solid var(--line);
          background: #fbfdff;
          border-radius: 10px;
          padding: .5rem .56rem;
        }

        .rl-metric span {
          display: block;
          font-family: "Manrope", sans-serif;
        }

        .rl-metric .k {
          color: #70879b;
          text-transform: uppercase;
          letter-spacing: .07em;
          font-size: .68rem;
          font-weight: 800;
        }

        .rl-metric .v {
          margin-top: .15rem;
          color: #12324c;
          font-size: 1.01rem;
          font-weight: 800;
        }

        @media (max-width: 920px) {
          .rl-title { font-size: 1.45rem; }
          .rl-metric-row { grid-template-columns: repeat(2, minmax(0,1fr)); }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _ensure_state() -> None:
    if "agent_runtime_session_id" not in st.session_state:
        st.session_state["agent_runtime_session_id"] = str(uuid.uuid4())
    if "agent_chat_messages" not in st.session_state:
        st.session_state["agent_chat_messages"] = [
            {
                "role": "assistant",
                "content": (
                    "I am ready. Ask any question about company risk. "
                    "I will infer company/year automatically and fetch missing filings if needed."
                ),
            }
        ]
    if "agent_prompt_queue" not in st.session_state:
        st.session_state["agent_prompt_queue"] = ""
    if "agent_last_contexts" not in st.session_state:
        st.session_state["agent_last_contexts"] = []


def _secret_get(key: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(key, default) or default)
    except Exception:
        return default


def _extract_json_obj(text: str):
    s = re.sub(r"```json|```", "", str(text or "")).strip()
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


def _normalize_report_payload(report: dict, company: str, year: int, user_query: str, mode_label: str) -> dict:
    out = dict(report or {})
    if "report" in out and isinstance(out.get("report"), dict):
        out = dict(out["report"])
    elif "result" in out and isinstance(out.get("result"), dict):
        out = dict(out["result"])

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
    out.setdefault("agent_steps", [])
    out.setdefault("planning", {})
    out.setdefault("tool_trace", [])

    steps = out.get("agent_steps")
    if not isinstance(steps, list):
        steps = [str(steps)]
    out["agent_steps"] = [f"Execution mode: {mode_label}", *steps]
    return out


def _get_agentcore_client(read_timeout: int = 120):
    region = _secret_get("AGENTCORE_REGION", _secret_get("BEDROCK_REGION", "us-west-2"))
    client_config = Config(
        connect_timeout=10,
        read_timeout=read_timeout,
        retries={"max_attempts": 2, "mode": "standard"},
    )
    return boto3.client(
        "bedrock-agentcore",
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=region,
        config=client_config,
    )


def _read_agentcore_response_text(resp: dict) -> str:
    body = resp.get("response")
    if body is None:
        return ""

    ctype = str(resp.get("contentType", "")).lower()
    if "text/event-stream" in ctype:
        chunks = []
        for raw_line in body.iter_lines(chunk_size=1024):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload and payload != "[DONE]":
                    chunks.append(payload)
            else:
                chunks.append(line)
        return "\n".join(chunks)

    payload = body.read()
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="ignore")
    return str(payload)


def _ensure_runtime_session_id(value: str) -> str:
    sid = str(value or "").strip()
    return sid if len(sid) >= 33 else str(uuid.uuid4())


def _contains_cjk(text: str) -> bool:
    s = str(text or "")
    return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", s))


def _language_instruction(text: str) -> str:
    if _contains_cjk(text):
        return "Please answer in Chinese and keep technical terms clear."
    return "Please answer in English."


def _invoke_agentcore_runtime(
    *,
    agent_runtime_arn: str,
    qualifier: str,
    runtime_session_id: str,
    company: str,
    year: int,
    user_query: str,
    risks: list,
    compare_data: dict | None,
) -> dict:
    client = _get_agentcore_client(read_timeout=300)
    runtime_session_id = _ensure_runtime_session_id(runtime_session_id)

    safe_company = str(company or "")
    safe_query = str(user_query or "")
    safe_year = int(year or 0)
    safe_risks = risks if isinstance(risks, list) else []
    safe_compare = compare_data if isinstance(compare_data, dict) else None

    runtime_query = (
        f"{safe_query}\n\n"
        f"[Response style]\n{_language_instruction(safe_query)} "
        "If evidence is uncertain, say uncertainty explicitly."
    )

    aws_ctx = {
        "aws_access_key_id": _secret_get("AWS_ACCESS_KEY_ID", ""),
        "aws_secret_access_key": _secret_get("AWS_SECRET_ACCESS_KEY", ""),
        "aws_session_token": _secret_get("AWS_SESSION_TOKEN", ""),
        "bedrock_region": _secret_get("BEDROCK_REGION", _secret_get("AGENTCORE_REGION", "us-west-2")),
    }
    if not aws_ctx["aws_access_key_id"] or not aws_ctx["aws_secret_access_key"]:
        aws_ctx = {}

    input_payload = {
        "user_query": runtime_query,
        "company": safe_company,
        "year": safe_year,
        "risks": safe_risks,
        "compare_data": safe_compare,
        "_aws": aws_ctx,
    }
    request_payload = {
        "company": safe_company,
        "year": safe_year,
        "user_query": runtime_query,
        "risks": safe_risks,
        "compare_data": safe_compare,
        "_aws": aws_ctx,
        "prompt": runtime_query,
        "input": input_payload,
        "body": json.dumps(input_payload, ensure_ascii=False, default=str),
    }

    kwargs = {
        "agentRuntimeArn": agent_runtime_arn,
        "runtimeSessionId": runtime_session_id,
        "contentType": "application/json",
        "accept": "application/json",
        "payload": json.dumps(request_payload, ensure_ascii=False, default=str).encode("utf-8"),
    }
    if qualifier.strip():
        kwargs["qualifier"] = qualifier.strip()

    resp = client.invoke_agent_runtime(**kwargs)
    text = _read_agentcore_response_text(resp)
    parsed = _extract_json_obj(text)
    if not isinstance(parsed, dict):
        parsed = {"executive_summary": text}

    report = _normalize_report_payload(
        parsed,
        company=company,
        year=year,
        user_query=user_query,
        mode_label="AgentCore Runtime",
    )
    report["runtime_session_id"] = resp.get("runtimeSessionId", runtime_session_id)
    report["agent_steps"] = [
        *report.get("agent_steps", []),
        f"AgentCore status: {resp.get('statusCode')}",
        f"Runtime session: {report['runtime_session_id']}",
    ]
    return report


def _norm_compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _extract_year_candidates(query: str) -> list[int]:
    years: list[int] = []
    for m in re.findall(r"\b20(1\d|2[0-6])\b", str(query or "")):
        y = int(f"20{m}")
        if y not in years:
            years.append(y)
    return years


def _company_match_in_query(query: str, company: str) -> bool:
    q = str(query or "")
    c = str(company or "")
    if not q or not c:
        return False
    if c.lower() in q.lower():
        return True
    return _norm_compact(c) in _norm_compact(q)


def _detect_companies(query: str, index: list[dict], ticker_map: dict) -> list[str]:
    companies = sorted({str(r.get("company", "")).strip() for r in index if str(r.get("company", "")).strip()})
    found: list[str] = []

    for company in companies:
        if _company_match_in_query(query, company) and company not in found:
            found.append(company)

    q_upper = str(query or "").upper()
    for company, ticker in (ticker_map or {}).items():
        tk = str(ticker or "").strip().upper()
        if tk and re.search(rf"\b{re.escape(tk)}\b", q_upper) and str(company) not in found:
            found.append(str(company))

    return found[:3]


def _latest_year_for_company(company: str, index: list[dict]) -> int | None:
    years = sorted(
        {
            int(r.get("year"))
            for r in index
            if str(r.get("company", "")).strip() == str(company).strip() and str(r.get("year", "")).isdigit()
        },
        reverse=True,
    )
    return years[0] if years else None


def _resolve_year_for_company(company: str, hinted_years: list[int], index: list[dict]) -> int:
    if hinted_years:
        return int(hinted_years[0])
    latest = _latest_year_for_company(company, index)
    if latest:
        return latest
    return int(datetime.utcnow().year - 1)


def _find_record_result(company: str, year: int, index: list[dict]) -> dict | None:
    comp = str(company).strip()
    yy = int(year)
    for rec in index:
        if (
            str(rec.get("company", "")).strip() == comp
            and int(rec.get("year", 0) or 0) == yy
            and str(rec.get("filing_type", "10-K")).upper() == "10-K"
        ):
            result = get_result(str(rec.get("record_id", "")))
            if isinstance(result, dict) and isinstance(result.get("risks"), list) and result.get("risks"):
                return {"record": rec, "result": result, "source": "local"}
    return None


def _ensure_filing_context(
    company: str,
    year: int,
    query: str,
    index: list[dict],
    ticker_map: dict,
) -> tuple[FilingContext | None, str]:
    existing = _find_record_result(company, year, index)
    if existing:
        return FilingContext(company=company, year=year, result=existing["result"], source="local"), ""

    boot = bootstrap_company_year_10k(
        company=company,
        year=year,
        ticker=str((ticker_map or {}).get(company, "") or ""),
        industry="Other",
        user_query=query,
    )
    if boot.get("status") != "ok":
        return None, str(boot.get("error", "Auto bootstrap failed."))

    result = boot.get("result")
    if not isinstance(result, dict) or not result.get("risks"):
        return None, "Bootstrap completed but no risk data was produced."

    return FilingContext(company=company, year=year, result=result, source="sec_bootstrap"), ""


def _needs_compare(query: str) -> bool:
    q = str(query or "").lower()
    return any(k in q for k in COMPARE_HINTS)


def _needs_yoy(query: str) -> bool:
    q = str(query or "").lower()
    return any(k in q for k in YOY_HINTS)


def _build_yoy_compare_data(
    *,
    company: str,
    year: int,
    current_result: dict,
    query: str,
    index: list[dict],
    ticker_map: dict,
) -> dict | None:
    if not _needs_yoy(query):
        return None

    prior_years = sorted(
        {
            int(r.get("year", 0) or 0)
            for r in index
            if str(r.get("company", "")).strip() == str(company).strip() and int(r.get("year", 0) or 0) < int(year)
        },
        reverse=True,
    )
    if not prior_years:
        return None

    prior_year = prior_years[0]
    prior_ctx, err = _ensure_filing_context(company, prior_year, query, index, ticker_map)
    if err or prior_ctx is None:
        return None

    return compare_risks(prior_ctx.result, current_result)


def _compose_assistant_content(report: dict, contexts: list[FilingContext]) -> str:
    answer = str(report.get("direct_answer", "") or "").strip()
    if not answer:
        answer = str(report.get("executive_summary", "") or "").strip()
    if not answer:
        answer = "I analyzed your request but no concise response was generated. Please refine the question."

    src_rows = [
        f"{ctx.company} {ctx.year} ({'local' if ctx.source == 'local' else 'auto-fetched'})"
        for ctx in contexts
    ]
    if src_rows:
        answer += "\n\nData used: " + " | ".join(src_rows)

    return answer


def _report_has_backend_error(report: dict) -> bool:
    summary = str(report.get("executive_summary", "") or "")
    direct = str(report.get("direct_answer", "") or "")
    text = f"{summary}\n{direct}"
    return any(x in text for x in (
        "Report generation encountered an error",
        "No module named 'boto3'",
        "Bedrock invoke failed",
    ))


def _fallback_companies_from_memory(query: str) -> list[str]:
    last_ctx = st.session_state.get("agent_last_contexts", [])
    if not isinstance(last_ctx, list) or not last_ctx:
        return []
    if _needs_compare(query):
        return [str(x.get("company", "")) for x in last_ctx[:2] if str(x.get("company", ""))]
    return [str(last_ctx[0].get("company", ""))] if str(last_ctx[0].get("company", "")) else []


def _execute_prompt(prompt: str, *, runtime_arn: str, runtime_qualifier: str) -> dict:
    index = load_index()
    ticker_map = load_company_ticker_map()

    companies = _detect_companies(prompt, index, ticker_map)
    hinted_years = _extract_year_candidates(prompt)

    if not companies:
        companies = _fallback_companies_from_memory(prompt)

    if not companies:
        helper = (
            "I couldn't identify a company from your message. "
            "Please include a company name, for example: `Analyze Tesla 2024 risks` or `Compare Apple vs NVIDIA in 2024`."
        )
        if _contains_cjk(prompt):
            helper = "我没有识别出公司名称。请在问题中包含公司名，例如：`分析 Tesla 2024 风险`。"
        return {"role": "assistant", "content": helper}

    if len(companies) > 2:
        companies = companies[:2]

    contexts: list[FilingContext] = []
    for company in companies:
        year = _resolve_year_for_company(company, hinted_years, index)
        ctx, err = _ensure_filing_context(company, year, prompt, index, ticker_map)
        if err:
            msg = f"I could not prepare data for `{company} {year}`.\n\nReason: {err}"
            if _contains_cjk(prompt):
                msg = f"无法为 `{company} {year}` 准备数据。\n\n原因：{err}"
            return {"role": "assistant", "content": msg}
        if ctx is not None:
            contexts.append(ctx)

    if not contexts:
        return {
            "role": "assistant",
            "content": "No usable filing context was prepared for this question.",
        }

    runtime_session_id = _ensure_runtime_session_id(st.session_state.get("agent_runtime_session_id", ""))

    if len(contexts) == 1:
        ctx = contexts[0]
        compare_data = _build_yoy_compare_data(
            company=ctx.company,
            year=ctx.year,
            current_result=ctx.result,
            query=prompt,
            index=index,
            ticker_map=ticker_map,
        )

        report = _invoke_agentcore_runtime(
            agent_runtime_arn=runtime_arn,
            qualifier=runtime_qualifier,
            runtime_session_id=runtime_session_id,
            company=ctx.company,
            year=ctx.year,
            user_query=prompt,
            risks=ctx.result.get("risks", []),
            compare_data=compare_data,
        )
        st.session_state["agent_runtime_session_id"] = _ensure_runtime_session_id(
            str(report.get("runtime_session_id", runtime_session_id))
        )

        content = _compose_assistant_content(report, contexts)
        if _report_has_backend_error(report):
            content = (
                "The backend returned an internal model/runtime error while generating the report. "
                "Please verify runtime dependencies and Bedrock permissions, then retry.\n\n"
                f"Raw summary: {str(report.get('executive_summary', ''))[:320]}"
            )
            if _contains_cjk(prompt):
                content = (
                    "后端在生成报告时返回内部错误。请检查 runtime 依赖与 Bedrock 权限后重试。\n\n"
                    f"原始摘要：{str(report.get('executive_summary', ''))[:320]}"
                )

        try:
            save_agent_report(
                company=ctx.company,
                year=ctx.year,
                filing_type="10-K",
                report_json=report,
            )
        except Exception:
            pass

        st.session_state["agent_last_contexts"] = [
            {"company": ctx.company, "year": ctx.year, "source": ctx.source}
        ]

        return {
            "role": "assistant",
            "content": content,
            "report": report,
            "contexts": st.session_state["agent_last_contexts"],
        }

    # cross-company compare
    a, b = contexts[0], contexts[1]
    cross = compare_risks(a.result, b.result)
    compare_prompt = (
        f"{prompt}\n\n"
        f"[Cross-company context]\n"
        f"Baseline company: {a.company} ({a.year})\n"
        f"Comparison company: {b.company} ({b.year})\n"
        f"Please explicitly contrast risk profile differences and practical implications."
    )

    report = _invoke_agentcore_runtime(
        agent_runtime_arn=runtime_arn,
        qualifier=runtime_qualifier,
        runtime_session_id=runtime_session_id,
        company=f"{a.company} vs {b.company}",
        year=min(a.year, b.year),
        user_query=compare_prompt,
        risks=b.result.get("risks", []),
        compare_data=cross,
    )
    st.session_state["agent_runtime_session_id"] = _ensure_runtime_session_id(
        str(report.get("runtime_session_id", runtime_session_id))
    )

    content = _compose_assistant_content(report, contexts)
    if _report_has_backend_error(report):
        content = (
            "The backend returned an internal model/runtime error while generating the cross-company report. "
            "Please verify runtime dependencies and retry.\n\n"
            f"Raw summary: {str(report.get('executive_summary', ''))[:320]}"
        )
        if _contains_cjk(prompt):
            content = (
                "后端在生成跨公司报告时返回内部错误。请检查 runtime 依赖后重试。\n\n"
                f"原始摘要：{str(report.get('executive_summary', ''))[:320]}"
            )

    try:
        save_agent_report(
            company=f"{a.company} vs {b.company}",
            year=min(a.year, b.year),
            filing_type="10-K",
            report_json=report,
        )
    except Exception:
        pass

    st.session_state["agent_last_contexts"] = [
        {"company": a.company, "year": a.year, "source": a.source},
        {"company": b.company, "year": b.year, "source": b.source},
    ]

    return {
        "role": "assistant",
        "content": content,
        "report": report,
        "contexts": st.session_state["agent_last_contexts"],
    }


def _enqueue_prompt(prompt: str) -> None:
    st.session_state["agent_prompt_queue"] = str(prompt or "").strip()


def _render_hero(runtime_missing: bool) -> None:
    st.markdown(
        """
        <div class="rl-hero">
            <span class="rl-tag">AI-Powered Risk Intelligence</span>
            <h1 class="rl-title">Understand Company Risks With One Question</h1>
            <p class="rl-subtitle">
              Ask naturally. The assistant identifies company and year automatically,
              fetches missing filings when needed, and answers with structured risk evidence.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if runtime_missing:
        st.markdown(
            '<div class="rl-warning">Runtime is not configured. Set `AGENTCORE_RUNTIME_ARN` in secrets.</div>',
            unsafe_allow_html=True,
        )


def _render_suggestions() -> None:
    st.markdown('<p class="rl-section">Suggested Prompts</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    for i, q in enumerate(SUGGESTED_QUERIES):
        with (c1 if i % 2 == 0 else c2):
            if st.button(q, key=f"agent_suggest_{i}", use_container_width=True):
                _enqueue_prompt(q)


def _render_report_details(report: dict, contexts: list[dict]) -> None:
    pm = report.get("priority_matrix", {}) if isinstance(report, dict) else {}
    high = int(pm.get("high", {}).get("count", 0) or 0)
    med = int(pm.get("medium", {}).get("count", 0) or 0)
    low = int(pm.get("low", {}).get("count", 0) or 0)
    rating = str(report.get("overall_risk_rating", "Unknown") or "Unknown")

    st.markdown(
        f"""
        <div class="rl-metric-row">
          <div class="rl-metric"><span class="k">Overall</span><span class="v">{rating}</span></div>
          <div class="rl-metric"><span class="k">High</span><span class="v">{high}</span></div>
          <div class="rl-metric"><span class="k">Medium</span><span class="v">{med}</span></div>
          <div class="rl-metric"><span class="k">Low</span><span class="v">{low}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if contexts:
        src = " | ".join(f"{c.get('company')} {c.get('year')} ({c.get('source')})" for c in contexts)
        st.markdown(f'<div class="rl-context"><strong>Context:</strong> {src}</div>', unsafe_allow_html=True)

    evidence = report.get("evidence", [])
    if isinstance(evidence, list) and evidence:
        st.markdown("**Evidence**")
        for ev in evidence[:6]:
            st.caption(f"- {str(ev)}")

    compare_insights = str(report.get("compare_insights", "") or "").strip()
    if compare_insights:
        st.markdown("**Compare Insights**")
        st.info(compare_insights)

    plan = report.get("planning", {})
    if isinstance(plan, dict) and plan:
        with st.expander("Planner + Trace", expanded=False):
            st.caption(f"Intent: {plan.get('intent', '—')}")
            st.caption(f"Reason: {plan.get('reason', '—')}")
            seq = plan.get("tool_sequence", [])
            if isinstance(seq, list) and seq:
                st.caption("Tools: " + " -> ".join(str(x) for x in seq))
            for step in report.get("agent_steps", [])[:20]:
                st.caption(f"· {str(step)}")


def _render_messages() -> None:
    for i, msg in enumerate(st.session_state.get("agent_chat_messages", [])):
        role = "assistant" if msg.get("role") != "user" else "user"
        with st.chat_message(role):
            st.markdown(str(msg.get("content", "")))
            report = msg.get("report")
            contexts = msg.get("contexts", [])
            if role == "assistant" and isinstance(report, dict):
                with st.expander("View structured details", expanded=False):
                    _render_report_details(report, contexts if isinstance(contexts, list) else [])
                st.download_button(
                    "Download This Reply (JSON)",
                    data=json.dumps(report, ensure_ascii=False, indent=2),
                    file_name=f"agent_reply_{i+1}.json",
                    mime="application/json",
                    key=f"agent_reply_dl_{i}",
                    use_container_width=False,
                )


def render() -> None:
    _inject_styles()
    _ensure_state()

    runtime_arn = _secret_get("AGENTCORE_RUNTIME_ARN", _secret_get("AGENTCORE_ARN", "")).strip()
    runtime_qualifier = _secret_get("AGENTCORE_QUALIFIER", _secret_get("AGENTCORE_RUNTIME_QUALIFIER", "")).strip()

    _render_hero(runtime_missing=(not runtime_arn))
    _render_suggestions()
    st.divider()

    _render_messages()

    queued = str(st.session_state.pop("agent_prompt_queue", "") or "").strip()
    prompt = queued or st.chat_input("Ask any risk question... e.g., Compare Apple vs NVIDIA risks in 2024")

    if prompt:
        user_msg = {"role": "user", "content": str(prompt).strip()}
        st.session_state["agent_chat_messages"].append(user_msg)

        if not runtime_arn:
            st.session_state["agent_chat_messages"].append(
                {
                    "role": "assistant",
                    "content": "Runtime is not configured yet. Set `AGENTCORE_RUNTIME_ARN` in secrets and retry.",
                }
            )
            st.rerun()

        with st.spinner("Analyzing your question..."):
            try:
                assistant_msg = _execute_prompt(
                    prompt=str(prompt).strip(),
                    runtime_arn=runtime_arn,
                    runtime_qualifier=runtime_qualifier,
                )
            except Exception as exc:
                assistant_msg = {
                    "role": "assistant",
                    "content": f"Execution failed: {type(exc).__name__}: {exc}",
                }

        st.session_state["agent_chat_messages"].append(copy.deepcopy(assistant_msg))
        st.session_state["agent_chat_messages"] = st.session_state["agent_chat_messages"][-30:]
        st.rerun()
