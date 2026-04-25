import React, { useMemo, useState } from 'react'
import { post } from '../lib/api'

const STARTER_PROMPTS = [
  'What are Apple\'s top risks in 2024?',
  'Compare NVIDIA and Microsoft risk profiles in 2024.',
  'Summarize urgent risks for Tesla and give recommendations.',
]

export default function AgentPage() {
  const [query, setQuery] = useState('')
  const [company, setCompany] = useState('')
  const [year, setYear] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: 'I am ready. Ask directly. I will use available filing context and answer in your language.',
      report: null,
    },
  ])

  const canSend = query.trim().length > 0 && !loading

  const send = async (forcedQuery) => {
    const userText = (forcedQuery ?? query).trim()
    if (!userText) return

    setMessages((prev) => [...prev, { role: 'user', text: userText, report: null }])
    setQuery('')
    setLoading(true)
    setError('')

    try {
      const payload = {
        user_query: userText,
        company: company.trim(),
        year: year ? Number(year) : 0,
      }
      const res = await post('/api/agent/query', payload)
      const report = res?.report || res?.result || {}
      const answer = report?.direct_answer || report?.executive_summary || 'No answer generated.'
      setMessages((prev) => [...prev, { role: 'assistant', text: answer, report }])
    } catch (e) {
      setError(e.message || 'Agent request failed')
    } finally {
      setLoading(false)
    }
  }

  const lastReport = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].report) return messages[i].report
    }
    return null
  }, [messages])

  return (
    <div className="space-y-4">
      <section className="card p-5">
        <p className="section-title">Risk Agent</p>
        <h3 className="mt-1 text-2xl font-extrabold text-slate-900">Chat-first Analyst Interface</h3>
        <p className="mt-1 text-sm text-slate-500">English UI, multilingual understanding and answers.</p>
      </section>

      {error && <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div>}

      <section className="card p-5">
        <div className="grid gap-3 md:grid-cols-3">
          <div>
            <label className="section-title">Company (optional)</label>
            <input className="input mt-2" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Apple" />
          </div>
          <div>
            <label className="section-title">Year (optional)</label>
            <input className="input mt-2" value={year} onChange={(e) => setYear(e.target.value.replace(/[^0-9]/g, ''))} placeholder="2024" />
          </div>
          <div className="flex flex-wrap items-end gap-2">
            {STARTER_PROMPTS.map((p) => (
              <button key={p} className="btn-secondary text-xs" onClick={() => send(p)} disabled={loading}>
                {p}
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="card p-5">
        <div className="space-y-3">
          {messages.map((m, idx) => (
            <div
              key={idx}
              className={`rounded-xl border px-4 py-3 text-sm leading-6 ${
                m.role === 'user'
                  ? 'ml-8 border-brand-200 bg-brand-50 text-brand-900'
                  : 'mr-8 border-slate-200 bg-white text-slate-700'
              }`}
            >
              <p className="mb-1 text-xs font-extrabold uppercase tracking-[0.12em] text-slate-500">{m.role}</p>
              <p className="whitespace-pre-wrap">{m.text}</p>
            </div>
          ))}
        </div>

        <div className="mt-4 flex gap-2">
          <textarea
            className="input min-h-[92px] flex-1"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask anything about risk profile, comparison, priorities, or recommendations…"
          />
          <button className="btn-primary h-fit" disabled={!canSend} onClick={() => send()}>
            {loading ? 'Thinking…' : 'Send'}
          </button>
        </div>
      </section>

      {lastReport && (
        <section className="grid gap-4 xl:grid-cols-2">
          <div className="card p-5">
            <p className="section-title">Priority Matrix</p>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center text-sm">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="font-bold">High</p>
                <p className="text-xl font-extrabold text-red-600">{lastReport?.priority_matrix?.high?.count ?? 0}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="font-bold">Medium</p>
                <p className="text-xl font-extrabold text-amber-600">{lastReport?.priority_matrix?.medium?.count ?? 0}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="font-bold">Low</p>
                <p className="text-xl font-extrabold text-green-600">{lastReport?.priority_matrix?.low?.count ?? 0}</p>
              </div>
            </div>
          </div>

          <div className="card p-5">
            <p className="section-title">Executive Summary</p>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{lastReport?.executive_summary || 'No summary available.'}</p>
          </div>
        </section>
      )}
    </div>
  )
}
