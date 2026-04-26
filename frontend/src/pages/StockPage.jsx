import React, { useMemo, useState } from 'react'
import { get } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'

function fmtNumber(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return Number(v).toLocaleString()
}

function fmtPrice(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return `$${Number(v).toFixed(2)}`
}

function fmtPct(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return `${Number(v).toFixed(2)}%`
}

function rangeSize(key) {
  if (key === '1W') return 5
  if (key === '1M') return 22
  if (key === '3M') return 66
  if (key === '6M') return 132
  return 252
}

export default function StockPage() {
  const { config } = useGlobalConfig()
  const [ticker, setTicker] = useState(config.ticker || 'AAPL')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [data, setData] = useState(null)
  const [rangeKey, setRangeKey] = useState('1M')

  React.useEffect(() => {
    if (!config.ticker) return
    setTicker(config.ticker)
  }, [config.ticker])

  const run = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await get(`/api/stock/quote?ticker=${encodeURIComponent(ticker)}`)
      setData(res?.data || null)
    } catch (e) {
      setError(e.message || 'Failed to load stock quote')
      setData(null)
    } finally {
      setLoading(false)
    }
  }

  const historyPreview = useMemo(() => {
    const h = Array.isArray(data?.history) ? data.history : []
    const n = rangeSize(rangeKey)
    return h.length <= n ? h : h.slice(-n)
  }, [data, rangeKey])

  return (
    <div className="rl-page-shell">
      <section className="card p-5">
        <div className="page-header !mb-0">
          <div className="page-header-left">
            <span className="page-icon">💹</span>
            <div>
              <p className="page-title">Stock</p>
              <p className="page-subtitle">Search market data and overlay your system risk signals</p>
            </div>
          </div>
          <button className="btn-secondary" onClick={run} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      {error ? <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div> : null}

      <section className="card p-5">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-full md:w-[340px]">
            <label className="section-title">Search company or ticker</label>
            <input className="input mt-2" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="e.g. AAPL" />
          </div>
          <button className="btn-primary" onClick={run} disabled={loading}>
            {loading ? 'Loading…' : 'Get Quote'}
          </button>
        </div>
        <p className="rl-note mt-3">Popular: AAPL, GOOGL, MSFT, AMZN, NVDA</p>
      </section>

      {data ? (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <div className="metric-card">
              <p className="metric-label">Current Price</p>
              <p className="metric-value">{fmtPrice(data.price)}</p>
            </div>
            <div className="metric-card">
              <p className="metric-label">Today</p>
              <p className="metric-value" style={{ color: Number(data.change_percent || 0) >= 0 ? '#16a34a' : '#dc2626' }}>
                {fmtPct(data.change_percent)}
              </p>
            </div>
            <div className="metric-card">
              <p className="metric-label">Change</p>
              <p className="metric-value">{fmtPrice(data.change)}</p>
            </div>
            <div className="metric-card">
              <p className="metric-label">Market Cap</p>
              <p className="metric-value !text-[1rem]">{fmtNumber(data.market_cap)}</p>
            </div>
            <div className="metric-card">
              <p className="metric-label">PE Ratio</p>
              <p className="metric-value !text-[1rem]">{fmtNumber(data.pe_ratio)}</p>
            </div>
            <div className="metric-card">
              <p className="metric-label">52W High / Low</p>
              <p className="metric-value !text-[0.95rem]">
                {fmtPrice(data.high_52)} / {fmtPrice(data.low_52)}
              </p>
            </div>
          </section>

          <section className="card p-5">
            <label className="section-title">Time Range</label>
            <div className="rl-segment mt-2">
              {['1W', '1M', '3M', '6M', '1Y'].map((k) => (
                <button key={k} className={rangeKey === k ? 'active' : ''} onClick={() => setRangeKey(k)}>
                  {k}
                </button>
              ))}
            </div>

            <div className="mt-4">
              <div className="rl-section-header">Price History ({rangeKey})</div>
              <div className="mt-2 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs uppercase tracking-[0.1em] text-slate-500">
                      <th className="py-2 pr-3">Date</th>
                      <th className="py-2 pr-3">Close</th>
                    </tr>
                  </thead>
                  <tbody>
                    {historyPreview.map((row) => (
                      <tr key={row.date} className="border-b border-slate-100">
                        <td className="py-2 pr-3">{row.date}</td>
                        <td className="py-2 pr-3 font-semibold">{fmtPrice(row.close)}</td>
                      </tr>
                    ))}
                    {historyPreview.length === 0 ? (
                      <tr>
                        <td className="py-3 text-slate-500" colSpan={2}>
                          No history in selected range.
                        </td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </>
      ) : null}
    </div>
  )
}
