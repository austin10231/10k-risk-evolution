import React, { useMemo, useState } from 'react'
import { get } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'

function formatDate(value) {
  if (!value) return 'N/A'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString()
}

export default function NewsPage() {
  const { config } = useGlobalConfig()
  const [company, setCompany] = useState(config.company || 'Apple')
  const [ticker, setTicker] = useState(config.ticker || 'AAPL')
  const [days, setDays] = useState(7)
  const [limit, setLimit] = useState(6)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [newsMode, setNewsMode] = useState('Ticker + Company')

  React.useEffect(() => {
    if (config.company) setCompany(config.company)
  }, [config.company])

  React.useEffect(() => {
    if (config.ticker) setTicker(config.ticker)
  }, [config.ticker])

  const run = async (nextLimit = limit) => {
    setLoading(true)
    setError('')
    try {
      const q = new URLSearchParams({
        company,
        ticker,
        days: String(days),
        limit: String(nextLimit),
      })
      const res = await get(`/api/news?${q.toString()}`)
      setItems(Array.isArray(res?.items) ? res.items : [])
      setLimit(nextLimit)
    } catch (e) {
      setError(e.message || 'Failed to load news')
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  const latestHeadlineTime = useMemo(() => {
    if (!items.length) return 'N/A'
    return formatDate(items[0]?.published_at)
  }, [items])

  const bySource = useMemo(() => {
    const map = new Map()
    items.forEach((item) => {
      const k = String(item.source || 'Unknown')
      map.set(k, (map.get(k) || 0) + 1)
    })
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1])
  }, [items])

  return (
    <div className="rl-page-shell">
      <section className="card p-5">
        <div className="page-header !mb-0 !pb-0">
          <div className="page-header-left">
            <span className="page-icon">📰</span>
            <div>
              <p className="page-title">News</p>
              <p className="page-subtitle">Track recent company headlines with optional risk-linked AI summary</p>
            </div>
          </div>
          <div className="rl-config-chip-row">
            <span className="rl-chip muted">Window: {days}D</span>
            <span className="rl-chip muted">Mode: {newsMode}</span>
          </div>
        </div>
      </section>

      {error ? <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div> : null}

      <section className="card p-5">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div>
            <label className="section-title">Company</label>
            <input className="input mt-2" value={company} onChange={(e) => setCompany(e.target.value)} />
          </div>
          <div>
            <label className="section-title">Ticker</label>
            <input className="input mt-2" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} />
          </div>
          <div>
            <label className="section-title">Window</label>
            <div className="rl-segment mt-2">
              {[7, 30].map((d) => (
                <button
                  key={d}
                  className={days === d ? 'active' : ''}
                  onClick={() => setDays(d)}
                >
                  {d}D
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-end">
            <button className="btn-primary w-full" onClick={() => run(6)} disabled={loading}>
              {loading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div className="metric-card">
          <p className="metric-label">Articles Loaded</p>
          <p className="metric-value">{items.length}</p>
        </div>
        <div className="metric-card">
          <p className="metric-label">Time Window</p>
          <p className="metric-value">{days} days</p>
        </div>
        <div className="metric-card">
          <p className="metric-label">Latest Headline</p>
          <p className="metric-value !text-[1rem]">{latestHeadlineTime}</p>
        </div>
        <div className="metric-card">
          <p className="metric-label">Top Source</p>
          <p className="metric-value !text-[1rem]">{bySource[0] ? `${bySource[0][0]} (${bySource[0][1]})` : '—'}</p>
        </div>
        <div className="metric-card">
          <p className="metric-label">Risk Link</p>
          <p className="metric-value !text-[1rem]">Ready</p>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        {items.map((item, idx) => (
          <article key={`${item.url}-${idx}`} className="card p-5">
            <div className="rl-news-head">
              <span className="rl-news-source">{item.source || 'Unknown'}</span>
              <span className="rl-news-time">{formatDate(item.published_at)}</span>
            </div>
            <h4 className="rl-news-title">{item.title || 'Untitled'}</h4>
            <p className="rl-news-summary">{item.summary || 'No summary.'}</p>
            {item.url ? (
              <a className="rl-news-link" href={item.url} target="_blank" rel="noreferrer">
                Open source →
              </a>
            ) : null}
          </article>
        ))}
        {!loading && items.length === 0 ? <div className="card p-4 text-sm text-slate-500">No recent news found. Run a query above.</div> : null}
      </section>

      <section className="card p-5">
        <div className="flex flex-wrap items-center gap-3">
          <button className="btn-secondary" onClick={() => run(limit + 6)} disabled={loading}>
            Load More
          </button>
          <p className="text-xs text-slate-500">
            Marketaux free tier may return fewer items per request. The page combines multiple fetches as you increase limit.
          </p>
        </div>
      </section>
    </div>
  )
}
