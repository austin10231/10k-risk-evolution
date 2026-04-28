"""Router-style chat agent with intent detection, tool dispatch, and lightweight memory."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, List

INTENTS = {
    "general_chat",
    "risk_analysis",
    "compare_risk",
    "stock_query",
    "news_query",
}

BUSINESS_INTENTS = {"risk_analysis", "compare_risk", "stock_query", "news_query"}


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


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _strip_markdown_artifacts(text: str) -> str:
    s = str(text or "")
    # remove common markdown emphasis markers while keeping content
    s = s.replace("**", "")
    s = s.replace("__", "")
    s = s.replace("`", "")
    s = s.replace("### ", "")
    s = s.replace("## ", "")
    s = s.replace("# ", "")
    return s.strip()


def _is_chinese_text(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _is_model_question(text: str) -> bool:
    q = _clean_text(text).lower()
    return any(
        k in q
        for k in (
            "你是什么模型",
            "你是啥模型",
            "什么大模型",
            "model",
            "llm",
            "bedrock",
            "nova",
            "gpt",
            "claude",
        )
    )


def _is_10k_topic(text: str) -> bool:
    q = _clean_text(text).lower()
    return any(
        k in q
        for k in (
            "10-k",
            "10k",
            "item 1a",
            "item1a",
            "risk factors",
            "md&a",
            "risk factor",
            "年报",
            "10-k报告",
            "10k报告",
            "风险披露",
            "风险因子",
        )
    )


def _looks_like_compare_request(text: str) -> bool:
    q = _clean_text(text).lower()
    return any(k in q for k in ("compare", "vs", "versus", "difference", "delta", "对比", "比较", "变化"))


def _looks_like_data_driven_10k_request(text: str) -> bool:
    q = _clean_text(text).lower()
    return any(
        k in q
        for k in (
            "基于",
            "根据",
            "这份",
            "该公司",
            "最新",
            "prioritize",
            "top risk",
            "critical risk",
            "评分",
            "优先级",
            "分析这份",
            "这个 filing",
            "this filing",
        )
    )


def _enforce_intent(intent: str, user_query: str, context: dict) -> str:
    q = _clean_text(user_query)
    has_risks = bool(context.get("has_risks"))
    has_compare_data = bool(context.get("has_compare_data"))
    is_10k = _is_10k_topic(q)
    wants_compare = _looks_like_compare_request(q)

    if _is_model_question(q):
        return "general_chat"

    if intent == "compare_risk":
        if wants_compare and (has_compare_data or is_10k):
            return "compare_risk"
        return "general_chat"

    if intent == "risk_analysis":
        # Only route to filing/risk tool when the query is clearly data-driven around 10-K context.
        if is_10k and (_looks_like_data_driven_10k_request(q) or has_risks):
            return "risk_analysis"
        return "general_chat"

    return intent


def _normalize_history(history: Any, max_items: int = 16) -> List[dict]:
    out: List[dict] = []
    if not isinstance(history, list):
        return out
    for row in history:
        if not isinstance(row, dict):
            continue
        role = _clean_text(row.get("role") or "").lower()
        text = _clean_text(row.get("text") or row.get("content") or "")
        if role not in {"user", "assistant"} or not text:
            continue
        out.append({"role": role, "text": text[:1200]})
    return out[-max_items:]


def _history_prompt(history: List[dict], max_items: int = 10) -> str:
    if not history:
        return "(none)"
    rows = history[-max_items:]
    return "\n".join([f"{x['role']}: {x['text']}" for x in rows])


def _fallback_intent(user_query: str) -> dict:
    q = _clean_text(user_query).lower()
    if _is_model_question(q):
        return {"intent": "general_chat", "confidence": 0.92, "reason": "keyword_fallback: model_identity"}
    if any(k in q for k in ("compare", "versus", "vs", "difference", "对比", "比较", "变化")):
        return {"intent": "compare_risk", "confidence": 0.72, "reason": "keyword_fallback: compare"}
    if any(k in q for k in ("stock", "ticker", "price", "share", "quote", "股价", "股票", "行情")):
        return {"intent": "stock_query", "confidence": 0.72, "reason": "keyword_fallback: stock"}
    if any(k in q for k in ("news", "headline", "article", "新闻", "头条", "报道")):
        return {"intent": "news_query", "confidence": 0.72, "reason": "keyword_fallback: news"}
    if _is_10k_topic(q) and _looks_like_data_driven_10k_request(q):
        return {"intent": "risk_analysis", "confidence": 0.68, "reason": "keyword_fallback: risk"}
    return {"intent": "general_chat", "confidence": 0.55, "reason": "keyword_fallback: default"}


def _classify_intent(user_query: str, history: List[dict], context: dict, llm_invoke: Callable[[str, int], str]) -> dict:
    q = _clean_text(user_query)
    if not q:
        return {"intent": "general_chat", "confidence": 0.1, "reason": "empty_query"}

    prompt = f"""You are an intent router for a financial risk assistant.

