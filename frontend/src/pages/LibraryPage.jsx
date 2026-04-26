import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../lib/api'
import { companyOverview, groupedRiskTitles, riskCategoryCount, riskItemCount } from '../lib/records'

const INDUSTRY_COLORS = {
  Technology: '#2563eb',
  Healthcare: '#059669',
  Financials: '#7c3aed',
  Energy: '#d97706',
  'Consumer Discretionary': '#db2777',
  'Consumer Staples': '#0891b2',
  Industrials: '#65a30d',
  Materials: '#b45309',
  Utilities: '#0284c7',
  'Real Estate': '#6d28d9',
  Telecom: '#0f766e',
  Other: '#6b7280',
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
        <Link to={`/compare?company=${encodeURIComponent(rec.company || '')}&year=${encodeURIComponent(String(rec.year || ''))}`} className="btn-secondary w-full">
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

export default function LibraryPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [selectedResult, setSelectedResult] = useState(null)
  const [loadingSelected, setLoadingSelected] = useState(false)

  const [industry, setIndustry] = useState('All')
  const [company, setCompany] = useState('All')
  const [year, setYear] = useState('All')
  const [filingType, setFilingType] = useState('All')
  const [search, setSearch] = useState('')

  const load = () => {
    let mounted = true
    setLoading(true)
    setError('')
    get('/api/records?include_result=1')
      .then((res) => {
        if (!mounted) return
        const next = Array.isArray(res?.items) ? res.items : []
        setItems(next)
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
  }

  useEffect(() => {
    const off = load()
    return off
  }, [])

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

  const industries = useMemo(
    () => ['All', ...Array.from(new Set(items.map((r) => String(r.industry || '').trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b))],
    [items],
  )
  const companies = useMemo(
    () => ['All', ...Array.from(new Set(items.map((r) => String(r.company || '').trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b))],
    [items],
  )
  const years = useMemo(
    () => ['All', ...Array.from(new Set(items.map((r) => String(r.year || '').trim()).filter(Boolean))).sort((a, b) => Number(b) - Number(a))],
    [items],
  )
  const filingTypes = useMemo(
    () => ['All', ...Array.from(new Set(items.map((r) => String(r.filing_type || '').trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b))],
    [items],
  )

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return items.filter((r) => {
      if (industry !== 'All' && String(r.industry || '') !== industry) return false
      if (company !== 'All' && String(r.company || '') !== company) return false
      if (year !== 'All' && String(r.year || '') !== year) return false
      if (filingType !== 'All' && String(r.filing_type || '') !== filingType) return false
      if (!q) return true
      return [r.company, r.industry, String(r.year), r.filing_type, r.record_id]
        .join(' ')
        .toLowerCase()
        .includes(q)
    })
  }, [items, industry, company, year, filingType, search])

  const selectedRec = useMemo(
    () => filtered.find((r) => String(r.record_id) === String(selectedId)) || items.find((r) => String(r.record_id) === String(selectedId)) || null,
    [filtered, items, selectedId],
  )

  return (
    <div className="rl-page-shell">
      <section className="card p-5">
        <div className="page-header !mb-0 !pb-0 !border-0">
          <div className="page-header-left">
            <span className="page-icon">📚</span>
            <div>
              <p className="page-title">Library</p>
              <p className="page-subtitle">Browse and manage your uploaded 10-K filings</p>
            </div>
          </div>
          <Link to="/upload" className="btn-primary">
            ➕ New Filing
          </Link>
        </div>
      </section>

      {error ? <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div> : null}

      <section className="card p-5">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <div>
            <label className="section-title">Industry</label>
            <select className="input mt-2" value={industry} onChange={(e) => setIndustry(e.target.value)}>
              {industries.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="section-title">Company</label>
            <select className="input mt-2" value={company} onChange={(e) => setCompany(e.target.value)}>
              {companies.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="section-title">Year</label>
            <select className="input mt-2" value={year} onChange={(e) => setYear(e.target.value)}>
              {years.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="section-title">Filing Type</label>
            <select className="input mt-2" value={filingType} onChange={(e) => setFilingType(e.target.value)}>
              {filingTypes.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="section-title">Search</label>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="company / industry / year"
              className="input mt-2"
            />
          </div>
        </div>
        <p className="rl-count-label">
          Showing <strong>{filtered.length}</strong> of {items.length} records
        </p>
      </section>

      {loadingSelected ? <div className="card p-4 text-sm text-slate-500">Loading selected filing…</div> : null}
      {!loadingSelected && selectedRec && selectedResult ? <RecordDetailPanel rec={selectedRec} result={selectedResult} /> : null}

      <section className="rl-record-grid">
        {loading ? <div className="card p-4 text-sm text-slate-500">Loading records…</div> : null}
        {!loading && filtered.length === 0 ? <div className="card p-4 text-sm text-slate-500">No records found.</div> : null}
        {!loading &&
          filtered.map((r) => {
            const c = INDUSTRY_COLORS[String(r.industry || 'Other')] || '#6b7280'
            const active = String(r.record_id) === String(selectedId)
            return (
              <article key={r.record_id} className={`rl-record-card ${active ? 'active' : ''}`}>
                <div className="rl-record-top">
                  <span className="rl-record-ticker" style={{ color: c, background: `${c}15`, borderColor: `${c}25` }}>
                    {String(r.company || 'NA').slice(0, 4).toUpperCase()}
                  </span>
                  <span className="rl-record-format">{String(r.file_ext || 'html').toUpperCase()}</span>
                </div>
                <p className="rl-record-company">{r.company || '—'}</p>
                <p className="rl-record-meta">
                  {r.industry || 'Other'} · {r.filing_type || '10-K'} · {r.year || '—'}
                </p>
                <p className="rl-record-submeta">
                  {r.risk_items ?? 0} risk items · {r.risk_categories ?? 0} categories
                </p>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button
                    className={active ? 'btn-primary w-full' : 'btn-secondary w-full'}
                    onClick={() => setSelectedId(String(r.record_id))}
                  >
                    {active ? '✓ Loaded' : 'Load'}
                  </button>
                  <button className="btn-secondary w-full" disabled title="Delete API is not enabled in decoupled runtime yet">
                    Delete
                  </button>
                </div>
              </article>
            )
          })}
      </section>
    </div>
  )
}
