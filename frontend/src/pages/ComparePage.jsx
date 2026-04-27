import React, { useEffect, useMemo, useState } from 'react'
import { get, post } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'
import GlobalConfigInlineEditor from '../components/GlobalConfigInlineEditor'
import useSlidingTabIndicator from '../lib/useSlidingTabIndicator'

function normalizeCategory(value) {
  const text = String(value || '').trim()
  return text || 'Unknown'
}

function groupRisks(risks, categoryFilter, keywordFilter) {
  const grouped = new Map()
  const keyword = String(keywordFilter || '').trim().toLowerCase()
  const category = String(categoryFilter || '').trim()

  ;(Array.isArray(risks) ? risks : []).forEach((row) => {
    const cat = normalizeCategory(row?.category)
    const title = String(row?.title || '').trim()
    if (!title) return
    if (category && category !== 'ALL' && category !== cat) return
    if (keyword && !`${cat} ${title}`.toLowerCase().includes(keyword)) return

    if (!grouped.has(cat)) grouped.set(cat, [])
    grouped.get(cat).push({ category: cat, title })
  })

  return Array.from(grouped.entries())
    .map(([cat, items]) => ({ category: cat, items }))
    .sort((a, b) => b.items.length - a.items.length || a.category.localeCompare(b.category))
}

