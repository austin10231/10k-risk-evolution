import React, { useEffect, useMemo, useState } from 'react'
import { get } from '../lib/api'
import { companyOverview, groupedRiskTitles, riskCategoryCount, riskItemCount } from '../lib/records'

export default function AnalyzePage() {
  const [tab, setTab] = useState('library')
  const [records, setRecords] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let mounted = true
    setLoading(true)
    get('/api/records?include_result=1')
      .then((res) => {
        if (!mounted) return
        const items = Array.isArray(res?.items) ? res.items : []
        setRecords(items)
        if (items[0]?.record_id) setSelectedId(String(items[0].record_id))
      })
      .catch((e) => {
        if (!mounted) return
        setError(e.message || 'Failed to load record list')
      })
      .finally(() => {
        if (!mounted) return
        setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  useEffect(() => {
    if (!selectedId) return
    let mounted = true
    setLoadingDetail(true)
    setResult(null)
    get(`/api/records/${encodeURIComponent(selectedId)}`)
      .then((res) => {
        if (!mounted) return
        setResult(res?.result || null)
      })
      .catch((e) => {
        if (!mounted) return
        setError(e.message || 'Failed to load record detail')
      })
      .finally(() => {
        if (!mounted) return
        setLoadingDetail(false)
      })
    return () => {
      mounted = false
    }
  }, [selectedId])

  const selectedRec = useMemo(
    () => records.find((r) => String(r.record_id) === String(selectedId)) || null,
    [records, selectedId],
  )
  const overview = companyOverview(result)
  const grouped = groupedRiskTitles(result)

  return (
    <div className="rl-page-shell">
      <section className="card p-5">
        <div className="page-header !mb-0 !pb-0">
          <div className="page-header-left">
            <span className="page-icon">🔬</span>
            <div>
              <p className="page-title">Analyze</p>
              <p className="page-subtitle">Inspect filing output, summary and risk category details</p>
            </div>
          </div>
        </div>
      </section>

      <section className="card p-5">
        <div className="rl-tabs">
          <button className={`rl-tab-btn ${tab === 'library' ? 'active' : ''}`} onClick={() => setTab('library')}>
            📚 Library
          </button>
          <button className={`rl-tab-btn ${tab === 'new' ? 'active' : ''}`} onClick={() => setTab('new')}>
            ➕ New Analysis
          </button>
        </div>
      </section>

      {error ? <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div> : null}

      {tab === 'library' ? (
        <>
          <section className="card p-5">
            <label className="section-title">Select A Record</label>
            <select className="input mt-2" value={selectedId} onChange={(e) => setSelectedId(e.target.value)} disabled={loading}>
              {records.map((r) => (
                <option key={r.record_id} value={r.record_id}>
                  {`${r.company} · ${r.year} · ${r.filing_type || '10-K'} · ${r.industry || 'Other'}`}
                </option>
              ))}
            </select>
          </section>

          {loadingDetail ? <div className="card p-4 text-sm text-slate-500">Loading record detail…</div> : null}

          {!loadingDetail && result ? (
            <>
              <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div className="metric-card">
                  <p className="metric-label">Company</p>
                  <p className="metric-value">{overview.company || selectedRec?.company || '—'}</p>
                </div>
                <div className="metric-card">
                  <p className="metric-label">Year</p>
                  <p className="metric-value">{overview.year || selectedRec?.year || '—'}</p>
                </div>
                <div className="metric-card">
                  <p className="metric-label">Risk Categories</p>
                  <p className="metric-value">{riskCategoryCount(result)}</p>
                </div>
                <div className="metric-card">
                  <p className="metric-label">Risk Items</p>
                  <p className="metric-value">{riskItemCount(result)}</p>
                </div>
              </section>

              <section className="card p-5">
                <div className="rl-section-header">🤖 AI Executive Summary</div>
                <div className="rl-info-box whitespace-pre-wrap">{result.ai_summary || 'No AI summary stored yet.'}</div>
              </section>

              {overview.background ? (
                <section className="card p-5">
                  <div className="rl-section-header">🏢 Company Overview</div>
                  <p className="rl-body-text">{overview.background}</p>
                </section>
              ) : null}

              <section className="card p-5">
                <div className="rl-section-header">⚠️ Risk Categories ({grouped.length})</div>
                <div className="space-y-2">
                  {grouped.length === 0 ? <p className="text-sm text-slate-500">No risk entries in this record.</p> : null}
                  {grouped.map((g) => (
                    <details key={g.category} className="rl-expander">
                      <summary>
                        {g.category} ({g.titles.length})
                      </summary>
                      <ul>
                        {g.titles.slice(0, 36).map((title, idx) => (
                          <li key={`${g.category}-${idx}`}>{title}</li>
                        ))}
                      </ul>
                    </details>
                  ))}
                </div>
              </section>
            </>
          ) : null}
        </>
      ) : (
        <section className="card p-5">
          <div className="rl-section-header">➕ New Analysis</div>
          <p className="rl-body-text">
            This decoupled frontend keeps the same visual workflow. Manual upload / SEC auto-fetch execution currently runs through the
            Streamlit runtime path, and will be migrated into API endpoints in the next backend phase.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <div className="rl-mini-tile">Upload filing HTML/PDF</div>
            <div className="rl-mini-tile">Choose year + industry + extraction mode</div>
            <div className="rl-mini-tile">Save record + result to runtime store</div>
          </div>
        </section>
      )}
    </div>
  )
}
