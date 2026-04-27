import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { get } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'

const DEFAULT_TICKERS = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL']
const RANGE_OPTIONS = ['1W', '1M', '3M', '6M', '1Y']
const RANGE_SIZE = { '1W': 5, '1M': 22, '3M': 66, '6M': 132, '1Y': 252 }
const STOCK_LAST_TICKER_KEY = 'rl_stock_last_ticker_v1'
const STOCK_RECENT_TICKERS_KEY = 'rl_stock_recent_tickers_v1'
const STOCK_BUNDLE_PREFIX = 'rl_stock_bundle_v1_'
const STOCK_BUNDLE_TTL_MS = 1000 * 60 * 60 * 12

function normalizeTicker(raw) {
  return String(raw || '')
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9.\-]/g, '')
}

function mergeTickers(...groups) {
  const out = []
  groups.flat().forEach((raw) => {
    const t = normalizeTicker(raw)
    if (!t || out.includes(t)) return
    out.push(t)
  })
  return out
}

function readLocalJson(key, fallback) {
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) return fallback
    const val = JSON.parse(raw)
    return val ?? fallback
  } catch {
    return fallback
  }
}

function writeLocalJson(key, value) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // ignore write failures
  }
}

function readLastTicker() {
  if (typeof window === 'undefined') return ''
  try {
    return normalizeTicker(window.localStorage.getItem(STOCK_LAST_TICKER_KEY) || '')
  } catch {
    return ''
  }
}

function writeLastTicker(ticker) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STOCK_LAST_TICKER_KEY, normalizeTicker(ticker))
  } catch {
    // ignore write failures
  }
}

function readRecentTickers() {
  const raw = readLocalJson(STOCK_RECENT_TICKERS_KEY, [])
  if (!Array.isArray(raw)) return []
  return mergeTickers(raw)
}

function writeRecentTickers(list) {
  writeLocalJson(STOCK_RECENT_TICKERS_KEY, mergeTickers(list).slice(0, 10))
}

function cacheKeyForTicker(ticker) {
  return `${STOCK_BUNDLE_PREFIX}${normalizeTicker(ticker)}`
}

function readBundleCache(ticker) {
  const key = cacheKeyForTicker(ticker)
  const payload = readLocalJson(key, null)
  if (!payload || typeof payload !== 'object') return null
  const savedAt = Number(payload.saved_at || 0)
  const data = payload.data && typeof payload.data === 'object' ? payload.data : null
  if (!data) return null
  return {
    savedAt: Number.isFinite(savedAt) ? savedAt : 0,
    data,
  }
}

function writeBundleCache(ticker, data) {
  if (!ticker || !data || typeof data !== 'object') return
  writeLocalJson(cacheKeyForTicker(ticker), {
    saved_at: Date.now(),
    data,
  })
}

function isBundleStale(savedAt) {
  if (!Number.isFinite(savedAt) || savedAt <= 0) return true
  return Date.now() - savedAt > STOCK_BUNDLE_TTL_MS
}

function fmtPrice(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—'
  return `$${Number(v).toFixed(2)}`
}