export default function ComparePage() {
  const modeTabsRef = React.useRef(null)
  const { config } = useGlobalConfig()
  const [records, setRecords] = useState([])
  const [mode, setMode] = useState('yoy')
  const [latestId, setLatestId] = useState('')
  const [priorId, setPriorId] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingRecords, setLoadingRecords] = useState(true)
  const [error, setError] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('ALL')
  const [keywordFilter, setKeywordFilter] = useState('')
  const [newOpenMap, setNewOpenMap] = useState({})
  const [removedOpenMap, setRemovedOpenMap] = useState({})

  useEffect(() => {
    let mounted = true
    setLoadingRecords(true)
    get('/api/records')
      .then((res) => {
        if (!mounted) return
        const items = res?.items || []
        setRecords(items)
        if (items.length > 0) setLatestId(items[0].record_id)
        if (items.length > 1) setPriorId(items[1].record_id)
      })
      .catch((e) => {
        if (!mounted) return
        setError(e.message || 'Failed to load records')
      })
      .finally(() => {
        if (!mounted) return
        setLoadingRecords(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  const labelMap = useMemo(() => {
    const m = new Map()
    records.forEach((r) => m.set(r.record_id, `${r.company} · ${r.year} · ${r.filing_type}`))
    return m
  }, [records])

  const companies = useMemo(
    () => Array.from(new Set(records.map((r) => String(r.company || '').trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b)),
    [records],
  )
  const [companyYoy, setCompanyYoy] = useState('')
  const [ftYoy, setFtYoy] = useState('10-K')
  const [latestYear, setLatestYear] = useState('')
  const [priorYear, setPriorYear] = useState('')

  const [companyA, setCompanyA] = useState('')
  const [companyB, setCompanyB] = useState('')
  const [yearA, setYearA] = useState('')
  const [yearB, setYearB] = useState('')

  useEffect(() => {
    if (!companies.length) return
    const preferred = config.company && companies.includes(config.company) ? config.company : companies[0]
    if (!companyYoy || !companies.includes(companyYoy)) setCompanyYoy(preferred)
    if (!companyA || !companies.includes(companyA)) setCompanyA(preferred)
    if (!companyB || !companies.includes(companyB)) {
      const alt = companies.find((c) => c !== preferred) || preferred
      setCompanyB(alt)
    }
  }, [companies, companyYoy, companyA, companyB, config.company])

  const yoyRecords = useMemo(
    () => records.filter((r) => String(r.company || '') === companyYoy && String(r.filing_type || '10-K') === ftYoy),
    [records, companyYoy, ftYoy],
  )
  const yoyYears = useMemo(
    () => Array.from(new Set(yoyRecords.map((r) => Number(r.year)).filter(Number.isFinite))).sort((a, b) => b - a),
    [yoyRecords],
  )
  useEffect(() => {
    if (!yoyYears.length) return
    if (config.year && yoyYears.includes(Number(config.year))) {
      setLatestYear(String(config.year))
      return
    }
    if (!latestYear || !yoyYears.includes(Number(latestYear))) setLatestYear(String(yoyYears[0]))
  }, [yoyYears, latestYear, config.year])
  const priorYearOptions = useMemo(
    () => yoyYears.filter((y) => y < Number(latestYear)),
    [yoyYears, latestYear],
  )
  useEffect(() => {
    if (!priorYearOptions.length) return
    if (!priorYear || !priorYearOptions.includes(Number(priorYear))) setPriorYear(String(priorYearOptions[0]))
  }, [priorYearOptions, priorYear])

  useEffect(() => {
    if (!companyYoy || !latestYear || !priorYear) return
    const latestRec = records
      .filter((r) => String(r.company || '') === companyYoy && Number(r.year) === Number(latestYear))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0]
    const priorRec = records
      .filter((r) => String(r.company || '') === companyYoy && Number(r.year) === Number(priorYear))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0]
    if (latestRec?.record_id) setLatestId(latestRec.record_id)
    if (priorRec?.record_id) setPriorId(priorRec.record_id)
  }, [companyYoy, latestYear, priorYear, records])

  const yearsForCompany = (name) =>
    Array.from(new Set(records.filter((r) => String(r.company || '') === name).map((r) => Number(r.year)).filter(Number.isFinite))).sort((a, b) => b - a)

  useEffect(() => {
    const aYears = yearsForCompany(companyA)
    const bYears = yearsForCompany(companyB)
    if (aYears.length) {
      if (config.year && aYears.includes(Number(config.year))) setYearA(String(config.year))
      else if (!yearA || !aYears.includes(Number(yearA))) setYearA(String(aYears[0]))
    }
    if (bYears.length) {
      if (config.year && bYears.includes(Number(config.year))) setYearB(String(config.year))
      else if (!yearB || !bYears.includes(Number(yearB))) setYearB(String(bYears[0]))
    }
  }, [companyA, companyB, yearA, yearB, records, config.year])

  useEffect(() => {
    if (!companyA || !companyB || !yearA || !yearB || mode !== 'cross') return
    const a = records
      .filter((r) => String(r.company || '') === companyA && Number(r.year) === Number(yearA))
      .sort((x, y) => String(y.created_at || '').localeCompare(String(x.created_at || '')))[0]
    const b = records
      .filter((r) => String(r.company || '') === companyB && Number(r.year) === Number(yearB))
      .sort((x, y) => String(y.created_at || '').localeCompare(String(x.created_at || '')))[0]
    if (b?.record_id) setLatestId(b.record_id)
    if (a?.record_id) setPriorId(a.record_id)
  }, [companyA, companyB, yearA, yearB, mode, records])

  const runCompare = async () => {
    if (!latestId || !priorId) return
    setLoading(true)
    setError('')
    setData(null)
    try {
      const res = await post('/api/compare', {
        latest_record_id: latestId,
        prior_record_id: priorId,
      })
      setData(res?.data || null)
    } catch (e) {
      setError(e.message || 'Compare failed')
    } finally {
      setLoading(false)
    }
  }

  useSlidingTabIndicator(modeTabsRef, [mode])

  const groupedNew = useMemo(
    () => groupRisks(data?.new_risks || [], categoryFilter, keywordFilter),
    [data?.new_risks, categoryFilter, keywordFilter],
  )
  const groupedRemoved = useMemo(
    () => groupRisks(data?.removed_risks || [], categoryFilter, keywordFilter),
    [data?.removed_risks, categoryFilter, keywordFilter],
  )

  const allCategories = useMemo(() => {
    const s = new Set()
    ;(Array.isArray(data?.new_risks) ? data.new_risks : []).forEach((r) => s.add(normalizeCategory(r?.category)))
    ;(Array.isArray(data?.removed_risks) ? data.removed_risks : []).forEach((r) => s.add(normalizeCategory(r?.category)))
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [data?.new_risks, data?.removed_risks])

  useEffect(() => {
    setNewOpenMap({})
    setRemovedOpenMap({})
    setCategoryFilter('ALL')
    setKeywordFilter('')
  }, [data?.latest_record_id, data?.prior_record_id])

  const toggleNewGroup = (cat) => {
    setNewOpenMap((prev) => ({ ...prev, [cat]: !prev[cat] }))
  }

  const toggleRemovedGroup = (cat) => {
    setRemovedOpenMap((prev) => ({ ...prev, [cat]: !prev[cat] }))
  }

  return (
    <div className="rl-page-shell rl-compare-page">
      <section className="rl-up-header">
        <div className="page-header !mb-0">
          <div className="page-header-left rl-up-title-block">
            <span className="page-icon">⚖️</span>
            <div>
              <p className="page-title">Compare</p>
              <p className="page-subtitle">Detect risk changes year-over-year or between companies</p>
            </div>
          </div>
          <GlobalConfigInlineEditor />
        </div>
      </section>

      {error ? <div className="rl-up-inline-error">{error}</div> : null}

      <section className="rl-compare-workbench">
        <div className="rl-up-form rl-compare-control">
          <p className="section-title">Configure</p>
          <div className="rl-tabs mt-2 rl-tab-motion" ref={modeTabsRef}>
            <button className={`rl-tab-btn ${mode === 'yoy' ? 'active' : ''}`} onClick={() => setMode('yoy')}>
              📅 Year-over-Year
            </button>
            <button className={`rl-tab-btn ${mode === 'cross' ? 'active' : ''}`} onClick={() => setMode('cross')}>
              🏢 Cross-Company
            </button>
          </div>

          {loadingRecords ? <p className="mt-2 text-sm text-slate-500">Loading records…</p> : null}

          {!loadingRecords && mode === 'yoy' ? (
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <div>
                <label className="section-title">Company</label>
                <select className="input mt-2" value={companyYoy} onChange={(e) => setCompanyYoy(e.target.value)}>
                  {companies.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="section-title">Filing Type</label>
                <select className="input mt-2" value={ftYoy} onChange={(e) => setFtYoy(e.target.value)}>
                  <option value="10-K">10-K</option>
                  <option value="10-Q">10-Q</option>
                </select>
              </div>
              <div>
                <label className="section-title">Latest Year</label>
                <select className="input mt-2" value={latestYear} onChange={(e) => setLatestYear(e.target.value)}>
                  {yoyYears.map((y) => (
                    <option key={y} value={String(y)}>
                      {y}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="section-title">Prior Year</label>
                <select className="input mt-2" value={priorYear} onChange={(e) => setPriorYear(e.target.value)}>
                  {priorYearOptions.map((y) => (
                    <option key={y} value={String(y)}>
                      {y}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          ) : null}

          {!loadingRecords && mode === 'cross' ? (
            <div className="mt-4 grid gap-4 xl:grid-cols-2">
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-3">
                <p className="text-sm font-bold text-blue-700">Company A</p>
                <div className="mt-2 grid gap-3 md:grid-cols-2">
                  <div>
                    <label className="section-title">Company</label>
                    <select className="input mt-2" value={companyA} onChange={(e) => setCompanyA(e.target.value)}>
                      {companies.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="section-title">Year</label>
                    <select className="input mt-2" value={yearA} onChange={(e) => setYearA(e.target.value)}>
                      {yearsForCompany(companyA).map((y) => (
                        <option key={y} value={String(y)}>
                          {y}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                <p className="text-sm font-bold text-emerald-700">Company B</p>
                <div className="mt-2 grid gap-3 md:grid-cols-2">
                  <div>
                    <label className="section-title">Company</label>
                    <select className="input mt-2" value={companyB} onChange={(e) => setCompanyB(e.target.value)}>
                      {companies.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="section-title">Year</label>
                    <select className="input mt-2" value={yearB} onChange={(e) => setYearB(e.target.value)}>
                      {yearsForCompany(companyB).map((y) => (
                        <option key={y} value={String(y)}>
                          {y}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          <div className="mt-4">
            <button className="btn-primary" onClick={runCompare} disabled={loading || !latestId || !priorId}>
              {loading ? 'Comparing…' : '🚀 Run Compare'}
            </button>
          </div>
        </div>

        <aside className="rl-up-results rl-compare-side">
          <p className="section-title">Comparison Lens</p>
          <div className="rl-compare-side-kpis">
            <div className="metric-card">
              <p className="metric-label">Mode</p>
              <p className="metric-value">{mode === 'yoy' ? 'YOY' : 'Cross'}</p>
            </div>
            <div className="metric-card">
              <p className="metric-label">Records Ready</p>
              <p className="metric-value">{records.length}</p>
            </div>
          </div>

          <div className="rl-up-result-meta">
            <span>Latest Record</span>
            <strong title={labelMap.get(latestId) || latestId || '—'}>{labelMap.get(latestId) || latestId || '—'}</strong>
          </div>
          <div className="rl-up-result-meta">
            <span>Prior Record</span>
            <strong title={labelMap.get(priorId) || priorId || '—'}>{labelMap.get(priorId) || priorId || '—'}</strong>
          </div>

          <div className="rl-compare-side-note">
            Tip: use Year-over-Year for trajectory shifts, and Cross-Company for relative exposure benchmarking.
          </div>
        </aside>
      </section>

      {data && (
        <>
          <section className="rl-compare-result-shell">
            <div className="rl-compare-result-top">
              <div className="rl-compare-result-pills">
                <div className="rl-compare-result-pill new">
                  <span>Only in newer filing</span>
                  <strong>{data?.summary?.new_count ?? 0} new</strong>
                </div>
                <div className="rl-compare-result-pill removed">
                  <span>Only in older filing</span>
                  <strong>{data?.summary?.removed_count ?? 0} removed</strong>
                </div>
              </div>

              <div className="rl-compare-filter-bar compact">
                <div className="rl-compare-filter-select">
                  <select className="input" value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
                    <option value="ALL">All Categories</option>
                    {allCategories.map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="rl-compare-filter-keyword">
                  <input
                    className="input"
                    placeholder="Search keyword…"
                    value={keywordFilter}
                    onChange={(e) => setKeywordFilter(e.target.value)}
                  />
                </div>
                <button
                  className="btn-secondary rl-compare-filter-clear"
                  onClick={() => {
                    setCategoryFilter('ALL')
                    setKeywordFilter('')
                  }}
                >
                  Clear
                </button>
              </div>
            </div>

            <div className="rl-compare-result-grid">
              <div className="rl-compare-column">
                <p className="section-title">🟢 Risks Unique to Newer Filing</p>
                {!groupedNew.length ? <p className="mt-2 text-sm text-slate-500">No unique risks in newer filing.</p> : null}
                <div className="rl-compare-group-list">
                  {groupedNew.map((group) => {
                    const isOpen = Boolean(newOpenMap[group.category])
                    return (
                      <div key={`new-${group.category}`} className="rl-compare-group">
                        <button className="rl-compare-group-head" onClick={() => toggleNewGroup(group.category)}>
                          <span>
                            {group.category} ({group.items.length})
                          </span>
                          <strong>{isOpen ? '−' : '+'}</strong>
                        </button>
                        {isOpen ? (
                          <ul className="rl-compare-group-items">
                            {group.items.map((item, idx) => (
                              <li key={`new-${group.category}-${idx}`}>
                                <span>{item.title}</span>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              </div>

              <div className="rl-compare-column">
                <p className="section-title">🔴 Risks Unique to Older Filing</p>
                {!groupedRemoved.length ? <p className="mt-2 text-sm text-slate-500">No unique risks in older filing.</p> : null}
                <div className="rl-compare-group-list">
                  {groupedRemoved.map((group) => {
                    const isOpen = Boolean(removedOpenMap[group.category])
                    return (
                      <div key={`old-${group.category}`} className="rl-compare-group">
                        <button className="rl-compare-group-head" onClick={() => toggleRemovedGroup(group.category)}>
                          <span>
                            {group.category} ({group.items.length})
                          </span>
                          <strong>{isOpen ? '−' : '+'}</strong>
                        </button>
                        {isOpen ? (
                          <ul className="rl-compare-group-items">
                            {group.items.map((item, idx) => (
                              <li key={`old-${group.category}-${idx}`}>
                                <span>{item.title}</span>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
