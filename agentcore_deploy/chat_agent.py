"""ReAct multi-step chat agent.

Replaces the router_v2 intent-classification flow with a Bedrock Converse
``toolUse`` loop. The LLM (AGENT_MODEL_ID, defaults to deepseek.v3-v1:0)
chooses tools, the runtime executes them, and we feed results back until
the LLM produces a tool-free text turn or hits the iteration cap.

Public entrypoint ``run_chat_agent`` keeps the same return-shape contract
as router_v2 (so main.py and the frontend don't need to change), but the
internal logic is fully replaced. See AGENT_UPGRADE_PLAN.md §3 for the
loop spec and §6 for guardrail constants.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, Callable, Dict, List

# ── ReAct loop guardrails (AGENT_UPGRADE_PLAN.md §6) ─────────────────────────
MAX_ITER = 6
TOOL_RESULT_MAX_CHARS = 16000        # ≈ 4000 tokens
CONTEXT_BUDGET_CHARS = 400000        # ≈ 100K tokens

ALLOWED_REPLY_LANGS = {"zh", "en"}
SPANISH_HINT_WORDS = {
    "el", "la", "los", "las", "de", "del", "que", "por", "para", "con", "sin", "una", "uno",
    "como", "pero", "muy", "más", "sus", "sobre", "entre", "cuando", "donde", "porque", "hola",
    "gracias", "buenos", "buenas", "usted", "ustedes", "hoy", "mañana", "riesgo", "noticias",
}


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


def _word_tokens(text: str) -> List[str]:
    return [x.lower() for x in re.findall(r"[A-Za-zÀ-ÿ']+", str(text or ""))]


def _contains_explicit_en_request(text: str) -> bool:
    q = _clean_text(text).lower()
    return any(
        x in q
        for x in (
            "in english",
            "reply in english",
            "speak english",
            "use english",
            "answer in english",
            "respond in english",
            "英文",
            "英语",
        )
    )


def _contains_explicit_zh_request(text: str) -> bool:
    q = _clean_text(text).lower()
    return any(
        x in q
        for x in (
            "in chinese",
            "reply in chinese",
            "speak chinese",
            "use chinese",
            "answer in chinese",
            "respond in chinese",
            "请用中文",
            "用中文",
            "中文回答",
            "中文回复",
            "汉语",
            "中文",
        )
    )


def _detect_target_lang(user_query: str, history: List[dict], context: dict) -> str:
    q = _clean_text(user_query)
    if _contains_explicit_zh_request(q):
        return "zh"
    if _contains_explicit_en_request(q):
        return "en"
    if _is_chinese_text(q):
        return "zh"
    if q:
        return "en"

    for row in reversed(history or []):
        if not isinstance(row, dict):
            continue
        if _clean_text(row.get("role")).lower() != "user":
            continue
        t = _clean_text(row.get("text"))
        if not t:
            continue
        if _contains_explicit_zh_request(t):
            return "zh"
        if _contains_explicit_en_request(t):
            return "en"
        if _is_chinese_text(t):
            return "zh"
        return "en"

    preferred = _clean_text((context or {}).get("preferred_lang")).lower()
    return preferred if preferred in ALLOWED_REPLY_LANGS else "en"


def _is_spanish_like(text: str) -> bool:
    t = _clean_text(text).lower()
    if not t:
        return False
    accent_hits = len(re.findall(r"[áéíóúñ¿¡]", t))
    if accent_hits >= 2:
        return True
    tokens = _word_tokens(t)
    if len(tokens) < 6:
        return False
    hits = sum(1 for tok in tokens if tok in SPANISH_HINT_WORDS)
    return hits >= 3 and (hits / max(1, len(tokens))) >= 0.18


def _looks_like_target_lang(text: str, target_lang: str) -> bool:
    t = _clean_text(text)
    if not t:
        return True
    if target_lang == "zh":
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", t))
        latin_count = len(re.findall(r"[A-Za-z]", t))
        if cjk_count >= 1:
            return True
        if latin_count <= 4 and len(t) <= 8:
            return True
        return False
    if target_lang == "en":
        if _is_chinese_text(t):
            return False
        if _is_spanish_like(t):
            return False
        return True
    return True


def _rewrite_in_language(
    text: str,
    target_lang: str,
    user_query: str,
    llm_invoke: Callable[[str, int], str],
) -> str:
    source = _clean_text(text)
    if not source:
        return source
    lang_label = "Simplified Chinese" if target_lang == "zh" else "English"
    prompt = f"""Rewrite the answer in {lang_label} only.
