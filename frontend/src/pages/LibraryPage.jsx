import React, { useEffect, useMemo, useState } from 'react'
import { get } from '../lib/api'

export default function LibraryPage() {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')

  useEffect(() => {
    let mounted = true
    setLoading(true)
    get('/api/records?include_result=1')
      .then((res) => {
        if (!mounted) return
        setItems(res?.items || [])
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

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return items
    return items.filter((r) =>
      [r.company, r.industry, String(r.year), r.filing_type].join(' ').toLowerCase().includes(q),
    )
  }, [items, search])

  return (
    <div className="space-y-4">
      <section className="card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="section-title">Records Library</p>
            <h3 className="mt-1 text-2xl font-extrabold text-slate-900">All Filing Records</h3>
          </div>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search company / industry / year"
            className="input w-full md:w-80"
          />
        </div>
      </section>

      {error && <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div>}

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {loading && <div className="card p-4 text-sm text-slate-500">Loading records…</div>}
        {!loading && filtered.length === 0 && <div className="card p-4 text-sm text-slate-500">No records found.</div>}
        {!loading &&
          filtered.map((r) => (
            <article key={r.record_id} className="card p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h4 className="text-lg font-extrabold text-slate-900">{r.company}</h4>
                  <p className="text-xs text-slate-500">{r.record_id}</p>
                </div>
                <span className="rounded-full border border-slate-300 px-2 py-0.5 text-xs font-bold text-slate-600">{r.year}</span>
              </div>
              <div className="mt-3 space-y-1 text-sm text-slate-600">
                <p><span className="font-semibold text-slate-700">Industry:</span> {r.industry || '—'}</p>
                <p><span className="font-semibold text-slate-700">Filing:</span> {r.filing_type || '10-K'} ({r.file_ext || 'html'})</p>
                <p><span className="font-semibold text-slate-700">Risk items:</span> {r.risk_items ?? 0}</p>
                <p><span className="font-semibold text-slate-700">Risk categories:</span> {r.risk_categories ?? 0}</p>
              </div>
            </article>
          ))}
      </section>
    </div>
  )
}
