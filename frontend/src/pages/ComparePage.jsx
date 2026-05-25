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

function groupRisks(risks, categoryFilter, keywordFilter, hintMap) {
  const grouped = new Map()
  const keyword = String(keywordFilter || '').trim().toLowerCase()
  const category = String(categoryFilter || '').trim()
  const hints = hintMap instanceof Map ? hintMap : new Map()

  ;(Array.isArray(risks) ? risks : []).forEach((row) => {
    const cat = normalizeCategory(row)
    const title = String(row?.title || '').trim()
    if (!title) return
    if (category && category !== 'ALL' && category !== cat) return
    if (keyword && !`${cat} ${title}`.toLowerCase().includes(keyword)) return

    if (!grouped.has(cat)) grouped.set(cat, [])
    grouped.get(cat).push({ category: cat, title, hint: hints.get(title) || null })
  })

  return Array.from(grouped.entries())
    .map(([cat, items]) => ({ category: cat, items }))
    .sort((a, b) => b.items.length - a.items.length || a.category.localeCompare(b.category))
}

function buildNearRewriteHints(candidates, tLow, addedItems, removedItems) {
  const rows = Array.isArray(candidates) ? candidates : []
  const low = Number.isFinite(Number(tLow)) ? Number(tLow) : 0.58
  const floor = Math.max(0.45, low - 0.12)
  const addedSet = new Set((Array.isArray(addedItems) ? addedItems : []).map((x) => String(x?.title || '')))
  const removedSet = new Set((Array.isArray(removedItems) ? removedItems : []).map((x) => String(x?.title || '')))
  const addedHints = new Map()
  const removedHints = new Map()

  rows.forEach((pair) => {
    const score = Number(pair?.score) || 0
    if (score >= low || score < floor) return
    const latestTitle = String(pair?.latest?.title || '')
    const priorTitle = String(pair?.prior?.title || '')
    if (!latestTitle || !priorTitle) return

    if (addedSet.has(latestTitle)) {
      const prev = addedHints.get(latestTitle)
      if (!prev || score > prev.score) {
        addedHints.set(latestTitle, { title: priorTitle, score })
      }
    }
    if (removedSet.has(priorTitle)) {
      const prev = removedHints.get(priorTitle)
      if (!prev || score > prev.score) {
        removedHints.set(priorTitle, { title: latestTitle, score })
      }
    }
  })

  return { addedHints, removedHints }
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

function buildConfidenceNote(pair) {
  const score = Number(pair?.score) || 0
  const comps = pair?.components || {}
  const entries = Object.entries(comps)
    .filter(([, v]) => typeof v === 'number' && Number.isFinite(v))
    .sort((a, b) => b[1] - a[1])
  const top = entries[0]
  const map = {
    embed: 'semantic embedding',
    concept: 'risk concepts',
    jaccard: 'keyword overlap',
    trigram: 'phrase structure',
    label: 'label match',
  }
  const topText = top ? `${map[top[0]] || top[0]} strong` : 'multiple signals agree'
  if (pair?.auto_promoted) return `Medium confidence (${Math.round(score * 100)}%): auto-merged from added/removed, ${topText}.`
  if (score >= 0.88) return `High confidence (${Math.round(score * 100)}%): ${topText}.`
  if (score >= 0.74) return `Mid-high confidence (${Math.round(score * 100)}%): ${topText}.`
  return `Medium confidence (${Math.round(score * 100)}%): recommended for manual review.`
}

function promoteNearRewrites(candidates, addedItems, removedItems, tLow) {
  const rows = Array.isArray(candidates) ? candidates : []
  const low = Number.isFinite(Number(tLow)) ? Number(tLow) : 0.58
  const floor = Math.max(0.45, low - 0.14)
  const addedByTitle = new Map((Array.isArray(addedItems) ? addedItems : []).map((x) => [String(x?.title || ''), x]))
  const removedByTitle = new Map((Array.isArray(removedItems) ? removedItems : []).map((x) => [String(x?.title || ''), x]))
  const usedAdded = new Set()
  const usedRemoved = new Set()
  const promoted = []

  const eligible = rows
    .filter((pair) => {
      const score = Number(pair?.score) || 0
      if (score >= low || score < floor) return false
      const latestTitle = String(pair?.latest?.title || '')
      const priorTitle = String(pair?.prior?.title || '')
      if (!latestTitle || !priorTitle) return false
      if (!addedByTitle.has(latestTitle) || !removedByTitle.has(priorTitle)) return false
      const concept = Number(pair?.components?.concept) || 0
      const jaccard = Number(pair?.components?.jaccard) || 0
      return concept >= 0.18 || jaccard >= 0.2
    })
    .sort((a, b) => (Number(b?.score) || 0) - (Number(a?.score) || 0))

  eligible.forEach((pair) => {
    const latestTitle = String(pair?.latest?.title || '')
    const priorTitle = String(pair?.prior?.title || '')
    if (usedAdded.has(latestTitle) || usedRemoved.has(priorTitle)) return
    usedAdded.add(latestTitle)
    usedRemoved.add(priorTitle)
    promoted.push({ ...pair, auto_promoted: true, title_changed: true })
  })

  const nextAdded = (Array.isArray(addedItems) ? addedItems : []).filter((x) => !usedAdded.has(String(x?.title || '')))
  const nextRemoved = (Array.isArray(removedItems) ? removedItems : []).filter((x) => !usedRemoved.has(String(x?.title || '')))

  return { promoted, nextAdded, nextRemoved }
}

function downloadCompareCsv({ data, priorYearLabel, latestYearLabel }) {
  if (!data) return
  const esc = (v) => {
    const s = String(v ?? '')
    if (s.includes('"') || s.includes(',') || s.includes('\n')) return `"${s.replace(/"/g, '""')}"`
    return s
  }
  const rows = [['section', 'category', 'score', 'confidence_note', `prior_${priorYearLabel}`, `latest_${latestYearLabel}`]]
  ;(Array.isArray(data?.pairs?.modified) ? data.pairs.modified : []).forEach((pair) => {
    rows.push([
      pair?.auto_promoted ? 'rewritten_auto' : 'rewritten',
      normalizeCategory(pair?.latest || pair?.prior || {}),
      Number(pair?.score || 0).toFixed(4),
      buildConfidenceNote(pair),
      pair?.prior?.title || '',
      pair?.latest?.title || '',
    ])
  })
  ;(Array.isArray(data?.pairs?.added) ? data.pairs.added : []).forEach((item) => {
    rows.push(['added', normalizeCategory(item), '', '', '', item?.title || ''])
  })
  ;(Array.isArray(data?.pairs?.removed) ? data.pairs.removed : []).forEach((item) => {
    rows.push(['removed', normalizeCategory(item), '', '', item?.title || '', ''])
  })
  ;(Array.isArray(data?.pairs?.retained) ? data.pairs.retained : []).forEach((pair) => {
    rows.push([
      'unchanged',
      normalizeCategory(pair?.latest || pair?.prior || {}),
      Number(pair?.score || 0).toFixed(4),
      buildConfidenceNote(pair),
      pair?.prior?.title || '',
      pair?.latest?.title || '',
    ])
  })

  const csv = rows.map((line) => line.map(esc).join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `compare_${priorYearLabel}_vs_${latestYearLabel}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
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

  let added = []
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

  let removed = []
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

  const promoted = promoteNearRewrites(candidates, added, removed, tLow)
  if (promoted.promoted.length) {
    modified.push(...promoted.promoted)
    added = promoted.nextAdded
    removed = promoted.nextRemoved
  }

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

function PairCard({ pair, tone, onDismiss, priorLabel = 'Prior', latestLabel = 'Latest' }) {
  const score = Number(pair?.score) || 0
  const pct = Math.round(score * 100)
  const cat = normalizeCategory(pair?.latest || pair?.prior || {})
  const note = buildConfidenceNote(pair)
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
      <p className="rl-compare-pair-note">{note}</p>
      <div className="rl-compare-pair-bodies">
        <div className="rl-compare-pair-body prior">
          <span className="rl-compare-pair-side-label">{priorLabel}</span>
          <p>{pair?.prior?.title || '—'}</p>
        </div>
        <div className="rl-compare-pair-body latest">
          <span className="rl-compare-pair-side-label">{latestLabel}</span>
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
  const [resultTab, setResultTab] = useState('changes') // 'changes' | 'unchanged' | 'category'
  const [thresholdLow, setThresholdLow] = useState(null)
  const [thresholdHigh, setThresholdHigh] = useState(null)
  const [dismissed, setDismissed] = useState(() => new Set())
  const resultTabsRef = React.useRef(null)

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
  const recordMap = useMemo(() => {
    const m = new Map()
    records.forEach((r) => m.set(r.record_id, r))
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
      .filter((r) => (
        String(r.company || '') === companyYoy
        && Number(r.year) === Number(latestYear)
        && String(r.filing_type || '10-K') === ftYoy
      ))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0]
    const priorRec = records
      .filter((r) => (
        String(r.company || '') === companyYoy
        && Number(r.year) === Number(priorYear)
        && String(r.filing_type || '10-K') === ftYoy
      ))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0]
    if (latestRec?.record_id) setLatestId(latestRec.record_id)
    if (priorRec?.record_id) setPriorId(priorRec.record_id)
  }, [companyYoy, ftYoy, latestYear, priorYear, records])

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
  useSlidingTabIndicator(resultTabsRef, [resultTab, rawData?.latest_record_id])

  const data = useMemo(
    () => rebucket(rawData, { low: thresholdLow, high: thresholdHigh }, dismissed),
    [rawData, thresholdLow, thresholdHigh, dismissed],
  )
  const hintMaps = useMemo(
    () => buildNearRewriteHints(
      data?.pairs?.candidates || [],
      Number.isFinite(thresholdLow) ? thresholdLow : data?.scoring?.threshold_low,
      data?.pairs?.added || [],
      data?.pairs?.removed || [],
    ),
    [data?.pairs?.candidates, data?.pairs?.added, data?.pairs?.removed, thresholdLow, data?.scoring?.threshold_low],
  )

  const groupedNew = useMemo(
    () => groupRisks(data?.pairs?.added || [], categoryFilter, keywordFilter, hintMaps.addedHints),
    [data?.pairs?.added, categoryFilter, keywordFilter, hintMaps.addedHints],
  )
  const groupedRemoved = useMemo(
    () => groupRisks(data?.pairs?.removed || [], categoryFilter, keywordFilter, hintMaps.removedHints),
    [data?.pairs?.removed, categoryFilter, keywordFilter, hintMaps.removedHints],
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
    setResultTab('changes')
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

  const priorRecord = recordMap.get(data?.prior_record_id) || null
  const latestRecord = recordMap.get(data?.latest_record_id) || null
  const priorYearLabel = priorRecord?.year ? String(priorRecord.year) : 'Prior'
  const latestYearLabel = latestRecord?.year ? String(latestRecord.year) : 'Latest'
  const rewrittenTitle = `Rewritten risks (${priorYearLabel} vs ${latestYearLabel})`
  const newRisksTitle = `New risks (only in ${latestYearLabel} filing)`
  const removedRisksTitle = `Removed risks (only in ${priorYearLabel} filing)`
  const diagnostics = useMemo(() => {
    if (!data) return []
    const list = []
    const priorTotal = Number(data?.summary?.prior_total || 0)
    const latestTotal = Number(data?.summary?.latest_total || 0)
    const matched = Number(data?.summary?.retained || 0) + Number(data?.summary?.modified || 0)
    const modifiedCount = Number(data?.summary?.modified || 0)
    const promotedCount = (Array.isArray(data?.pairs?.modified) ? data.pairs.modified : []).filter((p) => p?.auto_promoted).length
    if (priorTotal < 3 || latestTotal < 3) {
      list.push('Very few extracted risks in one filing. Verify source completeness or compare adjacent years.')
    }
    if (matched === 0 && (priorTotal > 0 || latestTotal > 0)) {
      list.push('No reliable pairs found. Review Added/Removed first and spot-check manually.')
    }
    if (modifiedCount && promotedCount) {
      list.push(`Auto-merged ${promotedCount} high-similarity added/removed pairs into rewritten items.`)
    }
    return list
  }, [data])

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

      <section className={`rl-compare-workbench ${mode === 'yoy' ? 'is-yoy' : 'is-cross'}`}>
        <div className="rl-up-form rl-compare-control">
          <p className="section-title rl-compare-title-lite">Configure</p>
          <div className="rl-tabs mt-2 rl-tab-motion" ref={modeTabsRef}>
            <button className={`rl-tab-btn ${mode === 'yoy' ? 'active' : ''}`} onClick={() => setMode('yoy')}>
              Year-over-Year
            </button>
            <button className={`rl-tab-btn ${mode === 'cross' ? 'active' : ''}`} onClick={() => setMode('cross')}>
              Cross-Company
            </button>
          </div>

          {loadingRecords ? <p className="mt-2 text-sm text-slate-500">Loading records…</p> : null}

          {!loadingRecords && mode === 'yoy' ? (
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <div>
                <label className="section-title rl-compare-title-lite">Company</label>
                <select className="input mt-2" value={companyYoy} onChange={(e) => setCompanyYoy(e.target.value)}>
                  {companies.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="section-title rl-compare-title-lite">Filing Type</label>
                <select className="input mt-2" value={ftYoy} onChange={(e) => setFtYoy(e.target.value)}>
                  <option value="10-K">10-K</option>
                  <option value="10-Q">10-Q</option>
                </select>
              </div>
              <div>
                <label className="section-title rl-compare-title-lite">Latest Year</label>
                <select className="input mt-2" value={latestYear} onChange={(e) => setLatestYear(e.target.value)}>
                  {yoyYears.map((y) => (
                    <option key={y} value={String(y)}>
                      {y}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="section-title rl-compare-title-lite">Prior Year</label>
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
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <label className="section-title rl-compare-title-lite">Company</label>
                    <select className="input mt-2" value={companyA} onChange={(e) => setCompanyA(e.target.value)}>
                      {companies.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="section-title rl-compare-title-lite">Year</label>
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
                <div className="grid gap-3 md:grid-cols-2">
                  <div>
                    <label className="section-title rl-compare-title-lite">Company</label>
                    <select className="input mt-2" value={companyB} onChange={(e) => setCompanyB(e.target.value)}>
                      {companies.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="section-title rl-compare-title-lite">Year</label>
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
              {loading ? 'Comparing…' : 'Run Compare'}
            </button>
          </div>
        </div>

        <aside className="rl-up-results rl-compare-side">
          <p className="section-title rl-compare-title-lite">Comparison Lens</p>
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
            <span>{latestRecord?.year ? `${latestRecord.year} Record` : 'Latest Record'}</span>
            <span className="rl-up-result-value" title={labelMap.get(latestId) || latestId || '—'}>
              {labelMap.get(latestId) || latestId || '—'}
            </span>
          </div>
          <div className="rl-up-result-meta">
            <span>{priorRecord?.year ? `${priorRecord.year} Record` : 'Prior Record'}</span>
            <span className="rl-up-result-value" title={labelMap.get(priorId) || priorId || '—'}>
              {labelMap.get(priorId) || priorId || '—'}
            </span>
          </div>
        </aside>
      </section>

      {data && (
        <section className="rl-compare-result-shell">
          {/* Plain-language headline so a first-time viewer knows the
              answer before touching anything else. */}
          <div className="rl-compare-headline">
            <p className="rl-compare-headline-pretitle">
              Comparing <strong>{labelMap.get(data?.prior_record_id) || data?.prior_record_id || '—'}</strong>
              <span className="rl-compare-headline-arrow">→</span>
              <strong>{labelMap.get(data?.latest_record_id) || data?.latest_record_id || '—'}</strong>
            </p>
            <p className="rl-compare-headline-summary">
              <span className="rl-compare-chip added">{data?.summary?.added ?? 0} added</span>
              <span className="rl-compare-chip removed">{data?.summary?.removed ?? 0} removed</span>
              <span className="rl-compare-chip rewritten">{data?.summary?.modified ?? 0} rewritten</span>
              <span className="rl-compare-chip muted">
                {data?.summary?.retained ?? 0} unchanged
                {(data?.summary?.retained ?? 0) > 0 && resultTab !== 'unchanged' ? (
                  <button
                    type="button"
                    className="rl-compare-chip-link"
                    onClick={() => setResultTab('unchanged')}
                  >
                    view →
                  </button>
                ) : null}
              </span>
              <button
                type="button"
                className="btn-secondary rl-compare-export-btn"
                onClick={() => downloadCompareCsv({ data, priorYearLabel, latestYearLabel })}
              >
                Export CSV
              </button>
            </p>
            <p className="rl-compare-inline-tip">
              Most changes are usually rewrites. Check rewritten pairs first, then review true additions/removals.
            </p>
            {diagnostics.length ? (
              <div className="rl-compare-inline-diagnostics">
                {diagnostics.map((msg, idx) => (
                  <p key={`diag-${idx}`} className="rl-compare-inline-tip">{msg}</p>
                ))}
              </div>
            ) : null}
          </div>

          {/* Result tabs — same visual language as the mode tabs above. */}
          <div className="rl-tabs rl-tab-motion rl-compare-result-tabs" ref={resultTabsRef}>
            <button
              className={`rl-tab-btn ${resultTab === 'changes' ? 'active' : ''}`}
              onClick={() => setResultTab('changes')}
            >
              Changes ({(data?.summary?.added ?? 0) + (data?.summary?.removed ?? 0) + (data?.summary?.modified ?? 0)})
            </button>
            <button
              className={`rl-tab-btn ${resultTab === 'unchanged' ? 'active' : ''}`}
              onClick={() => setResultTab('unchanged')}
            >
              Unchanged ({data?.summary?.retained ?? 0})
            </button>
            <button
              className={`rl-tab-btn ${resultTab === 'category' ? 'active' : ''}`}
              onClick={() => setResultTab('category')}
            >
              By Category
            </button>
          </div>

          {/* Filter bar — shared across Changes and Unchanged. Hidden in
              the By Category tab because the matrix already partitions. */}
          {resultTab !== 'category' ? (
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
          ) : null}

          {resultTab === 'changes' ? (
            <div className="rl-compare-changes-stack">
              {/* Rewritten pairs (was: Modified) */}
              <div className="rl-compare-column">
                <p className="section-title rl-compare-title-lite">{rewrittenTitle}</p>
                {!filteredModified.length ? (
                  <p className="mt-2 text-sm text-slate-500">No rewritten risks at the current sensitivity.</p>
                ) : (
                  <div className="rl-compare-pair-list">
                    {filteredModified.map((pair, idx) => (
                      <PairCard
                        key={`mod-${idx}-${pair?.prior?.title}-${pair?.latest?.title}`}
                        pair={pair}
                        tone="modified"
                        onDismiss={() => onDismissPair(pair)}
                        priorLabel={priorYearLabel}
                        latestLabel={latestYearLabel}
                      />
                    ))}
                  </div>
                )}
              </div>

              {/* Added */}
              <div className="rl-compare-column">
                <p className="section-title rl-compare-title-lite">{newRisksTitle}</p>
                {!groupedNew.length ? (
                  <p className="mt-2 text-sm text-slate-500">No new risks at the current sensitivity.</p>
                ) : (
                  <div className="rl-compare-group-list">
                    {groupedNew.map((group) => {
                      const isOpen = Boolean(newOpenMap[group.category])
                      return (
                        <div key={`new-${group.category}`} className="rl-compare-group">
                          <button className="rl-compare-group-head" onClick={() => toggleNewGroup(group.category)}>
                            <span>{group.category} ({group.items.length})</span>
                            <span className="rl-compare-group-chevron" aria-hidden="true">{isOpen ? '▾' : '▸'}</span>
                          </button>
                          {isOpen ? (
                            <ul className="rl-compare-group-items">
                              {group.items.map((item, idx) => (
                                <li key={`new-${group.category}-${idx}`}>
                                  <span>{item.title}</span>
                                  {item?.hint?.title ? (
                                    <p className="text-xs text-amber-700 mt-1">
                                      Possibly rewritten from prior: {item.hint.title} ({Math.round((Number(item.hint.score) || 0) * 100)}%)
                                    </p>
                                  ) : null}
                                </li>
                              ))}
                            </ul>
                          ) : null}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* Removed */}
              <div className="rl-compare-column">
                <p className="section-title rl-compare-title-lite">{removedRisksTitle}</p>
                {!groupedRemoved.length ? (
                  <p className="mt-2 text-sm text-slate-500">No removed risks at the current sensitivity.</p>
                ) : (
                  <div className="rl-compare-group-list">
                    {groupedRemoved.map((group) => {
                      const isOpen = Boolean(removedOpenMap[group.category])
                      return (
                        <div key={`old-${group.category}`} className="rl-compare-group">
                          <button className="rl-compare-group-head" onClick={() => toggleRemovedGroup(group.category)}>
                            <span>{group.category} ({group.items.length})</span>
                            <span className="rl-compare-group-chevron" aria-hidden="true">{isOpen ? '▾' : '▸'}</span>
                          </button>
                          {isOpen ? (
                            <ul className="rl-compare-group-items">
                              {group.items.map((item, idx) => (
                                <li key={`old-${group.category}-${idx}`}>
                                  <span>{item.title}</span>
                                  {item?.hint?.title ? (
                                    <p className="text-xs text-amber-700 mt-1">
                                      Possibly rewritten into latest: {item.hint.title} ({Math.round((Number(item.hint.score) || 0) * 100)}%)
                                    </p>
                                  ) : null}
                                </li>
                              ))}
                            </ul>
                          ) : null}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>
          ) : null}

          {resultTab === 'unchanged' ? (
            <div className="rl-compare-column">
              <p className="section-title rl-compare-title-lite">Risks present in both filings ({priorYearLabel} / {latestYearLabel})</p>
              {!filteredRetained.length ? (
                <p className="mt-2 text-sm text-slate-500">No unchanged risks at the current sensitivity.</p>
              ) : (
                <div className="rl-compare-pair-list">
                  {filteredRetained.map((pair, idx) => (
                    <PairCard
                      key={`ret-${idx}-${pair?.prior?.title}-${pair?.latest?.title}`}
                      pair={pair}
                      tone="retained"
                      onDismiss={() => onDismissPair(pair)}
                      priorLabel={priorYearLabel}
                      latestLabel={latestYearLabel}
                    />
                  ))}
                </div>
              )}
            </div>
          ) : null}

          {resultTab === 'category' ? (
            <div className="rl-compare-column">
              <p className="section-title rl-compare-title-lite">Risk counts by category</p>
              <p className="rl-compare-inline-tip">
                P = total in {priorYearLabel} filing · L = total in {latestYearLabel} filing.
              </p>
              <CategoryMatrix rows={data?.category_matrix} />
            </div>
          ) : null}

          <div className="rl-compare-filter-bar compact">
            {dismissed.size ? (
              <button className="btn-secondary rl-compare-threshold-reset" onClick={onResetDismissed}>
                Restore {dismissed.size} dismissed pair{dismissed.size === 1 ? '' : 's'}
              </button>
            ) : null}
          </div>
        </section>
      )}
    </div>
  )
}
