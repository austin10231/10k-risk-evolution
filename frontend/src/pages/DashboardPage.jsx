import React, { useEffect, useMemo, useState } from 'react'
import { get } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'

const TABS = [
  { key: 'pulse', label: 'Risk Pulse' },
  { key: 'category', label: 'Category Intelligence' },
]

function priorityHeatColor(rpi, total) {
  const score = Number(rpi || 0)
  const cnt = Number(total || 0)
  if (!cnt) return '#f8fafc'
  if (score >= 78) return '#ef4444'
  if (score >= 60) return '#f97316'
  if (score >= 42) return '#f59e0b'
  if (score >= 24) return '#84cc16'
  return '#22c55e'
}

function safeNumber(v, fallback = 0) {
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

export default function DashboardPage() {
  const { config } = useGlobalConfig()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState(null)
  const [activeTab, setActiveTab] = useState('pulse')
  const [industry, setIndustry] = useState('All Industries')
  const [selectedCategory, setSelectedCategory] = useState('')

  const load = () => {
    let mounted = true
    setLoading(true)
    setError('')
    get('/api/dashboard/summary')
      .then((summaryRes) => {
        if (!mounted) return
        setData(summaryRes?.data || null)
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

  const industryOptions = useMemo(() => {
    const fromApi = Array.isArray(data?.industry_options) ? data.industry_options : []
    const fromScopes = Object.keys(data?.scopes || {}).filter((k) => k !== '__all__')
    const uniq = Array.from(new Set([...fromApi, ...fromScopes].filter(Boolean))).sort((a, b) => a.localeCompare(b))
    return ['All Industries', ...uniq]
  }, [data])

  useEffect(() => {
    if (!industryOptions.includes(industry)) setIndustry('All Industries')
  }, [industryOptions, industry])

  useEffect(() => {
    if (!config.industry) return
    if (industryOptions.includes(config.industry)) setIndustry(config.industry)
  }, [config.industry, industryOptions])

  const scopeKey = industry === 'All Industries' ? '__all__' : industry
  const scopeData = useMemo(() => {
    const scopes = data?.scopes || {}
    return scopes[scopeKey] || scopes.__all__ || null
  }, [data, scopeKey])

  const metrics = scopeData?.metrics || data?.metrics || {}
  const priorityHeatmap = scopeData?.priority_heatmap || { years: [], companies: [], cells: [], max_rpi: 0, avg_rpi: 0 }
  const priorityTotals = scopeData?.priority_totals || { high: 0, medium: 0, low: 0 }
  const topCategories = scopeData?.top_categories || []
  const categoryYearly = scopeData?.category_yearly || []
  const yearlyRecords = scopeData?.yearly_records || []
  const recent = useMemo(() => {
    const rows = Array.isArray(data?.recent_records) ? data.recent_records : []
    if (industry === 'All Industries') return rows
    return rows.filter((r) => String(r.industry || '').trim() === industry)
  }, [data, industry])

  const heatCellMap = useMemo(() => {
    const m = new Map()
    ;(priorityHeatmap.cells || []).forEach((cell) => {
      const k = `${cell.company}__${cell.year}`
      m.set(k, cell)
    })
    return m
  }, [priorityHeatmap.cells])

  const companiesOrdered = useMemo(() => {
    const list = Array.isArray(priorityHeatmap.companies) ? priorityHeatmap.companies : []
    if (list.length > 0) return list
    return Array.from(
      new Set((priorityHeatmap.cells || []).map((row) => String(row.company || '').trim()).filter(Boolean)),
    ).sort((a, b) => a.localeCompare(b))
  }, [priorityHeatmap.companies, priorityHeatmap.cells])

  const yearsOrdered = useMemo(() => {
    const list = Array.isArray(priorityHeatmap.years) ? priorityHeatmap.years : []
    if (list.length > 0) return list
    return Array.from(
      new Set((priorityHeatmap.cells || []).map((row) => Number(row.year)).filter(Number.isFinite)),
    ).sort((a, b) => a - b)
  }, [priorityHeatmap.years, priorityHeatmap.cells])

  useEffect(() => {
    const options = topCategories.map((x) => String(x.category || '').trim()).filter(Boolean)
    if (!options.length) {
      setSelectedCategory('')
      return
    }
    if (!selectedCategory || !options.includes(selectedCategory)) {
      setSelectedCategory(options[0])
    }
  }, [topCategories, selectedCategory])

  const selectedCategoryTrend = useMemo(() => {
    if (!selectedCategory) return []
    const found = categoryYearly.find((row) => String(row.category || '').trim() === selectedCategory)
    return Array.isArray(found?.yearly) ? found.yearly : []
  }, [categoryYearly, selectedCategory])

  const metricTiles = [
    ['FILINGS', safeNumber(metrics.records), '#1e40af'],
    ['COMPANIES', safeNumber(metrics.companies), '#2563eb'],
    ['RISK ITEMS', safeNumber(metrics.risk_items), '#7c3aed'],
    ['AGENT COVERAGE', `${safeNumber(metrics.agent_coverage_rate).toFixed(1)}%`, '#dc2626'],
  ]

  return (
    <div className="rl-page-shell rl-up-page">
      <section className="rl-up-header">
        <div className="page-header !mb-0">
          <div className="page-header-left rl-up-title-block">
            <span className="page-icon">📈</span>
            <div>
              <p className="page-title">Dashboard</p>
              <p className="page-subtitle">Priority-driven risk pulse and category intelligence across filings</p>
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

      {activeTab === 'pulse' ? (
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

          <section className="grid gap-4 xl:grid-cols-[1.7fr_1fr]">
            <div className="card p-5">
              <div className="section-headline">
                <div className="section-rail" />
                <div>
                  <p className="section-title-strong">Priority Heatmap</p>
                  <p className="section-sub">Agent priority pressure by company and filing year (cell text: H / M / L).</p>
                </div>
              </div>

              {companiesOrdered.length === 0 || yearsOrdered.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
                  No priority heatmap data available for the selected scope.
                </div>
              ) : (
                <div className="mt-3 overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr>
                        <th className="w-48 py-2 pr-3 text-left text-xs font-bold uppercase tracking-[0.08em] text-slate-500">Company</th>
                        {yearsOrdered.map((y) => (
                          <th key={y} className="py-2 px-1 text-center text-xs font-bold uppercase tracking-[0.08em] text-slate-500">
                            {y}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {companiesOrdered.map((c) => (
                        <tr key={c} className="border-t border-slate-100">
                          <td className="py-2 pr-3 font-semibold text-slate-800">{c}</td>
                          {yearsOrdered.map((y) => {
                            const cell = heatCellMap.get(`${c}__${y}`)
                            const high = safeNumber(cell?.high)
                            const medium = safeNumber(cell?.medium)
                            const low = safeNumber(cell?.low)
                            const total = safeNumber(cell?.total)
                            const rpi = safeNumber(cell?.rpi)
                            const bg = priorityHeatColor(rpi, total)
                            const topHigh = (cell?.top_high || []).slice(0, 2).join(' | ')
                            const title = total
                              ? `${c} ${y}\nHigh: ${high}, Medium: ${medium}, Low: ${low}\nRPI: ${rpi.toFixed(1)}\nTop high: ${topHigh || 'n/a'}`
                              : `${c} ${y}\nNo priority data`
                            return (
                              <td key={`${c}-${y}`} className="py-2 px-1">
                                <div
                                  className="mx-auto flex h-12 w-[78px] flex-col items-center justify-center rounded-lg border border-white/65 text-[10px] font-bold text-slate-800"
                                  style={{ backgroundColor: bg }}
                                  title={title}
                                >
                                  {total ? (
                                    <>
                                      <span className="text-[9px] font-black tracking-[0.03em]">H{high} M{medium} L{low}</span>
                                      <span className="mt-[2px] text-[9px] font-semibold text-slate-700">RPI {rpi.toFixed(0)}</span>
                                    </>
                                  ) : (
                                    <span className="text-[10px] text-slate-400">—</span>
                                  )}
                                </div>
                              </td>
                            )
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="card p-5">
              <p className="section-title">Priority Mix</p>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center text-sm">
                <div className="rounded-xl border border-red-200 bg-red-50 p-3">
                  <p className="font-extrabold text-red-600">High</p>
                  <p className="mt-1 text-lg font-extrabold text-red-700">{loading ? '…' : safeNumber(priorityTotals.high)}</p>
                </div>
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-3">
                  <p className="font-extrabold text-amber-600">Medium</p>
                  <p className="mt-1 text-lg font-extrabold text-amber-700">{loading ? '…' : safeNumber(priorityTotals.medium)}</p>
                </div>
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                  <p className="font-extrabold text-emerald-600">Low</p>
                  <p className="mt-1 text-lg font-extrabold text-emerald-700">{loading ? '…' : safeNumber(priorityTotals.low)}</p>
                </div>
              </div>

              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Scope Snapshot</p>
                <p className="mt-2 text-sm font-semibold text-slate-700">Average RPI: {safeNumber(priorityHeatmap.avg_rpi).toFixed(1)}</p>
                <p className="mt-1 text-sm text-slate-600">Rows with priority data: {safeNumber(metrics.records_with_priority)} / {safeNumber(metrics.records)}</p>
              </div>

              <div className="mt-4">
                <p className="section-title">Recent Filings</p>
                <div className="mt-2 space-y-2">
                  {loading ? <p className="text-sm text-slate-500">Loading…</p> : null}
                  {!loading && recent.length === 0 ? <p className="text-sm text-slate-500">No records in this scope.</p> : null}
                  {!loading &&
                    recent.slice(0, 6).map((r) => (
                      <div key={r.record_id} className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                        <p className="text-sm font-semibold text-slate-800">{r.company} · {r.year}</p>
                        <p className="mt-1 text-xs text-slate-500">{r.industry || '—'} · {safeNumber(r.risk_items)} risk items</p>
                      </div>
                    ))}
                </div>
              </div>
            </div>
          </section>
        </>
      ) : null}

      {activeTab === 'category' ? (
        <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          <div className="card p-5">
            <div className="section-headline">
              <div className="section-rail" />
              <div>
                <p className="section-title-strong">Category Ranking</p>
                <p className="section-sub">Most frequent extracted risk categories within the selected industry scope.</p>
              </div>
            </div>

            <div className="mt-3 space-y-2">
              {loading ? <p className="text-sm text-slate-500">Loading…</p> : null}
              {!loading && topCategories.length === 0 ? <p className="text-sm text-slate-500">No category data yet.</p> : null}
              {!loading &&
                topCategories.map((row) => {
                  const max = Math.max(...topCategories.map((r) => safeNumber(r.count)), 1)
                  const width = `${Math.max(6, Math.round((safeNumber(row.count) / max) * 100))}%`
                  return (
                    <div key={row.category} className="rounded-xl border border-slate-200 px-3 py-2">
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold text-slate-700">{row.category}</p>
                        <p className="text-sm font-extrabold text-brand-700">{safeNumber(row.count)}</p>
                      </div>
                      <div className="mt-2 h-2 rounded-full bg-slate-100">
                        <div className="h-2 rounded-full bg-indigo-500" style={{ width }} />
                      </div>
                    </div>
                  )
                })}
            </div>
          </div>

          <div className="card p-5">
            <p className="section-title">Category Trend</p>
            <p className="mt-1 text-xs text-slate-500">Track one category across filing years in the current scope.</p>

            <div className="mt-3">
              <label className="section-title">Category</label>
              <select
                className="input mt-2"
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                disabled={!topCategories.length}
              >
                {!topCategories.length ? <option value="">No categories</option> : null}
                {topCategories.map((row) => (
                  <option key={row.category} value={row.category}>
                    {row.category}
                  </option>
                ))}
              </select>
            </div>

            <div className="mt-4 space-y-2">
              {selectedCategoryTrend.map((row) => {
                const max = Math.max(...selectedCategoryTrend.map((r) => safeNumber(r.count)), 1)
                const width = `${Math.max(5, Math.round((safeNumber(row.count) / max) * 100))}%`
                return (
                  <div key={`${selectedCategory}-${row.year}`}>
                    <div className="mb-1 flex items-center justify-between text-xs font-semibold text-slate-600">
                      <span>{row.year}</span>
                      <span>{safeNumber(row.count)}</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100">
                      <div className="h-2 rounded-full bg-sky-500" style={{ width }} />
                    </div>
                  </div>
                )
              })}

              {!selectedCategoryTrend.length ? <p className="text-sm text-slate-500">No year trend available for this category.</p> : null}
            </div>

            <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Filing Trend</p>
              <div className="mt-2 space-y-2">
                {yearlyRecords.map((row) => (
                  <div key={`filing-${row.year}`} className="flex items-center justify-between text-sm">
                    <span className="font-semibold text-slate-700">{row.year}</span>
                    <span className="font-extrabold text-slate-800">{safeNumber(row.count)}</span>
                  </div>
                ))}
                {!yearlyRecords.length ? <p className="text-sm text-slate-500">No filing trend data yet.</p> : null}
              </div>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  )
}
