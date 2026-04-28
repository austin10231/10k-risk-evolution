import React, { useEffect, useMemo, useState } from 'react'
import { get } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'

const TABS = [
  { key: 'overview', label: 'Risk Overview' },
  { key: 'category', label: 'Category Analysis' },
  { key: 'market', label: 'Market Performance' },
]

function heatColor(value, maxValue) {
  const v = Number(value || 0)
  const max = Number(maxValue || 0)
  if (!v || !max) return '#f1f5f9'
  const ratio = v / max
  if (ratio >= 0.85) return '#ef4444'
  if (ratio >= 0.65) return '#f97316'
  if (ratio >= 0.45) return '#f59e0b'
  if (ratio >= 0.25) return '#84cc16'
  return '#22c55e'
}

export default function DashboardPage() {
  const { config } = useGlobalConfig()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState(null)
  const [records, setRecords] = useState([])
  const [activeTab, setActiveTab] = useState('overview')
  const [industry, setIndustry] = useState('All Industries')

  const load = () => {
    let mounted = true
    setLoading(true)
    setError('')
    Promise.all([get('/api/dashboard/summary'), get('/api/records?include_result=1')])
      .then(([summaryRes, recordsRes]) => {
        if (!mounted) return
        setData(summaryRes?.data || null)
        setRecords(Array.isArray(recordsRes?.items) ? recordsRes.items : [])
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
  }

  useEffect(() => {
    const off = load()
    return off
  }, [])

  const rating = data?.rating_breakdown || {}
  const topCategoriesRaw = data?.top_categories || []
  const yearlyRaw = data?.yearly_records || []
  const recentRaw = data?.recent_records || []

  const industryOptions = useMemo(() => {
    const s = new Set()
    records.forEach((r) => {
      const v = String(r.industry || '').trim()
      if (v) s.add(v)
    })
    return ['All Industries', ...Array.from(s).sort((a, b) => a.localeCompare(b))]
  }, [records])

  useEffect(() => {
    if (!industryOptions.includes(industry)) setIndustry('All Industries')
  }, [industryOptions, industry])

  useEffect(() => {
    if (!config.industry) return
    if (industryOptions.includes(config.industry)) setIndustry(config.industry)
  }, [config.industry, industryOptions])

  const filteredRecords = useMemo(() => {
    if (industry === 'All Industries') return records
    return records.filter((r) => String(r.industry || '').trim() === industry)
  }, [records, industry])

  const years = useMemo(
    () => Array.from(new Set(filteredRecords.map((r) => Number(r.year)).filter(Number.isFinite))).sort((a, b) => a - b),
    [filteredRecords],
  )
  const companies = useMemo(
    () => Array.from(new Set(filteredRecords.map((r) => String(r.company || '').trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b)),
    [filteredRecords],
  )
  const totalRiskItems = useMemo(
    () => filteredRecords.reduce((sum, r) => sum + Number(r.risk_items || 0), 0),
    [filteredRecords],
  )

  const metricTiles = [
    ['COMPANIES', companies.length, '#1e40af'],
    ['YEARS COVERED', years.length > 0 ? `${years[0]}–${years[years.length - 1]}` : '—', '#1e40af'],
    ['TOTAL FILINGS', filteredRecords.length, '#6366f1'],
    ['TOTAL RISK ITEMS', totalRiskItems, '#dc2626'],
  ]

  const topCategories = useMemo(() => topCategoriesRaw.slice(0, 10), [topCategoriesRaw])
  const yearly = useMemo(() => yearlyRaw.slice().sort((a, b) => Number(a.year) - Number(b.year)), [yearlyRaw])
  const recent = useMemo(() => {
    if (industry === 'All Industries') return recentRaw
    return recentRaw.filter((r) => String(r.industry || '').trim() === industry)
  }, [recentRaw, industry])

  const heat = useMemo(() => {
    const byKey = new Map()
    filteredRecords.forEach((r) => {
      const c = String(r.company || '').trim()
      const y = Number(r.year)
      if (!c || !Number.isFinite(y)) return
      const k = `${c}__${y}`
      const prev = byKey.get(k)
      if (!prev || String(r.created_at || '') > String(prev.created_at || '')) byKey.set(k, r)
    })

    const companyMax = new Map()
    byKey.forEach((r) => {
      const c = String(r.company || '').trim()
      const val = Number(r.risk_items || 0)
      companyMax.set(c, Math.max(companyMax.get(c) || 0, val))
    })

    const orderedCompanies = Array.from(companyMax.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([c]) => c)

    let maxCell = 0
    const matrix = orderedCompanies.map((c) =>
      years.map((y) => {
        const rec = byKey.get(`${c}__${y}`)
        const v = Number(rec?.risk_items || 0)
        maxCell = Math.max(maxCell, v)
        return v
      }),
    )
    return { companies: orderedCompanies, years, matrix, maxCell }
  }, [filteredRecords, years])

  return (
    <div className="rl-page-shell rl-up-page">
      <section className="rl-up-header">
        <div className="page-header !mb-0">
          <div className="page-header-left rl-up-title-block">
            <span className="page-icon">📈</span>
            <div>
              <p className="page-title">Dashboard</p>
              <p className="page-subtitle">Risk heatmap and category ranking across all filings</p>
            </div>
          </div>
        </div>
      </section>

      <section className="card p-5">
        <div className="grid gap-3 md:grid-cols-[1fr_auto_auto] md:items-end">
          <div />
          <div>
            <label className="section-title">Industry Group</label>
            <select className="input mt-2 min-w-[260px]" value={industry} onChange={(e) => setIndustry(e.target.value)}>
              {industryOptions.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
          <button className="btn-secondary" onClick={load} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      {error ? <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div> : null}

      <div className="rl-tabs">
        {TABS.map((t) => (
          <button key={t.key} className={`rl-tab-btn ${activeTab === t.key ? 'active' : ''}`} onClick={() => setActiveTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === 'overview' ? (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {metricTiles.map(([k, v, color]) => (
              <div key={k} className="metric-card">
                <p className="metric-label">{k}</p>
                <p className="metric-value" style={{ color }}>
                  {loading ? '…' : v}
                </p>
              </div>
            ))}
          </section>

          <section className="card p-5">
            <div className="section-headline">
              <div className="section-rail" />
              <div>
                <p className="section-title-strong">Risk Heatmap</p>
                <p className="section-sub">Risk intensity proxy by company and year (based on risk items).</p>
              </div>
            </div>
            {heat.companies.length === 0 || heat.years.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
                No heatmap data available for the selected scope.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead>
                    <tr>
                      <th className="w-44 py-2 pr-3 text-left text-xs font-bold uppercase tracking-[0.08em] text-slate-500">Company</th>
                      {heat.years.map((y) => (
                        <th key={y} className="py-2 px-1 text-center text-xs font-bold uppercase tracking-[0.08em] text-slate-500">
                          {y}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {heat.companies.map((c, rowIdx) => (
                      <tr key={c} className="border-t border-slate-100">
                        <td className="py-2 pr-3 font-semibold text-slate-800">{c}</td>
                        {heat.matrix[rowIdx].map((v, colIdx) => (
                          <td key={`${c}-${heat.years[colIdx]}`} className="py-2 px-1">
                            <div className="heatmap-cell" style={{ backgroundColor: heatColor(v, heat.maxCell) }}>
                              {v > 0 ? v : '-'}
                            </div>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
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
              <p className="section-title">Recent Filings</p>
              <div className="mt-3 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-xs uppercase tracking-[0.12em] text-slate-500">
                      <th className="py-2 pr-3">Company</th>
                      <th className="py-2 pr-3">Year</th>
                      <th className="py-2 pr-3">Industry</th>
                      <th className="py-2 pr-3">Risk Items</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr>
                        <td className="py-3 text-slate-500" colSpan={4}>
                          Loading...
                        </td>
                      </tr>
                    ) : null}
                    {!loading && recent.length === 0 ? (
                      <tr>
                        <td className="py-3 text-slate-500" colSpan={4}>
                          No records found.
                        </td>
                      </tr>
                    ) : null}
                    {!loading &&
                      recent.slice(0, 10).map((r) => (
                        <tr key={r.record_id} className="border-b border-slate-100">
                          <td className="py-2 pr-3 font-semibold text-slate-800">{r.company}</td>
                          <td className="py-2 pr-3">{r.year}</td>
                          <td className="py-2 pr-3">{r.industry || '—'}</td>
                          <td className="py-2 pr-3">{r.risk_items ?? 0}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </>
      ) : null}

      {activeTab === 'category' ? (
        <section className="grid gap-4 xl:grid-cols-2">
          <div className="card p-5">
            <p className="section-title">Risk Category Ranking</p>
            <p className="mt-1 text-xs text-slate-500">Most frequent risk categories across filings.</p>
            <div className="mt-3 space-y-2">
              {loading ? <p className="text-sm text-slate-500">Loading…</p> : null}
              {!loading && topCategories.length === 0 ? <p className="text-sm text-slate-500">No data yet.</p> : null}
              {!loading &&
                topCategories.map((row) => (
                  <div key={row.category} className="flex items-center justify-between rounded-xl border border-slate-200 px-3 py-2">
                    <p className="text-sm font-semibold text-slate-700">{row.category}</p>
                    <p className="text-sm font-extrabold text-brand-700">{row.count}</p>
                  </div>
                ))}
            </div>
          </div>

          <div className="card p-5">
            <p className="section-title">Yearly Filing Trend</p>
            <div className="mt-3 space-y-2">
              {yearly.map((row) => {
                const max = Math.max(...yearly.map((r) => Number(r.count || 0)), 1)
                const width = `${Math.round((Number(row.count || 0) / max) * 100)}%`
                return (
                  <div key={row.year}>
                    <div className="mb-1 flex items-center justify-between text-xs font-semibold text-slate-600">
                      <span>{row.year}</span>
                      <span>{row.count}</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100">
                      <div className="h-2 rounded-full bg-indigo-500" style={{ width }} />
                    </div>
                  </div>
                )
              })}
              {yearly.length === 0 ? <p className="text-sm text-slate-500">No trend data yet.</p> : null}
            </div>
          </div>
        </section>
      ) : null}

      {activeTab === 'market' ? (
        <section className="card p-5">
          <p className="section-title">Market Performance</p>
          <div className="mt-3 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6">
            <p className="text-sm font-semibold text-slate-700">Market-linked charts are paused for fast dashboard navigation.</p>
            <p className="mt-1 text-sm text-slate-500">You can use the dedicated Stock page for detailed ticker analysis and overlays.</p>
          </div>
        </section>
      ) : null}
    </div>
  )
}
