"""Floating draggable chat widget (Nova Pro), isolated from page layout."""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from core.bedrock import MODEL_ID, _invoke


def _ensure_state() -> None:
    if "rl_chat_messages" not in st.session_state:
        st.session_state["rl_chat_messages"] = [
            {
                "role": "assistant",
                "content": (
                    "Hi, I am your RiskLens helper. Ask me about risk analysis, "
                    "dashboard, compare, stock, or agent features."
                ),
            }
        ]
    if "rl_chat_bridge_input" not in st.session_state:
        st.session_state["rl_chat_bridge_input"] = ""
    if "rl_chat_reset_bridge_input" not in st.session_state:
        st.session_state["rl_chat_reset_bridge_input"] = False
    if "rl_chat_last_send_token" not in st.session_state:
        st.session_state["rl_chat_last_send_token"] = ""
    # Safe reset: only touch widget-bound key before the widget is instantiated.
    if st.session_state.get("rl_chat_reset_bridge_input"):
        st.session_state["rl_chat_bridge_input"] = ""
        st.session_state["rl_chat_reset_bridge_input"] = False


def _get_query_param(name: str) -> str:
    try:
        val = st.query_params.get(name, "")
        if isinstance(val, list):
            return str(val[0] if val else "")
        return str(val or "")
    except Exception:
        return ""


def _clear_chat_query_params() -> None:
    for key in ("rl_chat_msg", "rl_chat_send_token"):
        try:
            if key in st.query_params:
                del st.query_params[key]
        except Exception:
            pass


