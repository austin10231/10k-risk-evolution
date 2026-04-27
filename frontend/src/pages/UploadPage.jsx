import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { get, post } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'
import { companyOverview, groupedRiskTitles, riskCategoryCount, riskItemCount } from '../lib/records'

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

function Chip({ label, value, tone = 'default' }) {
  return (
    <span className={`rl-up-chip ${tone}`} title={`${label}: ${value || 'Not Set'}`}>
      {label}: {value || '—'}
    </span>
  )
}

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

      <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
        <Link
          to={`/compare?company=${encodeURIComponent(rec.company || '')}&year=${encodeURIComponent(String(rec.year || ''))}`}
          className="btn-secondary w-full"
        >
          ⚖️ Run Compare
        </Link>
        <Link to={`/agent?record_id=${encodeURIComponent(rec.record_id || '')}`} className="btn-secondary w-full">
          🤖 Run Agent
        </Link>
        <Link to={`/dashboard?industry=${encodeURIComponent(rec.industry || '')}`} className="btn-secondary w-full">
          📈 Open Dashboard
        </Link>
        <Link to={`/tables?record_id=${encodeURIComponent(rec.record_id || '')}`} className="btn-secondary w-full">
          📊 Open Tables
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
          <div className="rl-section-header">🏢 Business Overview</div>
          <p className="rl-body-text">{ov.background}</p>
        </div>
      ) : null}

      <div className="mt-4">
        <div className="rl-section-header">⚠️ Risk Categories ({groups.length})</div>
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
  const { config, setConfig } = useGlobalConfig()

  const [tab, setTab] = useState('ingest')
  const [ingestMode, setIngestMode] = useState('manual')
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

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

  const [editingConfig, setEditingConfig] = useState(false)
  const [cfgDraft, setCfgDraft] = useState(config)

  const [selectedId, setSelectedId] = useState('')
  const [selectedResult, setSelectedResult] = useState(null)
  const [loadingSelected, setLoadingSelected] = useState(false)

  const fileInputRef = useRef(null)

  const refreshRecords = async (preferId = '') => {
    setLoading(true)
    setError('')
    try {
      const res = await get('/api/records?include_result=1')
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

  useEffect(() => {
    refreshRecords()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    setCfgDraft(config)
  }, [config])

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
    get(`/api/records/${encodeURIComponent(selectedId)}`)
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
  }, [selectedId])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return records
    return records.filter((r) =>
      [r.company, r.industry, r.filing_type, String(r.year), r.record_id].join(' ').toLowerCase().includes(q),
    )
  }, [records, search])

  const selectedRec = useMemo(
    () =>
      filtered.find((r) => String(r.record_id) === String(selectedId)) ||
      records.find((r) => String(r.record_id) === String(selectedId)) ||
      null,
    [filtered, records, selectedId],
  )

  const saveConfig = () => {
    setConfig(cfgDraft)
    setEditingConfig(false)
  }

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
      if (rid) setSelectedId(rid)
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
        start_year: start,
        end_year: end,
      })
      setAutoSummary(res)
      const successes = Array.isArray(res?.successes) ? res.successes : []
      const latest = successes.length ? successes[successes.length - 1] : null
      const latestRid = String(latest?.record?.record_id || '')
      await refreshRecords(latestRid)
      if (latestRid) setSelectedId(latestRid)
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
        </div>
      </section>

      <section className="rl-up-nav-stack">
        <div className="rl-up-nav-head">
          <div className="rl-up-pill-nav">
            <button className={`rl-strip-tab ${tab === 'ingest' ? 'active' : ''}`} onClick={() => setTab('ingest')}>
              🆕 Upload
            </button>
            <button className={`rl-strip-tab ${tab === 'records' ? 'active' : ''}`} onClick={() => setTab('records')}>
              📚 Records
            </button>
          </div>

          <div className="rl-up-right-group">
            <div className="rl-up-config-inline">
              <span className="rl-up-config-inline-label">Current Configuration</span>
              <Chip label="Company" value={config.company} tone="violet" />
              <Chip label="Year" value={config.year} tone="blue" />
              <Chip label="Ticker" value={config.ticker} tone="green" />
              <Chip label="Industry" value={config.industry} />
            </div>

            <div className="rl-up-edit-wrap">
              <button className="btn-secondary rl-up-header-edit" onClick={() => setEditingConfig((v) => !v)}>
                {editingConfig ? 'Close' : 'Edit'}
              </button>
              {editingConfig ? (
                <div className="rl-up-config-popover">
                  <div>
                    <label className="section-title">Company</label>
                    <input
                      className="input mt-2"
                      value={cfgDraft.company || ''}
                      onChange={(e) => setCfgDraft((p) => ({ ...p, company: e.target.value }))}
                      placeholder="e.g. Apple Inc."
                    />
                  </div>
                  <div>
                    <label className="section-title">Year</label>
                    <select
                      className="input mt-2"
                      value={cfgDraft.year || ''}
                      onChange={(e) => setCfgDraft((p) => ({ ...p, year: e.target.value }))}
                    >
                      <option value="">—</option>
                      {YEARS.map((y) => (
                        <option key={y} value={y}>
                          {y}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="section-title">Ticker</label>
                    <input
                      className="input mt-2"
                      value={cfgDraft.ticker || ''}
                      onChange={(e) => setCfgDraft((p) => ({ ...p, ticker: e.target.value.toUpperCase() }))}
                      placeholder="e.g. AAPL"
                    />
                  </div>
                  <div>
                    <label className="section-title">Industry</label>
                    <select
                      className="input mt-2"
                      value={cfgDraft.industry || ''}
                      onChange={(e) => setCfgDraft((p) => ({ ...p, industry: e.target.value }))}
                    >
                      <option value="">—</option>
                      {INDUSTRIES.map((v) => (
                        <option key={v} value={v}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="rl-up-config-actions">
                    <button
                      className="btn-secondary"
                      onClick={() => setCfgDraft({ company: '', year: '', ticker: '', industry: '' })}
                    >
                      Reset
                    </button>
                    <button className="btn-primary" onClick={saveConfig}>
                      Save
                    </button>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>

        {tab === 'ingest' ? (
          <div className="rl-up-pill-subnav">
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
                    <input className="input mt-2" value={company} onChange={(e) => setCompany(e.target.value)} />
                  </div>
                  <div>
                    <label className="rl-field-label">Ticker</label>
                    <input className="input mt-2" value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} />
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
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search company / industry / year"
                className="input w-full md:w-80"
              />
            </div>
            <p className="rl-count-label">
              Showing <strong>{filtered.length}</strong> of {records.length} records
            </p>

            <div className="rl-up-records-table-wrap">
              <table className="rl-up-record-table">
                <thead>
                  <tr>
                    <th>Company</th>
                    <th>Year</th>
                    <th>Industry</th>
                    <th>Type</th>
                    <th>Risk Items</th>
                    <th>Categories</th>
                    <th>Updated</th>
                    <th className="text-right">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td className="rl-up-record-empty" colSpan={8}>
                        Loading records…
                      </td>
                    </tr>
                  ) : null}

                  {!loading && filtered.length === 0 ? (
                    <tr>
                      <td className="rl-up-record-empty" colSpan={8}>
                        No records found.
                      </td>
                    </tr>
                  ) : null}

                  {!loading &&
                    filtered.map((r) => {
                      const active = String(r.record_id) === String(selectedId)
                      return (
                        <tr
                          key={r.record_id}
                          className={`rl-up-record-row ${active ? 'active' : ''}`}
                          onClick={() => setSelectedId(String(r.record_id))}
                        >
                          <td className="rl-up-company-cell">
                            <strong>{r.company || '—'}</strong>
                            <span>{r.record_id || '—'}</span>
                          </td>
                          <td>{r.year || '—'}</td>
                          <td>{r.industry || 'Other'}</td>
                          <td>{r.filing_type || '10-K'}</td>
                          <td>{r.risk_items ?? 0}</td>
                          <td>{r.risk_categories ?? 0}</td>
                          <td>{formatDate(r.created_at)}</td>
                          <td className="text-right">
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
          </section>

          {loadingSelected ? <div className="card p-4 text-sm text-slate-500">Loading selected filing…</div> : null}
          {!loadingSelected && selectedRec && selectedResult ? <RecordDetailPanel rec={selectedRec} result={selectedResult} /> : null}
        </>
      )}

      {error ? <div className="rl-up-inline-error">{error}</div> : null}
    </div>
  )
}
