import React, { useEffect, useRef, useState } from 'react'
import { post } from '../lib/api'

const MAX_MESSAGES = 30
const FAB_KEY = 'risklens_chat_fab_pos_v1'
const PANEL_KEY = 'risklens_chat_panel_pos_v1'
const CHATBOT_MESSAGES_KEY = 'risklens_product_chat_messages_v1'
const PANEL_WIDTH = 360
const PANEL_HEIGHT = 500

function clamp(v, min, max) {
  return Math.min(Math.max(v, min), max)
}

function getDefaultFabPos() {
  const w = typeof window !== 'undefined' ? window.innerWidth : 1440
  const h = typeof window !== 'undefined' ? window.innerHeight : 900
  return { x: Math.max(16, w - 88), y: Math.max(16, h - 92) }
}

function getDefaultPanelPos(fabPos) {
  const w = typeof window !== 'undefined' ? window.innerWidth : 1440
  const h = typeof window !== 'undefined' ? window.innerHeight : 900
  const pw = PANEL_WIDTH
  const ph = PANEL_HEIGHT
  return {
    x: clamp((fabPos?.x ?? w - 80) - 320, 12, Math.max(12, w - pw - 12)),
    y: clamp((fabPos?.y ?? h - 88) - 420, 12, Math.max(12, h - ph - 12)),
  }
}

function defaultMessage() {
  return {
    role: 'assistant',
    text: 'Hi, I am your RiskLens product assistant. I can help you use this app. Ask in English or 中文.',
    meta: { timestamp: Date.now() },
  }
}

function SendArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 17V7" />
      <path d="M7.5 11.5L12 7L16.5 11.5" />
    </svg>
  )
}