Rules:
- Keep the same meaning and facts.
- Keep tickers, company names, and numbers unchanged.
- Do not use Spanish or any third language.
- Output plain text only.

User query:
{_clean_text(user_query)}

Answer:
{source}
"""
    try:
        rewritten = _clean_text(llm_invoke(prompt, 700))
        if rewritten:
            return _strip_markdown_artifacts(rewritten)
    except Exception:
        pass
    return _strip_markdown_artifacts(source)


def _enforce_output_language(
    text: str,
    target_lang: str,
    user_query: str,
    llm_invoke: Callable[[str, int], str],
) -> str:
    cleaned = _strip_markdown_artifacts(_clean_text(text))
    if not cleaned:
        return cleaned
    if target_lang not in ALLOWED_REPLY_LANGS:
        return cleaned
    if _looks_like_target_lang(cleaned, target_lang):
        return cleaned
    rewritten = _rewrite_in_language(cleaned, target_lang, user_query, llm_invoke=llm_invoke)
    if rewritten and _looks_like_target_lang(rewritten, target_lang):
        return rewritten
    return cleaned


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


def _general_chat_answer(
    user_query: str,
    history: List[dict],
    context: dict,
    target_lang: str,
    llm_invoke: Callable[[str, int], str],
) -> str:
    model_id = _clean_text((context or {}).get("model_id")) or "deepseek.v3-v1:0"
    lang_rule = "Simplified Chinese" if target_lang == "zh" else "English"
    prompt = f"""You are a helpful assistant similar to ChatGPT.
You are RiskLens AI assistant.
Current model backend: Amazon Bedrock model `{model_id}`.
Style requirements:
- Be natural, warm, and concise.
- You must answer in {lang_rule} only.
- Do not use Spanish or any third language.
- If user asks conceptual 10-K questions (like Risk Factors vs MD&A), explain clearly with practical framing.
- Do not sound robotic or refuse being an LLM when asked; answer directly and honestly.

Conversation history (recent):
{_history_prompt(history, max_items=10)}

Context JSON:
{json.dumps(context or {{}}, ensure_ascii=False)}

User query:
{_clean_text(user_query)}

