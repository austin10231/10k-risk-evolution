import React, { useEffect, useMemo, useState } from 'react'
import { get, post } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'
import GlobalConfigInlineEditor from '../components/GlobalConfigInlineEditor'
import useSlidingTabIndicator from '../lib/useSlidingTabIndicator'
import { FIXED_RISK_CATEGORIES } from '../lib/records'

function normalizeCategory(row) {
  const value = String(row?.dashboard_category || row?.category || '').trim()
  return FIXED_RISK_CATEGORIES.includes(value) ? value : 'General & Other'
}

function groupRisks(risks, categoryFilter, keywordFilter) {
  const grouped = new Map()
  const keyword = String(keywordFilter || '').trim().toLowerCase()
  const category = String(categoryFilter || '').trim()

  ;(Array.isArray(risks) ? risks : []).forEach((row) => {
    const cat = normalizeCategory(row)
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

function pairMatchesFilters(pair, categoryFilter, keywordFilter) {
  const category = String(categoryFilter || '').trim()
  const keyword = String(keywordFilter || '').trim().toLowerCase()
  const cat = normalizeCategory(pair?.latest || pair?.prior || {})
  if (category && category !== 'ALL' && category !== cat) return false
  if (keyword) {
    const hay = `${cat} ${pair?.latest?.title || ''} ${pair?.prior?.title || ''}`.toLowerCase()
    if (!hay.includes(keyword)) return false
  }
  return true
}

// Local re-bucketing based on the user-controlled threshold slider.
// Backend returns `pairs.candidates` containing every Hungarian pair
// with score >= 0.45; we redistribute them into retained/modified/added/
// removed client-side so the slider feels instant.
function rebucket(data, threshold, dismissed) {
  if (!data) return null
  const candidates = Array.isArray(data?.pairs?.candidates) ? data.pairs.candidates : []
  const tLow = Number.isFinite(Number(threshold?.low)) ? Number(threshold.low) : (data?.scoring?.threshold_low ?? 0.58)
  const tHigh = Number.isFinite(Number(threshold?.high)) ? Number(threshold.high) : (data?.scoring?.threshold_high ?? 0.82)
  const dismissedSet = dismissed instanceof Set ? dismissed : new Set()

  const retained = []
  const modified = []
  const matchedPrior = new Set()
  const matchedLatest = new Set()

  candidates.forEach((pair) => {
    const key = `${pair?.prior?.title || ''}||${pair?.latest?.title || ''}`
    if (dismissedSet.has(key)) return
    const score = Number(pair?.score) || 0
    if (score < tLow) return
    if (score >= tHigh) retained.push(pair)
    else modified.push(pair)
    matchedPrior.add(pair?.prior?.title || '')
    matchedLatest.add(pair?.latest?.title || '')
  })

  const priorTotal = Number(data?.summary?.prior_total) || 0
  const latestTotal = Number(data?.summary?.latest_total) || 0

  // Build the added/removed lists from the original payload, removing any
  // titles that we just successfully matched and adding back any that we
  // intentionally dismissed.
  const baseAdded = Array.isArray(data?.pairs?.added) ? data.pairs.added : []
  const baseRemoved = Array.isArray(data?.pairs?.removed) ? data.pairs.removed : []

  const added = []
  const seenAddedTitles = new Set()
  baseAdded.forEach((item) => {
    const title = String(item?.title || '')
    if (matchedLatest.has(title)) return
    if (!title || seenAddedTitles.has(title)) return
    seenAddedTitles.add(title)
    added.push(item)
  })
  ;(Array.isArray(data?.pairs?.candidates) ? data.pairs.candidates : []).forEach((pair) => {
    const title = String(pair?.latest?.title || '')
    const key = `${pair?.prior?.title || ''}||${pair?.latest?.title || ''}`
    if (!matchedLatest.has(title) && title && !seenAddedTitles.has(title) && !dismissedSet.has(key)) {
      // Title is below threshold AND not currently matched — bring it
      // into the added column.
      seenAddedTitles.add(title)
      added.push(pair.latest)
    }
    if (dismissedSet.has(key)) {
      if (title && !seenAddedTitles.has(title)) {
        seenAddedTitles.add(title)
        added.push(pair.latest)
      }
    }
  })

  const removed = []
  const seenRemovedTitles = new Set()
  baseRemoved.forEach((item) => {
    const title = String(item?.title || '')
    if (matchedPrior.has(title)) return
    if (!title || seenRemovedTitles.has(title)) return
    seenRemovedTitles.add(title)
    removed.push(item)
  })
  ;(Array.isArray(data?.pairs?.candidates) ? data.pairs.candidates : []).forEach((pair) => {
    const title = String(pair?.prior?.title || '')
    const key = `${pair?.prior?.title || ''}||${pair?.latest?.title || ''}`
    if (!matchedPrior.has(title) && title && !seenRemovedTitles.has(title) && !dismissedSet.has(key)) {
      seenRemovedTitles.add(title)
      removed.push(pair.prior)
    }
    if (dismissedSet.has(key)) {
      if (title && !seenRemovedTitles.has(title)) {
        seenRemovedTitles.add(title)
        removed.push(pair.prior)
      }
    }
  })

  // Rebuild category coverage matrix from the bucketed results so the
  // table stays in sync with the slider.
  const matrix = new Map()
  const empty = () => ({ retained: 0, modified: 0, added: 0, removed: 0, prior_total: 0, latest_total: 0 })
  retained.forEach((p) => {
    const cat = normalizeCategory(p?.latest)
    if (!matrix.has(cat)) matrix.set(cat, empty())
    matrix.get(cat).retained += 1
  })
  modified.forEach((p) => {
    const cat = normalizeCategory(p?.latest)
    if (!matrix.has(cat)) matrix.set(cat, empty())
    matrix.get(cat).modified += 1
  })
  added.forEach((it) => {
    const cat = normalizeCategory(it)
    if (!matrix.has(cat)) matrix.set(cat, empty())
    matrix.get(cat).added += 1
  })
  removed.forEach((it) => {
    const cat = normalizeCategory(it)
    if (!matrix.has(cat)) matrix.set(cat, empty())
    matrix.get(cat).removed += 1
  })
  // Inject prior/latest totals from the original matrix so we keep the
  // overall denominators consistent.
  ;(Array.isArray(data?.category_matrix) ? data.category_matrix : []).forEach((row) => {
    const cat = row?.category || ''
    if (!cat) return
    if (!matrix.has(cat)) matrix.set(cat, empty())
    matrix.get(cat).prior_total = Number(row?.prior_total) || 0
    matrix.get(cat).latest_total = Number(row?.latest_total) || 0
  })
  const categoryMatrix = Array.from(matrix.entries())
    .map(([cat, counts]) => ({ category: cat, ...counts }))
    .sort((a, b) => (b.prior_total + b.latest_total) - (a.prior_total + a.latest_total) || a.category.localeCompare(b.category))

  const total = retained.length + modified.length + added.length + removed.length
  const summary = {
    retained: retained.length,
    modified: modified.length,
    added: added.length,
    removed: removed.length,
    prior_total: priorTotal,
    latest_total: latestTotal,
    churn_rate: total ? Math.round(((modified.length + added.length + removed.length) / total) * 1000) / 1000 : 0,
    avg_match_score: (() => {
      const merged = retained.concat(modified)
      if (!merged.length) return 0
      return Math.round((merged.reduce((acc, p) => acc + (Number(p?.score) || 0), 0) / merged.length) * 1000) / 1000
    })(),
    new_count: added.length,
    removed_count: removed.length,
  }

  return {
    ...data,
    pairs: { ...data.pairs, retained, modified, added, removed },
    category_matrix: categoryMatrix,
    summary,
  }
}

function DiffChips({ diff }) {
  const added = Array.isArray(diff?.added) ? diff.added : []
  const removed = Array.isArray(diff?.removed) ? diff.removed : []
  if (!added.length && !removed.length) return null
  return (
    <div className="rl-compare-diff-chips">
      {removed.slice(0, 6).map((tok, i) => (
        <span key={`rm-${i}`} className="rl-compare-diff-chip removed">− {tok}</span>
      ))}
      {added.slice(0, 6).map((tok, i) => (
        <span key={`ad-${i}`} className="rl-compare-diff-chip added">+ {tok}</span>
      ))}
    </div>
  )
}

function PairCard({ pair, tone, onDismiss }) {
  const score = Number(pair?.score) || 0
  const pct = Math.round(score * 100)
  const cat = normalizeCategory(pair?.latest || pair?.prior || {})
  return (
    <div className={`rl-compare-pair-card tone-${tone}`}>
      <div className="rl-compare-pair-meta">
        <span className="rl-compare-pair-cat">{cat}</span>
        <span className="rl-compare-pair-score" title={JSON.stringify(pair?.components || {})}>
          {pct}%
        </span>
        {onDismiss ? (
          <button
            type="button"
            className="rl-compare-pair-dismiss"
            onClick={onDismiss}
            title="Mark as wrong pair — splits this match back into Added and Removed"
          >
            ✕ wrong pair
          </button>
        ) : null}
      </div>
      <div className="rl-compare-pair-bodies">
        <div className="rl-compare-pair-body prior">
          <span className="rl-compare-pair-side-label">Prior</span>
          <p>{pair?.prior?.title || '—'}</p>
        </div>
        <div className="rl-compare-pair-body latest">
          <span className="rl-compare-pair-side-label">Latest</span>
          <p>{pair?.latest?.title || '—'}</p>
        </div>
      </div>
      {pair?.title_changed ? <DiffChips diff={pair?.diff} /> : null}
    </div>
  )
}

function CategoryMatrix({ rows }) {
  const visible = Array.isArray(rows) ? rows.filter((r) => (r.retained + r.modified + r.added + r.removed) > 0) : []
  if (!visible.length) return null
  return (
    <div className="rl-compare-matrix">
      <table>
        <thead>
          <tr>
            <th>Category</th>
            <th title="Same risk in both filings (high confidence)">Retained</th>
            <th title="Same risk, wording changed">Modified</th>
            <th title="Only in newer filing">Added</th>
            <th title="Only in older filing">Removed</th>
            <th title="Risk count on prior side">P</th>
            <th title="Risk count on latest side">L</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((row) => (
            <tr key={row.category}>
              <td className="rl-compare-matrix-cat">{row.category}</td>
              <td className="rl-compare-matrix-cell retained">{row.retained}</td>
              <td className="rl-compare-matrix-cell modified">{row.modified}</td>
              <td className="rl-compare-matrix-cell added">{row.added}</td>
              <td className="rl-compare-matrix-cell removed">{row.removed}</td>
              <td>{row.prior_total}</td>
              <td>{row.latest_total}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function dismissedStorageKey(latestId, priorId) {
  return `rl-compare-dismissed:${priorId || ''}::${latestId || ''}`
}

function loadDismissed(latestId, priorId) {
  try {
    const raw = window.localStorage.getItem(dismissedStorageKey(latestId, priorId))
    if (!raw) return new Set()
    const arr = JSON.parse(raw)
    return new Set(Array.isArray(arr) ? arr : [])
  } catch {
    return new Set()
  }
}

function saveDismissed(latestId, priorId, set) {
  try {
    window.localStorage.setItem(
      dismissedStorageKey(latestId, priorId),
      JSON.stringify(Array.from(set || [])),
    )
  } catch {
    // localStorage may be unavailable in private browsing; silently no-op.
  }
}

export default function ComparePage() {
  const modeTabsRef = React.useRef(null)
  const { config } = useGlobalConfig()
  const [records, setRecords] = useState([])
  const [mode, setMode] = useState('yoy')
  const [latestId, setLatestId] = useState('')
  const [priorId, setPriorId] = useState('')
  const [rawData, setRawData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingRecords, setLoadingRecords] = useState(true)
  const [error, setError] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('ALL')
  const [keywordFilter, setKeywordFilter] = useState('')
  const [newOpenMap, setNewOpenMap] = useState({})
  const [removedOpenMap, setRemovedOpenMap] = useState({})
  const [retainedOpen, setRetainedOpen] = useState(false)
  const [modifiedOpen, setModifiedOpen] = useState(true)
  const [matrixOpen, setMatrixOpen] = useState(false)
  const [thresholdLow, setThresholdLow] = useState(null)
  const [thresholdHigh, setThresholdHigh] = useState(null)
  const [dismissed, setDismissed] = useState(() => new Set())

  useEffect(() => {
    let mounted = true
    setLoadingRecords(true)
    get('/api/records', { timeoutMs: 15000 })
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
    setRawData(null)
    try {
      const res = await post(
        '/api/compare',
        { latest_record_id: latestId, prior_record_id: priorId, mode },
        { timeoutMs: 30000 },
      )
      const payload = res?.data || null
      setRawData(payload)
      if (payload?.scoring) {
        setThresholdLow(Number(payload.scoring.threshold_low))
        setThresholdHigh(Number(payload.scoring.threshold_high))
      }
      setDismissed(loadDismissed(payload?.latest_record_id, payload?.prior_record_id))
    } catch (e) {
      setError(e.message || 'Compare failed')
    } finally {
      setLoading(false)
    }
  }

  useSlidingTabIndicator(modeTabsRef, [mode])

  const data = useMemo(
    () => rebucket(rawData, { low: thresholdLow, high: thresholdHigh }, dismissed),
    [rawData, thresholdLow, thresholdHigh, dismissed],
  )

  const groupedNew = useMemo(
    () => groupRisks(data?.pairs?.added || [], categoryFilter, keywordFilter),
    [data?.pairs?.added, categoryFilter, keywordFilter],
  )
  const groupedRemoved = useMemo(
    () => groupRisks(data?.pairs?.removed || [], categoryFilter, keywordFilter),
    [data?.pairs?.removed, categoryFilter, keywordFilter],
  )

  const filteredRetained = useMemo(
    () => (data?.pairs?.retained || []).filter((p) => pairMatchesFilters(p, categoryFilter, keywordFilter)),
    [data?.pairs?.retained, categoryFilter, keywordFilter],
  )
  const filteredModified = useMemo(
    () => (data?.pairs?.modified || []).filter((p) => pairMatchesFilters(p, categoryFilter, keywordFilter)),
    [data?.pairs?.modified, categoryFilter, keywordFilter],
  )

  const allCategories = useMemo(() => {
    const s = new Set()
    ;(Array.isArray(data?.pairs?.added) ? data.pairs.added : []).forEach((r) => s.add(normalizeCategory(r)))
    ;(Array.isArray(data?.pairs?.removed) ? data.pairs.removed : []).forEach((r) => s.add(normalizeCategory(r)))
    ;(Array.isArray(data?.pairs?.retained) ? data.pairs.retained : []).forEach((r) => s.add(normalizeCategory(r?.latest || r?.prior || {})))
    ;(Array.isArray(data?.pairs?.modified) ? data.pairs.modified : []).forEach((r) => s.add(normalizeCategory(r?.latest || r?.prior || {})))
    return Array.from(s).sort((a, b) => a.localeCompare(b))
  }, [data?.pairs?.added, data?.pairs?.removed, data?.pairs?.retained, data?.pairs?.modified])

  useEffect(() => {
    setNewOpenMap({})
    setRemovedOpenMap({})
    setCategoryFilter('ALL')
    setKeywordFilter('')
  }, [rawData?.latest_record_id, rawData?.prior_record_id])

  const toggleNewGroup = (cat) => {
    setNewOpenMap((prev) => ({ ...prev, [cat]: !prev[cat] }))
  }

  const toggleRemovedGroup = (cat) => {
    setRemovedOpenMap((prev) => ({ ...prev, [cat]: !prev[cat] }))
  }

  const onDismissPair = (pair) => {
    if (!pair?.prior?.title || !pair?.latest?.title) return
    const key = `${pair.prior.title}||${pair.latest.title}`
    const next = new Set(dismissed)
    next.add(key)
    setDismissed(next)
    saveDismissed(rawData?.latest_record_id, rawData?.prior_record_id, next)
  }

  const onResetDismissed = () => {
    const empty = new Set()
    setDismissed(empty)
    saveDismissed(rawData?.latest_record_id, rawData?.prior_record_id, empty)
  }

  const onResetThresholds = () => {
    setThresholdLow(Number(rawData?.scoring?.threshold_low))
    setThresholdHigh(Number(rawData?.scoring?.threshold_high))
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
            <span className="rl-up-result-value" title={labelMap.get(latestId) || latestId || '—'}>
              {labelMap.get(latestId) || latestId || '—'}
            </span>
          </div>
          <div className="rl-up-result-meta">
            <span>Prior Record</span>
            <span className="rl-up-result-value" title={labelMap.get(priorId) || priorId || '—'}>
              {labelMap.get(priorId) || priorId || '—'}
            </span>
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
                <div className="rl-compare-result-pill retained">
                  <span>Same risk (high conf.)</span>
                  <strong>{data?.summary?.retained ?? 0} retained</strong>
                </div>
                <div className="rl-compare-result-pill modified">
                  <span>Same risk, rewritten</span>
                  <strong>{data?.summary?.modified ?? 0} modified</strong>
                </div>
                <div className="rl-compare-result-pill new">
                  <span>Only in newer filing</span>
                  <strong>{data?.summary?.added ?? 0} added</strong>
                </div>
                <div className="rl-compare-result-pill removed">
                  <span>Only in older filing</span>
                  <strong>{data?.summary?.removed ?? 0} removed</strong>
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

            <div className="rl-compare-threshold-bar">
              <div className="rl-compare-threshold-segment">
                <label className="section-title">Modified ≥</label>
                <input
                  type="range"
                  min={0.45}
                  max={Number.isFinite(thresholdHigh) ? thresholdHigh : 0.82}
                  step={0.01}
                  value={Number.isFinite(thresholdLow) ? thresholdLow : 0.58}
                  onChange={(e) => setThresholdLow(Number(e.target.value))}
                />
                <span className="rl-compare-threshold-value">
                  {Math.round(((Number.isFinite(thresholdLow) ? thresholdLow : 0.58)) * 100)}%
                </span>
              </div>
              <div className="rl-compare-threshold-segment">
                <label className="section-title">Retained ≥</label>
                <input
                  type="range"
                  min={Number.isFinite(thresholdLow) ? thresholdLow : 0.58}
                  max={0.99}
                  step={0.01}
                  value={Number.isFinite(thresholdHigh) ? thresholdHigh : 0.82}
                  onChange={(e) => setThresholdHigh(Number(e.target.value))}
                />
                <span className="rl-compare-threshold-value">
                  {Math.round(((Number.isFinite(thresholdHigh) ? thresholdHigh : 0.82)) * 100)}%
                </span>
              </div>
              <button className="btn-secondary rl-compare-threshold-reset" onClick={onResetThresholds}>
                Reset thresholds
              </button>
              {dismissed.size ? (
                <button className="btn-secondary rl-compare-threshold-reset" onClick={onResetDismissed}>
                  Restore {dismissed.size} dismissed pair{dismissed.size === 1 ? '' : 's'}
                </button>
              ) : null}
              <span className="rl-compare-side-note rl-compare-threshold-note">
                Avg match {Math.round(((data?.summary?.avg_match_score ?? 0)) * 100)}% ·
                method {data?.scoring?.method || '—'}
              </span>
            </div>

            {mode === 'cross' || matrixOpen ? (
              <div className="rl-compare-group" style={{ background: 'rgba(247, 251, 255, 0.45)' }}>
                <button className="rl-compare-group-head" onClick={() => setMatrixOpen((v) => !v)}>
                  <span>Category coverage matrix</span>
                  <strong>{matrixOpen || mode === 'cross' ? '−' : '+'}</strong>
                </button>
                {(matrixOpen || mode === 'cross') ? (
                  <CategoryMatrix rows={data?.category_matrix} />
                ) : null}
              </div>
            ) : (
              <button
                type="button"
                className="rl-compare-matrix-toggle"
                onClick={() => setMatrixOpen(true)}
              >
                Show category coverage matrix
              </button>
            )}

            <div className="rl-compare-group">
              <button className="rl-compare-group-head" onClick={() => setModifiedOpen((v) => !v)}>
                <span>🔄 Modified pairs ({filteredModified.length})</span>
                <strong>{modifiedOpen ? '−' : '+'}</strong>
              </button>
              {modifiedOpen ? (
                <div className="rl-compare-pair-list">
                  {!filteredModified.length ? (
                    <p className="rl-compare-pair-empty">No modified pairs at the current threshold.</p>
                  ) : (
                    filteredModified.map((pair, idx) => (
                      <PairCard
                        key={`mod-${idx}-${pair?.prior?.title}-${pair?.latest?.title}`}
                        pair={pair}
                        tone="modified"
                        onDismiss={() => onDismissPair(pair)}
                      />
                    ))
                  )}
                </div>
              ) : null}
            </div>

            <div className="rl-compare-group">
              <button className="rl-compare-group-head" onClick={() => setRetainedOpen((v) => !v)}>
                <span>🟦 Retained pairs ({filteredRetained.length})</span>
                <strong>{retainedOpen ? '−' : '+'}</strong>
              </button>
              {retainedOpen ? (
                <div className="rl-compare-pair-list">
                  {!filteredRetained.length ? (
                    <p className="rl-compare-pair-empty">No retained pairs at the current threshold.</p>
                  ) : (
                    filteredRetained.map((pair, idx) => (
                      <PairCard
                        key={`ret-${idx}-${pair?.prior?.title}-${pair?.latest?.title}`}
                        pair={pair}
                        tone="retained"
                        onDismiss={() => onDismissPair(pair)}
                      />
                    ))
                  )}
                </div>
              ) : null}
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
