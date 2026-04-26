import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../lib/api'
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
    <span className={`rl-up-chip ${tone}`}>
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
  const [extractionMode, setExtractionMode] = useState('Standard')

  const [editingConfig, setEditingConfig] = useState(false)
  const [cfgDraft, setCfgDraft] = useState(config)

  const [selectedId, setSelectedId] = useState('')
  const [selectedResult, setSelectedResult] = useState(null)
  const [loadingSelected, setLoadingSelected] = useState(false)

  const loadRecords = () => {
    let mounted = true
    setLoading(true)
    setError('')
    get('/api/records?include_result=1')
      .then((res) => {
        if (!mounted) return
        const next = Array.isArray(res?.items) ? res.items : []
        setRecords(next)
        if (!selectedId && next[0]?.record_id) setSelectedId(String(next[0].record_id))
      })
      .catch((e) => {
        if (!mounted) return
        setError(e.message || 'Failed to load records')
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
    const off = loadRecords()
    return off
  }, [])

  useEffect(() => {
    setCfgDraft(config)
  }, [config])

  useEffect(() => {
    if (config.company) setCompany(config.company)
    if (config.ticker) setTicker(config.ticker)
    if (config.industry) setIndustry(config.industry)
    if (config.year) setYear(config.year)
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

  return (
    <div className="rl-page-shell rl-up-page">
      <section className="rl-up-header">
        <div className="page-header !mb-0">
          <div className="page-header-left">
            <span className="page-icon">🗂️</span>
            <div>
              <p className="page-title">Filings</p>
              <p className="page-subtitle">Ingest new filings and manage existing records in one place</p>
            </div>
          </div>

          <div className="rl-up-config-wrap">
            <div className="rl-up-config-row">
              <strong>Current Configuration</strong>
              <Chip label="Company" value={config.company} tone="violet" />
              <Chip label="Year" value={config.year} tone="blue" />
              <Chip label="Ticker" value={config.ticker} tone="green" />
              <Chip label="Industry" value={config.industry} />
            </div>
            <button className="btn-secondary" onClick={() => setEditingConfig((v) => !v)}>
              {editingConfig ? 'Close' : 'Edit'} ▾
            </button>
          </div>
        </div>

        {editingConfig ? (
          <div className="rl-up-config-panel">
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
                Save Config
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <section className="rl-up-strip">
        <button className={`rl-strip-tab ${tab === 'ingest' ? 'active' : ''}`} onClick={() => setTab('ingest')}>
          🆕 New Ingestion
        </button>
        <button className={`rl-strip-tab ${tab === 'records' ? 'active' : ''}`} onClick={() => setTab('records')}>
          📚 Records
        </button>
      </section>

      {tab === 'ingest' ? (
        <>
          <section className="rl-up-strip">
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
          </section>

          {ingestMode === 'manual' ? (
            <section className="rl-up-grid rl-up-grid-manual">
              <div className="rl-up-form">
                <p className="section-title">Configure</p>
                <div className="rl-up-form-fields">
                  <div>
                    <label className="rl-field-label">Filing file (HTML or PDF)</label>
                    <div className="rl-upload-btn-row">
                      <button className="btn-secondary" disabled>
                        ⤴ Upload
                      </button>
                      <span>200MB per file • HTML, HTM, PDF</span>
                    </div>
                  </div>

                  <div className="rl-up-two-col">
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

                  <div className="rl-up-two-col">
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
                  </div>

                  <div className="rl-up-two-col">
                    <div>
                      <label className="rl-field-label">Filing Type</label>
                      <select className="input mt-2" value={filingType} onChange={(e) => setFilingType(e.target.value)}>
                        <option value="10-K">10-K</option>
                        <option value="10-Q">10-Q</option>
                      </select>
                    </div>
                    <div>
                      <label className="rl-field-label">Extraction Mode</label>
                      <select
                        className="input mt-2"
                        value={extractionMode}
                        onChange={(e) => setExtractionMode(e.target.value)}
                      >
                        <option value="Standard">Standard</option>
                        <option value="AI-Enhanced">AI-Enhanced</option>
                      </select>
                    </div>
                  </div>

                  <button className="btn-primary w-full rl-up-primary-btn" disabled>
                    🚀 Extract & Save
                  </button>
                </div>
              </div>

              <div className="rl-up-results">
                <p className="section-title">Results</p>
                <div className="rl-up-result-placeholder">
                  <p>📋</p>
                  <h4>Extraction results will appear here</h4>
                  <span>Configure the inputs on the left, then hit Extract & Save</span>
                </div>
              </div>
            </section>
          ) : (
            <section className="rl-up-grid">
              <div className="rl-up-form">
                <p className="section-title">Auto Fetch Config</p>
                <div className="rl-up-form-fields">
                  <div className="rl-up-two-col">
                    <div>
                      <label className="rl-field-label">Company Name</label>
                      <input className="input mt-2" value={company} onChange={(e) => setCompany(e.target.value)} />
                    </div>
                    <div>
                      <label className="rl-field-label">Ticker</label>
                      <input
                        className="input mt-2"
                        value={ticker}
                        onChange={(e) => setTicker(e.target.value.toUpperCase())}
                      />
                    </div>
                  </div>
                  <div className="rl-up-three-col">
                    <div>
                      <label className="rl-field-label">Start Year</label>
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
                      <label className="rl-field-label">End Year</label>
                      <select className="input mt-2" value="2024" disabled>
                        <option value="2024">2024</option>
                      </select>
                    </div>
                  </div>
                  <button className="btn-primary w-full rl-up-primary-btn" disabled>
                    🚀 Auto Fetch & Analyze
                  </button>
                </div>
              </div>

              <div className="rl-up-results">
                <p className="section-title">Status</p>
                <div className="rl-up-result-placeholder">
                  <h4>Auto-fetch pipeline ready</h4>
                  <span>SEC runtime migration is the next backend step.</span>
                </div>
              </div>
            </section>
          )}
        </>
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

      {error ? <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div> : null}
    </div>
  )
}
