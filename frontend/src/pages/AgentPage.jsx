import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { post } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'
import { useChatMemory } from '../lib/chatMemory'

const STARTER_PROMPTS = [
  'What are Apple’s top 5 critical risks in 2024, and why?',
  'Compare NVIDIA vs Microsoft risk profile and what changed most.',
  'Summarize emerging risks and provide monitoring actions.',
  'Any recent news that may amplify Tesla’s filing risks?',
  'If I am a portfolio manager, what should I watch this quarter?',
]

const MODULE_LINKS = [
  { label: 'Upload', to: '/upload', icon: '➕' },
  { label: 'Dashboard', to: '/dashboard', icon: '📈' },
  { label: 'Library', to: '/library', icon: '📚' },
  { label: 'Compare', to: '/compare', icon: '⚖️' },
  { label: 'News', to: '/news', icon: '📰' },
  { label: 'Stock', to: '/stock', icon: '💹' },
  { label: 'Tables', to: '/tables', icon: '📊' },
]

function detectLang(text) {
  return /[\u4e00-\u9fff]/.test(text || '') ? 'Chinese' : 'English'
}

function plannedTools(query, hasConfig) {
  const q = String(query || '').toLowerCase()
  const tools = ['Risk Synthesis']
  if (q.includes('compare') || q.includes('对比')) tools.push('Cross-Filing Compare')
  if (
    q.includes('stock') ||
    q.includes('market') ||
    q.includes('price') ||
    q.includes('股') ||
    q.includes('市场')
  ) {
    tools.push('Market Context')
  }
  if (q.includes('news') || q.includes('headline') || q.includes('新闻')) tools.push('News Scan')
  if (hasConfig) tools.push('Global Config Memory')
  return Array.from(new Set(tools))
}

