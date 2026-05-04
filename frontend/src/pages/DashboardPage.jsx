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

// localStorage key for the Risk Pulse view preference (currently only
// `sortMode` — 'rpi' | 'name'). Read once at mount, write on every change.
const PULSE_PREFS_KEY = 'rl.dashboard.pulsePrefs.v1'

function _readPulsePrefs() {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(PULSE_PREFS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function _writePulsePrefs(prefs) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(PULSE_PREFS_KEY, JSON.stringify(prefs))
  } catch {
    // SSR / private mode / quota — safe to ignore.
  }
}

const TABS = [
  { key: 'pulse', label: 'Risk Pulse' },
  { key: 'category', label: 'Category Intelligence' },
]

function priorityHeatColor(rpi, total) {
  // Three-state RPI from the backend:
  //   null/undefined → scoring failed/missing → light grey
  //   total === 0    → no risk data           → lighter grey
  //   number         → green … red ramp
  if (rpi === null || rpi === undefined) return '#e2e8f0'
  const cnt = Number(total || 0)
  if (!cnt) return '#f1f5f9'
  const score = Number(rpi)
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
  const [heatPageSize, setHeatPageSize] = useState(40)
  const [heatPage, setHeatPage] = useState(1)
  const [hoverPopup, setHoverPopup] = useState(null)
  const [stockCache, setStockCache] = useState({})

  // Risk Pulse view preference — only `sortMode` is user-tweakable now.
  // Heatmap renders compact by default, year columns always collapse to the
  // current paged viewport; refresh runs implicitly via the dashboard cache
  // TTL + ensure-priority background load.
  const [sortMode, setSortMode] = useState(() => {
    const v = _readPulsePrefs().sortMode
    return v === 'name' ? 'name' : 'rpi'
  })

  useEffect(() => {
    _writePulsePrefs({ sortMode })
  }, [sortMode])

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

    const path = force ? '/api/dashboard/summary?force=1' : '/api/dashboard/summary'
    dashboardSummaryCache.inFlight = get(path, { timeoutMs: 20000 }).then((summaryRes) => {
      const nextData = summaryRes?.data || null
      if (!nextData || typeof nextData !== 'object') {
        throw new Error('Dashboard summary returned empty payload.')
      }
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

  useEffect(() => {
    if (!data || autoEnsuredRef.current || loading) return
    const total = safeNumber(metrics.records)
    const withPriority = safeNumber(metrics.records_with_priority)
    if (total <= 0 || withPriority >= total) return

    autoEnsuredRef.current = true
    post('/api/dashboard/ensure-priority', {}, { timeoutMs: 30000 })
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

  // Backend already orders priority_heatmap.companies by max RPI DESC
  // (main.py:_dashboard_summary L2023-2027). When sortMode === 'rpi' we
  // pass that ordering through unchanged; 'name' switches to alphabetical.
  const sortedCompanies = useMemo(() => {
    const fromApi = Array.isArray(priorityHeatmap.companies) ? priorityHeatmap.companies : []
    const base = fromApi.length
      ? fromApi
      : Array.from(
          new Set((priorityHeatmap.cells || []).map((row) => String(row.company || '').trim()).filter(Boolean)),
        )
    if (sortMode === 'name') {
      return [...base].sort((a, b) => a.localeCompare(b))
    }
    return base
  }, [priorityHeatmap.companies, priorityHeatmap.cells, sortMode])

  const yearsOrdered = useMemo(() => {
    const list = Array.isArray(priorityHeatmap.years) ? priorityHeatmap.years : []
    if (list.length > 0) return list
    return Array.from(new Set((priorityHeatmap.cells || []).map((row) => Number(row.year)).filter(Number.isFinite))).sort((a, b) => a - b)
  }, [priorityHeatmap.years, priorityHeatmap.cells])

  const filteredCompanies = useMemo(() => {
    const q = String(heatSearch || '').trim().toLowerCase()
    if (!q) return sortedCompanies
    return sortedCompanies.filter((c) => c.toLowerCase().includes(q))
  }, [sortedCompanies, heatSearch])

  const totalHeatPages = useMemo(() => {
    const size = Math.max(1, safeNumber(heatPageSize, 10))
    return Math.max(1, Math.ceil(filteredCompanies.length / size))
  }, [filteredCompanies.length, heatPageSize])

  useEffect(() => {
    setHeatPage(1)
  }, [heatSearch, heatPageSize, industry, sortMode])

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

  // Effective year columns — hide year columns where no company on the
  // current page has data. Avoids the "2020 mostly —" wall when a single
  // legacy filing forces the column on for the other 75 companies.
  const effectiveYears = useMemo(() => {
    if (!pagedCompanies.length || !heatCellMap.size) return yearsOrdered
    const filtered = yearsOrdered.filter((y) => pagedCompanies.some((c) => heatCellMap.has(`${c}__${y}`)))
    // Defensive: if the viewport has no data at all, fall back to full year list
    // so the empty-state message has something to anchor to.
    return filtered.length ? filtered : yearsOrdered
  }, [yearsOrdered, pagedCompanies, heatCellMap])

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

          <section>
            <div className={`${panelClass} p-4`}>
              {/* Top stripe — double-column header */}
              <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
                <div>
                  <div className="section-headline">
                    <div className="section-rail" />
                    <div>
                      <p className="section-title-strong">Priority Heatmap</p>
                      <p className="section-sub">Cards display RPI only. Hover a card for company/year risk detail and stock info.</p>
                    </div>
                  </div>

                  <div className="mt-3 rounded-xl border border-slate-200/80 bg-slate-50/65 p-3 text-xs text-slate-600">
                    <p className="font-semibold text-slate-700">How to read quickly:</p>
                    <p className="mt-1">RPI (0-100) is weighted by H/M/L counts. Higher RPI means higher pressure from high-priority risks. "—" indicates a filing whose risks couldn't be scored.</p>
                    <div className="mt-2 flex flex-wrap gap-3 text-[11px]">
                      <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: '#22c55e' }} />Lower pressure</span>
                      <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: '#f59e0b' }} />Mid pressure</span>
                      <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-full" style={{ background: '#ef4444' }} />High pressure</span>
                    </div>
                  </div>
                </div>

                <aside className="rl-heatmap-priority-side">
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
                    <p className="mt-1 text-sm font-semibold text-slate-700">
                      Average RPI:{' '}
                      {priorityHeatmap.avg_rpi === null || priorityHeatmap.avg_rpi === undefined
                        ? '—'
                        : safeNumber(priorityHeatmap.avg_rpi).toFixed(1)}
                    </p>
                    <p className="mt-1 text-sm text-slate-600">Rows with priority data: {safeNumber(metrics.records_with_priority)} / {safeNumber(metrics.records)}</p>
                  </div>
                </aside>
              </div>

              {/* Middle stripe — single-row filter bar */}
              <div className="rl-heatmap-filter-row mt-4">
                <label className="rl-heatmap-filter-cell">
                  <span className="section-title">Company Search</span>
                  <input className="input mt-1" placeholder="Filter companies..." value={heatSearch} onChange={(e) => setHeatSearch(e.target.value)} />
                </label>

                <label className="rl-heatmap-filter-cell">
                  <span className="section-title">Industry Group</span>
                  <select className="input mt-1" value={industry} onChange={(e) => setIndustry(e.target.value)}>
                    {industryOptions.map((opt) => (
                      <option key={opt} value={opt}>{opt}</option>
                    ))}
                  </select>
                </label>

                <label className="rl-heatmap-filter-cell">
                  <span className="section-title">Sort</span>
                  <select className="input mt-1" value={sortMode} onChange={(e) => setSortMode(e.target.value)}>
                    <option value="rpi">RPI (high → low)</option>
                    <option value="name">Company A → Z</option>
                  </select>
                </label>

                <label className="rl-heatmap-filter-cell rl-heatmap-filter-cell--narrow">
                  <span className="section-title">Rows / Page</span>
                  <select className="input mt-1" value={heatPageSize} onChange={(e) => setHeatPageSize(Number(e.target.value) || 10)}>
                    {[10, 20, 40, 80].map((n) => (
                      <option key={n} value={n}>{n}</option>
                    ))}
                  </select>
                </label>

                <label className="rl-heatmap-filter-cell rl-heatmap-filter-cell--narrow">
                  <span className="section-title">Page</span>
                  <select className="input mt-1" value={heatPage} onChange={(e) => setHeatPage(Number(e.target.value) || 1)}>
                    {Array.from({ length: totalHeatPages }, (_, i) => i + 1).map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </select>
                </label>
              </div>

              <p className="mt-2 text-xs font-semibold text-slate-600">
                Showing {heatRangeLabel} / {filteredCompanies.length}
                {sortMode === 'rpi' ? <span className="ml-2 text-slate-500">· Sorted by RPI (high → low); unscored companies fall to the bottom.</span> : null}
                <span className="ml-2 text-slate-500">· Year columns without data on this page are hidden.</span>
              </p>

              {/* Bottom stripe — full-width heatmap table */}
              {pagedCompanies.length === 0 || effectiveYears.length === 0 ? (
                <div className="mt-3 rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
                  No priority heatmap data available for the selected scope.
                </div>
              ) : (
                <div className="mt-3 overflow-x-auto">
                  <table className="min-w-full text-sm">
                    <thead>
                      <tr>
                        <th className="w-48 py-1 pr-2 text-left text-xs font-bold uppercase tracking-[0.08em] text-slate-500">Company</th>
                        {effectiveYears.map((y) => (
                          <th key={y} className="py-1 px-1 text-center text-xs font-bold uppercase tracking-[0.08em] text-slate-500">
                            {y}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {pagedCompanies.map((c) => (
                        <tr key={c} className="border-t border-slate-100/80">
                          <td className="py-1 pr-2 font-semibold text-slate-800">{c}</td>
                          {effectiveYears.map((y) => {
                            const cell = heatCellMap.get(`${c}__${y}`)
                            const total = safeNumber(cell?.total)
                            // Keep null/undefined as-is so we can distinguish
                            // "scoring failed" from "all-Low (RPI=0)".
                            const rpi = cell?.rpi
                            const bg = priorityHeatColor(rpi, total)
                            const isUnscored = cell && (rpi === null || rpi === undefined)
                            const display = isUnscored ? '—' : Number(rpi).toFixed(0)

                            return (
                              <td key={`${c}-${y}`} className="py-1 px-1">
                                {cell ? (
                                  <a
                                    href={`/upload?tab=records&record_id=${encodeURIComponent(cell.record_id || '')}`}
                                    onMouseEnter={(e) => setHoverPopup({ cell, x: e.clientX, y: e.clientY })}
                                    onMouseMove={(e) => setHoverPopup((prev) => (prev ? { ...prev, x: e.clientX, y: e.clientY } : prev))}
                                    onMouseLeave={() => setHoverPopup(null)}
                                    title={isUnscored ? 'Risk scoring unavailable for this filing' : undefined}
                                    className="rl-heatmap-cell-compact"
                                    style={{ backgroundColor: bg }}
                                  >
                                    <span className="text-[12px] font-black leading-none">{display}</span>
                                  </a>
                                ) : (
                                  <div className="rl-heatmap-cell-compact rl-heatmap-cell-compact--empty">—</div>
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
            <p className="mt-2 text-sm font-semibold text-slate-700">
              RPI:{' '}
              {hoverPopup.cell.rpi === null || hoverPopup.cell.rpi === undefined
                ? 'Not scored'
                : safeNumber(hoverPopup.cell.rpi).toFixed(1)}
            </p>
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
