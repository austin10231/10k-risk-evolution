import React, { useMemo, useState } from 'react'
import { get } from '../lib/api'

function fmtNumber(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return Number(v).toLocaleString()
}

function fmtPrice(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return `$${Number(v).toFixed(2)}`
}

export default function StockPage() {
  const [ticker, setTicker] = useState('AAPL')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [data, setData] = useState(null)

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
    const h = data?.history || []
    if (h.length <= 8) return h
    return h.slice(-8)
  }, [data])

  return (
    <div className="space-y-4">
      <section className="card p-5">
        <p className="section-title">Stock Intelligence</p>
        <h3 className="mt-1 text-2xl font-extrabold text-slate-900">Ticker Snapshot</h3>
      </section>

      {error && <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div>}

      <section className="card p-5">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-full md:w-64">
            <label className="section-title">Ticker</label>
            <input className="input mt-2" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} />
          </div>
          <button className="btn-primary" onClick={run} disabled={loading}>{loading ? 'Loading…' : 'Get Quote'}</button>
        </div>
      </section>

      {data && (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <div className="card p-4"><p className="section-title">Symbol</p><p className="mt-2 text-xl font-extrabold">{data.symbol}</p></div>
            <div className="card p-4"><p className="section-title">Price</p><p className="mt-2 text-xl font-extrabold">{fmtPrice(data.price)}</p></div>
            <div className="card p-4"><p className="section-title">Change</p><p className="mt-2 text-xl font-extrabold">{fmtPrice(data.change)}</p></div>
            <div className="card p-4"><p className="section-title">Change %</p><p className="mt-2 text-xl font-extrabold">{data.change_percent != null ? `${Number(data.change_percent).toFixed(2)}%` : '—'}</p></div>
            <div className="card p-4"><p className="section-title">Market Cap</p><p className="mt-2 text-xl font-extrabold">{fmtNumber(data.market_cap)}</p></div>
          </section>

          <section className="card p-5">
            <p className="section-title">Recent History (1Y sample)</p>
            <div className="mt-3 overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-xs uppercase tracking-[0.12em] text-slate-500">
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
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
