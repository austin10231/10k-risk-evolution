import React, { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { useChatMemory } from '../lib/chatMemory'
import { useWorkspaceChat } from '../lib/workspaceChat'
import { popPendingChat } from '../lib/pendingChat'

export default function AgentPage() {
  const threadRef = useRef(null)
  const pendingSentRef = useRef('')
  const location = useLocation()
  const { currentThread, currentThreadId } = useChatMemory()
  const { loading, error, isConversationStarted, send } = useWorkspaceChat()
  const messages = currentThread?.messages || []

  useEffect(() => {
    if (location.pathname !== '/agent') return
    const pending = popPendingChat()
    if (!pending?.text) return
    const marker = `${pending.ts || 0}:${pending.text}`
    if (pendingSentRef.current === marker) return
    pendingSentRef.current = marker
    send(pending.text, {
      pathname: pending.originPath || '/agent',
      search: pending.originSearch || '',
    })
  }, [location.pathname, location.search, send])

  useEffect(() => {
    requestAnimationFrame(() => {
      if (!threadRef.current) return
      threadRef.current.scrollTop = threadRef.current.scrollHeight
    })
  }, [currentThreadId, messages.length, loading])

  if (!isConversationStarted && !loading) {
    return null
  }

  return (
    <div className="rl-ask-shell">
      {error ? <div className="rl-agent-error">{error}</div> : null}

      <section className="rl-ask-thread" ref={threadRef}>
        <div className="rl-ask-status rl-ask-status-inline">
          <span className={`dot ${loading ? 'busy' : 'idle'}`} />
          <span>{loading ? 'Agent Thinking' : 'Ready'}</span>
        </div>

        {messages.map((m, idx) => (
          <article key={`${m.role}-${idx}`} className={`rl-agent-msg ${m.role}`}>
            <div className="rl-agent-msg-avatar">{m.role === 'user' ? 'U' : 'AI'}</div>
            <div className="rl-agent-msg-body">
              <div className="rl-agent-msg-top">
                <strong>{m.role === 'user' ? 'You' : 'RiskLens Agent'}</strong>
                <span>{new Date(m.meta?.timestamp || Date.now()).toLocaleTimeString()}</span>
              </div>
              <p>{m.text}</p>
              {m.meta?.tools?.length ? (
                <div className="rl-agent-tool-row">
                  {m.meta.tools.map((tool) => (
                    <span key={tool} className="rl-agent-tool-pill">
                      {tool}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          </article>
        ))}

        {loading ? (
          <article className="rl-agent-msg assistant">
            <div className="rl-agent-msg-avatar">AI</div>
            <div className="rl-agent-msg-body">
              <div className="rl-agent-msg-top">
                <strong>RiskLens Agent</strong>
                <span>Running</span>
              </div>
              <div className="rl-agent-thinking-dots">
                <span />
                <span />
                <span />
              </div>
            </div>
          </article>
        ) : null}
      </section>
    </div>
  )
}