def _chat_reply_with_nova(current_page: str, user_message: str) -> str:
    history = st.session_state.get("rl_chat_messages", [])
    history_lines = []
    for msg in history[-8:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        text = str(msg.get("content", "") or "").strip()
        if text:
            history_lines.append(f"{role}: {text[:800]}")
    history_text = "\n".join(history_lines)

    prompt = f"""You are RiskLens Assistant running inside the RiskLens Streamlit app.
Current page: {current_page}
Model: {MODEL_ID}

You help users with:
1) How to use this app's pages (Upload, Library, Dashboard, Stock, Compare, Agent)
2) Interpreting risk outputs, scores, trends, and market overlays
3) Troubleshooting common usage issues in plain language

Rules:
- Be concise and practical.
- Prefer actionable steps.
- If uncertain, state uncertainty clearly and suggest what to check.
- Do not invent data the app has not shown.

Recent conversation:
{history_text}

User question:
{user_message}

Answer directly."""
    return _invoke(prompt, max_tokens=700)


def _handle_bridge_events(current_page: str, send_clicked: bool, clear_clicked: bool) -> None:
    if clear_clicked:
        st.session_state["rl_chat_messages"] = [
            {
                "role": "assistant",
                "content": "Chat cleared. Ask me anything about your RiskLens workflow.",
            }
        ]
        st.session_state["rl_chat_reset_bridge_input"] = True
        st.rerun()

    if send_clicked:
        msg = str(st.session_state.get("rl_chat_bridge_input", "") or "").strip()
        qp_msg = _get_query_param("rl_chat_msg").strip()
        qp_token = _get_query_param("rl_chat_send_token").strip()
        last_token = str(st.session_state.get("rl_chat_last_send_token", "") or "")

        if qp_token and qp_token == last_token:
            _clear_chat_query_params()
            return

        # Prefer the URL payload from JS bridge when present.
        if qp_msg:
            msg = qp_msg

        # Do not write to widget-bound key after instantiation (Streamlit API restriction).
        # Bridge input is overwritten by JS on each send, so explicit reset is unnecessary here.
        if not msg:
            return

        st.session_state["rl_chat_messages"].append({"role": "user", "content": msg})
        try:
            reply = _chat_reply_with_nova(current_page=current_page, user_message=msg)
        except Exception as e:
            reply = f"Sorry, chat is temporarily unavailable: {e}"
        st.session_state["rl_chat_messages"].append({"role": "assistant", "content": str(reply)})
        st.session_state["rl_chat_messages"] = st.session_state["rl_chat_messages"][-30:]
        st.session_state["rl_chat_reset_bridge_input"] = True
        st.session_state["rl_chat_last_send_token"] = qp_token or f"msg-{len(st.session_state['rl_chat_messages'])}"
        _clear_chat_query_params()
        st.rerun()


def _render_hidden_bridge() -> tuple[bool, bool]:
    # Hidden bridge widgets used by JS to trigger Streamlit reruns.
    with st.container():
        st.markdown('<div id="rl-chat-bridge-anchor"></div>', unsafe_allow_html=True)
        st.text_input(
            "RL_CHAT_BRIDGE_INPUT",
            key="rl_chat_bridge_input",
            label_visibility="collapsed",
            placeholder="RL_CHAT_BRIDGE_INPUT",
        )
        send_clicked = st.button("RL_CHAT_BRIDGE_SEND", key="rl_chat_bridge_send_btn")
        clear_clicked = st.button("RL_CHAT_BRIDGE_CLEAR", key="rl_chat_bridge_clear_btn")
    return bool(send_clicked), bool(clear_clicked)


def _inject_floating_widget(messages: list[dict], current_page: str) -> None:
    safe_messages = []
    for m in messages[-30:]:
        role = "user" if str(m.get("role", "")).lower() == "user" else "assistant"
        content = str(m.get("content", "") or "").strip()
        if content:
            safe_messages.append({"role": role, "content": content})

    payload = json.dumps(
        {
            "messages": safe_messages,
            "page": current_page,
        },
        ensure_ascii=False,
    )

    html_block = f"""
    <script>
    (function() {{
      const pdoc = window.parent.document;
      const pwin = window.parent;
      const payload = {payload};
      const STORE_POS = "risklens_chat_pos_v2";
      const STORE_PANEL_POS = "risklens_chat_panel_pos_v2";
      const STORE_OPEN = "risklens_chat_open_v2";

      function esc(s) {{
        return String(s || "").replace(/[&<>"]/g, (ch) => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}}[ch]));
      }}

      function byId(id) {{ return pdoc.getElementById(id); }}

      function clamp(v, lo, hi) {{ return Math.max(lo, Math.min(hi, v)); }}

      function readJson(key, fallback) {{
        try {{
          const raw = pwin.localStorage.getItem(key);
          if (!raw) return fallback;
          return JSON.parse(raw);
        }} catch (e) {{ return fallback; }}
      }}

      function writeJson(key, obj) {{
        try {{ pwin.localStorage.setItem(key, JSON.stringify(obj)); }} catch (e) {{}}
      }}

      function writeSendPayloadToUrl(text) {{
        try {{
          const token = String(Date.now()) + "-" + String(Math.floor(Math.random() * 100000));
          const url = new URL(pwin.location.href);
          url.searchParams.set("rl_chat_msg", text);
          url.searchParams.set("rl_chat_send_token", token);
          pwin.history.replaceState({{}}, "", url.toString());
        }} catch (e) {{}}
      }}

      function hideNearestContainer(el) {{
        if (!el) return;
        let node = el;
        for (let i = 0; i < 24 && node; i++) {{
          const tid = node.getAttribute ? node.getAttribute("data-testid") : "";
          if (tid === "stElementContainer") {{
            node.style.position = "fixed";
            node.style.left = "-10000px";
            node.style.top = "-10000px";
            node.style.width = "1px";
            node.style.height = "1px";
            node.style.opacity = "0";
            node.style.pointerEvents = "none";
            node.style.overflow = "hidden";
            node.style.zIndex = "-1";
            return;
          }}
          node = node.parentElement;
        }}
      }}

      function hideBridgeWidgets() {{
        hideNearestContainer(getBridgeInput());
        hideNearestContainer(getBridgeButton("RL_CHAT_BRIDGE_SEND"));
        hideNearestContainer(getBridgeButton("RL_CHAT_BRIDGE_CLEAR"));
      }}

      function getBridgeInput() {{
        return pdoc.querySelector('input[aria-label="RL_CHAT_BRIDGE_INPUT"]')
          || pdoc.querySelector('input[placeholder="RL_CHAT_BRIDGE_INPUT"]');
      }}

      function getBridgeButton(label) {{
        const btns = pdoc.querySelectorAll("button");
        for (const b of btns) {{
          const t = (b.innerText || b.textContent || "").trim();
          if (t === label) return b;
        }}
        return null;
      }}

      function setNativeInputValue(el, value) {{
        if (!el) return;
        const proto = Object.getPrototypeOf(el);
        const desc = Object.getOwnPropertyDescriptor(proto, "value");
        if (desc && desc.set) {{
          desc.set.call(el, value);
        }} else {{
          el.value = value;
        }}
        el.dispatchEvent(new Event("input", {{ bubbles: true }}));
        el.dispatchEvent(new Event("change", {{ bubbles: true }}));
      }}

      function ensureDom() {{
        let created = false;
        let fab = byId("rl-chat-fab");
        if (!fab) {{
          created = true;
          fab = pdoc.createElement("div");
          fab.id = "rl-chat-fab";
          fab.innerHTML = "💬";
          pdoc.body.appendChild(fab);
        }}

        let panel = byId("rl-chat-panel");
        if (!panel) {{
          created = true;
          panel = pdoc.createElement("div");
          panel.id = "rl-chat-panel";
          panel.innerHTML = `
            <div id="rl-chat-header">
              <div id="rl-chat-title">RiskLens AI Assistant</div>
              <button id="rl-chat-close" type="button">×</button>
            </div>
            <div id="rl-chat-messages"></div>
            <div id="rl-chat-footer">
              <input id="rl-chat-input" type="text" placeholder="Ask anything..." />
              <button id="rl-chat-send" type="button">Send</button>
            </div>
          `;
          pdoc.body.appendChild(panel);
        }}

        let style = byId("rl-chat-style");
        if (!style) {{
          style = pdoc.createElement("style");
          style.id = "rl-chat-style";
          style.textContent = `
            #rl-chat-fab {{
              position: fixed;
              width: 56px;
              height: 56px;
              border-radius: 50%;
              background: #1e40af;
              color: #fff;
              display: flex;
              align-items: center;
              justify-content: center;
              font-size: 24px;
              box-shadow: 0 10px 24px rgba(30,64,175,0.35);
              cursor: grab;
              user-select: none;
              z-index: 9999;
            }}
            #rl-chat-panel {{
              position: fixed;
              width: 400px;
              height: 500px;
              max-width: calc(100vw - 20px);
              max-height: calc(100vh - 20px);
              background: #fff;
              border: 1px solid #dbe7ff;
              border-radius: 12px;
              box-shadow: 0 16px 36px rgba(15,23,42,0.22);
              overflow: hidden;
              z-index: 9999;
              display: none;
            }}
            #rl-chat-header {{
              height: 48px;
              background: #1e40af;
              color: #fff;
              display: flex;
              align-items: center;
              justify-content: space-between;
              padding: 0 12px;
              cursor: move;
            }}
            #rl-chat-title {{
              font-size: 14px;
              font-weight: 700;
              letter-spacing: 0.01em;
            }}
            #rl-chat-close {{
              background: transparent;
              border: none;
              color: #fff;
              font-size: 24px;
              line-height: 1;
              cursor: pointer;
            }}
            #rl-chat-messages {{
              height: calc(100% - 108px);
              overflow-y: auto;
              background: #f8fafc;
              padding: 10px;
            }}
            .rl-chat-row {{
              display: flex;
              margin: 8px 0;
            }}
            .rl-chat-row.user {{ justify-content: flex-end; }}
            .rl-chat-row.assistant {{ justify-content: flex-start; }}
            .rl-chat-bubble {{
              max-width: 82%;
              border-radius: 10px;
              padding: 8px 10px;
              font-size: 13px;
              line-height: 1.35;
              white-space: pre-wrap;
              word-break: break-word;
            }}
            .rl-chat-row.user .rl-chat-bubble {{
              background: #2563eb;
              color: #fff;
            }}
            .rl-chat-row.assistant .rl-chat-bubble {{
              background: #e2e8f0;
              color: #0f172a;
            }}
            #rl-chat-footer {{
              height: 60px;
              border-top: 1px solid #e2e8f0;
              display: flex;
              gap: 8px;
              align-items: center;
              padding: 8px;
              background: #fff;
            }}
            #rl-chat-input {{
              flex: 1;
              height: 38px;
              border: 1px solid #cbd5e1;
              border-radius: 8px;
              padding: 0 10px;
              font-size: 13px;
              outline: none;
            }}
            #rl-chat-send {{
              height: 38px;
              min-width: 72px;
              border: none;
              border-radius: 8px;
              background: #1e40af;
              color: #fff;
              font-weight: 600;
              cursor: pointer;
            }}
          `;
          pdoc.head.appendChild(style);
        }}

        return {{ fab, panel, created }};
      }}

      function placeDefaults(fab, panel) {{
        const vw = pwin.innerWidth || 1280;
        const vh = pwin.innerHeight || 720;
        const fabSize = 56;
        const margin = 16;

        const fp = readJson(STORE_POS, {{ x: vw - fabSize - margin, y: vh - fabSize - margin }});
        fp.x = clamp(fp.x, 8, Math.max(8, vw - fabSize - 8));
        fp.y = clamp(fp.y, 8, Math.max(8, vh - fabSize - 8));
        fab.style.left = fp.x + "px";
        fab.style.top = fp.y + "px";
        writeJson(STORE_POS, fp);

        const panelW = Math.min(400, vw - 20);
        const panelH = Math.min(500, vh - 20);
        const pp = readJson(STORE_PANEL_POS, {{
          x: clamp(fp.x - panelW + fabSize, 10, Math.max(10, vw - panelW - 10)),
          y: clamp(fp.y - panelH - 10, 10, Math.max(10, vh - panelH - 10))
        }});
        pp.x = clamp(pp.x, 10, Math.max(10, vw - panelW - 10));
        pp.y = clamp(pp.y, 10, Math.max(10, vh - panelH - 10));
        panel.style.left = pp.x + "px";
        panel.style.top = pp.y + "px";
        writeJson(STORE_PANEL_POS, pp);
      }}

      function renderMessages(panel) {{
        const box = panel.querySelector("#rl-chat-messages");
        if (!box) return;
        const prevScrollBottom = box.scrollHeight - box.scrollTop - box.clientHeight;
        box.innerHTML = "";
        (payload.messages || []).forEach((m) => {{
          const row = pdoc.createElement("div");
          row.className = "rl-chat-row " + (m.role === "user" ? "user" : "assistant");
          const bubble = pdoc.createElement("div");
          bubble.className = "rl-chat-bubble";
          bubble.innerHTML = esc(m.content).replace(/\\n/g, "<br>");
          row.appendChild(bubble);
          box.appendChild(row);
        }});
        if (prevScrollBottom < 60) {{
          box.scrollTop = box.scrollHeight;
        }}
      }}

      function bindDrag(el, opts) {{
        opts = opts || {{}};
        let dragging = false;
        let sx = 0, sy = 0, ox = 0, oy = 0;
        const onMove = (e) => {{
          if (!dragging) return;
          const dx = e.clientX - sx;
          const dy = e.clientY - sy;
          el.style.left = (ox + dx) + "px";
          el.style.top = (oy + dy) + "px";
          if (opts.onMove) opts.onMove(dx, dy, e);
        }};
        const onUp = () => {{
          if (!dragging) return;
          dragging = false;
          pdoc.removeEventListener("mousemove", onMove);
          pdoc.removeEventListener("mouseup", onUp);
          if (opts.onEnd) opts.onEnd();
        }};
        return (e) => {{
          dragging = true;
          sx = e.clientX;
          sy = e.clientY;
          const r = el.getBoundingClientRect();
          ox = r.left;
          oy = r.top;
          pdoc.addEventListener("mousemove", onMove);
          pdoc.addEventListener("mouseup", onUp);
        }};
      }}

      function wire(fab, panel) {{
        const state = pwin.__rlChatState || {{ sending: false }};
        pwin.__rlChatState = state;

        let moved = false;
        const dragStart = bindDrag(fab, {{
          onMove: (dx, dy) => {{
            if (Math.abs(dx) + Math.abs(dy) > 4) moved = true;
          }},
          onEnd: () => {{
            const r = fab.getBoundingClientRect();
            writeJson(STORE_POS, {{ x: r.left, y: r.top }});
            if (moved) {{
              setTimeout(() => {{ moved = false; }}, 120);
            }}
          }}
        }});
        fab.onmousedown = (e) => {{
          if (e.button !== 0) return;
          moved = false;
          dragStart(e);
        }};
        fab.onclick = () => {{
          if (moved) return;
          const open = !(readJson(STORE_OPEN, false));
          writeJson(STORE_OPEN, open);
          panel.style.display = open ? "block" : "none";
          if (open) {{
            const vw = pwin.innerWidth || 1280;
            const vh = pwin.innerHeight || 720;
            const r = panel.getBoundingClientRect();
            const nx = clamp(r.left, 10, Math.max(10, vw - r.width - 10));
            const ny = clamp(r.top, 10, Math.max(10, vh - r.height - 10));
            panel.style.left = nx + "px";
            panel.style.top = ny + "px";
            writeJson(STORE_PANEL_POS, {{ x: nx, y: ny }});
          }}
        }};

        const header = panel.querySelector("#rl-chat-header");
        const dragPanel = bindDrag(panel, {{
          onEnd: () => {{
            const r = panel.getBoundingClientRect();
            writeJson(STORE_PANEL_POS, {{ x: r.left, y: r.top }});
          }}
        }});
        if (header) {{
          header.onmousedown = (e) => {{
            if (e.target && e.target.id === "rl-chat-close") return;
            dragPanel(e);
          }};
        }}

        const closeBtn = panel.querySelector("#rl-chat-close");
        if (closeBtn) {{
          closeBtn.onclick = () => {{
            panel.style.display = "none";
            writeJson(STORE_OPEN, false);
          }};
        }}

        const sendBtn = panel.querySelector("#rl-chat-send");
        const inputEl = panel.querySelector("#rl-chat-input");
        function sendNow() {{
          if (!sendBtn || !inputEl || sendBtn.disabled || state.sending) return;
          const text = (inputEl && inputEl.value || "").trim();
          if (!text) return;
          writeSendPayloadToUrl(text);
          const bridgeInput = getBridgeInput();
          const bridgeBtn = getBridgeButton("RL_CHAT_BRIDGE_SEND");
          if (!bridgeInput || !bridgeBtn) {{
            inputEl.placeholder = "Bridge not ready, please try again...";
            setTimeout(() => {{
              inputEl.placeholder = "Ask anything...";
            }}, 1500);
            return;
          }}
          state.sending = true;
          sendBtn.disabled = true;
          setNativeInputValue(bridgeInput, text);
          bridgeInput.dispatchEvent(new Event("blur", {{ bubbles: true }}));
          setTimeout(() => {{
            try {{
              bridgeBtn.focus();
              bridgeBtn.dispatchEvent(new MouseEvent("mousedown", {{ bubbles: true, cancelable: true }}));
              bridgeBtn.dispatchEvent(new MouseEvent("mouseup", {{ bubbles: true, cancelable: true }}));
              bridgeBtn.click();
            }} catch (e) {{}}
          }}, 30);
          inputEl.value = "";
          inputEl.placeholder = "Thinking...";
          setTimeout(() => {{
            inputEl.placeholder = "Ask anything...";
            sendBtn.disabled = false;
            state.sending = false;
          }}, 1500);
        }}
        if (sendBtn) {{
          sendBtn.onclick = sendNow;
        }}
        if (inputEl) {{
          inputEl.onkeydown = (e) => {{
            if (e.key === "Enter") {{
              e.preventDefault();
              sendNow();
            }}
          }};
        }}
      }}

      hideBridgeWidgets();
      const dom = ensureDom();
      if (dom.created) {{
        placeDefaults(dom.fab, dom.panel);
      }}
      renderMessages(dom.panel);
      if (pwin.__rlChatState) {{
        pwin.__rlChatState.sending = false;
      }}
      const syncInput = dom.panel.querySelector("#rl-chat-input");
      const syncSend = dom.panel.querySelector("#rl-chat-send");
      if (syncInput && syncInput.placeholder === "Thinking...") {{
        syncInput.placeholder = "Ask anything...";
      }}
      if (syncSend && syncSend.disabled) {{
        syncSend.disabled = false;
      }}
      wire(dom.fab, dom.panel);
      hideBridgeWidgets();
      setTimeout(hideBridgeWidgets, 120);
      setTimeout(hideBridgeWidgets, 400);

      const isOpen = !!readJson(STORE_OPEN, false);
      dom.panel.style.display = isOpen ? "block" : "none";
    }})();
    </script>
    """
    components.html(html_block, height=0)


def render_chat_widget(current_page: str) -> None:
    _ensure_state()
    send_clicked, clear_clicked = _render_hidden_bridge()
    _handle_bridge_events(current_page, send_clicked, clear_clicked)
    _inject_floating_widget(st.session_state.get("rl_chat_messages", []), current_page)