Write a direct, concise answer in {lang_rule}.
Do not output JSON."""
    try:
        text = _clean_text(llm_invoke(prompt, 900))
        if text:
            return text
    except Exception:
        pass
    return "I can help with general questions and workflow tasks. Tell me what you want to do next."


def _model_identity_answer(user_query: str, context: dict) -> str:
    model_id = _clean_text((context or {}).get("model_id")) or "deepseek.v3-v1:0"
    extraction_id = _clean_text((context or {}).get("extraction_model_id")) or "us.amazon.nova-pro-v1:0"
    if _is_chinese_text(user_query):
        return (
            f"我是 RiskLens AI 助手。这次对话由 Amazon Bedrock 上的 `{model_id}`（DeepSeek V3.2）生成回复；"
            f"风险因子提取、分类与 RPI 评分则走 `{extraction_id}`（Amazon Nova Pro）。"
            "所以这里是有大模型推理的，不只是规则系统。"
            "如果想换成别的 Bedrock 模型，我可以帮你改 `BEDROCK_AGENT_MODEL_ID` / `BEDROCK_EXTRACTION_MODEL_ID` 配置。"
        )
    return (
        f"I’m RiskLens AI. This chat reply comes from Amazon Bedrock model `{model_id}` (DeepSeek V3.2); "
        f"the extraction / classification / RPI scoring path uses `{extraction_id}` (Amazon Nova Pro). "
        "So this chat is backed by an LLM, not only rule logic. "
        "If you prefer a different Bedrock model, I can help switch `BEDROCK_AGENT_MODEL_ID` / `BEDROCK_EXTRACTION_MODEL_ID`."
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


def _build_react_system_prompt(
    context: dict,
    available_companies_summary: str,
    target_lang: str,
) -> str:
    """Render the ReAct system prompt. ``available_companies_summary`` should
    be a short newline-separated string built by the caller (typically from
    ``list_available_companies`` invoked once before the loop)."""
    lang_label = "Simplified Chinese" if target_lang == "zh" else "English"
    ctx = context or {}
    sel_company = _clean_text(ctx.get("company"))
    sel_year = ctx.get("year")
    sel_ticker = _clean_text(ctx.get("ticker"))
    has_risks = bool(ctx.get("has_risks"))
    risk_count = ctx.get("risk_count")
    has_compare = bool(ctx.get("has_compare_data"))

    lines = [
        "You are RiskLens AI, a multi-step research assistant for SEC 10-K risk factor analysis.",
        f"You can call up to {MAX_ITER} tool calls before producing a final answer.",
        "",
        "== USER CONTEXT ==",
        f"Currently selected filing:",
        f"  - Company: {sel_company or '(none)'}",
        f"  - Year:    {sel_year or '(none)'}",
        f"  - Ticker:  {sel_ticker or '(none)'}",
        f"Data already loaded for this filing:",
        f"  - has_risks:        {has_risks}",
        f"  - risk_count:       {risk_count if risk_count is not None else 0}",
        f"  - has_compare_data: {has_compare}",
        "",
        "== AVAILABLE DATA (from the system index) ==",
        available_companies_summary or "(no data available; offer to upload a 10-K)",
        "",
        "== BEHAVIOR RULES ==",
        "1. NEVER fabricate risk factors, scores, or company data. If a tool returns no data or an `error` field, tell the user honestly and suggest what they could do (upload, pick a different year, etc.).",
        "2. When citing a specific risk, include the exact title (or first 12 words) from the tool result. Do not paraphrase risk titles.",
        "3. The preloaded AVAILABLE DATA may be truncated. Before saying a company is unavailable, you MUST call list_available_companies (or load_company_risks directly) to verify.",
        "4. For comparison questions, prefer compare_risks (one call) over two separate load_company_risks calls.",
        "5. Keep tool calls minimal — never call the same tool twice with the same input. If you already have the data, use it.",
        "6. For stock market / price / trading questions, call stock_quote first before answering. Do not claim market features are unavailable unless stock_quote explicitly returns an error.",
        "7. For headline / media / breaking-news questions, call fetch_news first before answering. Do not claim news features are unavailable unless fetch_news explicitly returns an error.",
        "8. For metadata questions (industry, ticker, record_id, available years), call load_company_risks or list_available_companies and answer from tool output. Do not say 'cannot query' if tools are available.",
        "9. Never fabricate sample JSON/tool outputs. If user asks for fields like auto_fetch_attempt, only show fields observed in actual tool results from this conversation.",
        "10. For capability questions like '会不会自动去SEC拉取', answer policy first from tool contract: missing company/year triggers SEC auto-fetch attempt. Then clarify whether the specific example was already in local index (retrieval_mode=existing_index) or fetched now (retrieval_mode=sec_auto_fetch).",
        f"11. Respond in {lang_label} only. If the user wrote in Chinese, answer in Chinese; otherwise English.",
        "12. The dashboard's Risk Priority Index (RPI, 0-100) is weighted from three per-risk dimensions (Financial Impact, Likelihood, Urgency) into High/Medium/Low buckets. Mention this only if the user asks how scoring works.",
        "",
        "When you have enough information, write a final natural-language answer (no JSON, no tool_use blocks). Final answer should be 3-7 sentences plus optional bullet evidence.",
    ]
    return "\n".join(lines)


def _seed_messages(history: List[dict], user_query: str, max_history: int = 10) -> List[dict]:
    """Build the initial ``messages`` list for Bedrock Converse. Drops empty
    turns, caps at ``max_history`` recent rows, ensures the conversation
    ends with the current user query, and guarantees the first message is
    a user turn (Bedrock rejects 400 otherwise)."""
    out: List[dict] = []
    for h in (history or [])[-max_history:]:
        if not isinstance(h, dict):
            continue
        role = _clean_text(h.get("role")).lower()
        text = _clean_text(h.get("text") or h.get("content"))
        if role not in ("user", "assistant") or not text:
            continue
        out.append({"role": role, "content": [{"text": text}]})
    out.append({"role": "user", "content": [{"text": _clean_text(user_query)}]})
    while out and out[0]["role"] != "user":
        out.pop(0)
    return out


def _approx_chars(messages: List[dict]) -> int:
    """Rough byte-budget estimator. Walks content blocks and sums ``text``
    string lengths plus serialized JSON length for tool-shaped blocks.
    Coarse — we don't need a real tokenizer; the budget is set with
    ~20% headroom anyway (AGENT_UPGRADE_PLAN.md §6)."""
    total = 0
    for m in messages or []:
        content = m.get("content") if isinstance(m, dict) else None
        if not isinstance(content, list):
            continue
        for b in content:
            if not isinstance(b, dict):
                continue
            if "text" in b:
                total += len(str(b.get("text") or ""))
            else:
                try:
                    total += len(json.dumps(b, ensure_ascii=False, default=str))
                except Exception:
                    total += 256
    return total


def _serialize_tool_result(payload: Any, max_chars: int = TOOL_RESULT_MAX_CHARS) -> dict:
    """Convert a handler dict into a Bedrock Converse ``toolResult.content``
    block, with per-result size cap. Returns ``{block, status}`` where
    ``status`` is ``"success"`` or ``"error"``."""
    is_error = isinstance(payload, dict) and "error" in payload
    try:
        as_json = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        as_json = json.dumps({"error": "serialize_failed"})

    if len(as_json) <= max_chars:
        if isinstance(payload, (dict, list)):
            block = {"json": payload}
        else:
            block = {"text": as_json}
    else:
        block = {"text": as_json[:max_chars] + '..."(truncated)"'}

    return {"block": block, "status": "error" if is_error else "success"}


def _force_finalize(
    messages: List[dict],
    tool_trace: List[dict],
    target_lang: str,
    llm_invoke: Callable[[str, int], str],
) -> str:
    """Synthesize a fallback summary when the loop runs out of iterations
    without a tool-free text turn. Surfaces the last assistant text block
    if any, otherwise asks the LLM (text-only) to summarize the partial
    tool trace honestly."""
    last_text = ""
    for m in reversed(messages or []):
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        for b in m.get("content", []) or []:
            if isinstance(b, dict) and b.get("text"):
                last_text = _clean_text(b["text"])
                break
        if last_text:
            break

    lang_label = "Simplified Chinese" if target_lang == "zh" else "English"
    summary_prompt = (
        f"After {MAX_ITER} reasoning steps without a final answer, summarize what was learned "
        f"from the tool calls below in 3-4 sentences. Be honest if the data is insufficient. "
        f"Reply in {lang_label} only.\n\n"
        f"Tool trace (most recent first):\n{json.dumps(list(reversed(tool_trace[-4:])), ensure_ascii=False, default=str)}"
    )
    try:
        synthesized = _clean_text(llm_invoke(summary_prompt, 600))
        if synthesized:
            return synthesized
    except Exception:
        pass
    if last_text:
        return last_text
    return (
        "我已经查了多次工具但还没拿到能直接回答你的数据。可以换个更具体的问题再试一次。"
        if target_lang == "zh"
        else "I tried several tools but didn't reach a definitive answer. Please rephrase or narrow the question."
    )


def _extract_response_text(content_blocks: List[dict]) -> str:
    """Concat all ``text`` blocks from a Converse assistant message."""
    parts: List[str] = []
    for b in content_blocks or []:
        if isinstance(b, dict) and isinstance(b.get("text"), str):
            t = _clean_text(b["text"])
            if t:
                parts.append(t)
    return "\n".join(parts).strip()


def run_chat_agent(
    *,
    user_query: str,
    history: Any,
    context: dict,
    llm_invoke: Callable[[str, int], str],
    llm_invoke_with_tools: Callable[..., dict],
    tools: Dict[str, Callable[..., dict]],
    tool_specs: List[dict],
    available_companies_summary: str = "",
) -> dict:
    started = time.time()
    query = _clean_text(user_query)
    memory = _normalize_history(history)
    ctx = dict(context or {})
    target_lang = _detect_target_lang(query, memory, ctx)
    ctx["preferred_lang"] = target_lang

    # Preserve the model-identity short-circuit — direct rule-based reply,
    # no ReAct loop, saves 1-2 LLM calls and shows the dual-model split
    # without the LLM hallucinating about it.
    if _is_model_question(query):
        response = {"type": "text", "content": _model_identity_answer(query, ctx)}
        normalized_response = _normalize_response(response)
        reply_text = _enforce_output_language(
            _clean_text(normalized_response.get("content")),
            target_lang,
            query,
            llm_invoke=llm_invoke,
        )
        normalized_response["content"] = reply_text
        return {
            "agent_version": "react_v1",
            "intent": "general_chat",
            "intent_confidence": 1.0,
            "intent_reason": "rule: model_identity",
            "response": normalized_response,
            "tool_payload": {},
            "memory": {
                "turns_used": len(memory),
                "recent_history": memory[-8:],
                "preferred_lang": target_lang,
            },
            "tool_trace": [{"step": 0, "tool": "general_chat", "status": "ok", "note": "model identity direct answer"}],
            "direct_answer": reply_text,
            "executive_summary": reply_text,
            "runtime_ms": int((time.time() - started) * 1000),
        }

    system_prompt = _build_react_system_prompt(ctx, available_companies_summary, target_lang)
    messages = _seed_messages(memory, query)

    tool_trace: List[dict] = []
    tool_payload_agg: Dict[str, Any] = {}
    risk_report: Dict[str, Any] = {}
    final_text = ""
    final_reason = "loop_completed"
    iterations = 0
    system_overhead = len(system_prompt)

    for step in range(MAX_ITER):
        iterations = step + 1
        if _approx_chars(messages) + system_overhead > CONTEXT_BUDGET_CHARS:
            tool_trace.append({"step": step, "status": "context_budget_exceeded"})
            final_reason = "context_budget_exceeded"
            break

        try:
            resp = llm_invoke_with_tools(
                system=system_prompt,
                messages=messages,
                tool_specs=tool_specs,
                max_tokens=2000,
            )
        except Exception as exc:
            tool_trace.append({"step": step, "status": "llm_call_failed", "error": f"{type(exc).__name__}: {exc}"})
            final_reason = "llm_call_failed"
            break

        content_blocks = list(resp.get("contentBlocks", []) or [])
        tool_uses = [b for b in content_blocks if isinstance(b, dict) and "toolUse" in b]
        text_only = _extract_response_text(content_blocks)
        stop_reason = _clean_text(resp.get("stopReason"))

        # Bedrock requires the assistant turn to be appended exactly as
        # received (preserving toolUse blocks) so the next user turn's
        # toolResult IDs align.
        messages.append({"role": "assistant", "content": content_blocks})

        if not tool_uses:
            final_text = text_only
            final_reason = f"final_text(stop={stop_reason or 'end_turn'})"
            tool_trace.append({"step": step, "status": "final_text", "stop_reason": stop_reason})
            break

        tool_result_blocks: List[dict] = []
        for tu_block in tool_uses:
            tu = tu_block.get("toolUse") if isinstance(tu_block, dict) else {}
            tu = tu if isinstance(tu, dict) else {}
            tool_name = _clean_text(tu.get("name"))
            tool_use_id = _clean_text(tu.get("toolUseId")) or f"tu_{uuid.uuid4().hex[:8]}"
            raw_input = tu.get("input")
            tool_input = raw_input if isinstance(raw_input, dict) else {}

            handler = tools.get(tool_name) if tool_name else None
            if not callable(handler):
                payload: Any = {"error": f"unknown_tool:{tool_name or '<missing>'}"}
            else:
                try:
                    payload = handler(**tool_input)
                except TypeError as exc:
                    # Bad input shape from the LLM (extra keys, wrong types).
                    payload = {"error": f"bad_tool_input:{type(exc).__name__}: {exc}"}
                except Exception as exc:
                    payload = {"error": f"{type(exc).__name__}: {exc}"}

            serialized = _serialize_tool_result(payload, max_chars=TOOL_RESULT_MAX_CHARS)
            tool_result_blocks.append({
                "toolResult": {
                    "toolUseId": tool_use_id,
                    "content": [serialized["block"]],
                    "status": serialized["status"],
                }
            })

            # Aggregate for the response payload. Last write wins per tool name —
            # rich enough for the frontend's existing tool_payload reader.
            if isinstance(payload, dict):
                tool_payload_agg[tool_name] = payload
                # Keep the most recent risk-shaped result for backward-compat
                # so legacy frontend code that reads `risk_report.priority_matrix`
                # still has something to render.
                if tool_name in ("load_company_risks", "compare_risks") and not payload.get("error"):
                    risk_report = payload

            try:
                output_preview = json.dumps(payload, ensure_ascii=False, default=str)[:300]
            except Exception:
                output_preview = str(payload)[:300]
            tool_trace.append({
                "step": step,
                "tool": tool_name,
                "status": serialized["status"],
                "input": tool_input,
                "output_preview": output_preview,
            })

        messages.append({"role": "user", "content": tool_result_blocks})

    if not final_text:
        final_text = _force_finalize(messages, tool_trace, target_lang, llm_invoke)
        if final_reason == "loop_completed":
            final_reason = "hit_max_iter"

    final_text = _enforce_output_language(final_text, target_lang, query, llm_invoke=llm_invoke)
    normalized_response = _normalize_response({"type": "text", "content": final_text})
    reply_text = _clean_text(normalized_response.get("content"))

    out = {
        "agent_version": "react_v1",
        "intent": "react_multi_step",
        "intent_confidence": 1.0,
        "intent_reason": f"react: {final_reason} ({iterations}/{MAX_ITER} step(s))",
        "response": normalized_response,
        "tool_payload": tool_payload_agg,
        "memory": {
            "turns_used": len(memory),
            "recent_history": memory[-8:],
            "preferred_lang": target_lang,
        },
        "tool_trace": tool_trace,
        "direct_answer": reply_text,
        "executive_summary": reply_text,
        "runtime_ms": int((time.time() - started) * 1000),
    }

    if risk_report:
        # Backward-compat: surface the last risk-shaped tool result at the top
        # level so the legacy UI keeps reading `priority_matrix` etc. The
        # ReAct text answer still wins for `direct_answer`/`executive_summary`.
        for k, v in risk_report.items():
            if k not in out:
                out[k] = v
        out["risk_report"] = risk_report

    return out
