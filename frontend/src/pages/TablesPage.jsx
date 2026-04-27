import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { get, post } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'
import GlobalConfigInlineEditor from '../components/GlobalConfigInlineEditor'
import useSlidingTabIndicator from '../lib/useSlidingTabIndicator'

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

export default function TablesPage() {
  const location = useLocation()
  const { config } = useGlobalConfig()
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [ingestMode, setIngestMode] = useState('manual')

  const [company, setCompany] = useState(config.company || '')
  const [ticker, setTicker] = useState(config.ticker || '')
  const [year, setYear] = useState(config.year || '2024')
  const [industry, setIndustry] = useState(config.industry || 'Technology')
  const [filingType, setFilingType] = useState('10-K')
  const [uploadFile, setUploadFile] = useState(null)
  const [autoStartYear, setAutoStartYear] = useState(config.year || '2024')
  const [autoEndYear, setAutoEndYear] = useState(config.year || '2024')
  const [tableBusy, setTableBusy] = useState(false)
  const [autoBusy, setAutoBusy] = useState(false)
  const [autoSummary, setAutoSummary] = useState(null)
  const [tableResult, setTableResult] = useState(null)

  const fileInputRef = useRef(null)
  const modeTabsRef = useRef(null)
  const initialRecordIdRef = useRef('')

  useSlidingTabIndicator(modeTabsRef, [ingestMode])

  useEffect(() => {
    const rid = new URLSearchParams(location.search || '').get('record_id')
    initialRecordIdRef.current = rid ? String(rid) : ''
  }, [location.search])

  const refreshRecords = async (preferId = '') => {
    setLoading(true)
    setError('')
    try {
      const res = await get('/api/records?include_result=1')
      const next = Array.isArray(res?.items) ? res.items : []
      setRecords(next)
      const requestedId = String(preferId || initialRecordIdRef.current || '').trim()
      if (requestedId && next.some((r) => String(r.record_id) === requestedId)) {
        setSelectedId(requestedId)
      }
      if (preferId || initialRecordIdRef.current) initialRecordIdRef.current = ''
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

  const selected = useMemo(
    () => records.find((r) => String(r.record_id) === String(selectedId)) || null,
    [records, selectedId],
  )

  useEffect(() => {
    if (config.company) setCompany(config.company)
    if (config.ticker) setTicker(config.ticker)
    if (config.year) {
      setYear(config.year)
      setAutoStartYear(config.year)
      setAutoEndYear(config.year)
    }
    if (config.industry) setIndustry(config.industry)
  }, [config.company, config.ticker, config.year, config.industry])

  useEffect(() => {
    if (!selected) return
    setCompany(selected.company || '')
    setTicker(selected.ticker || '')
    setYear(String(selected.year || ''))
    setIndustry(selected.industry || '')
    setFilingType(selected.filing_type || '10-K')
  }, [selected])

  useEffect(() => {
    let mounted = true
    if (!selected) return () => {}
    const companyName = String(selected.company || '').trim()
    const selectedYear = Number(selected.year || 0)
    const selectedFilingType = String(selected.filing_type || '10-K').trim() || '10-K'
    if (!companyName || !selectedYear) return () => {}

    get(
      `/api/tables/result?company=${encodeURIComponent(companyName)}&year=${encodeURIComponent(
        String(selectedYear),
      )}&filing_type=${encodeURIComponent(selectedFilingType)}`,
    )
      .then((res) => {
        if (!mounted) return
        if (res?.result && typeof res.result === 'object') {
          setTableResult(res.result)
        }
      })
      .catch(() => {
        if (!mounted) return
      })

    return () => {
      mounted = false
    }
  }, [selected])

  const runManualExtract = async () => {
    const companyName = String(company || '').trim()
    if (!companyName) {
      setError('Please enter company name.')
      return
    }
    if (!uploadFile) {
      setError('Please choose a PDF filing first.')
      return
    }

    setError('')
    setAutoSummary(null)
    setTableBusy(true)
    try {
      const dataUrl = await toBase64DataUrl(uploadFile)
      const fileB64 = dataUrl.includes(',') ? dataUrl.split(',', 2)[1] : dataUrl
      const res = await post('/api/tables/extract/manual', {
        company: companyName,
        ticker: ticker,
        industry: industry,
        year: Number(year),
        filing_type: filingType,
        file_name: uploadFile.name,
        file_b64: fileB64,
      })
      if (res?.result && typeof res.result === 'object') {
        setTableResult(res.result)
      }
    } catch (e) {
      setError(e.message || 'Table extraction failed')
    } finally {
      setTableBusy(false)
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
    setTableBusy(false)
    setAutoBusy(true)
    try {
      const res = await post('/api/tables/extract/auto-fetch', {
        company: companyName,
        ticker: ticker,
        industry: industry,
        start_year: start,
        end_year: end,
        filing_type: filingType,
      })
      setAutoSummary(res)
      const latest = res?.latest_result && typeof res.latest_result === 'object' ? res.latest_result : null
      if (latest) {
        setTableResult(latest)
      }
    } catch (e) {
      setError(e.message || 'Auto fetch failed')
    } finally {
      setAutoBusy(false)
    }
  }

  return (
    <div className="rl-page-shell rl-tables-page">
      <section className="rl-up-header">
        <div className="page-header !mb-0">
          <div className="page-header-left rl-up-title-block">
            <span className="page-icon">📊</span>
            <div>
              <p className="page-title">Financial Tables</p>
              <p className="page-subtitle">Extract key financial statements from 10-K filings via Textract pipeline</p>
            </div>
          </div>
          <GlobalConfigInlineEditor />
        </div>
      </section>

      {error ? <div className="rl-up-inline-error">{error}</div> : null}

      <section className="rl-up-grid rl-tables-grid">
        <div className="rl-up-form rl-tables-form">
          <div className="rl-tabs rl-tab-motion" ref={modeTabsRef}>
            <button className={`rl-tab-btn ${ingestMode === 'manual' ? 'active' : ''}`} onClick={() => setIngestMode('manual')}>
              📄 Manual PDF Upload
            </button>
            <button className={`rl-tab-btn ${ingestMode === 'auto' ? 'active' : ''}`} onClick={() => setIngestMode('auto')}>
              🛰️ Auto Fetch from SEC EDGAR
            </button>
          </div>

          {ingestMode === 'manual' ? (
            <div className="rl-up-form-fields">
              <div>
                <label className="rl-field-label">Filing file (PDF)</label>
                <div className="rl-upload-btn-row">
                  <button className="btn-secondary" onClick={() => fileInputRef.current?.click()}>
                    {uploadFile ? '↻ Change File' : '⤴ Upload'}
                  </button>
                  <span className={`rl-upload-file-text ${uploadFile ? 'has-file' : ''}`}>
                    {uploadFile ? `${uploadFile.name} • ${formatBytes(uploadFile.size)}` : '200MB per file • PDF only'}
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
                    accept=".pdf,application/pdf"
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

              <button className="btn-primary w-full rl-up-primary-btn" onClick={runManualExtract} disabled={tableBusy || autoBusy}>
                {tableBusy ? 'Extracting…' : '🚀 Run Textract Extraction'}
              </button>
            </div>
          ) : (
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
              <button className="btn-primary w-full rl-up-primary-btn" onClick={runAutoFetch} disabled={autoBusy || tableBusy}>
                {autoBusy ? 'Fetching…' : '🚀 Auto Fetch & Save'}
              </button>
            </div>
          )}
        </div>

        <div className="rl-up-results rl-tables-results">
          <p className="section-title">Results</p>
          <h3 className="rl-tables-result-headline">Statement Preview Workspace</h3>
          <p className="rl-tables-result-sub">
            This panel is prepared for Balance Sheet, Income Statement, Cash Flow, and Notes output with CSV/JSON export.
          </p>

          <div className="mt-3">
            <label className="rl-field-label">Load Existing Filing Context</label>
            <select className="input mt-2" value={selectedId} onChange={(e) => setSelectedId(e.target.value)} disabled={loading}>
              <option value="">Select one record…</option>
              {records.map((r) => (
                <option key={r.record_id} value={r.record_id}>
                  {r.company} · {r.year} · {r.filing_type || '10-K'}
                </option>
              ))}
            </select>
          </div>

          <div className="rl-tables-result-kpis">
            <div className="metric-card">
              <p className="metric-label">Company</p>
              <p className="metric-value">{company || '—'}</p>
            </div>
            <div className="metric-card">
              <p className="metric-label">Year</p>
              <p className="metric-value">{year || '—'}</p>
            </div>
            <div className="metric-card">
              <p className="metric-label">Industry</p>
              <p className="metric-value">{industry || '—'}</p>
            </div>
          </div>

          {ingestMode === 'auto' && autoSummary ? (
            <div className="rl-tables-auto-summary">
              <div className="rl-up-result-meta">
                <span>Saved</span>
                <strong>{autoSummary?.count ?? 0}</strong>
              </div>
              <div className="rl-up-result-meta">
                <span>Skipped</span>
                <strong>{Array.isArray(autoSummary?.skipped) ? autoSummary.skipped.length : 0}</strong>
              </div>
            </div>
          ) : null}

          <div className="rl-tables-statement-grid">
            <div className="rl-tables-statement-card">
              <p>Balance Sheet</p>
              <span>
                {tableResult
                  ? tableResult?.balance_sheet?.found
                    ? `${Array.isArray(tableResult?.balance_sheet?.rows) ? tableResult.balance_sheet.rows.length : 0} rows extracted`
                    : 'Not found in filing'
                  : 'Pending extraction'}
              </span>
            </div>
            <div className="rl-tables-statement-card">
              <p>Income Statement</p>
              <span>
                {tableResult
                  ? tableResult?.income_statement?.found
                    ? `${Array.isArray(tableResult?.income_statement?.rows) ? tableResult.income_statement.rows.length : 0} rows extracted`
                    : 'Not found in filing'
                  : 'Pending extraction'}
              </span>
            </div>
            <div className="rl-tables-statement-card">
              <p>Cash Flow</p>
              <span>
                {tableResult
                  ? tableResult?.cash_flow?.found
                    ? `${Array.isArray(tableResult?.cash_flow?.rows) ? tableResult.cash_flow.rows.length : 0} rows extracted`
                    : 'Not found in filing'
                  : 'Pending extraction'}
              </span>
            </div>
            <div className="rl-tables-statement-card">
              <p>Footnotes</p>
              <span>
                {tableResult
                  ? tableResult?.comprehensive_income?.found || tableResult?.shareholders_equity?.found
                    ? 'Supplementary tables extracted'
                    : 'No supplementary table found'
                  : 'Pending extraction'}
              </span>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
