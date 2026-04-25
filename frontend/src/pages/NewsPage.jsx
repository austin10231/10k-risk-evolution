import React, { useState } from 'react'
import { get } from '../lib/api'

export default function NewsPage() {
  const [company, setCompany] = useState('Apple')
  const [ticker, setTicker] = useState('AAPL')
  const [days, setDays] = useState(30)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const run = async () => {
    setLoading(true)
    setError('')
    try {
      const q = new URLSearchParams({
        company,
        ticker,
        days: String(days),
        limit: '20',
      })
      const res = await get(`/api/news?${q.toString()}`)
      setItems(res?.items || [])
    } catch (e) {
      setError(e.message || 'Failed to load news')
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <section className="card p-5">
        <p className="section-title">News Intelligence</p>
        <h3 className="mt-1 text-2xl font-extrabold text-slate-900">Company News Feed</h3>
      </section>

      {error && <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div>}

      <section className="card grid gap-3 p-5 md:grid-cols-4">
        <div>
          <label className="section-title">Company</label>
          <input className="input mt-2" value={company} onChange={(e) => setCompany(e.target.value)} />
        </div>
        <div>
          <label className="section-title">Ticker</label>
          <input className="input mt-2" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} />
        </div>
        <div>
          <label className="section-title">Days</label>
          <input className="input mt-2" type="number" min={1} max={365} value={days} onChange={(e) => setDays(Number(e.target.value || 30))} />
        </div>
        <div className="flex items-end">
          <button className="btn-primary w-full" onClick={run} disabled={loading}>{loading ? 'Loading…' : 'Fetch News'}</button>
        </div>
      </section>

      <section className="space-y-3">
        {items.map((item, idx) => (
          <article key={`${item.url}-${idx}`} className="card p-5">
            <h4 className="text-lg font-extrabold text-slate-900">{item.title}</h4>
            <p className="mt-2 text-sm leading-6 text-slate-700">{item.summary || 'No summary.'}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span className="rounded-full border border-slate-300 px-2 py-0.5">{item.source}</span>
              <span>{item.published_at}</span>
              {item.url && (
                <a className="font-bold text-brand-600 hover:text-brand-700" href={item.url} target="_blank" rel="noreferrer">
                  Open source →
                </a>
              )}
            </div>
          </article>
        ))}
        {!loading && items.length === 0 && (
          <div className="card p-4 text-sm text-slate-500">No news yet. Run a query above.</div>
        )}
      </section>
    </div>
  )
}
