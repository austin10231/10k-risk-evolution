import React, { useEffect, useMemo, useRef, useState } from 'react'
import { get, post } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'
import useSlidingTabIndicator from '../lib/useSlidingTabIndicator'

const DASHBOARD_CACHE_TTL_MS = 5 * 60 * 1000
const dashboardSummaryCache = {
  data: null,
  ts: 0,
  inFlight: null,
}

const TABS = [
  { key: 'pulse', label: 'Risk Pulse' },
  { key: 'category', label: 'Category Intelligence' },
]

function priorityHeatColor(rpi, total) {
  const score = Number(rpi || 0)
  const cnt = Number(total || 0)
  if (!cnt) return '#f1f5f9'
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

function prettyPrice(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `$${n.toFixed(2)}`
}

function tooltipPosition(x, y) {
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1280
  const vh = typeof window !== 'undefined' ? window.innerHeight : 720
  const w = 320
  const h = 220
  let left = x + 14
  let top = y + 14
  if (left + w > vw - 8) left = Math.max(8, x - w - 14)
  if (top + h > vh - 8) top = Math.max(8, y - h - 14)
  return { left, top }
}

export default function DashboardPage() {
  const { config } = useGlobalConfig()
  const tabsRef = useRef(null)
  const autoEnsuredRef = useRef(false)
  const mountedRef = useRef(true)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [data, setData] = useState(null)
  const [activeTab, setActiveTab] = useState('pulse')
  const [industry, setIndustry] = useState('All Industries')
  const [selectedCategory, setSelectedCategory] = useState('')
  const [heatSearch, setHeatSearch] = useState('')
  const [heatPageSize, setHeatPageSize] = useState(10)
  const [heatPage, setHeatPage] = useState(1)
  const [hoverPopup, setHoverPopup] = useState(null)
  const [stockCache, setStockCache] = useState({})

  useSlidingTabIndicator(tabsRef, [activeTab])

  const load = ({ force = false, background = false } = {}) => {
    const now = Date.now()
    const hasCache = Boolean(dashboardSummaryCache.data)
    const isFresh = hasCache && now - safeNumber(dashboardSummaryCache.ts) < DASHBOARD_CACHE_TTL_MS

    if (!force && isFresh) {
      setData(dashboardSummaryCache.data)
      setError('')
      setLoading(false)
      return Promise.resolve(dashboardSummaryCache.data)
    }

    if (dashboardSummaryCache.inFlight) {
      if (!background) setLoading(!hasCache)
      return dashboardSummaryCache.inFlight
        .then((cachedData) => {
          if (!mountedRef.current) return cachedData
          if (cachedData) setData(cachedData)
          return cachedData
        })
        .catch((e) => {
          if (!mountedRef.current) return null
          if (!hasCache) setError(e.message || 'Failed to load dashboard summary')
          return null
        })
        .finally(() => {
          if (!mountedRef.current) return
          if (!background || !hasCache) setLoading(false)
        })
    }

    if (!background) setLoading(!hasCache)
    setError('')

    dashboardSummaryCache.inFlight = get('/api/dashboard/summary').then((summaryRes) => {
      const nextData = summaryRes?.data || null
      dashboardSummaryCache.data = nextData
      dashboardSummaryCache.ts = Date.now()
      return nextData
    })

    return dashboardSummaryCache.inFlight
      .then((nextData) => {
        if (!mountedRef.current) return nextData
        setData(nextData)
        return nextData
      })
      .catch((e) => {
        if (!mountedRef.current) return null
        if (!hasCache) setError(e.message || 'Failed to load dashboard summary')
        return null
      })
      .finally(() => {
        dashboardSummaryCache.inFlight = null
        if (!mountedRef.current) return
        if (!background || !hasCache) setLoading(false)
      })
  }

  useEffect(() => {
    mountedRef.current = true
    const hasCache = Boolean(dashboardSummaryCache.data)
    const cacheAge = Date.now() - safeNumber(dashboardSummaryCache.ts)
    const cacheFresh = hasCache && cacheAge < DASHBOARD_CACHE_TTL_MS

    if (hasCache) {
      setData(dashboardSummaryCache.data)
      setError('')
      setLoading(false)
    }

    if (!cacheFresh) {
      load({ background: hasCache })
    }

    return () => {
      mountedRef.current = false
    }
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
  const categoryCounts = scopeData?.category_counts || scopeData?.top_categories || []
  const topCategories = scopeData?.top_categories || []
  const categoryYearly = scopeData?.category_yearly || []
  const yearlyRecords = scopeData?.yearly_records || []

  const recent = useMemo(() => {
    const rows = Array.isArray(data?.recent_records) ? data.recent_records : []
    if (industry === 'All Industries') return rows
    return rows.filter((r) => String(r.industry || '').trim() === industry)
  }, [data, industry])

  useEffect(() => {
    if (!data || autoEnsuredRef.current || loading) return
    const total = safeNumber(metrics.records)
    const withPriority = safeNumber(metrics.records_with_priority)
    if (total <= 0 || withPriority >= total) return

    autoEnsuredRef.current = true
    post('/api/dashboard/ensure-priority', {})
      .then((res) => {
        if (safeNumber(res?.updated) > 0) load({ force: true, background: true })
      })
      .catch(() => {
        // keep UI usable if ensure-priority fails
      })
  }, [data, loading, metrics.records, metrics.records_with_priority])

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
    return Array.from(new Set((priorityHeatmap.cells || []).map((row) => Number(row.year)).filter(Number.isFinite))).sort((a, b) => a - b)
  }, [priorityHeatmap.years, priorityHeatmap.cells])

  const filteredCompanies = useMemo(() => {
    const q = String(heatSearch || '').trim().toLowerCase()
    if (!q) return companiesOrdered
    return companiesOrdered.filter((c) => c.toLowerCase().includes(q))
  }, [companiesOrdered, heatSearch])

  const totalHeatPages = useMemo(() => {
    const size = Math.max(1, safeNumber(heatPageSize, 10))
    return Math.max(1, Math.ceil(filteredCompanies.length / size))
  }, [filteredCompanies.length, heatPageSize])

  useEffect(() => {
    setHeatPage(1)
  }, [heatSearch, heatPageSize, industry])

  useEffect(() => {
    if (heatPage > totalHeatPages) setHeatPage(totalHeatPages)
  }, [heatPage, totalHeatPages])

  const pagedCompanies = useMemo(() => {
    const size = Math.max(1, safeNumber(heatPageSize, 10))
    const start = (Math.max(1, heatPage) - 1) * size
    return filteredCompanies.slice(start, start + size)
  }, [filteredCompanies, heatPage, heatPageSize])

  const heatRangeLabel = useMemo(() => {
    if (!filteredCompanies.length) return '0-0'
    const size = Math.max(1, safeNumber(heatPageSize, 10))
    const start = (Math.max(1, heatPage) - 1) * size
    const end = Math.min(start + size, filteredCompanies.length)
    return `${start + 1}-${end}`
  }, [filteredCompanies.length, heatPage, heatPageSize])

  useEffect(() => {
    const options = categoryCounts.map((x) => String(x.category || '').trim()).filter(Boolean)
    if (!options.length) {
      setSelectedCategory('')
      return
    }
    if (!selectedCategory || !options.includes(selectedCategory)) {
      setSelectedCategory(options[0])
    }
  }, [categoryCounts, selectedCategory])

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

  const panelClass = 'rounded-2xl border border-slate-200/85 bg-white/62 shadow-sm backdrop-blur-[2px]'

  const hoveredCell = hoverPopup?.cell || null

  useEffect(() => {
    const ticker = String(hoveredCell?.ticker || '').trim().toUpperCase()
    if (!ticker) return
    if (stockCache[ticker]?.done || stockCache[ticker]?.loading) return

    setStockCache((prev) => ({ ...prev, [ticker]: { loading: true, done: false, data: null, error: '' } }))
    get(`/api/stock/quote?ticker=${encodeURIComponent(ticker)}&lite=1`)
      .then((res) => {
        setStockCache((prev) => ({ ...prev, [ticker]: { loading: false, done: true, data: res?.data || null, error: '' } }))
      })
      .catch((e) => {
        setStockCache((prev) => ({ ...prev, [ticker]: { loading: false, done: true, data: null, error: e.message || 'Stock unavailable' } }))
      })
  }, [hoveredCell, stockCache])

  const hoverStock = useMemo(() => {
    const t = String(hoveredCell?.ticker || '').trim().toUpperCase()
    if (!t) return null
    return stockCache[t] || null
  }, [hoveredCell, stockCache])

  const metricCardStyle = { backgroundColor: 'rgba(255,255,255,0.62)', padding: '0.62rem 0.82rem' }

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

      <section className="rl-up-nav-stack">
        <div className="rl-up-nav-head">
          <div className="rl-up-pill-nav rl-tab-motion" ref={tabsRef}>
            {TABS.map((t) => (
              <button key={t.key} className={`rl-strip-tab ${activeTab === t.key ? 'active' : ''}`} onClick={() => setActiveTab(t.key)}>
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {error ? <div className={`${panelClass} border-red-200 bg-red-50/88 p-3 text-sm font-semibold text-red-700`}>{error}</div> : null}

      {activeTab === 'pulse' ? (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {metricTiles.map(([k, v, color]) => (
              <div key={k} className="metric-card" style={metricCardStyle}>
                <p className="metric-label">{k}</p>
                <p className="metric-value" style={{ color, fontSize: '2rem' }}>
                  {loading ? '…' : v}
                </p>
              </div>
            ))}
          </section>

          <section className="grid gap-4 xl:grid-cols-[1.75fr_1fr]">
            <div className={`${panelClass} p-4`}>
              <div className="section-headline">
                <div className="section-rail" />
                <div>
                  <p className="section-title-strong">Priority Heatmap</p>
                  <p className="section-sub">Cards display RPI only. Hover a card for company/year risk detail and stock info.</p>
                </div>
              </div>

              <div className="mt-3 rounded-xl border border-slate-200/80 bg-slate-50/65 p-3 text-xs text-slate-600">
                <p className="font-semibold text-slate-700">How to read quickly:</p>
                <p className="mt-1">RPI (0-100) is weighted by H/M/L counts. Higher RPI means higher pressure from high-priority risks.</p>
                <div className="mt-2 flex flex-wrap gap-3 text-[11px]">
                  <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: '#22c55e' }} />Lower pressure</span>
                  <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: '#f59e0b' }} />Mid pressure</span>
                  <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: '#ef4444' }} />High pressure</span>
                </div>
              </div>

              <div className="mt-3 grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(220px,0.8fr)_auto_auto_auto] md:items-end">
                <div>
                  <label className="section-title">Company Search</label>
                  <input className="input mt-2" placeholder="Filter companies..." value={heatSearch} onChange={(e) => setHeatSearch(e.target.value)} />
                </div>

                <div>
                  <label className="section-title">Industry Group</label>
                  <select className="input mt-2" value={industry} onChange={(e) => setIndustry(e.target.value)}>
                    {industryOptions.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="section-title">Rows / Page</label>
                  <select className="input mt-2 min-w-[110px]" value={heatPageSize} onChange={(e) => setHeatPageSize(Number(e.target.value) || 10)}>
                    {[8, 10, 14, 20].map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="section-title">Page</label>
                  <select className="input mt-2 min-w-[95px]" value={heatPage} onChange={(e) => setHeatPage(Number(e.target.value) || 1)}>
                    {Array.from({ length: totalHeatPages }, (_, i) => i + 1).map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </div>

                <button className="btn-secondary" onClick={() => load({ force: true })} disabled={loading}>
                  {loading ? 'Refreshing…' : 'Refresh'}
                </button>
              </div>

              <p className="mt-2 text-xs font-semibold text-slate-600">Showing {heatRangeLabel} / {filteredCompanies.length}</p>

              {pagedCompanies.length === 0 || yearsOrdered.length === 0 ? (
                <div className="mt-3 rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
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
                      {pagedCompanies.map((c) => (
                        <tr key={c} className="border-t border-slate-100/80">
                          <td className="py-2 pr-3 font-semibold text-slate-800">{c}</td>
                          {yearsOrdered.map((y) => {
                            const cell = heatCellMap.get(`${c}__${y}`)
                            const total = safeNumber(cell?.total)
                            const rpi = safeNumber(cell?.rpi)
                            const bg = priorityHeatColor(rpi, total)

                            return (
                              <td key={`${c}-${y}`} className="py-2 px-1">
                                {cell ? (
                                  <a
                                    href={`/library?record_id=${encodeURIComponent(cell.record_id || '')}`}
                                    onMouseEnter={(e) => setHoverPopup({ cell, x: e.clientX, y: e.clientY })}
                                    onMouseMove={(e) => setHoverPopup((prev) => (prev ? { ...prev, x: e.clientX, y: e.clientY } : prev))}
                                    onMouseLeave={() => setHoverPopup(null)}
                                    className="mx-auto flex h-11 w-[78px] flex-col items-center justify-center rounded-lg border border-white/70 text-[10px] font-bold text-slate-800 transition-transform hover:scale-[1.03]"
                                    style={{ backgroundColor: bg }}
                                  >
                                    <span className="text-[9px] font-black tracking-[0.04em]">RPI</span>
                                    <span className="mt-[2px] text-[13px] leading-none font-black">{rpi.toFixed(0)}</span>
                                  </a>
                                ) : (
                                  <div className="mx-auto flex h-11 w-[78px] items-center justify-center rounded-lg border border-slate-200/70 bg-slate-100/70 text-[10px] font-semibold text-slate-400">—</div>
                                )}
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

            <div className={`${panelClass} p-4`}>
              <p className="section-title">Priority Mix</p>
              <div className="mt-2 grid grid-cols-3 gap-2 text-center text-sm">
                <div className="rounded-xl border border-red-200/90 bg-red-50/70 p-2.5">
                  <p className="font-extrabold text-red-600">High</p>
                  <p className="mt-0.5 text-base font-extrabold text-red-700">{loading ? '…' : safeNumber(priorityTotals.high)}</p>
                </div>
                <div className="rounded-xl border border-amber-200/90 bg-amber-50/70 p-2.5">
                  <p className="font-extrabold text-amber-600">Medium</p>
                  <p className="mt-0.5 text-base font-extrabold text-amber-700">{loading ? '…' : safeNumber(priorityTotals.medium)}</p>
                </div>
                <div className="rounded-xl border border-emerald-200/90 bg-emerald-50/70 p-2.5">
                  <p className="font-extrabold text-emerald-600">Low</p>
                  <p className="mt-0.5 text-base font-extrabold text-emerald-700">{loading ? '…' : safeNumber(priorityTotals.low)}</p>
                </div>
              </div>

              <div className="mt-3 rounded-xl border border-slate-200/80 bg-slate-50/70 p-3">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Scope Snapshot</p>
                <p className="mt-1 text-sm font-semibold text-slate-700">Average RPI: {safeNumber(priorityHeatmap.avg_rpi).toFixed(1)}</p>
                <p className="mt-1 text-sm text-slate-600">Rows with priority data: {safeNumber(metrics.records_with_priority)} / {safeNumber(metrics.records)}</p>
              </div>

              <div className="mt-3 rounded-xl border border-slate-200/70 bg-slate-100/55 p-2.5">
                <p className="section-title">Recent Filings</p>
                <div className="mt-1.5 space-y-1.5">
                  {loading ? <p className="text-sm text-slate-500">Loading…</p> : null}
                  {!loading && recent.length === 0 ? <p className="text-sm text-slate-500">No records in this scope.</p> : null}
                  {!loading &&
                    recent.slice(0, 5).map((r) => (
                      <div key={r.record_id} className="rounded-xl border border-slate-200/85 bg-slate-50/85 px-3 py-2">
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
          <div className={`${panelClass} p-4`}>
            <div className="section-headline">
              <div className="section-rail" />
              <div>
                <p className="section-title-strong">Category Ranking</p>
                <p className="section-sub">Most frequent extracted risk categories within the selected industry scope.</p>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-end gap-2">
              <div className="min-w-[240px]">
                <label className="section-title">Industry Group</label>
                <select className="input mt-2" value={industry} onChange={(e) => setIndustry(e.target.value)}>
                  {industryOptions.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </div>
              <button className="btn-secondary" onClick={() => load({ force: true })} disabled={loading}>
                {loading ? 'Refreshing…' : 'Refresh'}
              </button>
            </div>

            <div className="mt-3 space-y-2">
              {loading ? <p className="text-sm text-slate-500">Loading…</p> : null}
              {!loading && topCategories.length === 0 ? <p className="text-sm text-slate-500">No category data yet.</p> : null}
              {!loading &&
                topCategories.map((row) => {
                  const max = Math.max(...topCategories.map((r) => safeNumber(r.count)), 1)
                  const width = `${Math.max(6, Math.round((safeNumber(row.count) / max) * 100))}%`
                  return (
                    <div key={row.category} className="rounded-xl border border-slate-200/80 bg-white/52 px-3 py-2">
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

          <div className={`${panelClass} p-4`}>
            <p className="section-title">Category Trend</p>
            <p className="mt-1 text-xs text-slate-500">Track one category across filing years in the current scope.</p>

            <div className="mt-3">
              <label className="section-title">Category</label>
              <select
                className="input mt-2"
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                disabled={!categoryCounts.length}
              >
                {!categoryCounts.length ? <option value="">No categories</option> : null}
                {categoryCounts.map((row) => (
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

            <div className="mt-5 rounded-xl border border-slate-200/80 bg-slate-50/70 p-3">
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

      {hoverPopup?.cell ? (() => {
        const pos = tooltipPosition(safeNumber(hoverPopup.x), safeNumber(hoverPopup.y))
        return (
          <div
            className="fixed z-[80] w-[320px] rounded-xl border border-slate-300 bg-white p-3 shadow-2xl"
            style={{ left: `${pos.left}px`, top: `${pos.top}px`, pointerEvents: 'none' }}
          >
            <p className="text-sm font-bold text-slate-800">{hoverPopup.cell.company} · {hoverPopup.cell.year}</p>
            <p className="mt-1 text-xs text-slate-600">{hoverPopup.cell.industry || '—'} · {hoverPopup.cell.filing_type || '10-K'}</p>
            <p className="mt-2 text-sm font-semibold text-slate-700">RPI: {safeNumber(hoverPopup.cell.rpi).toFixed(1)}</p>
            <p className="mt-1 text-sm text-slate-700">H/M/L: {safeNumber(hoverPopup.cell.high)} / {safeNumber(hoverPopup.cell.medium)} / {safeNumber(hoverPopup.cell.low)}</p>
            <p className="mt-1 text-sm text-slate-700">Risk items: {safeNumber(hoverPopup.cell.risk_items)}</p>
            <p className="mt-1 text-sm text-slate-700">Ticker: {hoverPopup.cell.ticker || '—'}</p>
            <p className="mt-1 text-sm text-slate-700">
              Recent price:{' '}
              {hoverStock?.loading
                ? 'Loading...'
                : hoverStock?.data
                  ? prettyPrice(hoverStock.data.price)
                  : hoverStock?.error
                    ? 'Unavailable'
                    : '—'}
            </p>
            <p className="mt-2 text-xs font-semibold text-slate-600">Click the heatmap card to open this record.</p>
          </div>
        )
      })() : null}
    </div>
  )
}
