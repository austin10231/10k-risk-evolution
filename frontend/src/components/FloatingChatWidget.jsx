import React, { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useChatMemory } from '../lib/chatMemory'
import { useWorkspaceChat } from '../lib/workspaceChat'
import { stashPendingChat } from '../lib/pendingChat'

const MAX_MESSAGES = 30
const FAB_KEY = 'risklens_chat_fab_pos_v1'
const PANEL_KEY = 'risklens_chat_panel_pos_v1'

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
  const pw = 390
  const ph = 560
  return {
    x: clamp((fabPos?.x ?? w - 80) - 320, 12, Math.max(12, w - pw - 12)),
    y: clamp((fabPos?.y ?? h - 88) - 420, 12, Math.max(12, h - ph - 12)),
  }
}

function defaultMessage() {
  return {
    role: 'assistant',
    text: 'Hi, I am your RiskLens assistant. Ask me in English or Chinese.',
  }
}

function buildAgentHref(search = '') {
  const src = new URLSearchParams(search || '')
  const next = new URLSearchParams()
  const recordId = String(src.get('record_id') || '').trim()
  const compareRecordId = String(src.get('compare_record_id') || '').trim()
  if (recordId) next.set('record_id', recordId)
  if (compareRecordId) next.set('compare_record_id', compareRecordId)
  const query = next.toString()
  return `/agent${query ? `?${query}` : ''}`
}

function SendArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 17V7" />
      <path d="M7.5 11.5L12 7L16.5 11.5" />
    </svg>
  )
}

export default function FloatingChatWidget() {
  const location = useLocation()
  const navigate = useNavigate()
  const { currentThread } = useChatMemory()
  const { send, loading, error, clearError, startNewThread } = useWorkspaceChat()

  const [open, setOpen] = useState(false)
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
  const bottomRef = useRef(null)
  const fabDragRef = useRef(null)
  const panelDragRef = useRef(null)
  const isComposingRef = useRef(false)
  const lastCompositionEndAtRef = useRef(0)

  const threadMessages = currentThread?.messages || []
  const messages = threadMessages.length ? threadMessages.slice(-MAX_MESSAGES) : [defaultMessage()]

  useEffect(() => {
    if (!open) return
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [threadMessages.length, open, loading])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(FAB_KEY, JSON.stringify(fabPos))
  }, [fabPos])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(PANEL_KEY, JSON.stringify(panelPos))
  }, [panelPos])

  useEffect(() => {
    const onResize = () => {
      const w = window.innerWidth
      const h = window.innerHeight
      setFabPos((prev) => ({
        x: clamp(prev.x, 8, Math.max(8, w - 72)),
        y: clamp(prev.y, 8, Math.max(8, h - 72)),
      }))
      setPanelPos((prev) => ({
        x: clamp(prev.x, 8, Math.max(8, w - 390)),
        y: clamp(prev.y, 8, Math.max(8, h - 560)),
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
    isComposingRef.current = true
  }

  const markCompositionEnd = () => {
    isComposingRef.current = false
    lastCompositionEndAtRef.current = Date.now()
  }

  const shouldIgnoreEnterSubmit = (event) => {
    const nativeEvent = event?.nativeEvent || {}
    if (isComposingRef.current) return true
    if (nativeEvent.isComposing || event?.isComposing || nativeEvent.keyCode === 229) return true
    return Date.now() - Number(lastCompositionEndAtRef.current || 0) < 120
  }

  const clearChat = () => {
    startNewThread()
    clearError()
    setQuery('')
  }

  const sendFromWidget = async () => {
    const text = query.trim()
    if (!text || loading) return

    const originPath = location.pathname || '/agent'
    const originSearch = location.search || ''
    const targetHref = buildAgentHref(originSearch)
    const needsJump = `${location.pathname || ''}${location.search || ''}` !== targetHref
    if (needsJump) {
      stashPendingChat({ text, originPath, originSearch })
      setQuery('')
      setOpen(false)
      navigate(targetHref)
      return
    }
    await send(text, { pathname: originPath, search: originSearch })

    setQuery('')
    setOpen(false)
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
      x: clamp(d.origX + dx, 8, Math.max(8, w - 390)),
      y: clamp(d.origY + dy, 8, Math.max(8, h - 560)),
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
              <p className="rl-chat-title">RiskLens AI Assistant</p>
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
                <div className="rl-chat-bubble">Thinking...</div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {error && <p className="rl-chat-error">{error}</p>}

          <footer className="rl-chat-footer">
            <textarea
              className="rl-chat-input"
              value={query}
              placeholder="Ask anything about company risk..."
              onChange={(e) => {
                if (error) clearError()
                setQuery(e.target.value)
              }}
              onCompositionStart={markCompositionStart}
              onCompositionEnd={markCompositionEnd}
              onKeyDown={(e) => {
                if (shouldIgnoreEnterSubmit(e)) return
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  sendFromWidget()
                }
              }}
            />
            <div className="rl-chat-actions">
              <button className="btn-secondary text-xs" onClick={clearChat} disabled={loading}>
                New Chat
              </button>
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
          title="Drag me anywhere"
        >
          <span className="rl-chat-fab-inner" aria-hidden="true">💬</span>
        </button>
      )}
    </div>
  )
}