export default function FloatingChatWidget() {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [fabPos, setFabPos] = useState(() => {
    if (typeof window === 'undefined') return { x: 0, y: 0 }
    try {
      const raw = window.localStorage.getItem(FAB_KEY)
      if (!raw) return getDefaultFabPos()
      const parsed = JSON.parse(raw)
      return {
        x: Number(parsed?.x) || getDefaultFabPos().x,
        y: Number(parsed?.y) || getDefaultFabPos().y,
      }
    } catch {
      return getDefaultFabPos()
    }
  })
  const [panelPos, setPanelPos] = useState(() => {
    if (typeof window === 'undefined') return { x: 0, y: 0 }
    try {
      const raw = window.localStorage.getItem(PANEL_KEY)
      if (!raw) return getDefaultPanelPos(getDefaultFabPos())
      const parsed = JSON.parse(raw)
      return {
        x: Number(parsed?.x) || getDefaultPanelPos(getDefaultFabPos()).x,
        y: Number(parsed?.y) || getDefaultPanelPos(getDefaultFabPos()).y,
      }
    } catch {
      return getDefaultPanelPos(getDefaultFabPos())
    }
  })
  const [query, setQuery] = useState('')
  const [messages, setMessages] = useState(() => {
    if (typeof window === 'undefined') return [defaultMessage()]
    try {
      const raw = window.localStorage.getItem(CHATBOT_MESSAGES_KEY)
      if (!raw) return [defaultMessage()]
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || !parsed.length) return [defaultMessage()]
      const rows = parsed
        .filter((m) => m && typeof m === 'object')
        .map((m) => ({
          role: String(m.role || '').toLowerCase() === 'user' ? 'user' : 'assistant',
          text: String(m.text || '').trim(),
          meta: m.meta && typeof m.meta === 'object' ? m.meta : {},
        }))
        .filter((m) => m.text)
      return rows.length ? rows.slice(-MAX_MESSAGES) : [defaultMessage()]
    } catch {
      return [defaultMessage()]
    }
  })

  const bottomRef = useRef(null)
  const fabDragRef = useRef(null)
  const panelDragRef = useRef(null)
  const isComposingRef = useRef(false)
  const lastCompositionEndAtRef = useRef(0)
  const ignoreNextEnterRef = useRef(false)
  const compositionEndTimerRef = useRef(0)

  useEffect(() => {
    if (!open) return
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, open, loading])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(FAB_KEY, JSON.stringify(fabPos))
  }, [fabPos])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(PANEL_KEY, JSON.stringify(panelPos))
  }, [panelPos])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(CHATBOT_MESSAGES_KEY, JSON.stringify(messages.slice(-MAX_MESSAGES)))
  }, [messages])

  useEffect(() => {
    const onResize = () => {
      const w = window.innerWidth
      const h = window.innerHeight
      setFabPos((prev) => ({
        x: clamp(prev.x, 8, Math.max(8, w - 72)),
        y: clamp(prev.y, 8, Math.max(8, h - 72)),
      }))
      setPanelPos((prev) => ({
        x: clamp(prev.x, 8, Math.max(8, w - PANEL_WIDTH)),
        y: clamp(prev.y, 8, Math.max(8, h - PANEL_HEIGHT)),
      }))
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    if (!open) return
    setPanelPos((prev) => {
      if (prev.x || prev.y) return prev
      return getDefaultPanelPos(fabPos)
    })
  }, [open, fabPos])

  const canSend = query.trim().length > 0 && !loading

  const markCompositionStart = () => {
    if (compositionEndTimerRef.current && typeof window !== 'undefined') {
      window.clearTimeout(compositionEndTimerRef.current)
      compositionEndTimerRef.current = 0
    }
    isComposingRef.current = true
    ignoreNextEnterRef.current = false
  }

  const markCompositionEnd = () => {
    lastCompositionEndAtRef.current = Date.now()
    ignoreNextEnterRef.current = true
    if (typeof window !== 'undefined') {
      if (compositionEndTimerRef.current) window.clearTimeout(compositionEndTimerRef.current)
      compositionEndTimerRef.current = window.setTimeout(() => {
        isComposingRef.current = false
        compositionEndTimerRef.current = 0
      }, 0)
    } else {
      isComposingRef.current = false
    }
  }

  const shouldIgnoreEnterSubmit = (event) => {
    const nativeEvent = event?.nativeEvent || {}
    const key = String(event?.key || nativeEvent.key || '')
    const isEnterKey = key === 'Enter' || key === 'NumpadEnter'
    if (key && key !== 'Enter' && key !== 'NumpadEnter' && key !== 'Process') {
      ignoreNextEnterRef.current = false
      return false
    }
    const keyCode = Number(nativeEvent.keyCode || nativeEvent.which || nativeEvent.charCode || 0)
    const isProcessKey = key === 'Process' || String(nativeEvent.code || '') === 'Process'
    if (isComposingRef.current) return true
    if (nativeEvent.isComposing || event?.isComposing || keyCode === 229 || isProcessKey) return true
    const justEndedComposition = Date.now() - Number(lastCompositionEndAtRef.current || 0) < 18
    if (isEnterKey && justEndedComposition && ignoreNextEnterRef.current) {
      ignoreNextEnterRef.current = false
      return true
    }
    return false
  }

  useEffect(() => () => {
    if (compositionEndTimerRef.current && typeof window !== 'undefined') {
      window.clearTimeout(compositionEndTimerRef.current)
      compositionEndTimerRef.current = 0
    }
  }, [])

  const sendFromWidget = async () => {
    const text = query.trim()
    if (!text || loading) return

    const userMsg = {
      role: 'user',
      text,
      meta: { timestamp: Date.now() },
    }
    const historyPayload = [...messages, userMsg]
      .filter((m) => (m.role === 'user' || m.role === 'assistant') && String(m.text || '').trim())
      .slice(-16)
      .map((m) => ({ role: m.role, text: String(m.text || '').trim() }))

    setMessages((prev) => [...prev, userMsg].slice(-MAX_MESSAGES))
    setQuery('')
    setLoading(true)
    setError('')

    try {
      const res = await post('/api/chatbot/help', {
        user_query: text,
        history: historyPayload,
      })
      const answer = String(res?.answer || '').trim() || 'I can help explain how to use this app. Ask me about pages or workflow steps.'
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: answer, meta: { timestamp: Date.now() } },
      ].slice(-MAX_MESSAGES))
    } catch (e) {
      const msg = e?.message || 'Chatbot request failed'
      setError(msg)
      const failText = /[\u4e00-\u9fff]/.test(text)
        ? `我暂时无法完成这次回答：${msg}。请稍后重试。`
        : `I could not complete this help request: ${msg}. Please try again.`
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: failText, meta: { timestamp: Date.now() } },
      ].slice(-MAX_MESSAGES))
    } finally {
      setLoading(false)
    }
  }

  const startFabDrag = (e) => {
    if (e.button !== 0) return
    e.preventDefault()
    fabDragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origX: fabPos.x,
      origY: fabPos.y,
      moved: false,
    }
    window.addEventListener('pointermove', onFabDrag)
    window.addEventListener('pointerup', endFabDrag)
  }

  const onFabDrag = (e) => {
    if (!fabDragRef.current) return
    const d = fabDragRef.current
    const dx = e.clientX - d.startX
    const dy = e.clientY - d.startY
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) d.moved = true
    const w = window.innerWidth
    const h = window.innerHeight
    setFabPos({
      x: clamp(d.origX + dx, 8, Math.max(8, w - 72)),
      y: clamp(d.origY + dy, 8, Math.max(8, h - 72)),
    })
  }

  const endFabDrag = () => {
    const d = fabDragRef.current
    window.removeEventListener('pointermove', onFabDrag)
    window.removeEventListener('pointerup', endFabDrag)
    fabDragRef.current = null
    if (d && !d.moved) {
      setOpen(true)
      setPanelPos(getDefaultPanelPos(fabPos))
    }
  }

  const startPanelDrag = (e) => {
    if (e.button !== 0) return
    const isClose = e.target && e.target.closest && e.target.closest('.rl-chat-close')
    if (isClose) return
    e.preventDefault()
    panelDragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origX: panelPos.x,
      origY: panelPos.y,
    }
    window.addEventListener('pointermove', onPanelDrag)
    window.addEventListener('pointerup', endPanelDrag)
  }

  const onPanelDrag = (e) => {
    if (!panelDragRef.current) return
    const d = panelDragRef.current
    const dx = e.clientX - d.startX
    const dy = e.clientY - d.startY
    const w = window.innerWidth
    const h = window.innerHeight
    setPanelPos({
      x: clamp(d.origX + dx, 8, Math.max(8, w - PANEL_WIDTH)),
      y: clamp(d.origY + dy, 8, Math.max(8, h - PANEL_HEIGHT)),
    })
  }

  const endPanelDrag = () => {
    window.removeEventListener('pointermove', onPanelDrag)
    window.removeEventListener('pointerup', endPanelDrag)
    panelDragRef.current = null
  }

  return (
    <div className="rl-chat-widget">
      {open && (
        <section className="rl-chat-panel" style={{ left: `${panelPos.x}px`, top: `${panelPos.y}px` }}>
          <header className="rl-chat-header" onPointerDown={startPanelDrag}>
            <div>
              <p className="rl-chat-title">RiskLens Product Assistant</p>
            </div>
            <button className="rl-chat-close" onClick={() => setOpen(false)} aria-label="Close chat">
              ×
            </button>
          </header>

          <div className="rl-chat-messages">
            {messages.map((m, idx) => (
              <div key={`${m.role}-${idx}-${m.meta?.timestamp || idx}`} className={`rl-chat-row ${m.role === 'user' ? 'user' : 'assistant'}`}>
                <div className="rl-chat-bubble">{m.text}</div>
              </div>
            ))}
            {loading && (
              <div className="rl-chat-row assistant">
                <div className="rl-chat-bubble">Thinking... / 正在整理使用建议...</div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {error && <p className="rl-chat-error">{error}</p>}

          <footer className="rl-chat-footer">
            <div className="rl-chat-input-wrap">
              <textarea
                className="rl-chat-input"
                value={query}
                placeholder="Ask how to use RiskLens features..."
                onChange={(e) => {
                  if (error) setError('')
                  setQuery(e.target.value)
                }}
                onCompositionStart={markCompositionStart}
                onCompositionEnd={markCompositionEnd}
                onKeyDown={(e) => {
                  if (shouldIgnoreEnterSubmit(e)) {
                    if (e.key === 'Enter' && !e.shiftKey) e.preventDefault()
                    return
                  }
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    sendFromWidget()
                  }
                }}
              />
              <button
                className={`rl-chat-send-round ${loading ? 'loading' : ''}`}
                onClick={sendFromWidget}
                disabled={!canSend}
                aria-label={loading ? 'Thinking' : 'Send'}
              >
                <SendArrowIcon />
              </button>
            </div>
          </footer>
        </section>
      )}

      {!open && (
        <button
          className="rl-chat-fab"
          onPointerDown={startFabDrag}
          style={{ left: `${fabPos.x}px`, top: `${fabPos.y}px` }}
          aria-label="Open chat"
          title="Drag to move"
        >
          <span className="rl-chat-fab-inner" aria-hidden="true">💬</span>
        </button>
      )}
    </div>
  )
}