Allowed intents:
- general_chat
- risk_analysis
- compare_risk
- stock_query
- news_query

Routing rules:
- Use `risk_analysis` only for filing-data-driven 10-K analysis requests (for example: prioritize risks in this filing).
- Use `compare_risk` only for explicit risk delta/comparison requests.
- Conceptual or educational questions (even about 10-K concepts) should stay in `general_chat`.
- If user asks about model identity/capability, use `general_chat`.

Conversation history (recent):
{_history_prompt(history, max_items=8)}

Current user query:
{q}

Current context JSON:
{json.dumps(context or {{}}, ensure_ascii=False)}

Return ONLY JSON:
{{
  "intent": "one allowed intent",
  "confidence": 0.0,
  "reason": "short reason"
}}"""

    try:
        out = _extract_json_obj(llm_invoke(prompt, 300))
        if isinstance(out, dict):
            intent = _clean_text(out.get("intent"))
            if intent in INTENTS:
                confidence = out.get("confidence", 0.0)
                try:
                    confidence_f = float(confidence)
                except Exception:
                    confidence_f = 0.0
                confidence_f = max(0.0, min(1.0, confidence_f))
                routed_intent = _enforce_intent(intent, q, context or {})
                reason = _clean_text(out.get("reason") or "llm_intent")
                if routed_intent != intent:
                    reason = f"{reason}; overridden={routed_intent}"
                return {
                    "intent": routed_intent,
                    "confidence": confidence_f,
                    "reason": reason,
                }
    except Exception:
        pass

    fb = _fallback_intent(q)
    fb["intent"] = _enforce_intent(str(fb.get("intent") or "general_chat"), q, context or {})
    return fb


def _general_chat_answer(
    user_query: str,
    history: List[dict],
    context: dict,
    llm_invoke: Callable[[str, int], str],
) -> str:
    model_id = _clean_text((context or {}).get("model_id")) or "us.amazon.nova-pro-v1:0"
    prompt = f"""You are a helpful assistant similar to ChatGPT.
You are RiskLens AI assistant.
Current model backend: Amazon Bedrock model `{model_id}`.
Style requirements:
- Be natural, warm, and concise.
- Answer in the same language as the user.
- If user asks conceptual 10-K questions (like Risk Factors vs MD&A), explain clearly with practical framing.
- Do not sound robotic or refuse being an LLM when asked; answer directly and honestly.

Conversation history (recent):
{_history_prompt(history, max_items=10)}

Context JSON:
{json.dumps(context or {{}}, ensure_ascii=False)}

User query:
{_clean_text(user_query)}