export default function AgentPage() {
  const { config } = useGlobalConfig()
  const { currentThread, currentThreadId, appendMessage, createThread } = useChatMemory()
  const threadRef = useRef(null)

  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const messages = currentThread?.messages || []

  const hasGlobalConfig = Boolean(config.company || config.year || config.ticker || config.industry)

  const canSend = query.trim().length > 0 && !loading

  const lastReport = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].report) return messages[i].report
    }
    return null
  }, [messages])

  const scrollToBottom = () => {
    requestAnimationFrame(() => {
      if (!threadRef.current) return
      threadRef.current.scrollTop = threadRef.current.scrollHeight
    })
  }

  useEffect(() => {
    scrollToBottom()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentThreadId, messages.length])

  const send = async (forcedQuery) => {
    const userText = (forcedQuery ?? query).trim()
    if (!userText || loading) return

    const lang = detectLang(userText)
    const tools = plannedTools(userText, hasGlobalConfig)

    const createdId = !currentThreadId ? createThread() : ''
    const targetThreadId = currentThreadId || currentThread?.id || createdId
    if (!targetThreadId) return

    appendMessage(targetThreadId, {
      role: 'user',
      text: userText,
      report: null,
      meta: { lang, timestamp: Date.now() },
    })

    setQuery('')
    setLoading(true)
    setError('')
    scrollToBottom()

    try {
      const payload = {
        user_query: userText,
        company: config.company || '',
        year: config.year ? Number(config.year) : 0,
      }
      const res = await post('/api/agent/query', payload)
      const report = res?.report || res?.result || {}
      const answer =
        report?.direct_answer ||
        report?.executive_summary ||
        'I completed the analysis, but no direct answer text was returned.'

      appendMessage(targetThreadId, {
        role: 'assistant',
        text: answer,
        report,
        meta: { lang, tools, timestamp: Date.now() },
      })
    } catch (e) {
      const msg = e.message || 'Agent request failed'
      setError(msg)
      appendMessage(targetThreadId, {
        role: 'assistant',
        text: `I could not complete this run: ${msg}`,
        report: null,
        meta: { lang, tools, timestamp: Date.now() },
      })
    } finally {
      setLoading(false)
      scrollToBottom()
    }
  }

  return (
    <div className="rl-agent-shell">
      <section className="rl-agent-hero">
        <div className="rl-agent-hero-grid" />
        <div className="rl-agent-hero-content">
          <div className="rl-agent-hero-top">
            <p className="rl-agent-badge">Autonomous Risk Agent</p>
            <button className="btn-secondary" onClick={() => createThread()}>
              + New Conversation
            </button>
          </div>
          <h1>Ask one question. Get an adaptive risk workflow.</h1>
          <p>
            The agent selects tools automatically across filings, compare, market, and news context. It understands both
            English and Chinese input.
          </p>
          <div className="rl-agent-hero-links">
            {MODULE_LINKS.slice(0, 4).map((m) => (
              <Link key={m.label} to={m.to}>
                {m.icon} {m.label}
              </Link>
            ))}
          </div>
        </div>
      </section>

      <div className="rl-agent-workspace">
        <section className="rl-agent-chat card">
          <header className="rl-agent-chat-head">
            <div>
              <p className="rl-agent-chat-title">{currentThread?.title || 'New conversation'}</p>
              <p className="rl-agent-chat-sub">Conversation memory is saved in sidebar history.</p>
            </div>
            <div className="rl-agent-head-status">
              <span className={`dot ${loading ? 'busy' : 'idle'}`} />
              <span>{loading ? 'Agent Thinking' : 'Ready'}</span>
            </div>
          </header>

          {error ? <div className="rl-agent-error">{error}</div> : null}

          <div className="rl-agent-thread" ref={threadRef}>
            {!messages.length ? (
              <article className="rl-agent-empty">
                <h4>Start chatting</h4>
                <p>Ask any company risk question and the agent will decide the analysis path automatically.</p>
              </article>
            ) : null}

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
                  <p>Planning analysis path and querying the best available context…</p>
                  <div className="rl-agent-thinking-dots">
                    <span />
                    <span />
                    <span />
                  </div>
                </div>
              </article>
            ) : null}
          </div>

          <div className="rl-agent-input-wrap">
            <textarea
              className="rl-agent-input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask any risk question… e.g. 对比一下 Apple 和 Tesla 2024 年最关键风险"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
            />
            <button className="btn-primary rl-agent-send-btn" disabled={!canSend} onClick={() => send()}>
              {loading ? 'Thinking…' : 'Send'}
            </button>
          </div>
        </section>

        <aside className="rl-agent-side">
          <article className="card rl-agent-side-card">
            <p className="section-title">Starter Prompts</p>
            <div className="rl-agent-chip-list">
              {STARTER_PROMPTS.map((p) => (
                <button key={p} className="rl-agent-chip" onClick={() => send(p)} disabled={loading}>
                  {p}
                </button>
              ))}
            </div>
          </article>

          <article className="card rl-agent-side-card">
            <p className="section-title">Saved Global Config</p>
            <div className="rl-agent-config-grid">
              <div>
                <span>Company</span>
                <strong>{config.company || '—'}</strong>
              </div>
              <div>
                <span>Year</span>
                <strong>{config.year || '—'}</strong>
              </div>
              <div>
                <span>Ticker</span>
                <strong>{config.ticker || '—'}</strong>
              </div>
              <div>
                <span>Industry</span>
                <strong>{config.industry || '—'}</strong>
              </div>
            </div>
          </article>

          <article className="card rl-agent-side-card">
            <p className="section-title">Workspace Modules</p>
            <div className="rl-agent-link-grid">
              {MODULE_LINKS.map((m) => (
                <Link key={m.label} to={m.to}>
                  <span>{m.icon}</span>
                  <span>{m.label}</span>
                </Link>
              ))}
            </div>
          </article>
        </aside>
      </div>

      {lastReport ? (
        <section className="rl-agent-summary-grid">
          <article className="card p-5">
            <p className="section-title">Priority Snapshot</p>
            <div className="rl-agent-priority-grid">
              <div>
                <span>High</span>
                <strong>{lastReport?.priority_matrix?.high?.count ?? 0}</strong>
              </div>
              <div>
                <span>Medium</span>
                <strong>{lastReport?.priority_matrix?.medium?.count ?? 0}</strong>
              </div>
              <div>
                <span>Low</span>
                <strong>{lastReport?.priority_matrix?.low?.count ?? 0}</strong>
              </div>
            </div>
          </article>
          <article className="card p-5">
            <p className="section-title">Executive Summary</p>
            <p className="rl-agent-exec-summary">
              {lastReport?.executive_summary || 'No summary available from the last run.'}
            </p>
          </article>
        </section>
      ) : null}
    </div>
  )
}
