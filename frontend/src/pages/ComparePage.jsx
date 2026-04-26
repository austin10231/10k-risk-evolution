import React, { useEffect, useMemo, useState } from 'react'
import { get, post } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'

export default function ComparePage() {
  const { config } = useGlobalConfig()
  const [records, setRecords] = useState([])
  const [mode, setMode] = useState('yoy')
  const [latestId, setLatestId] = useState('')
  const [priorId, setPriorId] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [loadingRecords, setLoadingRecords] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let mounted = true
    setLoadingRecords(true)
    get('/api/records')
      .then((res) => {
        if (!mounted) return
        const items = res?.items || []
        setRecords(items)
        if (items.length > 0) setLatestId(items[0].record_id)
        if (items.length > 1) setPriorId(items[1].record_id)
      })
      .catch((e) => {
        if (!mounted) return
        setError(e.message || 'Failed to load records')
      })
      .finally(() => {
        if (!mounted) return
        setLoadingRecords(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  const labelMap = useMemo(() => {
    const m = new Map()
    records.forEach((r) => m.set(r.record_id, `${r.company} · ${r.year} · ${r.filing_type}`))
    return m
  }, [records])

  const companies = useMemo(
    () => Array.from(new Set(records.map((r) => String(r.company || '').trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b)),
    [records],
  )
  const [companyYoy, setCompanyYoy] = useState('')
  const [ftYoy, setFtYoy] = useState('10-K')
  const [latestYear, setLatestYear] = useState('')
  const [priorYear, setPriorYear] = useState('')

  const [companyA, setCompanyA] = useState('')
  const [companyB, setCompanyB] = useState('')
  const [yearA, setYearA] = useState('')
  const [yearB, setYearB] = useState('')

  useEffect(() => {
    if (!companies.length) return
    const preferred = config.company && companies.includes(config.company) ? config.company : companies[0]
    if (!companyYoy || !companies.includes(companyYoy)) setCompanyYoy(preferred)
    if (!companyA || !companies.includes(companyA)) setCompanyA(preferred)
    if (!companyB || !companies.includes(companyB)) {
      const alt = companies.find((c) => c !== preferred) || preferred
      setCompanyB(alt)
    }
  }, [companies, companyYoy, companyA, companyB, config.company])

  const yoyRecords = useMemo(
    () => records.filter((r) => String(r.company || '') === companyYoy && String(r.filing_type || '10-K') === ftYoy),
    [records, companyYoy, ftYoy],
  )
  const yoyYears = useMemo(
    () => Array.from(new Set(yoyRecords.map((r) => Number(r.year)).filter(Number.isFinite))).sort((a, b) => b - a),
    [yoyRecords],
  )
  useEffect(() => {
    if (!yoyYears.length) return
    if (config.year && yoyYears.includes(Number(config.year))) {
      setLatestYear(String(config.year))
      return
    }
    if (!latestYear || !yoyYears.includes(Number(latestYear))) setLatestYear(String(yoyYears[0]))
  }, [yoyYears, latestYear, config.year])
  const priorYearOptions = useMemo(
    () => yoyYears.filter((y) => y < Number(latestYear)),
    [yoyYears, latestYear],
  )
  useEffect(() => {
    if (!priorYearOptions.length) return
    if (!priorYear || !priorYearOptions.includes(Number(priorYear))) setPriorYear(String(priorYearOptions[0]))
  }, [priorYearOptions, priorYear])

  useEffect(() => {
    if (!companyYoy || !latestYear || !priorYear) return
    const latestRec = records
      .filter((r) => String(r.company || '') === companyYoy && Number(r.year) === Number(latestYear))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0]
    const priorRec = records
      .filter((r) => String(r.company || '') === companyYoy && Number(r.year) === Number(priorYear))
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0]
    if (latestRec?.record_id) setLatestId(latestRec.record_id)
    if (priorRec?.record_id) setPriorId(priorRec.record_id)
  }, [companyYoy, latestYear, priorYear, records])

  const yearsForCompany = (name) =>
    Array.from(new Set(records.filter((r) => String(r.company || '') === name).map((r) => Number(r.year)).filter(Number.isFinite))).sort((a, b) => b - a)

  useEffect(() => {
    const aYears = yearsForCompany(companyA)
    const bYears = yearsForCompany(companyB)
    if (aYears.length) {
      if (config.year && aYears.includes(Number(config.year))) setYearA(String(config.year))
      else if (!yearA || !aYears.includes(Number(yearA))) setYearA(String(aYears[0]))
    }
    if (bYears.length) {
      if (config.year && bYears.includes(Number(config.year))) setYearB(String(config.year))
      else if (!yearB || !bYears.includes(Number(yearB))) setYearB(String(bYears[0]))
    }
  }, [companyA, companyB, yearA, yearB, records, config.year])

  useEffect(() => {
    if (!companyA || !companyB || !yearA || !yearB || mode !== 'cross') return
    const a = records
      .filter((r) => String(r.company || '') === companyA && Number(r.year) === Number(yearA))
      .sort((x, y) => String(y.created_at || '').localeCompare(String(x.created_at || '')))[0]
    const b = records
      .filter((r) => String(r.company || '') === companyB && Number(r.year) === Number(yearB))
      .sort((x, y) => String(y.created_at || '').localeCompare(String(x.created_at || '')))[0]
    if (b?.record_id) setLatestId(b.record_id)
    if (a?.record_id) setPriorId(a.record_id)
  }, [companyA, companyB, yearA, yearB, mode, records])

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
    <div className="rl-page-shell">
      <section className="card p-5">
        <div className="page-header !mb-0 !pb-0">
          <div className="page-header-left">
            <span className="page-icon">⚖️</span>
            <div>
              <p className="page-title">Compare</p>
              <p className="page-subtitle">Detect risk changes year-over-year or between companies</p>
            </div>
          </div>
          <div className="rl-config-chip-row">
            <span className="rl-chip muted">Company: —</span>
            <span className="rl-chip muted">Year: —</span>
          </div>
        </div>
      </section>

      {error && <div className="card border-red-200 bg-red-50 p-4 text-sm font-semibold text-red-700">{error}</div>}

      <section className="card p-5">
        <p className="section-title">Comparison Mode</p>
        <div className="rl-tabs mt-2">
          <button className={`rl-tab-btn ${mode === 'yoy' ? 'active' : ''}`} onClick={() => setMode('yoy')}>
            📅 Year-over-Year
          </button>
          <button className={`rl-tab-btn ${mode === 'cross' ? 'active' : ''}`} onClick={() => setMode('cross')}>
            🏢 Cross-Company
          </button>
        </div>

        {loadingRecords ? <p className="mt-4 text-sm text-slate-500">Loading records…</p> : null}

        {!loadingRecords && mode === 'yoy' ? (
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <div>
              <label className="section-title">Company</label>
              <select className="input mt-2" value={companyYoy} onChange={(e) => setCompanyYoy(e.target.value)}>
                {companies.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="section-title">Filing Type</label>
              <select className="input mt-2" value={ftYoy} onChange={(e) => setFtYoy(e.target.value)}>
                <option value="10-K">10-K</option>
                <option value="10-Q">10-Q</option>
              </select>
            </div>
            <div>
              <label className="section-title">Latest Year</label>
              <select className="input mt-2" value={latestYear} onChange={(e) => setLatestYear(e.target.value)}>
                {yoyYears.map((y) => (
                  <option key={y} value={String(y)}>
                    {y}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="section-title">Prior Year</label>
              <select className="input mt-2" value={priorYear} onChange={(e) => setPriorYear(e.target.value)}>
                {priorYearOptions.map((y) => (
                  <option key={y} value={String(y)}>
                    {y}
                  </option>
                ))}
              </select>
            </div>
          </div>
        ) : null}

        {!loadingRecords && mode === 'cross' ? (
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <div className="rounded-xl border border-blue-200 bg-blue-50 p-3">
              <p className="text-sm font-bold text-blue-700">Company A</p>
              <div className="mt-2 grid gap-3 md:grid-cols-2">
                <div>
                  <label className="section-title">Company</label>
                  <select className="input mt-2" value={companyA} onChange={(e) => setCompanyA(e.target.value)}>
                    {companies.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="section-title">Year</label>
                  <select className="input mt-2" value={yearA} onChange={(e) => setYearA(e.target.value)}>
                    {yearsForCompany(companyA).map((y) => (
                      <option key={y} value={String(y)}>
                        {y}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3">
              <p className="text-sm font-bold text-emerald-700">Company B</p>
              <div className="mt-2 grid gap-3 md:grid-cols-2">
                <div>
                  <label className="section-title">Company</label>
                  <select className="input mt-2" value={companyB} onChange={(e) => setCompanyB(e.target.value)}>
                    {companies.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="section-title">Year</label>
                  <select className="input mt-2" value={yearB} onChange={(e) => setYearB(e.target.value)}>
                    {yearsForCompany(companyB).map((y) => (
                      <option key={y} value={String(y)}>
                        {y}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          </div>
        ) : null}

        <div className="mt-4">
          <button className="btn-primary" onClick={runCompare} disabled={loading || !latestId || !priorId}>
            {loading ? 'Comparing…' : '🚀 Run Compare'}
          </button>
        </div>
      </section>

      {data && (
        <>
          <section className="grid gap-4 xl:grid-cols-2">
            <div className="metric-card border border-emerald-200">
              <p className="metric-label">Only in Newer Filing</p>
              <p className="metric-value !text-emerald-600">{data?.summary?.new_count ?? 0} new</p>
            </div>
            <div className="metric-card border border-red-200">
              <p className="metric-label">Only in Older Filing</p>
              <p className="metric-value !text-red-600">{data?.summary?.removed_count ?? 0} removed</p>
            </div>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <div className="card p-5">
              <p className="section-title">🟢 Risks Unique to Newer Filing</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                {(data.new_risks || []).slice(0, 60).map((r, i) => (
                  <li key={i}>{r.title}</li>
                ))}
                {(data.new_risks || []).length === 0 ? <li className="list-none text-slate-500">No unique risks in newer filing.</li> : null}
              </ul>
            </div>
            <div className="card p-5">
              <p className="section-title">🔴 Risks Unique to Older Filing</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                {(data.removed_risks || []).slice(0, 60).map((r, i) => (
                  <li key={i}>{r.title}</li>
                ))}
                {(data.removed_risks || []).length === 0 ? <li className="list-none text-slate-500">No unique risks in older filing.</li> : null}
              </ul>
            </div>
          </section>
          <section className="card p-5">
            <div className="rl-section-header">Comparison Metadata</div>
            <div className="mt-2 grid gap-2 md:grid-cols-2 xl:grid-cols-3">
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                <span className="font-semibold text-slate-700">Latest Record:</span> {labelMap.get(data.latest_record_id) || data.latest_record_id}
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                <span className="font-semibold text-slate-700">Prior Record:</span> {labelMap.get(data.prior_record_id) || data.prior_record_id}
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
                <span className="font-semibold text-slate-700">Mode:</span> {mode === 'yoy' ? 'Year-over-Year' : 'Cross-Company'}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