Write a direct, concise answer in the user's language.
Do not output JSON."""
    try:
        text = _clean_text(llm_invoke(prompt, 900))
        if text:
            return text
    except Exception:
        pass
    return "I can help with general questions and workflow tasks. Tell me what you want to do next."


def _model_identity_answer(user_query: str, context: dict) -> str:
    model_id = _clean_text((context or {}).get("model_id")) or "us.amazon.nova-pro-v1:0"
    if _is_chinese_text(user_query):
        return (
            f"我是 RiskLens AI 助手，底层会调用 Amazon Bedrock 的 `{model_id}`（Nova Pro）来生成回答。"
            "所以这里是有大模型推理的，不只是规则系统。"
            "如果你希望切到 Nova Lite，我也可以帮你把配置改成 Lite。"
        )
    return (
        f"I’m RiskLens AI, and I generate responses through Amazon Bedrock using `{model_id}` (Nova Pro). "
        "So this chat is backed by an LLM, not only rule logic. "
        "If you prefer Nova Lite, I can help switch the config."
    )


def _normalize_response(response: Any) -> dict:
    if isinstance(response, dict):
        typ = _clean_text(response.get("type")).lower()
        if typ == "action":
            action = _clean_text(response.get("action") or "navigate") or "navigate"
            target = _clean_text(response.get("target") or "")
            params = response.get("params") if isinstance(response.get("params"), dict) else {}
            message = _strip_markdown_artifacts(_clean_text(response.get("message") or ""))
            return {
                "type": "action",
                "action": action,
                "target": target,
                "params": params,
                "message": message or "I found a relevant business module.",
            }
        if typ == "text":
            content = _strip_markdown_artifacts(_clean_text(response.get("content") or ""))
            return {"type": "text", "content": content or "No content returned."}

    if isinstance(response, str):
        content = _strip_markdown_artifacts(_clean_text(response))
        return {"type": "text", "content": content or "No content returned."}

    return {"type": "text", "content": "No content returned."}


def run_chat_agent(
    *,
    user_query: str,
    history: Any,
    context: dict,
    llm_invoke: Callable[[str, int], str],
    tools: Dict[str, Callable[..., dict]],
) -> dict:
    started = time.time()
    query = _clean_text(user_query)
    memory = _normalize_history(history)
    ctx = dict(context or {})

    tool_trace: List[dict] = []

    if _is_model_question(query):
        response = {"type": "text", "content": _model_identity_answer(query, ctx)}
        normalized_response = _normalize_response(response)
        reply_text = _clean_text(normalized_response.get("content"))
        return {
            "agent_version": "router_v2",
            "intent": "general_chat",
            "intent_confidence": 0.95,
            "intent_reason": "rule: model_identity",
            "response": normalized_response,
            "tool_payload": {},
            "memory": {
                "turns_used": len(memory),
                "recent_history": memory[-8:],
            },
            "tool_trace": [{"tool": "general_chat", "status": "ok", "note": "model identity direct answer"}],
            "direct_answer": reply_text,
            "executive_summary": reply_text,
            "runtime_ms": int((time.time() - started) * 1000),
        }

    intent_meta = _classify_intent(query, memory, ctx, llm_invoke=llm_invoke)
    intent = intent_meta.get("intent", "general_chat")

    response: dict | None = None
    tool_payload: dict = {}
    risk_report: dict = {}

    if intent in BUSINESS_INTENTS:
        fn = tools.get(intent)
        if callable(fn):
            try:
                out = fn(query=query, history=memory, context=ctx) or {}
                if isinstance(out, dict):
                    response = _normalize_response(out.get("response"))
                    tool_payload = out.get("tool_payload") if isinstance(out.get("tool_payload"), dict) else {}
                    rr = out.get("risk_report")
                    if isinstance(rr, dict):
                        risk_report = rr
                    tool_trace.append({"tool": intent, "status": "ok"})
                else:
                    tool_trace.append({"tool": intent, "status": "error", "note": "tool did not return dict"})
            except Exception as exc:
                tool_trace.append({"tool": intent, "status": "error", "note": str(exc)})
                response = {"type": "text", "content": f"Tool execution failed: {type(exc).__name__}: {exc}"}
        else:
            tool_trace.append({"tool": intent, "status": "error", "note": "tool not configured"})
            response = {"type": "text", "content": "This business module is not configured yet."}

    if response is None:
        intent = "general_chat"
        text = _general_chat_answer(query, memory, ctx, llm_invoke=llm_invoke)
        response = {"type": "text", "content": text}
        tool_trace.append({"tool": "general_chat", "status": "ok"})

    normalized_response = _normalize_response(response)
    reply_text = (
        _clean_text(normalized_response.get("content"))
        if normalized_response.get("type") == "text"
        else _clean_text(normalized_response.get("message"))
    )

    out = {
        "agent_version": "router_v2",
        "intent": intent,
        "intent_confidence": float(intent_meta.get("confidence", 0.0) or 0.0),
        "intent_reason": _clean_text(intent_meta.get("reason") or ""),
        "response": normalized_response,
        "tool_payload": tool_payload,
        "memory": {
            "turns_used": len(memory),
            "recent_history": memory[-8:],
        },
        "tool_trace": tool_trace,
        "direct_answer": reply_text,
        "executive_summary": reply_text,
        "runtime_ms": int((time.time() - started) * 1000),
    }

    if isinstance(risk_report, dict):
        # Keep compatibility with existing UI that expects priority fields for risk workflows.
        out.update(risk_report)
        out["response"] = normalized_response
        out["intent"] = intent
        out["intent_confidence"] = float(intent_meta.get("confidence", 0.0) or 0.0)
        out["intent_reason"] = _clean_text(intent_meta.get("reason") or "")
        out["tool_payload"] = tool_payload
        out["memory"] = {
            "turns_used": len(memory),
            "recent_history": memory[-8:],
        }
        out["tool_trace"] = tool_trace
        out["direct_answer"] = reply_text or _clean_text(risk_report.get("direct_answer") or risk_report.get("executive_summary"))
        out["executive_summary"] = _clean_text(risk_report.get("executive_summary") or out["direct_answer"])

    return out
