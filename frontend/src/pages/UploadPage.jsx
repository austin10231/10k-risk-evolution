import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { get, post } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'
import GlobalConfigInlineEditor from '../components/GlobalConfigInlineEditor'
import { companyOverview, groupedRiskTitles, riskCategoryCount, riskItemCount } from '../lib/records'
import useSlidingTabIndicator from '../lib/useSlidingTabIndicator'

const SCORING_HINT_SEEN_KEY = 'rl.upload.scoringHintSeen.v1'

const YEARS = Array.from({ length: 16 }, (_, i) => String(2025 - i))
const INDUSTRIES = [
  'Technology',
  'Healthcare',
  'Financials',
  'Energy',
  'Consumer Discretionary',
  'Consumer Staples',
  'Industrials',
  'Materials',
  'Utilities',
  'Real Estate',
  'Telecom',
  'Other',
]

function formatDate(v) {
  if (!v) return '—'
  try {
    const d = new Date(v)
    if (Number.isNaN(d.getTime())) return '—'
    return d.toLocaleString()
  } catch {
    return '—'
  }
}

function formatBytes(bytes) {
  const n = Number(bytes || 0)
  if (!Number.isFinite(n) || n <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let idx = 0
  let value = n
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${units[idx]}`
}

function toBase64DataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('Failed to read file'))
    reader.readAsDataURL(file)
  })
}

function RecordDetailPanel({ rec, result }) {
  if (!rec || !result) return null
  const ov = companyOverview(result)
  const aiSummary = String(result?.ai_summary || '').trim()
  const groups = groupedRiskTitles(result)
  const is10q = String(ov.filing_type || rec?.filing_type || '').toUpperCase() === '10-Q'
  const incremental = result?.incremental_10q_update && typeof result.incremental_10q_update === 'object'
    ? result.incremental_10q_update
    : null
  const hasIncremental = Boolean(incremental?.has_incremental_updates)
  const incrementalCount = Number(incremental?.incremental_count || 0)

  return (
    <section className="card p-5">
      <div className="rl-selected-banner">Selected filing loaded. Details are shown below for faster review.</div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="metric-card">
          <p className="metric-label">Company</p>
          <p className="metric-value">{ov.company || rec.company || '—'}</p>
        </div>
        <div className="metric-card">
          <p className="metric-label">Year</p>
          <p className="metric-value">{ov.year || rec.year || '—'}</p>
        </div>
        <div className="metric-card">
          <p className="metric-label">Risk Categories</p>
          <p className="metric-value">{riskCategoryCount(result)}</p>
        </div>
        <div className="metric-card">
          <p className="metric-label">Risk Items</p>
          <p className="metric-value">{riskItemCount(result)}</p>
        </div>
      </div>

      <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        <Link
          to={`/compare?company=${encodeURIComponent(rec.company || '')}&year=${encodeURIComponent(String(rec.year || ''))}`}
          className="btn-secondary w-full"
        >
          Go Compare
        </Link>
        <Link to={`/dashboard?industry=${encodeURIComponent(rec.industry || '')}`} className="btn-secondary w-full">
          Go Dashboard
        </Link>
        <Link to={`/tables?record_id=${encodeURIComponent(rec.record_id || '')}`} className="btn-secondary w-full">
          Go Tables
        </Link>
      </div>

      {aiSummary ? (
        <div className="mt-4">
          <div className="rl-section-header">🤖 AI Executive Summary</div>
          <div className="rl-info-box whitespace-pre-wrap">{aiSummary}</div>
        </div>
      ) : null}

      {ov.background ? (
        <div className="mt-4">
          <div className="rl-section-header">Business Overview</div>
          <p className="rl-body-text">{ov.background}</p>
        </div>
      ) : null}

      {is10q ? (
        <div className="mt-4">
          <div className="rl-section-header">10-Q Incremental Risk Updates</div>
          <div className="rl-info-box">
            {hasIncremental
              ? `Detected incremental updates in Item 1A (${incrementalCount} items).`
              : 'No explicit incremental risk update block detected in Item 1A.'}
          </div>
          {hasIncremental && Array.isArray(incremental?.incremental_risk_items) ? (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
              {incremental.incremental_risk_items.slice(0, 8).map((item, idx) => (
                <li key={`inc-risk-${idx}`}>{String(item || '').trim()}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="mt-4">
        <div className="rl-section-header">Risk Categories ({groups.length})</div>
        <div className="space-y-2">
          {groups.map((g) => (
            <details key={g.category} className="rl-expander">
              <summary>
                {g.category} ({g.titles.length})
              </summary>
              <ul>
                {g.titles.slice(0, 24).map((t, idx) => (
                  <li key={`${g.category}-${idx}`}>{t}</li>
                ))}
              </ul>
            </details>
          ))}
        </div>
      </div>
    </section>
  )
}

export default function UploadPage() {
  const { config } = useGlobalConfig()

  const [tab, setTab] = useState('ingest')
  const [ingestMode, setIngestMode] = useState('manual')
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // "How risk scoring works" hint — default open on first visit, collapsed
  // afterwards once the user has seen it (or actively closed it). Stored
  // under localStorage key SCORING_HINT_SEEN_KEY.
  const [scoringHintOpen, setScoringHintOpen] = useState(() => {
    if (typeof window === 'undefined') return false
    try {
      return !window.localStorage.getItem(SCORING_HINT_SEEN_KEY)
    } catch {
      return false
    }
  })

  const handleScoringHintToggle = (e) => {
    const next = Boolean(e?.target?.open)
    setScoringHintOpen(next)
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(SCORING_HINT_SEEN_KEY, '1')
    } catch {
      // SSR / private mode / quota — safe to ignore.
    }
  }

  const [search, setSearch] = useState('')
  const [company, setCompany] = useState('')
  const [ticker, setTicker] = useState('')
  const [industry, setIndustry] = useState('Technology')
  const [year, setYear] = useState('2024')
  const [filingType, setFilingType] = useState('10-K')

  const [autoStartYear, setAutoStartYear] = useState('2024')
  const [autoEndYear, setAutoEndYear] = useState('2024')

  const [uploadFile, setUploadFile] = useState(null)
  const [manualBusy, setManualBusy] = useState(false)
  const [autoBusy, setAutoBusy] = useState(false)
  const [manualResult, setManualResult] = useState(null)
  const [manualRecord, setManualRecord] = useState(null)
  const [manualFileName, setManualFileName] = useState('')
  const [autoSummary, setAutoSummary] = useState(null)

  const [selectedId, setSelectedId] = useState('')
  const [selectedResult, setSelectedResult] = useState(null)
  const [loadingSelected, setLoadingSelected] = useState(false)
  const [selectedReloadTick, setSelectedReloadTick] = useState(0)
  const [recordsIndustryFilter, setRecordsIndustryFilter] = useState('all')
  const [recordsFilingTypeFilter, setRecordsFilingTypeFilter] = useState('all')
  const [selectedCompanyKey, setSelectedCompanyKey] = useState('')

  const fileInputRef = useRef(null)
  const topTabsRef = useRef(null)
  const subTabsRef = useRef(null)

  useSlidingTabIndicator(topTabsRef, [tab])
  useSlidingTabIndicator(subTabsRef, [tab, ingestMode])

  const refreshRecords = async (preferId = '') => {
    setLoading(true)
    setError('')
    try {
      const res = await get('/api/records', { timeoutMs: 15000 })
      const next = Array.isArray(res?.items) ? res.items : []
      setRecords(next)
      const fallbackId = preferId || selectedId || next[0]?.record_id || ''
      if (fallbackId) setSelectedId(String(fallbackId))
      return next
    } catch (e) {
      setError(e.message || 'Failed to load records')
      return []
    } finally {
      setLoading(false)
    }
  }

  const forceReloadSelectedResult = async (rid) => {
    const id = String(rid || '').trim()
    if (!id) return
    setLoadingSelected(true)
    try {
      const res = await get(`/api/records/${encodeURIComponent(id)}?t=${Date.now()}`, { timeoutMs: 15000 })
      setSelectedResult(res?.result || null)
    } catch {
      setSelectedResult(null)
    } finally {
      setLoadingSelected(false)
    }
  }

  useEffect(() => {
    // Honor `?tab=records&record_id=…` deep links (e.g. from the Dashboard
    // heatmap). When a record_id is present, force the records tab open,
    // hand the id to refreshRecords as the selected row, and once records
    // come back expand the matching company group.
    let preferRid = ''
    let cancelled = false
    if (typeof window !== 'undefined') {
      try {
        const params = new URLSearchParams(window.location.search || '')
        const t = String(params.get('tab') || '').toLowerCase()
        const rid = String(params.get('record_id') || '').trim()
        if (t === 'records' || rid) setTab('records')
        if (rid) {
          preferRid = rid
          setSelectedId(rid)
        }
      } catch {
        // Malformed URL — fall through to default tab.
      }
    }
    refreshRecords(preferRid).then((items) => {
      if (cancelled || !preferRid || !Array.isArray(items)) return
      const match = items.find((r) => String(r?.record_id || '') === preferRid)
      const companyKey = match?.company ? String(match.company).toLowerCase() : ''
      if (companyKey) setSelectedCompanyKey(companyKey)
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (config.company) setCompany(config.company)
    if (config.ticker) setTicker(config.ticker)
    if (config.industry) setIndustry(config.industry)
    if (config.year) {
      setYear(config.year)
      setAutoStartYear(config.year)
      setAutoEndYear(config.year)
    }
  }, [config])

  useEffect(() => {
    if (!selectedId) return
    let mounted = true
    setLoadingSelected(true)
    get(`/api/records/${encodeURIComponent(selectedId)}?t=${Date.now()}`, { timeoutMs: 15000 })
      .then((res) => {
        if (!mounted) return
        setSelectedResult(res?.result || null)
      })
      .catch(() => {
        if (!mounted) return
        setSelectedResult(null)
      })
      .finally(() => {
        if (!mounted) return
        setLoadingSelected(false)
      })
    return () => {
      mounted = false
    }
  }, [selectedId, selectedReloadTick])

  const recordIndustries = useMemo(() => {
    const set = new Set()
    records.forEach((r) => {
      const value = String(r?.industry || 'Other').trim() || 'Other'
      set.add(value)
    })
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [records])

  const recordFilingTypes = useMemo(() => {
    const set = new Set(['10-K', '10-Q'])
    records.forEach((r) => {
      const value = String(r?.filing_type || '10-K').trim() || '10-K'
      set.add(value)
    })
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [records])

  const visibleRecords = useMemo(() => {
    const q = search.trim().toLowerCase()
    return records.filter((r) => {
      const recordIndustry = String(r?.industry || 'Other').trim() || 'Other'
      if (recordsIndustryFilter !== 'all' && recordIndustry !== recordsIndustryFilter) return false
      const recordFilingType = String(r?.filing_type || '10-K').trim() || '10-K'
      if (recordsFilingTypeFilter !== 'all' && recordFilingType !== recordsFilingTypeFilter) return false
      if (!q) return true
      return [r.company, r.industry, r.filing_type, String(r.year), r.record_id].join(' ').toLowerCase().includes(q)
    })
  }, [records, search, recordsIndustryFilter, recordsFilingTypeFilter])

  const companyGroups = useMemo(() => {
    const groups = new Map()
    visibleRecords.forEach((r) => {
      const companyName = String(r?.company || 'Unknown Company').trim() || 'Unknown Company'
      const key = companyName.toLowerCase()
      const industryLabel = String(r?.industry || 'Other').trim() || 'Other'
      if (!groups.has(key)) {
        groups.set(key, {
          key,
          company: companyName,
          industry: industryLabel,
          records: [],
        })
      }
      groups.get(key).records.push(r)
    })

    const toMillis = (value) => {
      const n = new Date(value || 0).getTime()
      return Number.isFinite(n) ? n : 0
    }

    return Array.from(groups.values())
      .map((group) => {
        const sorted = [...group.records].sort((a, b) => {
          const ay = Number(a?.year || 0)
          const by = Number(b?.year || 0)
          if (by !== ay) return by - ay
          return toMillis(b?.created_at) - toMillis(a?.created_at)
        })
        const years = Array.from(new Set(sorted.map((r) => String(r?.year || '—'))))
        const latestUpdated = sorted[0]?.created_at || ''
        return {
          ...group,
          records: sorted,
          years,
          recordCount: sorted.length,
          latestUpdated,
        }
      })
      .sort((a, b) => {
        if (b.recordCount !== a.recordCount) return b.recordCount - a.recordCount
        return a.company.localeCompare(b.company)
      })
  }, [visibleRecords])

  const selectedRec = useMemo(
    () =>
      visibleRecords.find((r) => String(r.record_id) === String(selectedId)) ||
      records.find((r) => String(r.record_id) === String(selectedId)) ||
      null,
    [visibleRecords, records, selectedId],
  )

  useEffect(() => {
    if (!companyGroups.length) {
      if (selectedCompanyKey) setSelectedCompanyKey('')
      return
    }
    if (selectedCompanyKey && !companyGroups.some((g) => g.key === selectedCompanyKey)) {
      setSelectedCompanyKey('')
    }
  }, [companyGroups, selectedCompanyKey])

  const runManualExtract = async () => {
    const companyName = String(company || '').trim()
    if (!companyName) {
      setError('Please enter company name.')
      return
    }
    if (!uploadFile) {
      setError('Please choose a filing file.')
      return
    }
    setError('')
    setAutoSummary(null)
    setManualBusy(true)
    try {
      const dataUrl = await toBase64DataUrl(uploadFile)
      const fileB64 = dataUrl.includes(',') ? dataUrl.split(',', 2)[1] : dataUrl
      const res = await post('/api/upload/manual', {
        company: companyName,
        ticker: ticker,
        industry: industry,
        year: Number(year),
        filing_type: filingType,
        file_name: uploadFile.name,
        file_b64: fileB64,
      })
      setManualResult(res?.result || null)
      setManualRecord(res?.record || null)
      setManualFileName(uploadFile.name)

      const rid = String(res?.record?.record_id || '')
      await refreshRecords(rid)
      if (rid) {
        setSelectedId(rid)
        setSelectedReloadTick((v) => v + 1)
        await forceReloadSelectedResult(rid)
      }
    } catch (e) {
      setError(e.message || 'Extraction failed')
    } finally {
      setManualBusy(false)
    }
  }

  const runAutoFetch = async () => {
    const companyName = String(company || '').trim()
    if (!companyName) {
      setError('Please enter company name.')
      return
    }
    const start = Number(autoStartYear)
    const end = Number(autoEndYear)
    if (!Number.isFinite(start) || !Number.isFinite(end) || start > end) {
      setError('Start year must be less than or equal to end year.')
      return
    }

    setError('')
    setManualResult(null)
    setManualRecord(null)
    setAutoBusy(true)
    try {
      const res = await post('/api/upload/auto-fetch', {
        company: companyName,
        ticker: ticker,
        industry: industry,
        filing_type: filingType,
        start_year: start,
        end_year: end,
      })
      setAutoSummary(res)
      const successes = Array.isArray(res?.successes) ? res.successes : []
      const latest = successes.length ? successes[successes.length - 1] : null
      const latestRid = String(latest?.record?.record_id || '')
      await refreshRecords(latestRid)
      if (latestRid) {
        setSelectedId(latestRid)
        setSelectedReloadTick((v) => v + 1)
        await forceReloadSelectedResult(latestRid)
      }
    } catch (e) {
      setError(e.message || 'Auto fetch failed')
    } finally {
      setAutoBusy(false)
    }
  }

  return (
    <div className="rl-page-shell rl-up-page">
      <section className="rl-up-header">
        <div className="page-header !mb-0">
          <div className="page-header-left rl-up-title-block">
            <span className="page-icon">🗂️</span>
            <div>
              <p className="page-title">Filings</p>
              <p className="page-subtitle">Ingest new filings and manage existing records in one place</p>
            </div>
          </div>
          <GlobalConfigInlineEditor />
        </div>
      </section>

      <section className="rl-up-nav-stack">
        <div className="rl-up-nav-head">
          <div className="rl-up-pill-nav rl-tab-motion" ref={topTabsRef}>
            <button className={`rl-strip-tab ${tab === 'ingest' ? 'active' : ''}`} onClick={() => setTab('ingest')}>
              🆕 Upload
            </button>
            <button className={`rl-strip-tab ${tab === 'records' ? 'active' : ''}`} onClick={() => setTab('records')}>
              📚 Records
            </button>
          </div>
        </div>

        {tab === 'ingest' ? (
          <div className="rl-up-pill-subnav rl-tab-motion" ref={subTabsRef}>
            <button
              className={`rl-strip-tab ${ingestMode === 'manual' ? 'active' : ''}`}
              onClick={() => setIngestMode('manual')}
            >
              📄 Manual Upload
            </button>
            <button
              className={`rl-strip-tab ${ingestMode === 'auto' ? 'active' : ''}`}
              onClick={() => setIngestMode('auto')}
            >
              🛰️ Auto Fetch from SEC EDGAR
            </button>
          </div>
        ) : null}
      </section>

      {tab === 'ingest' ? (
        <details
          className="rl-pipeline-hint"
          open={scoringHintOpen}
          onToggle={handleScoringHintToggle}
        >
          <summary className="rl-pipeline-hint-summary">
            <span className="rl-pipeline-hint-icon" aria-hidden="true">ⓘ</span>
            <span className="rl-pipeline-hint-label">How risk scoring works</span>
          </summary>
          <div className="rl-pipeline-steps">
            <div className="rl-pipeline-step">
              <p className="rl-pipeline-step-title">Extract</p>
              <p className="rl-pipeline-step-body">Risk factors pulled from Item 1A of the 10-K filing.</p>
            </div>
            <span className="rl-pipeline-step-arrow" aria-hidden="true">→</span>
            <div className="rl-pipeline-step">
              <p className="rl-pipeline-step-title">Score 3 dimensions</p>
              <p className="rl-pipeline-step-body">Each risk graded 1-10 on Financial Impact, Likelihood, and Urgency.</p>
            </div>
            <span className="rl-pipeline-step-arrow" aria-hidden="true">→</span>
            <div className="rl-pipeline-step">
              <p className="rl-pipeline-step-title">See on Dashboard</p>
              <p className="rl-pipeline-step-body">Aggregated into RPI (Risk Priority Index, 0-100) per filing.</p>
            </div>
          </div>
        </details>
      ) : null}

      {tab === 'ingest' ? (
        ingestMode === 'manual' ? (
          <section className="rl-up-grid rl-up-grid-manual">
            <div className="rl-up-form">
              <p className="section-title">Configure</p>
              <div className="rl-up-form-fields">
                <div>
                  <label className="rl-field-label">Filing file (HTML or PDF)</label>
                  <div className="rl-upload-btn-row">
                    <button className="btn-secondary" onClick={() => fileInputRef.current?.click()}>
                      {uploadFile ? '↻ Change File' : '⤴ Upload'}
                    </button>
                    <span className={`rl-upload-file-text ${uploadFile ? 'has-file' : ''}`}>
                      {uploadFile ? `${uploadFile.name} • ${formatBytes(uploadFile.size)}` : '200MB per file • HTML, HTM, PDF'}
                    </span>
                    {uploadFile ? (
                      <button
                        className="rl-upload-clear-btn"
                        onClick={() => {
                          setUploadFile(null)
                          if (fileInputRef.current) fileInputRef.current.value = ''
                        }}
                      >
                        Clear
                      </button>
                    ) : null}
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".html,.htm,.pdf"
                      className="rl-hidden-file-input"
                      onChange={(e) => {
                        const f = e.target.files && e.target.files[0] ? e.target.files[0] : null
                        setUploadFile(f)
                      }}
                    />
                  </div>
                </div>

                <div className="rl-up-two-col rl-up-company-ticker-row">
                  <div>
                    <label className="rl-field-label">Company Name</label>
                    <input
                      className="input mt-2"
                      placeholder="e.g. Apple Inc."
                      value={company}
                      onChange={(e) => setCompany(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="rl-field-label">Stock Ticker (optional)</label>
                    <input
                      className="input mt-2"
                      placeholder="e.g. AAPL"
                      value={ticker}
                      onChange={(e) => setTicker(e.target.value.toUpperCase())}
                    />
                  </div>
                </div>

                <div className="rl-up-three-col rl-up-taxonomy-row">
                  <div>
                    <label className="rl-field-label">Filing Year</label>
                    <select className="input mt-2" value={year} onChange={(e) => setYear(e.target.value)}>
                      {YEARS.map((y) => (
                        <option key={y} value={y}>
                          {y}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="rl-field-label">Industry</label>
                    <select className="input mt-2" value={industry} onChange={(e) => setIndustry(e.target.value)}>
                      {INDUSTRIES.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="rl-field-label">Filing Type</label>
                    <select className="input mt-2" value={filingType} onChange={(e) => setFilingType(e.target.value)}>
                      <option value="10-K">10-K</option>
                      <option value="10-Q">10-Q</option>
                    </select>
                  </div>
                </div>

                <button className="btn-primary w-full rl-up-primary-btn" onClick={runManualExtract} disabled={manualBusy}>
                  {manualBusy ? 'Extracting…' : '🚀 Extract & Save'}
                </button>
              </div>
            </div>

            <div className="rl-up-results">
              <p className="section-title">Results</p>
              {manualBusy ? (
                <div className="rl-up-result-placeholder">
                  <h4>Running extraction pipeline…</h4>
                  <span>Processing filing and saving to records.</span>
                </div>
              ) : manualResult ? (
                <div className="rl-up-result-summary">
                  <p className="rl-up-result-head">Extraction completed</p>
                  <div className="rl-up-result-meta">
                    <span>Uploaded File</span>
                    <strong title={manualFileName || '—'}>{manualFileName || '—'}</strong>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="metric-card">
                      <p className="metric-label">Risk Categories</p>
                      <p className="metric-value">{riskCategoryCount(manualResult)}</p>
                    </div>
                    <div className="metric-card">
                      <p className="metric-label">Risk Items</p>
                      <p className="metric-value">{riskItemCount(manualResult)}</p>
                    </div>
                  </div>
                  <div className="rl-up-result-meta">
                    <span>Record ID</span>
                    <strong title={manualRecord?.record_id || '—'}>{manualRecord?.record_id || '—'}</strong>
                  </div>
                  <button
                    className="btn-secondary w-full"
                    onClick={() => {
                      if (manualRecord?.record_id) setSelectedId(String(manualRecord.record_id))
                      setTab('records')
                    }}
                  >
                    Open in Records
                  </button>
                </div>
              ) : (
                <div className="rl-up-result-placeholder">
                  <p>📋</p>
                  <h4>Extraction results will appear here</h4>
                </div>
              )}
            </div>
          </section>
        ) : (
          <section className="rl-up-grid">
            <div className="rl-up-form">
              <p className="section-title">Auto Fetch Config</p>
              <div className="rl-up-form-fields">
                <div className="rl-up-two-col rl-up-company-ticker-row">
                  <div>
                    <label className="rl-field-label">Company Name</label>
                    <input
                      className="input mt-2"
                      placeholder="e.g. Apple Inc."
                      value={company}
                      onChange={(e) => setCompany(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="rl-field-label">Ticker</label>
                    <input
                      className="input mt-2"
                      placeholder="e.g. AAPL"
                      value={ticker}
                      onChange={(e) => setTicker(e.target.value.toUpperCase())}
                    />
                  </div>
                </div>
                <div className="rl-up-three-col rl-up-range-row">
                  <div>
                    <label className="rl-field-label">Start Year</label>
                    <select className="input mt-2" value={autoStartYear} onChange={(e) => setAutoStartYear(e.target.value)}>
                      {YEARS.map((y) => (
                        <option key={y} value={y}>
                          {y}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="rl-field-label">Industry</label>
                    <select className="input mt-2" value={industry} onChange={(e) => setIndustry(e.target.value)}>
                      {INDUSTRIES.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="rl-field-label">Filing Type</label>
                    <select className="input mt-2" value={filingType} onChange={(e) => setFilingType(e.target.value)}>
                      <option value="10-K">10-K</option>
                      <option value="10-Q">10-Q</option>
                    </select>
                  </div>
                  <div>
                    <label className="rl-field-label">End Year</label>
                    <select className="input mt-2" value={autoEndYear} onChange={(e) => setAutoEndYear(e.target.value)}>
                      {YEARS.map((y) => (
                        <option key={y} value={y}>
                          {y}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <button className="btn-primary w-full rl-up-primary-btn" onClick={runAutoFetch} disabled={autoBusy}>
                  {autoBusy ? 'Fetching…' : '🚀 Auto Fetch & Save'}
                </button>
              </div>
            </div>

            <div className="rl-up-results">
              <p className="section-title">Status</p>
              {autoBusy ? (
                <div className="rl-up-result-placeholder">
                  <h4>Auto fetch pipeline running…</h4>
                </div>
              ) : autoSummary ? (
                <div className="rl-up-result-summary">
                  <p className="rl-up-result-head">Run completed</p>
                  <div className="rl-up-result-meta">
                    <span>Saved</span>
                    <strong>{autoSummary?.count ?? 0}</strong>
                  </div>
                  <div className="rl-up-result-meta">
                    <span>Skipped</span>
                    <strong>{Array.isArray(autoSummary?.skipped) ? autoSummary.skipped.length : 0}</strong>
                  </div>
                  <button className="btn-secondary w-full" onClick={() => setTab('records')}>
                    Open Records
                  </button>
                </div>
              ) : (
                <div className="rl-up-result-placeholder">
                  <h4>Ready to fetch SEC filings</h4>
                </div>
              )}
            </div>
          </section>
        )
      ) : (
        <>
          <section className="rl-up-records">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3>All Filing Records</h3>
              <div className="rl-up-records-filters">
                <select
                  value={recordsIndustryFilter}
                  onChange={(e) => setRecordsIndustryFilter(e.target.value)}
                  className="input w-full md:w-48"
                >
                  <option value="all">All industries</option>
                  {recordIndustries.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
                <select
                  value={recordsFilingTypeFilter}
                  onChange={(e) => setRecordsFilingTypeFilter(e.target.value)}
                  className="input w-full md:w-40"
                >
                  <option value="all">All filing types</option>
                  {recordFilingTypes.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search company / year / record ID"
                  className="input w-full md:w-80"
                />
              </div>
            </div>
            <p className="rl-count-label">
              Showing <strong>{companyGroups.length}</strong> companies and <strong>{visibleRecords.length}</strong> of {records.length} records
            </p>

            <div className="rl-up-company-panel">
              <div className="rl-up-records-table-wrap rl-up-company-table-wrap">
                <table className="rl-up-record-table rl-up-company-table">
                  <thead>
                    <tr>
                      <th>Company</th>
                      <th>Industry</th>
                      <th>Years</th>
                      <th>Records</th>
                      <th>Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr>
                        <td className="rl-up-record-empty" colSpan={5}>
                          Loading records…
                        </td>
                      </tr>
                    ) : null}

                    {!loading && companyGroups.length === 0 ? (
                      <tr>
                        <td className="rl-up-record-empty" colSpan={5}>
                          No records found.
                        </td>
                      </tr>
                    ) : null}

                    {!loading &&
                      companyGroups.map((group) => {
                        const expanded = group.key === selectedCompanyKey
                        return (
                          <React.Fragment key={group.key}>
                            <tr
                              className={`rl-up-record-row ${expanded ? 'active' : ''}`}
                              onClick={() => {
                                if (expanded) {
                                  setSelectedCompanyKey('')
                                  return
                                }
                                setSelectedCompanyKey(group.key)
                                const firstRecordId = group.records[0]?.record_id
                                if (firstRecordId) setSelectedId(String(firstRecordId))
                              }}
                            >
                              <td className="rl-up-company-cell">
                                <strong>{group.company}</strong>
                              </td>
                              <td>{group.industry || 'Other'}</td>
                              <td>{group.years.length}</td>
                              <td>{group.recordCount}</td>
                              <td className="rl-up-updated-cell">
                                <span>{formatDate(group.latestUpdated)}</span>
                                <span className={`rl-up-expand-caret ${expanded ? 'open' : ''}`} aria-hidden="true">
                                  ▾
                                </span>
                              </td>
                            </tr>

                            {expanded ? (
                              <tr className="rl-up-company-expand-row">
                                <td colSpan={5}>
                                  <div className="rl-up-company-expand">
                                    <div className="rl-up-records-table-wrap rl-up-company-records-wrap">
                                      <table className="rl-up-record-table rl-up-company-record-table">
                                        <thead>
                                          <tr>
                                            <th>Year</th>
                                            <th>Type</th>
                                            <th>Risk Items</th>
                                            <th>Categories</th>
                                            <th>Updated</th>
                                            <th>Action</th>
                                          </tr>
                                        </thead>
                                        <tbody>
                                          {group.records.map((r) => {
                                            const active = String(r.record_id) === String(selectedId)
                                            return (
                                              <tr
                                                key={r.record_id}
                                                className={`rl-up-record-row ${active ? 'active' : ''}`}
                                                onClick={() => setSelectedId(String(r.record_id))}
                                              >
                                                <td className="rl-up-company-year-cell">{r.year || '—'}</td>
                                                <td>{r.filing_type || '10-K'}</td>
                                                <td>{r.risk_items ?? '—'}</td>
                                                <td>{r.risk_categories ?? '—'}</td>
                                                <td>{formatDate(r.created_at)}</td>
                                                <td>
                                                  <button
                                                    className={active ? 'btn-primary rl-up-row-btn' : 'btn-secondary rl-up-row-btn'}
                                                    onClick={(e) => {
                                                      e.stopPropagation()
                                                      setSelectedId(String(r.record_id))
                                                    }}
                                                  >
                                                    {active ? 'Loaded' : 'Load'}
                                                  </button>
                                                </td>
                                              </tr>
                                            )
                                          })}
                                        </tbody>
                                      </table>
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            ) : null}
                          </React.Fragment>
                        )
                      })}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          {loadingSelected ? <div className="card p-4 text-sm text-slate-500">Loading selected filing…</div> : null}
          {!loadingSelected && selectedRec && selectedResult ? <RecordDetailPanel rec={selectedRec} result={selectedResult} /> : null}
        </>
      )}

      {error ? <div className="rl-up-inline-error">{error}</div> : null}
    </div>
  )
}
