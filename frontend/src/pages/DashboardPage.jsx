import React, { useEffect, useMemo, useState } from 'react'
import { get } from '../lib/api'

export default function DashboardPage() {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState(null)

  useEffect(() => {
    let mounted = true
    setLoading(true)
    setError('')
    get('/api/dashboard/summary')
      .then((res) => {
        if (!mounted) return
        setData(res?.data || null)
      })
      .catch((e) => {
        if (!mounted) return
        setError(e.message || 'Failed to load dashboard summary')
      })
      .finally(() => {
        if (!mounted) return
        setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  const metrics = data?.metrics || {}
  const rating = data?.rating_breakdown || {}
  const topCategories = data?.top_categories || []
  const recent = data?.recent_records || []

  const metricTiles = useMemo(
    () => [
      ['Records', metrics.records ?? 0],
      ['Companies', metrics.companies ?? 0],
      ['Years Covered', metrics.years_covered ?? 0],
      ['Risk Items', metrics.risk_items ?? 0],
      ['Agent Reports', metrics.agent_reports ?? 0],
    ],
    [metrics],
  )

  return (
    <div className="space-y-4">
      {error && <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div>}

      <section className="card p-5">
        <p className="section-title">Overview</p>
        <h3 className="mt-1 text-2xl font-extrabold text-slate-900">Portfolio Snapshot</h3>
        <p className="mt-1 text-sm text-slate-500">Aggregated from filing index + risk results + agent reports.</p>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {metricTiles.map(([k, v]) => (
          <div key={k} className="card p-4">
            <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-slate-500">{k}</p>
            <p className="mt-2 text-2xl font-extrabold text-slate-900">{loading ? '…' : v}</p>
          </div>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <div className="card p-5">
          <p className="section-title">Priority Breakdown</p>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center text-sm">
            {['High', 'Medium-High', 'Medium', 'Medium-Low', 'Low', 'Unknown'].map((level) => (
              <div key={level} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="font-extrabold text-slate-800">{level}</p>
                <p className="mt-1 text-lg font-extrabold text-brand-700">{loading ? '…' : rating[level] ?? 0}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-5">
          <p className="section-title">Top Risk Categories</p>
          <div className="mt-3 space-y-2">
            {loading && <p className="text-sm text-slate-500">Loading…</p>}
            {!loading && topCategories.length === 0 && <p className="text-sm text-slate-500">No data yet.</p>}
            {!loading &&
              topCategories.map((row) => (
                <div key={row.category} className="flex items-center justify-between rounded-xl border border-slate-200 px-3 py-2">
                  <p className="text-sm font-semibold text-slate-700">{row.category}</p>
                  <p className="text-sm font-extrabold text-brand-700">{row.count}</p>
                </div>
              ))}
          </div>
        </div>
      </section>

      <section className="card p-5">
        <p className="section-title">Recent Filings</p>
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-[0.12em] text-slate-500">
                <th className="py-2 pr-3">Company</th>
                <th className="py-2 pr-3">Year</th>
                <th className="py-2 pr-3">Industry</th>
                <th className="py-2 pr-3">Risk Items</th>
                <th className="py-2 pr-3">Created</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td className="py-3 text-slate-500" colSpan={5}>
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && recent.length === 0 && (
                <tr>
                  <td className="py-3 text-slate-500" colSpan={5}>
                    No records found.
                  </td>
                </tr>
              )}
              {!loading &&
                recent.map((r) => (
                  <tr key={r.record_id} className="border-b border-slate-100">
                    <td className="py-2 pr-3 font-semibold text-slate-800">{r.company}</td>
                    <td className="py-2 pr-3">{r.year}</td>
                    <td className="py-2 pr-3">{r.industry}</td>
                    <td className="py-2 pr-3">{r.risk_items ?? 0}</td>
                    <td className="py-2 pr-3 text-slate-500">{String(r.created_at || '').replace('T', ' ').slice(0, 19)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
