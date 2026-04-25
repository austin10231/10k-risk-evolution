import React, { useEffect, useMemo, useState } from 'react'
import { get } from '../lib/api'

export default function AnalyzePage() {
  const [records, setRecords] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let mounted = true
    setLoading(true)
    get('/api/records')
      .then((res) => {
        if (!mounted) return
        const items = res?.items || []
        setRecords(items)
        if (items.length > 0) setSelectedId(items[0].record_id)
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
    get(`/api/records/${selectedId}`)
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

  const riskBlocks = useMemo(() => result?.risks || [], [result])

  return (
    <div className="space-y-4">
      <section className="card p-5">
        <p className="section-title">Analyze Filing</p>
        <h3 className="mt-1 text-2xl font-extrabold text-slate-900">Record Drilldown</h3>
        <p className="mt-1 text-sm text-slate-500">Select one record to inspect overview, summary, and risk categories.</p>
      </section>

      {error && <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div>}

      <section className="card p-5">
        <label className="section-title">Record</label>
        <select className="input mt-2" value={selectedId} onChange={(e) => setSelectedId(e.target.value)} disabled={loading}>
          {records.map((r) => (
            <option key={r.record_id} value={r.record_id}>{`${r.company} · ${r.year} · ${r.filing_type}`}</option>
          ))}
        </select>
      </section>

      {loadingDetail && <div className="card p-4 text-sm text-slate-500">Loading record detail…</div>}

      {!loadingDetail && result && (
        <>
          <section className="card p-5">
            <p className="section-title">Executive Summary</p>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{result.ai_summary || 'No AI summary stored yet.'}</p>
          </section>

          <section className="card p-5">
            <p className="section-title">Risk Categories</p>
            <div className="mt-3 space-y-3">
              {riskBlocks.length === 0 && <p className="text-sm text-slate-500">No risk entries in this record.</p>}
              {riskBlocks.map((block, idx) => (
                <details key={`${block.category}-${idx}`} className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
                  <summary className="cursor-pointer text-sm font-bold text-slate-800">
                    {block.category || 'Unknown'} ({(block.sub_risks || []).length})
                  </summary>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                    {(block.sub_risks || []).map((risk, i) => {
                      const title = typeof risk === 'string' ? risk : risk?.title || ''
                      return <li key={i}>{title}</li>
                    })}
                  </ul>
                </details>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  )
}