function fmtPct(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—'
  const n = Number(v)
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

function fmtCompact(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—'
  const n = Number(v)
  const abs = Math.abs(n)
  if (abs >= 1_000_000_000_000) return `${(n / 1_000_000_000_000).toFixed(2)}T`
  if (abs >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString()
}

function fmtSigned(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—'
  const n = Number(v)
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

function timeAgoFrom(ts) {
  const n = Number(ts || 0)
  if (!Number.isFinite(n) || n <= 0) return 'N/A'
  const diff = Math.max(0, Date.now() - n)
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function providerLabel(raw) {
  const key = String(raw || '').trim().toLowerCase()
  if (!key) return 'N/A'
  if (key === 'twelvedata') return 'TwelveData'
  if (key === 'fmp') return 'FMP'
  if (key === 'yahoo') return 'Yahoo'
  if (key === 'stooq') return 'Stooq'
  if (key === 'derived') return 'Derived'
  return key
}

function buildBundleHint(payload, mode = '') {
  const p = payload && typeof payload === 'object' ? payload : {}
  const quoteSource = providerLabel(p.quote_source)
  const historySource = providerLabel(p.history_source)
  const warning = String(p.warning || '').trim()
  const fromCache = mode === 'cache' || Boolean(p.cache_hit)

  if (warning && fromCache) {
    return `Live refresh rate-limited; using cached view. Quote: ${quoteSource} · History: ${historySource}`
  }
  if (warning) {
    return `${warning} Quote: ${quoteSource} · History: ${historySource}`
  }
  if (fromCache) {
    return `Cached data active. Quote: ${quoteSource} · History: ${historySource}`
  }
  return `Live data. Quote: ${quoteSource} · History: ${historySource}`
}

function sanitizeCompanyName(raw) {
  let s = String(raw || '').trim().toLowerCase()
  if (!s) return ''
  s = s.replace(/[.,()]/g, ' ')
  s = s.replace(/\b(inc|incorporated|corp|corporation|company|co|ltd|limited|plc|holdings?|group|class [ab])\b/g, ' ')
  s = s.replace(/\s+/g, ' ').trim()
  return s
}

function buildCompanyQuery(name) {
  const normalized = sanitizeCompanyName(name)
  if (!normalized) return ''
  const tokens = normalized.split(' ').filter(Boolean)
  if (!tokens.length) return ''
  return tokens.slice(0, 2).join(' ')
}

function numericSeries(history, key) {
  return history.map((row) => Number(row?.[key])).filter((v) => Number.isFinite(v))
}

function returnSeries(closeVals) {
  if (!closeVals.length) return []
  const base = closeVals[0]
  if (!Number.isFinite(base) || base === 0) return closeVals.map(() => 0)
  return closeVals.map((v) => ((v / base - 1) * 100.0))
}

function drawdownSeries(closeVals) {
  if (!closeVals.length) return []
  let rollingHigh = closeVals[0]
  return closeVals.map((v) => {
    rollingHigh = Math.max(rollingHigh, v)
    if (!Number.isFinite(rollingHigh) || rollingHigh === 0) return 0
    return (v / rollingHigh - 1) * 100.0
  })
}

function rangeSize(key) {
  return RANGE_SIZE[key] || RANGE_SIZE['1M']
}

function clipHistory(history, key) {
  const rows = Array.isArray(history) ? history : []
  const cleaned = rows
    .map((row) => ({
      date: String(row?.date || ''),
      close: Number(row?.close),
      volume: Number(row?.volume || 0),
    }))
    .filter((row) => row.date && Number.isFinite(row.close))

  if (!cleaned.length) return []
  const size = rangeSize(key)
  return cleaned.length <= size ? cleaned : cleaned.slice(-size)
}

function chartColorFor(values, fallbackUp = '#2563eb', fallbackDown = '#dc2626') {
  if (!Array.isArray(values) || values.length < 2) return fallbackUp
  const last = Number(values[values.length - 1])
  const first = Number(values[0])
  if (!Number.isFinite(last) || !Number.isFinite(first)) return fallbackUp
  return last >= first ? fallbackUp : fallbackDown
}

function lineGeometry(values, width, height, padding = 12) {
  if (!Array.isArray(values) || !values.length) {
    return { path: '', areaPath: '', points: [], min: 0, max: 0 }
  }
  const min = Math.min(...values)
  const max = Math.max(...values)
  const minSafe = Number.isFinite(min) ? min : 0
  const maxSafe = Number.isFinite(max) ? max : 0
  const span = Math.max(1e-6, maxSafe - minSafe)
  const innerW = Math.max(1, width - padding * 2)
  const innerH = Math.max(1, height - padding * 2)

  const points = values.map((v, i) => {
    const x = padding + (values.length <= 1 ? 0 : (innerW * i) / (values.length - 1))
    const y = padding + innerH - ((v - minSafe) / span) * innerH
    return { x, y, v }
  })

  const path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`)
    .join(' ')

  const first = points[0]
  const last = points[points.length - 1]
  const areaPath = `${path} L ${last.x.toFixed(2)} ${(height - padding).toFixed(2)} L ${first.x.toFixed(2)} ${(height - padding).toFixed(2)} Z`

  return { path, areaPath, points, min: minSafe, max: maxSafe }
}

function barsGeometry(values, width, height, padding = 12) {
  if (!Array.isArray(values) || !values.length) {
    return { bars: [], max: 0 }
  }
  const max = Math.max(...values, 0)
  const maxSafe = Math.max(max, 1)
  const innerW = Math.max(1, width - padding * 2)
  const innerH = Math.max(1, height - padding * 2)
  const slotW = innerW / values.length
  const barW = Math.max(1.2, slotW * 0.66)

  const bars = values.map((v, i) => {
    const h = (Math.max(0, v) / maxSafe) * innerH
    const x = padding + i * slotW + (slotW - barW) / 2
    const y = padding + innerH - h
    return { x, y, w: barW, h }
  })

  return { bars, max: maxSafe }
}

function matchRecordsToCompany(items, displayName) {
  const rows = Array.isArray(items) ? items : []
  if (!rows.length) return []

  const target = sanitizeCompanyName(displayName)
  if (!target) return rows

  const exact = rows.filter((r) => {
    const c = sanitizeCompanyName(r?.company)
    return c && (c === target || c.includes(target) || target.includes(c))
  })
  if (exact.length) return exact

  const targetTokens = target.split(' ').filter(Boolean)
  const loose = rows.filter((r) => {
    const cTokens = sanitizeCompanyName(r?.company).split(' ').filter(Boolean)
    const overlap = cTokens.filter((t) => targetTokens.includes(t)).length
    return overlap >= Math.min(2, targetTokens.length)
  })
  return loose.length ? loose : rows
}

function buildFilingSummary(items) {
  const rows = Array.isArray(items) ? items : []
  const sorted = [...rows].sort((a, b) => String(b?.created_at || '').localeCompare(String(a?.created_at || '')))
  const years = Array.from(new Set(sorted.map((r) => Number(r?.year)).filter(Number.isFinite))).sort((a, b) => b - a)

  const riskItems = sorted.map((r) => Number(r?.risk_items || 0)).filter(Number.isFinite)
  const categories = sorted.map((r) => Number(r?.risk_categories || 0)).filter(Number.isFinite)

  const avgRiskItems = riskItems.length ? riskItems.reduce((a, b) => a + b, 0) / riskItems.length : 0
  const avgCategories = categories.length ? categories.reduce((a, b) => a + b, 0) / categories.length : 0
  const latest = sorted[0] || null

  const byYear = years
    .map((y) => {
      const yr = sorted.filter((r) => Number(r?.year) === Number(y))
      const vals = yr.map((r) => Number(r?.risk_items || 0)).filter(Number.isFinite)
      const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
      return { year: y, avgRiskItems: avg }
    })
    .sort((a, b) => a.year - b.year)

  return {
    count: sorted.length,
    years,
    latest,
    avgRiskItems,
    avgCategories,
    byYear,
    recent: sorted.slice(0, 4),
  }
}

function MiniChart({ values, kind, color }) {
  const width = 240
  const height = 76

  if (!Array.isArray(values) || values.length < 2) {
    return (
      <svg viewBox={`0 0 ${width} ${height}`} className="rl-stock-mini-svg" aria-hidden="true">
        <text x="8" y="42" className="rl-stock-mini-empty">
          No data
        </text>
      </svg>
    )
  }

  if (kind === 'bars') {
    const bars = barsGeometry(values, width, height, 10)
    return (
      <svg viewBox={`0 0 ${width} ${height}`} className="rl-stock-mini-svg" aria-hidden="true">
        {bars.bars.map((bar, idx) => (
          <rect
            key={`${idx}-${bar.x}`}
            x={bar.x}
            y={bar.y}
            width={bar.w}
            height={bar.h}
            rx="1.8"
            fill={color}
            opacity="0.86"
          />
        ))}
      </svg>
    )
  }

  const line = lineGeometry(values, width, height, 10)
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="rl-stock-mini-svg" aria-hidden="true">
      <path d={line.areaPath} fill={color} opacity="0.14" />
      <path d={line.path} fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function FocusChart({ title, subtitle, values, kind, color, dateRange, rangeKey }) {
  const width = 920
  const height = 360

  if (!Array.isArray(values) || values.length < 2) {
    return (
      <div className="rl-stock-focus-chart-empty">
        <p>No chart data yet</p>
        <span>Pick a ticker from quick switches above.</span>
      </div>
    )
  }

  const minVal = Math.min(...values)
  const maxVal = Math.max(...values)

  if (kind === 'bars') {
    const bars = barsGeometry(values, width, height, 28)
    return (
      <div className="rl-stock-focus-chart-shell">
        <div className="rl-stock-focus-chart-head">
          <p>{title}</p>
          <span>{subtitle}</span>
        </div>
        <svg viewBox={`0 0 ${width} ${height}`} className="rl-stock-focus-svg" aria-hidden="true">
          {[0.2, 0.4, 0.6, 0.8].map((ratio) => (
            <line
              key={ratio}
              x1="28"
              x2={width - 24}
              y1={(height - 28) * ratio + 8}
              y2={(height - 28) * ratio + 8}
              stroke="rgba(148, 163, 184, 0.2)"
              strokeWidth="1"
            />
          ))}
          {bars.bars.map((bar, idx) => (
            <rect
              key={`${idx}-${bar.x}`}
              x={bar.x}
              y={bar.y}
              width={bar.w}
              height={bar.h}
              rx="2"
              fill={color}
              opacity="0.9"
            />
          ))}
        </svg>
        <div className="rl-stock-focus-foot">
          <span>{dateRange?.start || '—'}</span>
          <span>{rangeKey}</span>
          <span>{dateRange?.end || '—'}</span>
        </div>
      </div>
    )
  }

  const line = lineGeometry(values, width, height, 28)
  const lastPoint = line.points[line.points.length - 1]

  return (
    <div className="rl-stock-focus-chart-shell">
      <div className="rl-stock-focus-chart-head">
        <p>{title}</p>
        <span>{subtitle}</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} className="rl-stock-focus-svg" aria-hidden="true">
        {[0.2, 0.4, 0.6, 0.8].map((ratio) => (
          <line
            key={ratio}
            x1="28"
            x2={width - 24}
            y1={(height - 28) * ratio + 8}
            y2={(height - 28) * ratio + 8}
            stroke="rgba(148, 163, 184, 0.2)"
            strokeWidth="1"
          />
        ))}
        <path d={line.areaPath} fill={color} opacity="0.12" />
        <path d={line.path} fill="none" stroke={color} strokeWidth="2.8" strokeLinecap="round" strokeLinejoin="round" />
        {lastPoint ? (
          <>
            <circle cx={lastPoint.x} cy={lastPoint.y} r="4.7" fill={color} stroke="#ffffff" strokeWidth="2" />
            <line
              x1={lastPoint.x}
              x2={lastPoint.x}
              y1={lastPoint.y + 10}
              y2={height - 22}
              stroke={color}
              strokeOpacity="0.25"
              strokeWidth="1.2"
              strokeDasharray="4 3"
            />
          </>
        ) : null}
      </svg>
      <div className="rl-stock-focus-foot">
        <span>{dateRange?.start || '—'}</span>
        <span>
          Min {fmtSigned(minVal)} · Max {fmtSigned(maxVal)}
        </span>
        <span>{dateRange?.end || '—'}</span>
      </div>
    </div>
  )
}

export default function StockPage() {
  const { config } = useGlobalConfig()

  const [selectedTicker, setSelectedTicker] = useState('AAPL')
  const [tickerInput, setTickerInput] = useState('')
  const [watchlist, setWatchlist] = useState(DEFAULT_TICKERS)
  const [bundleMap, setBundleMap] = useState({})
  const [loadingTicker, setLoadingTicker] = useState('')
  const [error, setError] = useState('')
  const [statusHint, setStatusHint] = useState('')
  const [rangeKey, setRangeKey] = useState('3M')
  const [activeChart, setActiveChart] = useState('price')
  const [filingSummaryMap, setFilingSummaryMap] = useState({})
  const [filingLoading, setFilingLoading] = useState(false)
  const initializedRef = useRef(false)

  const upsertBundle = useCallback((ticker, data, savedAt = Date.now(), source = 'live') => {
    const sym = normalizeTicker(ticker)
    if (!sym || !data || typeof data !== 'object') return
    setBundleMap((prev) => ({
      ...prev,
      [sym]: { data, savedAt, source },
    }))
  }, [])

  const rememberTicker = useCallback(
    (ticker) => {
      const sym = normalizeTicker(ticker)
      if (!sym) return
      writeLastTicker(sym)
      const next = mergeTickers([sym], readRecentTickers(), watchlist, DEFAULT_TICKERS).slice(0, 10)
      writeRecentTickers(next)
      setWatchlist(next)
    },
    [watchlist],
  )

  const fetchBundle = useCallback(
    async (rawTicker, options = {}) => {
      const sym = normalizeTicker(rawTicker)
      if (!sym) return null
      const { preferCache = false, silent = false, skipIfFresh = false, force = false } = options

      let hasCached = false
      let cachedPayload = null
      if (preferCache) {
        const cached = readBundleCache(sym)
        if (cached?.data) {
          hasCached = true
          cachedPayload = cached
          upsertBundle(sym, cached.data, cached.savedAt, 'cache')
          setStatusHint(buildBundleHint(cached.data, 'cache'))
          if (!force && skipIfFresh && !isBundleStale(cached.savedAt)) {
            setError('')
            return cached.data
          }
        }
      }

      if (!silent) setLoadingTicker(sym)

      try {
        const res = await get(`/api/stock/quote?ticker=${encodeURIComponent(sym)}`)
        const payload = res?.data || null
        if (!payload || typeof payload !== 'object') throw new Error('No stock payload returned')

        writeBundleCache(sym, payload)
        upsertBundle(sym, payload, Date.now(), 'live')
        rememberTicker(sym)
        setError('')
        setStatusHint(buildBundleHint(payload, 'live'))
        return payload
      } catch (e) {
        if (!hasCached) {
          setError(e.message || `Failed to load ${sym}`)
          setStatusHint('')
        } else if (cachedPayload?.data) {
          setStatusHint(buildBundleHint({ ...cachedPayload.data, warning: e.message || 'refresh failed' }, 'cache'))
        }
        return null
      } finally {
        if (!silent) {
          setLoadingTicker((prev) => (prev === sym ? '' : prev))
        }
      }
    },
    [rememberTicker, upsertBundle],
  )

  useEffect(() => {
    const cfgTicker = normalizeTicker(config.ticker)

    if (!initializedRef.current) {
      initializedRef.current = true
      const last = readLastTicker()
      const recent = readRecentTickers()
      const merged = mergeTickers([last, cfgTicker], recent, DEFAULT_TICKERS).slice(0, 10)
      const startTicker = normalizeTicker(last || cfgTicker || merged[0] || 'AAPL')

      setWatchlist(merged)
      setSelectedTicker(startTicker)
      setTickerInput(startTicker)

      merged.forEach((tk) => {
        const cached = readBundleCache(tk)
        if (cached?.data) {
          upsertBundle(tk, cached.data, cached.savedAt, 'cache')
        }
      })
      return
    }

    if (cfgTicker) {
      setWatchlist((prev) => mergeTickers([cfgTicker], prev, DEFAULT_TICKERS).slice(0, 10))
    }
  }, [config.ticker, upsertBundle])

  useEffect(() => {
    if (!selectedTicker) return
    fetchBundle(selectedTicker, { preferCache: true, silent: false, skipIfFresh: true })
  }, [selectedTicker, fetchBundle])

  const selectedEntry = bundleMap[selectedTicker] || null
  const data = selectedEntry?.data || null

  const chartRows = useMemo(() => clipHistory(data?.history || [], rangeKey), [data?.history, rangeKey])

  const closeValues = useMemo(() => numericSeries(chartRows, 'close'), [chartRows])
  const volumeValues = useMemo(() => numericSeries(chartRows, 'volume'), [chartRows])
  const returnValues = useMemo(() => returnSeries(closeValues), [closeValues])
  const drawdownValues = useMemo(() => drawdownSeries(closeValues), [closeValues])

  const dateRange = useMemo(() => {
    if (!chartRows.length) return { start: '', end: '' }
    return {
      start: chartRows[0].date || '',
      end: chartRows[chartRows.length - 1].date || '',
    }
  }, [chartRows])

  const chartDefs = useMemo(() => {
    const lastClose = closeValues.length ? closeValues[closeValues.length - 1] : null
    const lastVol = volumeValues.length ? volumeValues[volumeValues.length - 1] : null
    const lastRet = returnValues.length ? returnValues[returnValues.length - 1] : null
    const lastDd = drawdownValues.length ? drawdownValues[drawdownValues.length - 1] : null

    return [
      {
        key: 'price',
        title: 'Price Trend',
        subtitle: 'Close (USD)',
        value: fmtPrice(lastClose),
        series: closeValues,
        kind: 'line',
        color: chartColorFor(closeValues, '#2563eb', '#ef4444'),
      },
      {
        key: 'volume',
        title: 'Trading Volume',
        subtitle: 'Shares traded',
        value: fmtCompact(lastVol),
        series: volumeValues,
        kind: 'bars',
        color: '#0ea5e9',
      },
      {
        key: 'return',
        title: 'Cumulative Return',
        subtitle: 'vs first point in range',
        value: fmtPct(lastRet),
        series: returnValues,
        kind: 'line',
        color: chartColorFor(returnValues, '#16a34a', '#ef4444'),
      },
      {
        key: 'drawdown',
        title: 'Drawdown',
        subtitle: 'From rolling high',
        value: fmtPct(lastDd),
        series: drawdownValues,
        kind: 'line',
        color: '#f59e0b',
      },
    ]
  }, [closeValues, volumeValues, returnValues, drawdownValues])

  const activeDef = chartDefs.find((def) => def.key === activeChart) || chartDefs[0]

  const selectedCompanyQuery = useMemo(() => buildCompanyQuery(data?.name || ''), [data?.name])
  const selectedDisplayName = String(data?.name || selectedTicker || '').trim()

  useEffect(() => {
    if (!selectedCompanyQuery) return
    if (filingSummaryMap[selectedCompanyQuery]) return

    let alive = true
    setFilingLoading(true)

    get(`/api/records?company=${encodeURIComponent(selectedCompanyQuery)}&include_result=1`)
      .then((res) => {
        if (!alive) return
        const items = Array.isArray(res?.items) ? res.items : []
        const matched = matchRecordsToCompany(items, selectedDisplayName)
        const summary = buildFilingSummary(matched)
        setFilingSummaryMap((prev) => ({
          ...prev,
          [selectedCompanyQuery]: summary,
        }))
      })
      .catch(() => {
        if (!alive) return
        setFilingSummaryMap((prev) => ({
          ...prev,
          [selectedCompanyQuery]: {
            count: 0,
            years: [],
            latest: null,
            avgRiskItems: 0,
            avgCategories: 0,
            byYear: [],
            recent: [],
          },
        }))
      })
      .finally(() => {
        if (!alive) return
        setFilingLoading(false)
      })

    return () => {
      alive = false
    }
  }, [selectedCompanyQuery, filingSummaryMap, selectedDisplayName])

  const filingSummary = selectedCompanyQuery ? filingSummaryMap[selectedCompanyQuery] : null

  const submitTicker = () => {
    const next = normalizeTicker(tickerInput)
    if (!next) return
    setSelectedTicker(next)
    setTickerInput(next)
    setWatchlist((prev) => mergeTickers([next], prev, DEFAULT_TICKERS).slice(0, 10))
  }

  const refreshSelected = () => {
    if (!selectedTicker) return
    fetchBundle(selectedTicker, { preferCache: true, silent: false, force: true })
  }

  return (
    <div className="rl-page-shell rl-up-page rl-stock-page">
      <section className="rl-up-header">
        <div className="page-header !mb-0">
          <div className="page-header-left rl-up-title-block">
            <span className="page-icon">💹</span>
            <div>
              <p className="page-title">Stock</p>
              <p className="page-subtitle">Market view with 10-K filing risk context and fast ticker switching</p>
            </div>
          </div>
          <button className="btn-secondary" onClick={refreshSelected} disabled={loadingTicker === selectedTicker}>
            {loadingTicker === selectedTicker ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      <section className="rl-stock-command">
        <div className="rl-stock-command-row">
          <label className="section-title">Ticker</label>
          <div className="rl-stock-input-row">
            <input
              className="input"
              value={tickerInput}
              onChange={(e) => setTickerInput(normalizeTicker(e.target.value))}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submitTicker()
              }}
              placeholder="e.g. AAPL"
            />
            <button className="btn-primary" onClick={submitTicker}>
              Open
            </button>
          </div>
        </div>
        <div className="rl-stock-chip-row">
          {watchlist.map((tk) => {
            const entry = bundleMap[tk]
            const payload = entry?.data || null
            const pct = Number(payload?.change_percent)
            const tone = Number.isFinite(pct) ? (pct >= 0 ? 'up' : 'down') : 'flat'
            return (
              <button
                key={tk}
                className={`rl-stock-chip ${selectedTicker === tk ? 'active' : ''}`}
                onClick={() => {
                  setSelectedTicker(tk)
                  setTickerInput(tk)
                }}
              >
                <span>{tk}</span>
                <em className={tone}>{Number.isFinite(pct) ? fmtPct(pct) : '—'}</em>
              </button>
            )
          })}
        </div>
        <p className="rl-stock-cache-note">
          {selectedEntry?.savedAt ? `Instant view from cache (${timeAgoFrom(selectedEntry.savedAt)}), then auto refresh.` : 'Loading data and caching for faster next visit.'}
        </p>
        {statusHint ? <p className="rl-stock-cache-note rl-stock-status-note">{statusHint}</p> : null}
      </section>

      {error ? <div className="rl-up-inline-error">{error}</div> : null}

      <section className="rl-stock-metrics-grid">
        <div className="metric-card rl-stock-metric-card">
          <p className="metric-label">Ticker</p>
          <p className="metric-value">{selectedTicker || '—'}</p>
          <span className="rl-stock-metric-sub">{data?.exchange || 'US Equities'}</span>
        </div>
        <div className="metric-card rl-stock-metric-card">
          <p className="metric-label">Current Price</p>
          <p className="metric-value">{fmtPrice(data?.price)}</p>
          <span className="rl-stock-metric-sub">{data?.name || '—'}</span>
        </div>
        <div className="metric-card rl-stock-metric-card">
          <p className="metric-label">Today</p>
          <p className={`metric-value ${Number(data?.change_percent || 0) >= 0 ? 'rl-stock-up' : 'rl-stock-down'}`}>
            {fmtPct(data?.change_percent)}
          </p>
          <span className="rl-stock-metric-sub">Change {fmtPrice(data?.change)}</span>
        </div>
        <div className="metric-card rl-stock-metric-card">
          <p className="metric-label">Market Cap</p>
          <p className="metric-value !text-[1.05rem]">{fmtCompact(data?.market_cap)}</p>
          <span className="rl-stock-metric-sub">PE {data?.pe_ratio ? Number(data.pe_ratio).toFixed(2) : '—'}</span>
        </div>
        <div className="metric-card rl-stock-metric-card">
          <p className="metric-label">52W Range</p>
          <p className="metric-value !text-[1rem]">
            {fmtPrice(data?.low_52)} - {fmtPrice(data?.high_52)}
          </p>
          <span className="rl-stock-metric-sub">Range watch</span>
        </div>
      </section>

      <section className="rl-stock-workbench">
        <div className="rl-stock-left">
          <div className="rl-stock-range-row">
            <label className="section-title">Time Range</label>
            <div className="rl-segment">
              {RANGE_OPTIONS.map((key) => (
                <button key={key} className={rangeKey === key ? 'active' : ''} onClick={() => setRangeKey(key)}>
                  {key}
                </button>
              ))}
            </div>
          </div>

          <div className="rl-stock-chart-grid">
            {chartDefs.map((def) => (
              <button
                key={def.key}
                className={`rl-stock-chart-tile ${activeChart === def.key ? 'active' : ''}`}
                onClick={() => setActiveChart(def.key)}
              >
                <div className="rl-stock-chart-tile-top">
                  <p>{def.title}</p>
                  <span>{def.value}</span>
                </div>
                <small>{def.subtitle}</small>
                <MiniChart values={def.series} kind={def.kind} color={def.color} />
              </button>
            ))}
          </div>

          <div className="rl-stock-focus-card">
            <FocusChart
              title={`${activeDef?.title || 'Chart'} · ${selectedTicker}`}
              subtitle={`${selectedDisplayName || selectedTicker} (${rangeKey})`}
              values={activeDef?.series || []}
              kind={activeDef?.kind || 'line'}
              color={activeDef?.color || '#2563eb'}
              dateRange={dateRange}
              rangeKey={rangeKey}
            />
          </div>
        </div>

        <aside className="rl-stock-side">
          <section className="rl-stock-side-card">
            <div className="rl-stock-side-head">
              <p>10-K Filing Signals</p>
              <span>{selectedCompanyQuery ? `match: ${selectedCompanyQuery}` : 'no company match'}</span>
            </div>

            {filingLoading ? <p className="rl-stock-muted">Loading filing context…</p> : null}

            {!filingLoading && filingSummary ? (
              <>
                <div className="rl-stock-side-metrics">
                  <div>
                    <span>Filings</span>
                    <strong>{filingSummary.count}</strong>
                  </div>
                  <div>
                    <span>Years</span>
                    <strong>{filingSummary.years.length}</strong>
                  </div>
                  <div>
                    <span>Avg Risk Items</span>
                    <strong>{filingSummary.count ? Math.round(filingSummary.avgRiskItems) : '—'}</strong>
                  </div>
                  <div>
                    <span>Latest Year</span>
                    <strong>{filingSummary.latest?.year || '—'}</strong>
                  </div>
                </div>

                <div className="rl-stock-side-list">
                  {(filingSummary.recent || []).map((rec) => (
                    <div key={rec.record_id || `${rec.company}-${rec.year}`} className="rl-stock-side-item">
                      <p>{rec.company || 'Unknown company'}</p>
                      <span>
                        {rec.year || '—'} · {rec.filing_type || '10-K'} · risks {Number(rec.risk_items || 0)}
                      </span>
                    </div>
                  ))}

                  {!filingSummary.recent?.length ? <p className="rl-stock-muted">No linked filing records yet.</p> : null}
                </div>
              </>
            ) : null}
          </section>

          <section className="rl-stock-side-card">
            <div className="rl-stock-side-head">
              <p>Quick Actions</p>
              <span>Jump to deeper analysis</span>
            </div>
            <div className="rl-stock-action-grid">
              <Link to={`/compare?company=${encodeURIComponent(filingSummary?.latest?.company || '')}&year=${encodeURIComponent(String(filingSummary?.latest?.year || ''))}`} className="btn-secondary w-full">
                ⚖️ Open Compare
              </Link>
              <Link to="/upload" className="btn-secondary w-full">
                🗂️ Open Filings
              </Link>
              <Link to={`/news?ticker=${encodeURIComponent(selectedTicker || '')}&company=${encodeURIComponent(selectedDisplayName || '')}`} className="btn-secondary w-full">
                📰 Open News
              </Link>
            </div>
          </section>
        </aside>
      </section>
    </div>
  )
}
