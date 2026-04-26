import React, { useEffect, useMemo, useState } from 'react'
import { get } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'

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

export default function TablesPage() {
  const { config } = useGlobalConfig()
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [company, setCompany] = useState(config.company || '')
  const [year, setYear] = useState(config.year || '2024')
  const [industry, setIndustry] = useState(config.industry || 'Technology')

  useEffect(() => {
    let mounted = true
    setLoading(true)
    get('/api/records?include_result=1')
      .then((res) => {
        if (!mounted) return
        const next = Array.isArray(res?.items) ? res.items : []
        setRecords(next)
        if (!selectedId && next[0]?.record_id) setSelectedId(next[0].record_id)
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
  }, [])

  const selected = useMemo(
    () => records.find((r) => String(r.record_id) === String(selectedId)) || null,
    [records, selectedId],
  )

  useEffect(() => {
    if (config.company) setCompany(config.company)
    if (config.year) setYear(config.year)
    if (config.industry) setIndustry(config.industry)
  }, [config.company, config.year, config.industry])

  useEffect(() => {
    if (!selected) return
    setCompany(selected.company || '')
    setYear(String(selected.year || ''))
    setIndustry(selected.industry || '')
  }, [selected])

  return (
    <div className="rl-page-shell">
      <section className="card p-5">
        <div className="page-header !mb-0 !pb-0">
          <div className="page-header-left">
            <span className="page-icon">📊</span>
            <div>
              <p className="page-title">Financial Tables</p>
              <p className="page-subtitle">Extract 5 core financial statements from 10-K PDFs via AWS Textract</p>
            </div>
          </div>
          <div className="rl-config-chip-row">
            <span className="rl-chip muted">Company: —</span>
            <span className="rl-chip muted">Year: —</span>
            <span className="rl-chip muted">Industry: —</span>
          </div>
        </div>
      </section>

      {error ? <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div> : null}

      <section className="grid gap-5 xl:grid-cols-[1.1fr_1.5fr]">
        <div className="card p-5">
          <div className="rl-tabs">
            <button className="rl-tab-btn active">📄 Manual PDF Upload</button>
            <button className="rl-tab-btn">🛰️ Auto Fetch from SEC EDGAR</button>
          </div>
          <div className="mt-4 space-y-3">
            <div>
              <label className="section-title">PDF Filing</label>
              <input className="input mt-2" type="file" disabled />
            </div>
            <div>
              <label className="section-title">Company</label>
              <input className="input mt-2" placeholder="e.g. Apple Inc." value={company} onChange={(e) => setCompany(e.target.value)} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="section-title">Year</label>
                <select className="input mt-2" value={year} onChange={(e) => setYear(e.target.value)}>
                  {YEARS.map((y) => (
                    <option key={y} value={y}>
                      {y}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="section-title">Industry</label>
                <select className="input mt-2" value={industry} onChange={(e) => setIndustry(e.target.value)}>
                  {INDUSTRIES.map((v) => (
                    <option key={v} value={v}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <button className="btn-primary w-full" disabled>
              Run Textract Extraction
            </button>
            <p className="rl-note">Tables API write-back 还未在 decoupled runtime 打开，这里先保持 Streamlit 同款交互结构。</p>
          </div>
        </div>

        <div className="card p-5">
          <p className="section-title">Results Panel</p>
          <h3 className="mt-1 text-xl font-extrabold text-slate-900">Extracted Statements</h3>
          <p className="mt-2 text-sm text-slate-600">When extraction completes, this panel will contain balance sheet, income statement, cash flow and export actions.</p>

          <div className="mt-4">
            <label className="section-title">Load Existing Filing Context</label>
            <select className="input mt-2" value={selectedId} onChange={(e) => setSelectedId(e.target.value)} disabled={loading}>
              <option value="">Select one record…</option>
              {records.map((r) => (
                <option key={r.record_id} value={r.record_id}>
                  {r.company} · {r.year} · {r.filing_type || '10-K'}
                </option>
              ))}
            </select>
          </div>

          <div className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center">
            <p className="text-sm font-semibold text-slate-700">
              {selected ? `Ready to extract tables for ${company || selected.company} ${year || selected.year}.` : 'No record selected.'}
            </p>
            <p className="mt-1 text-sm text-slate-500">CSV/JSON export buttons will appear here after extraction runtime migration.</p>
          </div>
        </div>
      </section>
    </div>
  )
}
