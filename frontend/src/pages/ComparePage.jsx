import React, { useEffect, useMemo, useState } from 'react'
import { get, post } from '../lib/api'

export default function ComparePage() {
  const [records, setRecords] = useState([])
  const [latestId, setLatestId] = useState('')
  const [priorId, setPriorId] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    get('/api/records')
      .then((res) => {
        const items = res?.items || []
        setRecords(items)
        if (items.length > 0) setLatestId(items[0].record_id)
        if (items.length > 1) setPriorId(items[1].record_id)
      })
      .catch((e) => setError(e.message || 'Failed to load records'))
  }, [])

  const labelMap = useMemo(() => {
    const m = new Map()
    records.forEach((r) => m.set(r.record_id, `${r.company} · ${r.year} · ${r.filing_type}`))
    return m
  }, [records])

  const runCompare = async () => {
    if (!latestId || !priorId) return
    setLoading(true)
    setError('')
    setData(null)
    try {
      const res = await post('/api/compare', {
        latest_record_id: latestId,
        prior_record_id: priorId,
      })
      setData(res?.data || null)
    } catch (e) {
      setError(e.message || 'Compare failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <section className="card p-5">
        <p className="section-title">Compare</p>
        <h3 className="mt-1 text-2xl font-extrabold text-slate-900">Risk Delta</h3>
        <p className="mt-1 text-sm text-slate-500">Compare two filing records and highlight newly emerged / removed risks.</p>
      </section>

      {error && <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div>}

      <section className="card grid gap-3 p-5 md:grid-cols-2">
        <div>
          <label className="section-title">Latest Record</label>
          <select className="input mt-2" value={latestId} onChange={(e) => setLatestId(e.target.value)}>
            {records.map((r) => <option key={r.record_id} value={r.record_id}>{labelMap.get(r.record_id)}</option>)}
          </select>
        </div>
        <div>
          <label className="section-title">Prior Record</label>
          <select className="input mt-2" value={priorId} onChange={(e) => setPriorId(e.target.value)}>
            {records.map((r) => <option key={r.record_id} value={r.record_id}>{labelMap.get(r.record_id)}</option>)}
          </select>
        </div>
        <div className="md:col-span-2">
          <button className="btn-primary" onClick={runCompare} disabled={loading || !latestId || !priorId}>
            {loading ? 'Comparing…' : 'Run Compare'}
          </button>
        </div>
      </section>

      {data && (
        <section className="grid gap-4 xl:grid-cols-2">
          <div className="card p-5">
            <p className="section-title">New Risks ({data?.summary?.new_count ?? 0})</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
              {(data.new_risks || []).map((r, i) => <li key={i}>{r.title}</li>)}
              {(data.new_risks || []).length === 0 && <li className="list-none text-slate-500">No new risks detected.</li>}
            </ul>
          </div>
          <div className="card p-5">
            <p className="section-title">Removed Risks ({data?.summary?.removed_count ?? 0})</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
              {(data.removed_risks || []).map((r, i) => <li key={i}>{r.title}</li>)}
              {(data.removed_risks || []).length === 0 && <li className="list-none text-slate-500">No removed risks detected.</li>}
            </ul>
          </div>
        </section>
      )}
    </div>
  )
}
