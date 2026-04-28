import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { get } from '../lib/api'
import { useGlobalConfig } from '../lib/globalConfig'

const DEFAULT_TICKERS = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL']
const RANGE_OPTIONS = ['1W', '1M', '3M', '6M', '1Y']
const RANGE_SIZE = { '1W': 5, '1M': 22, '3M': 66, '6M': 132, '1Y': 252 }
const MINI_CARD_RANGE = '3M'
const TABLE_SECTIONS = [
  { key: 'income_statement', label: 'Income Statement' },
  { key: 'comprehensive_income', label: 'Comprehensive Income' },
  { key: 'balance_sheet', label: 'Balance Sheet' },
  { key: 'shareholders_equity', label: "Shareholders' Equity" },
  { key: 'cash_flow', label: 'Cash Flow' },
]

const STOCK_LAST_TICKER_KEY = 'rl_stock_last_ticker_v1'
const STOCK_RECENT_TICKERS_KEY = 'rl_stock_recent_tickers_v1'
const STOCK_BUNDLE_PREFIX = 'rl_stock_bundle_v1_'
const STOCK_BUNDLE_TTL_MS = 1000 * 60 * 60 * 12

const LOGO_DOMAIN_BY_TICKER = {
  AAPL: 'apple.com',
  MSFT: 'microsoft.com',
  NVDA: 'nvidia.com',
  AMZN: 'amazon.com',
  GOOGL: 'google.com',
  GOOG: 'google.com',
  META: 'meta.com',
  TSLA: 'tesla.com',
  NFLX: 'netflix.com',
  ORCL: 'oracle.com',
  IBM: 'ibm.com',
  INTC: 'intel.com',
  AMD: 'amd.com',
  AVGO: 'broadcom.com',
  ADBE: 'adobe.com',
  CSCO: 'cisco.com',
  QCOM: 'qualcomm.com',
  SAP: 'sap.com',
  JPM: 'jpmorganchase.com',
  BAC: 'bankofamerica.com',
  WFC: 'wellsfargo.com',
  C: 'citigroup.com',
  V: 'visa.com',
  MA: 'mastercard.com',
  'BRK.B': 'berkshirehathaway.com',
  WMT: 'walmart.com',
  COST: 'costco.com',
  PG: 'pg.com',
  KO: 'coca-colacompany.com',
  PEP: 'pepsico.com',
  MCD: 'mcdonalds.com',
  NKE: 'nike.com',
  XOM: 'exxonmobil.com',
  CVX: 'chevron.com',
  BA: 'boeing.com',
  CAT: 'cat.com',
  GE: 'ge.com',
  UNH: 'unitedhealthgroup.com',
  JNJ: 'jnj.com',
  PFE: 'pfizer.com',
  LLY: 'lilly.com',
  MRK: 'merck.com',
  TMO: 'thermofisher.com',
  ABBV: 'abbvie.com',
  DIS: 'disney.com',
  CMCSA: 'corporate.comcast.com',
  T: 'att.com',
  VZ: 'verizon.com',
  TMUS: 't-mobile.com',
  AAL: 'aa.com',
  UAL: 'united.com',
  DAL: 'delta.com',
  AIR: 'airbus.com',
}

const SECTOR_BY_TICKER = {
  AAPL: 'Technology',
  MSFT: 'Technology',
  NVDA: 'Technology',
  AMD: 'Technology',
  INTC: 'Technology',
  QCOM: 'Technology',
  CSCO: 'Technology',
  ORCL: 'Technology',
  META: 'Communication Services',
  GOOGL: 'Communication Services',
  GOOG: 'Communication Services',
  NFLX: 'Communication Services',
  CMCSA: 'Communication Services',
  T: 'Communication Services',
  VZ: 'Communication Services',
  TMUS: 'Communication Services',
  AMZN: 'Consumer Cyclical',
  TSLA: 'Consumer Cyclical',
  MCD: 'Consumer Cyclical',
  NKE: 'Consumer Cyclical',
  WMT: 'Consumer Defensive',
  COST: 'Consumer Defensive',
  PG: 'Consumer Defensive',
  KO: 'Consumer Defensive',
  PEP: 'Consumer Defensive',
  JPM: 'Financial Services',
  BAC: 'Financial Services',
  WFC: 'Financial Services',
  C: 'Financial Services',
  V: 'Financial Services',
  MA: 'Financial Services',
  'BRK.B': 'Financial Services',
  XOM: 'Energy',
  CVX: 'Energy',
  BA: 'Industrials',
  CAT: 'Industrials',
  GE: 'Industrials',
  UNH: 'Healthcare',
  JNJ: 'Healthcare',
  PFE: 'Healthcare',
  LLY: 'Healthcare',
  MRK: 'Healthcare',
  TMO: 'Healthcare',
  ABBV: 'Healthcare',
}

const EQUITY_SECTOR_BENCHMARKS = [
  { industry: 'Technology', ticker: 'XLK' },
  { industry: 'Energy', ticker: 'XLE' },
  { industry: 'Consumer Cyclical', ticker: 'XLY' },
  { industry: 'Consumer Defensive', ticker: 'XLP' },
  { industry: 'Communication Services', ticker: 'XLC' },
  { industry: 'Industrials', ticker: 'XLI' },
  { industry: 'Financial Services', ticker: 'XLF' },
  { industry: 'Utilities', ticker: 'XLU' },
  { industry: 'Basic Materials', ticker: 'XLB' },
  { industry: 'Real Estate', ticker: 'XLRE' },
  { industry: 'Healthcare', ticker: 'XLV' },
]

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
    // ignore
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
    // ignore
  }
}

function readRecentTickers() {
  const raw = readLocalJson(STOCK_RECENT_TICKERS_KEY, [])
  if (!Array.isArray(raw)) return []
  return mergeTickers(raw)
}

function writeRecentTickers(list) {
  writeLocalJson(STOCK_RECENT_TICKERS_KEY, mergeTickers(list).slice(0, 12))
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
  return { savedAt: Number.isFinite(savedAt) ? savedAt : 0, data }
}

function writeBundleCache(ticker, data) {
  if (!ticker || !data || typeof data !== 'object') return
  writeLocalJson(cacheKeyForTicker(ticker), { saved_at: Date.now(), data })
}

function isBundleStale(savedAt) {
  if (!Number.isFinite(savedAt) || savedAt <= 0) return true
  return Date.now() - savedAt > STOCK_BUNDLE_TTL_MS
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
  return `${Math.floor(hours / 24)}d ago`
}

function fmtPrice(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `$${n.toFixed(2)}`
}

function fmtPct(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

function fmtPctPlain(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${n.toFixed(2)}%`
}

function fmtSigned(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`
}

function fmtCompact(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  const abs = Math.abs(n)
  if (abs >= 1_000_000_000_000) return `${(n / 1_000_000_000_000).toFixed(2)}T`
  if (abs >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(2)}B`
  if (abs >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`
  if (abs >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString()
}

function fmtWhole(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return Math.round(n).toLocaleString()
}

function fmtYield(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  const pct = Math.abs(n) <= 1 ? n * 100 : n
  return `${pct.toFixed(2)}%`
}

function fmtRange(a, b, formatter = fmtPrice) {
  const left = formatter(a)
  const right = formatter(b)
  if (left === '—' && right === '—') return '—'
  return `${left} - ${right}`
}

function fmtDateOnly(value) {
  const raw = String(value || '').trim()
  if (!raw) return '—'
  const direct = new Date(raw)
  if (!Number.isNaN(direct.getTime())) return direct.toLocaleDateString()
  const numeric = Number(value)
  if (Number.isFinite(numeric) && numeric > 0) {
    const ms = numeric > 1e12 ? numeric : numeric * 1000
    const d = new Date(ms)
    if (!Number.isNaN(d.getTime())) return d.toLocaleDateString()
  }
  return raw
}

function fmtDateTime(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return '—'
  const ms = numeric > 1e12 ? numeric : numeric * 1000
  const d = new Date(ms)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString()
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

  if (warning && fromCache) return `Rate-limited refresh, showing cache. Quote: ${quoteSource} · History: ${historySource}`
  if (warning) return `${warning} Quote: ${quoteSource} · History: ${historySource}`
  if (fromCache) return `Cached data active. Quote: ${quoteSource} · History: ${historySource}`
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
  return normalized.split(' ').filter(Boolean).slice(0, 2).join(' ')
}

function clipHistory(history, key) {
  const rows = (Array.isArray(history) ? history : [])
    .map((row) => ({
      date: String(row?.date || ''),
      close: Number(row?.close),
      open: Number(row?.open),
      high: Number(row?.high),
      low: Number(row?.low),
      volume: Number(row?.volume || 0),
    }))
    .filter((row) => row.date && Number.isFinite(row.close))

  if (!rows.length) return []
  const size = RANGE_SIZE[key] || RANGE_SIZE['1M']
  return rows.length <= size ? rows : rows.slice(-size)
}

function numericSeries(history, key) {
  return history.map((row) => Number(row?.[key])).filter((v) => Number.isFinite(v))
}

function chartColorFor(values, up = '#16a34a', down = '#ef4444') {
  if (!Array.isArray(values) || values.length < 2) return '#2563eb'
  return Number(values[values.length - 1]) >= Number(values[0]) ? up : down
}

function lineGeometry(values, width, height, padding = 12) {
  if (!Array.isArray(values) || !values.length) return { path: '', areaPath: '', points: [], min: 0, max: 0 }
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(1e-6, max - min)
  const innerW = Math.max(1, width - padding * 2)
  const innerH = Math.max(1, height - padding * 2)

  const points = values.map((v, i) => ({
    x: padding + (values.length <= 1 ? 0 : (innerW * i) / (values.length - 1)),
    y: padding + innerH - ((v - min) / span) * innerH,
    v,
  }))

  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join(' ')
  const first = points[0]
  const last = points[points.length - 1]
  const areaPath = `${path} L ${last.x.toFixed(2)} ${(height - padding).toFixed(2)} L ${first.x.toFixed(2)} ${(height - padding).toFixed(2)} Z`
  return { path, areaPath, points, min, max }
}

function barsGeometry(values, width, height, padding = 12) {
  if (!Array.isArray(values) || !values.length) return { bars: [] }
  const max = Math.max(...values, 0)
  const maxSafe = Math.max(1, max)
  const innerW = Math.max(1, width - padding * 2)
  const innerH = Math.max(1, height - padding * 2)
  const slotW = innerW / values.length
  const barW = Math.max(1.2, slotW * 0.66)

  const bars = values.map((v, i) => {
    const h = (Math.max(0, v) / maxSafe) * innerH
    return {
      x: padding + i * slotW + (slotW - barW) / 2,
      y: padding + innerH - h,
      w: barW,
      h,
    }
  })
  return { bars }
}

function buildUploadedCompanies(items) {
  const rows = Array.isArray(items) ? items : []
  const tickerByCompanyKey = {}
  rows.forEach((r) => {
    const company = String(r?.company || '').trim()
    const ticker = normalizeTicker(r?.ticker)
    if (!company || !ticker) return
    const key = sanitizeCompanyName(company)
    if (!key || tickerByCompanyKey[key]) return
    tickerByCompanyKey[key] = ticker
  })

  const sorted = [...rows].sort((a, b) => String(b?.created_at || '').localeCompare(String(a?.created_at || '')))
  const seen = new Set()
  const out = []
  sorted.forEach((r) => {
    const company = String(r?.company || '').trim()
    const companyKey = sanitizeCompanyName(company)
    const ticker = normalizeTicker(r?.ticker || tickerByCompanyKey[companyKey] || '')
    if (!company || !ticker) return
    const key = `${companyKey}::${ticker}`
    if (seen.has(key)) return
    seen.add(key)
    out.push({
      company,
      ticker,
      industry: String(r?.industry || '').trim() || 'Other',
      year: Number(r?.year) || null,
      record_id: String(r?.record_id || ''),
      created_at: String(r?.created_at || ''),
    })
  })
  return out
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
  return rows.filter((r) => {
    const cTokens = sanitizeCompanyName(r?.company).split(' ').filter(Boolean)
    const overlap = cTokens.filter((t) => targetTokens.includes(t)).length
    return overlap >= Math.min(2, targetTokens.length)
  })
}

function buildFilingSummary(items) {
  const rows = Array.isArray(items) ? items : []
  const sorted = [...rows].sort((a, b) => String(b?.created_at || '').localeCompare(String(a?.created_at || '')))
  const years = Array.from(new Set(sorted.map((r) => Number(r?.year)).filter(Number.isFinite))).sort((a, b) => b - a)
  const riskItems = sorted.map((r) => Number(r?.risk_items || 0)).filter(Number.isFinite)
  const categories = sorted.map((r) => Number(r?.risk_categories || 0)).filter(Number.isFinite)

  const avgRiskItems = riskItems.length ? riskItems.reduce((a, b) => a + b, 0) / riskItems.length : 0
  const avgCategories = categories.length ? categories.reduce((a, b) => a + b, 0) / categories.length : 0

  return {
    count: sorted.length,
    years,
    latest: sorted[0] || null,
    avgRiskItems,
    avgCategories,
    recent: sorted.slice(0, 5),
  }
}

function initialsFor(name, ticker) {
  const words = String(name || '').trim().split(/\s+/).filter(Boolean)
  if (words.length >= 2) return `${words[0][0] || ''}${words[1][0] || ''}`.toUpperCase()
  if (words.length === 1 && words[0].length >= 2) return words[0].slice(0, 2).toUpperCase()
  return String(ticker || '').slice(0, 2).toUpperCase() || 'ST'
}

function normalizeCompanyRoot(raw) {
  let s = String(raw || '').trim().toLowerCase()
  if (!s) return ''
  s = s.replace(/[.,()']/g, ' ')
  s = s.replace(/\b(inc|incorporated|corp|corporation|company|co|ltd|limited|plc|holdings?|group|class [ab])\b/g, ' ')
  s = s.replace(/\s+/g, ' ').trim()
  const token = s.split(' ').filter(Boolean)[0] || ''
  return token.replace(/[^a-z0-9-]/g, '')
}

function logoCandidates(ticker, companyName) {
  const sym = normalizeTicker(ticker)
  const domains = []
  const mappedDomain = LOGO_DOMAIN_BY_TICKER[sym]
  if (mappedDomain) domains.push(mappedDomain)

  const root = normalizeCompanyRoot(companyName)
  if (root && root.length >= 3) domains.push(`${root}.com`)

  const uniq = Array.from(new Set(domains))
  const urls = []
  uniq.forEach((domain) => {
    urls.push(`https://logo.clearbit.com/${domain}`)
    urls.push(`https://www.google.com/s2/favicons?domain=${encodeURIComponent(domain)}&sz=128`)
  })
  return urls
}

function normalizeSectorName(raw) {
  const text = String(raw || '').trim()
  if (!text) return ''
  const lower = text.toLowerCase()
  const replacements = [
    ['information technology', 'Technology'],
    ['technology', 'Technology'],
    ['communication services', 'Communication Services'],
    ['communications', 'Communication Services'],
    ['consumer discretionary', 'Consumer Cyclical'],
    ['consumer cyclical', 'Consumer Cyclical'],
    ['consumer defensive', 'Consumer Defensive'],
    ['consumer staples', 'Consumer Defensive'],
    ['financials', 'Financial Services'],
    ['financial services', 'Financial Services'],
    ['health care', 'Healthcare'],
    ['healthcare', 'Healthcare'],
    ['energy', 'Energy'],
    ['industrials', 'Industrials'],
    ['industrial', 'Industrials'],
    ['utilities', 'Utilities'],
    ['real estate', 'Real Estate'],
    ['materials', 'Basic Materials'],
    ['basic materials', 'Basic Materials'],
  ]
  const found = replacements.find(([k]) => lower.includes(k))
  if (found) return found[1]
  return text
}

function inferSectorFromName(companyName = '') {
  const c = String(companyName || '').toLowerCase()
  if (!c) return ''
  if (/(bank|capital|financial|insurance|asset|trust|credit)/.test(c)) return 'Financial Services'
  if (/(health|pharma|therapeutics|medical|biotech)/.test(c)) return 'Healthcare'
  if (/(energy|oil|gas|petro)/.test(c)) return 'Energy'
  if (/(software|semiconductor|micro|tech|cloud|systems|electronics)/.test(c)) return 'Technology'
  if (/(media|communications|telecom|wireless|internet)/.test(c)) return 'Communication Services'
  if (/(retail|consumer|restaurant|auto|apparel|travel)/.test(c)) return 'Consumer Cyclical'
  if (/(beverage|food|grocery|household)/.test(c)) return 'Consumer Defensive'
  if (/(industrial|machinery|aerospace|airlines|logistics)/.test(c)) return 'Industrials'
  return ''
}

function resolveEquitySector({ filingIndustry, quoteSector, ticker, company }) {
  const filing = normalizeSectorName(filingIndustry)
  if (filing && filing.toLowerCase() !== 'other') return filing

  const quote = normalizeSectorName(quoteSector)
  if (quote && quote.toLowerCase() !== 'other') return quote

  const mapped = normalizeSectorName(SECTOR_BY_TICKER[normalizeTicker(ticker)])
  if (mapped) return mapped

  const inferred = inferSectorFromName(company)
  if (inferred) return inferred

  return 'Other'
}

function CompanyLogo({ ticker, company }) {
  const [cursor, setCursor] = useState(0)
  const candidates = useMemo(() => logoCandidates(ticker, company), [ticker, company])
  const src = candidates[cursor] || ''

  useEffect(() => {
    setCursor(0)
  }, [ticker, company])

  return (
    <div className="rl-stock-logo" aria-hidden="true">
      {src ? (
        <img
          key={`${ticker}-${cursor}`}
          className="rl-stock-logo-img"
          src={src}
          alt=""
          loading="lazy"
          onError={() => setCursor((idx) => idx + 1)}
        />
      ) : (
        <span className="rl-stock-logo-fallback">{initialsFor(company, ticker)}</span>
      )}
    </div>
  )
}

function toneClass(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 'flat'
  if (n > 0) return 'up'
  if (n < 0) return 'down'
  return 'flat'
}

function MiniChart({ values, kind, color, compact = true }) {
  const width = compact ? 320 : 360
  const height = compact ? 116 : 132

  if (!Array.isArray(values) || values.length < 2) {
    return (
      <svg viewBox={`0 0 ${width} ${height}`} className={`rl-stock-mini-svg ${compact ? '' : 'large'}`} aria-hidden="true">
        <text x="8" y={compact ? '42' : '66'} className="rl-stock-mini-empty">No data</text>
      </svg>
    )
  }

  if (kind === 'bars') {
    const bars = barsGeometry(values, width, height, compact ? 10 : 14)
    return (
      <svg viewBox={`0 0 ${width} ${height}`} className={`rl-stock-mini-svg ${compact ? '' : 'large'}`} aria-hidden="true">
        {bars.bars.map((bar, idx) => (
          <rect key={`${idx}-${bar.x}`} x={bar.x} y={bar.y} width={bar.w} height={bar.h} rx="2" fill={color} opacity="0.86" />
        ))}
      </svg>
    )
  }

  const line = lineGeometry(values, width, height, compact ? 10 : 14)
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={`rl-stock-mini-svg ${compact ? '' : 'large'}`} aria-hidden="true">
      <path d={line.areaPath} fill={color} opacity="0.13" />
      <path d={line.path} fill="none" stroke={color} strokeWidth={compact ? '2.2' : '2.6'} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function FocusChart({
  title,
  subtitle,
  values,
  kind,
  color,
  dateRange,
  rangeKey,
  formal = false,
  rows = [],
  showRangeSelector = false,
  onSelectRange = null,
  hideTitle = false,
}) {
  const [hoverIdx, setHoverIdx] = useState(-1)
  const width = 920
  const height = 360
  const chartRows = Array.isArray(rows) ? rows : []
  const series = Array.isArray(values) && values.length ? values : numericSeries(chartRows, 'close')

  if (!Array.isArray(series) || series.length < 2) {
    return (
      <div className="rl-stock-focus-chart-empty">
        <p>No chart data yet</p>
        <span>Select any company card to populate charts.</span>
      </div>
    )
  }

  const minVal = Math.min(...series)
  const maxVal = Math.max(...series)

  if (kind === 'bars') {
    const bars = barsGeometry(series, width, height, 28)
    return (
      <div className="rl-stock-focus-chart-shell">
        {!hideTitle ? (
          <div className="rl-stock-focus-chart-head">
            <p>{title}</p>
            <span>{subtitle}</span>
          </div>
        ) : null}
        <svg viewBox={`0 0 ${width} ${height}`} className="rl-stock-focus-svg" aria-hidden="true">
          {[0.2, 0.4, 0.6, 0.8].map((ratio) => (
            <line key={ratio} x1="28" x2={width - 24} y1={(height - 28) * ratio + 8} y2={(height - 28) * ratio + 8} stroke={formal ? 'rgba(100, 116, 139, 0.28)' : 'rgba(148, 163, 184, 0.2)'} strokeWidth="1" />
          ))}
          {bars.bars.map((bar, idx) => (
            <rect key={`${idx}-${bar.x}`} x={bar.x} y={bar.y} width={bar.w} height={bar.h} rx="2" fill={color} opacity="0.9" />
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

  const line = lineGeometry(series, width, height, 28)
  const lastPoint = line.points[line.points.length - 1]
  const hasHover = hoverIdx >= 0
  const resolvedHoverIdx = hasHover ? hoverIdx : -1
  const hoveredPoint = hasHover ? line.points[Math.max(0, Math.min(resolvedHoverIdx, line.points.length - 1))] : null
  const hoveredRow = hasHover ? (chartRows[resolvedHoverIdx] || null) : null
  const hoveredValue = Number(hoveredPoint?.v)

  const onPointerMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const xNorm = Math.max(0, Math.min(1, x / Math.max(1, rect.width)))
    const idx = Math.round(xNorm * (line.points.length - 1))
    setHoverIdx(Math.max(0, Math.min(idx, line.points.length - 1)))
  }

  const tooltipLeftPct = hoveredPoint ? (hoveredPoint.x / width) * 100 : 50
  const tooltipTopPct = hoveredPoint ? (hoveredPoint.y / height) * 100 : 12

  return (
    <div className="rl-stock-focus-chart-shell">
      {!hideTitle ? (
        <div className="rl-stock-focus-chart-head">
          <p>{title}</p>
          <span>{subtitle}</span>
        </div>
      ) : null}
      <div className="rl-stock-focus-svg-wrap">
        {showRangeSelector ? (
          <div className="rl-stock-focus-range-overlay">
            <div className="rl-segment rl-segment-inline">
              {RANGE_OPTIONS.map((key) => (
                <button key={key} className={rangeKey === key ? 'active' : ''} onClick={() => onSelectRange?.(key)}>{key}</button>
              ))}
            </div>
          </div>
        ) : null}
        {hasHover && hoveredPoint && hoveredRow ? (
          <div
            className="rl-stock-focus-tooltip"
            style={{
              left: `clamp(128px, ${tooltipLeftPct}%, calc(100% - 132px))`,
              top: `clamp(56px, ${tooltipTopPct}%, calc(100% - 104px))`,
            }}
          >
            <strong>{hoveredRow.date || '—'}</strong>
            <span>Close {fmtPrice(hoveredValue)}</span>
            <em>Open {fmtPrice(hoveredRow.open)} · High {fmtPrice(hoveredRow.high)} · Low {fmtPrice(hoveredRow.low)}</em>
            <em>Volume {fmtCompact(hoveredRow.volume)}</em>
          </div>
        ) : null}
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="rl-stock-focus-svg"
          aria-hidden="true"
          onMouseMove={onPointerMove}
          onMouseLeave={() => setHoverIdx(-1)}
        >
          {[0.2, 0.4, 0.6, 0.8].map((ratio) => (
            <line key={ratio} x1="28" x2={width - 24} y1={(height - 28) * ratio + 8} y2={(height - 28) * ratio + 8} stroke={formal ? 'rgba(100, 116, 139, 0.28)' : 'rgba(148, 163, 184, 0.2)'} strokeWidth="1" />
          ))}
          <path d={line.areaPath} fill={color} opacity={formal ? '0.05' : '0.12'} />
          <path d={line.path} fill="none" stroke={color} strokeWidth={formal ? '2.25' : '2.8'} strokeLinecap="round" strokeLinejoin="round" />
          {hasHover && hoveredPoint ? (
            <>
              <line
                x1={hoveredPoint.x}
                x2={hoveredPoint.x}
                y1={16}
                y2={height - 20}
                stroke={color}
                strokeOpacity="0.32"
                strokeWidth="1.15"
                strokeDasharray="4 4"
              />
              <circle cx={hoveredPoint.x} cy={hoveredPoint.y} r="4.4" fill={color} stroke="#ffffff" strokeWidth="2" />
            </>
          ) : null}
          {!hasHover && !formal && lastPoint ? (
            <>
              <circle cx={lastPoint.x} cy={lastPoint.y} r="4.7" fill={color} stroke="#ffffff" strokeWidth="2" />
              <line x1={lastPoint.x} x2={lastPoint.x} y1={lastPoint.y + 10} y2={height - 22} stroke={color} strokeOpacity="0.25" strokeWidth="1.2" strokeDasharray="4 3" />
            </>
          ) : null}
        </svg>
      </div>
      <div className="rl-stock-focus-foot">
        <span>{dateRange?.start || '—'}</span>
        <span>Min {fmtSigned(minVal)} · Max {fmtSigned(maxVal)}</span>
        <span>{dateRange?.end || '—'}</span>
      </div>
    </div>
  )
}

function makeSpotlightSummary(row, sectorText) {
  const name = row.company || row.name || row.ticker
  const chg = Number(row.change_percent)
  const direction = Number.isFinite(chg) ? (chg >= 0 ? 'rose' : 'fell') : 'moved'
  const pct = Number.isFinite(chg) ? `${Math.abs(chg).toFixed(2)}%` : 'notably'
  const risk = row.riskItems > 0 ? `Latest filing shows ${row.riskItems} risk items.` : 'No filing risk count available yet.'
  return `${name} ${direction} ${pct} in the selected window. ${sectorText} ${risk}`
}

export default function StockPage() {
  const { config } = useGlobalConfig()
  const navigate = useNavigate()
  const { ticker: routeTicker = '' } = useParams()

  const [selectedTicker, setSelectedTicker] = useState('AAPL')
  const [watchlist, setWatchlist] = useState(DEFAULT_TICKERS)
  const [bundleMap, setBundleMap] = useState({})
  const [loadingTicker, setLoadingTicker] = useState('')
  const [error, setError] = useState('')
  const [statusHint, setStatusHint] = useState('')
  const [rangeKey, setRangeKey] = useState('3M')
  const [filingSummaryMap, setFilingSummaryMap] = useState({})
  const [filingLoading, setFilingLoading] = useState(false)
  const [uploadedCompanies, setUploadedCompanies] = useState([])
  const [featuredCompanies, setFeaturedCompanies] = useState([])
  const [recordsLoading, setRecordsLoading] = useState(true)
  const [boardTab, setBoardTab] = useState('gainers')
  const [summaryOpenIdx, setSummaryOpenIdx] = useState(0)
  const [showAddTicker, setShowAddTicker] = useState(false)
  const [addTickerInput, setAddTickerInput] = useState('')
  const [filingRecordsMap, setFilingRecordsMap] = useState({})
  const [detailTablesMap, setDetailTablesMap] = useState({})
  const [detailTableLoading, setDetailTableLoading] = useState(false)
  const [detailTableSection, setDetailTableSection] = useState('income_statement')
  const [detailActiveRecordId, setDetailActiveRecordId] = useState('')
  const [detailMainTab, setDetailMainTab] = useState('overview')
  const [heatmapHover, setHeatmapHover] = useState(null)

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
      const next = mergeTickers([sym], readRecentTickers(), watchlist, DEFAULT_TICKERS).slice(0, 14)
      writeRecentTickers(next)
      setWatchlist(next)
    },
    [watchlist],
  )

  const fetchBundle = useCallback(
    async (rawTicker, options = {}) => {
      const sym = normalizeTicker(rawTicker)
      if (!sym) return null
      const {
        preferCache = false,
        silent = false,
        skipIfFresh = false,
        force = false,
        remember = true,
        muteError = false,
        muteStatus = false,
        lite = false,
      } = options

      let hasCached = false
      let cachedPayload = null
      if (preferCache) {
        const cached = readBundleCache(sym)
        if (cached?.data) {
          hasCached = true
          cachedPayload = cached
          upsertBundle(sym, cached.data, cached.savedAt, 'cache')
          if (!muteStatus) setStatusHint(buildBundleHint(cached.data, 'cache'))
          if (!force && skipIfFresh && !isBundleStale(cached.savedAt)) {
            if (!muteError) setError('')
            return cached.data
          }
        }
      }

      if (!silent) setLoadingTicker(sym)

      try {
        const q = new URLSearchParams({ ticker: sym })
        if (lite) q.set('lite', '1')
        const res = await get(`/api/stock/quote?${q.toString()}`)
        const payload = res?.data || null
        if (!payload || typeof payload !== 'object') throw new Error('No stock payload returned')

        writeBundleCache(sym, payload)
        upsertBundle(sym, payload, Date.now(), 'live')
        if (remember) rememberTicker(sym)
        if (!muteError) setError('')
        if (!muteStatus) setStatusHint(buildBundleHint(payload, 'live'))
        return payload
      } catch (e) {
        if (!hasCached) {
          if (!muteError) setError(e.message || `Failed to load ${sym}`)
          if (!muteStatus) setStatusHint('')
        } else if (cachedPayload?.data) {
          if (!muteStatus) setStatusHint(buildBundleHint({ ...cachedPayload.data, warning: e.message || 'refresh failed' }, 'cache'))
        }
        return null
      } finally {
        if (!silent) setLoadingTicker((prev) => (prev === sym ? '' : prev))
      }
    },
    [rememberTicker, upsertBundle],
  )

  useEffect(() => {
    let alive = true
    setRecordsLoading(true)
    get('/api/records')
      .then((res) => {
        if (!alive) return
        const items = Array.isArray(res?.items) ? res.items : []
        const companies = buildUploadedCompanies(items)
        setUploadedCompanies(companies)
      })
      .catch(() => {
        if (!alive) return
        setUploadedCompanies([])
      })
      .finally(() => {
        if (!alive) return
        setRecordsLoading(false)
      })

    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    const cfgTicker = normalizeTicker(config.ticker)
    if (!initializedRef.current) {
      initializedRef.current = true
      const last = readLastTicker()
      const recent = readRecentTickers()
      const merged = mergeTickers([last, cfgTicker], recent, DEFAULT_TICKERS).slice(0, 14)
      const startTicker = normalizeTicker(last || cfgTicker || merged[0] || 'AAPL')
      setWatchlist(merged)
      setSelectedTicker(startTicker)
      merged.forEach((tk) => {
        const cached = readBundleCache(tk)
        if (cached?.data) upsertBundle(tk, cached.data, cached.savedAt, 'cache')
      })
      return
    }
    if (cfgTicker) {
      setWatchlist((prev) => mergeTickers([cfgTicker], prev, DEFAULT_TICKERS).slice(0, 14))
    }
  }, [config.ticker, upsertBundle])

  useEffect(() => {
    if (!uploadedCompanies.length) return
    const uploadedTickers = uploadedCompanies.map((c) => c.ticker)
    setWatchlist((prev) => mergeTickers(uploadedTickers, prev, DEFAULT_TICKERS).slice(0, 14))
    if (!normalizeTicker(selectedTicker)) {
      setSelectedTicker(uploadedTickers[0])
    }
  }, [uploadedCompanies, selectedTicker])

  useEffect(() => {
    if (!uploadedCompanies.length) {
      setFeaturedCompanies([])
      return
    }
    const shuffled = [...uploadedCompanies]
    for (let i = shuffled.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1))
      const tmp = shuffled[i]
      shuffled[i] = shuffled[j]
      shuffled[j] = tmp
    }
    setFeaturedCompanies(shuffled.slice(0, 9))
  }, [uploadedCompanies])

  useEffect(() => {
    if (!selectedTicker) return
    fetchBundle(selectedTicker, { preferCache: true, skipIfFresh: true })
  }, [selectedTicker, fetchBundle])

  useEffect(() => {
    const candidates = mergeTickers(
      [selectedTicker],
      uploadedCompanies.map((c) => c.ticker),
    ).slice(0, 6)

    if (!candidates.length) return

    const timers = []
    candidates.forEach((tk, idx) => {
      if (tk === selectedTicker) return
      const timer = window.setTimeout(() => {
        fetchBundle(tk, { preferCache: true, silent: true, skipIfFresh: true })
      }, 700 + idx * 500)
      timers.push(timer)
    })

    return () => {
      timers.forEach((id) => window.clearTimeout(id))
    }
  }, [selectedTicker, uploadedCompanies, fetchBundle])

  useEffect(() => {
    const timers = []
    EQUITY_SECTOR_BENCHMARKS.forEach((item, idx) => {
      const timer = window.setTimeout(() => {
        fetchBundle(item.ticker, {
          preferCache: true,
          silent: true,
          skipIfFresh: true,
          remember: false,
          muteError: true,
          muteStatus: true,
          lite: true,
        })
      }, 900 + idx * 4200)
      timers.push(timer)
    })
    return () => timers.forEach((id) => window.clearTimeout(id))
  }, [fetchBundle])

  const selectedEntry = bundleMap[selectedTicker] || null
  const data = selectedEntry?.data || null

  const chartRows = useMemo(() => clipHistory(data?.history || [], rangeKey), [data?.history, rangeKey])
  const closeValues = useMemo(() => numericSeries(chartRows, 'close'), [chartRows])

  const dateRange = useMemo(() => {
    if (!chartRows.length) return { start: '', end: '' }
    return { start: chartRows[0].date, end: chartRows[chartRows.length - 1].date }
  }, [chartRows])

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
        setFilingRecordsMap((prev) => ({ ...prev, [selectedCompanyQuery]: matched }))
        const summary = buildFilingSummary(matched)
        setFilingSummaryMap((prev) => ({ ...prev, [selectedCompanyQuery]: summary }))
      })
      .catch(() => {
        if (!alive) return
        setFilingRecordsMap((prev) => ({ ...prev, [selectedCompanyQuery]: [] }))
        setFilingSummaryMap((prev) => ({
          ...prev,
          [selectedCompanyQuery]: { count: 0, years: [], latest: null, avgRiskItems: 0, avgCategories: 0, recent: [] },
        }))
      })
      .finally(() => {
        if (!alive) return
        setFilingLoading(false)
      })

    return () => {
      alive = false
    }
  }, [selectedCompanyQuery, selectedDisplayName, filingSummaryMap])

  const filingSummary = selectedCompanyQuery ? filingSummaryMap[selectedCompanyQuery] : null

  const companyMapByTicker = useMemo(() => {
    const map = {}
    uploadedCompanies.forEach((c) => {
      map[c.ticker] = c
    })
    return map
  }, [uploadedCompanies])

  const trackedRows = useMemo(() => {
    const tickers = mergeTickers(uploadedCompanies.map((c) => c.ticker), watchlist).slice(0, 18)
    return tickers.map((tk) => {
      const meta = companyMapByTicker[tk] || {}
      const payload = bundleMap[tk]?.data || null
      const company = meta.company || payload?.name || tk
      return {
        ticker: tk,
        company,
        industry: resolveEquitySector({
          filingIndustry: meta.industry,
          quoteSector: payload?.sector,
          ticker: tk,
          company,
        }),
        year: meta.year || null,
        data: payload,
        change_percent: Number(payload?.change_percent),
        market_cap: Number(payload?.market_cap),
        volume: Number((Array.isArray(payload?.history) ? payload.history[payload.history.length - 1]?.volume : 0) || 0),
        riskItems: Number(filingSummary?.latest?.risk_items || 0),
      }
    })
  }, [uploadedCompanies, watchlist, companyMapByTicker, bundleMap, filingSummary?.latest?.risk_items])

  const loadedRows = useMemo(() => trackedRows.filter((r) => r.data), [trackedRows])

  const boardRows = useMemo(() => {
    const rows = [...loadedRows]
    if (boardTab === 'losers') rows.sort((a, b) => Number(a.change_percent) - Number(b.change_percent))
    else if (boardTab === 'active') rows.sort((a, b) => Number(b.volume || 0) - Number(a.volume || 0))
    else rows.sort((a, b) => Number(b.change_percent) - Number(a.change_percent))
    return rows.slice(0, 5)
  }, [loadedRows, boardTab])

  const popularRows = useMemo(() => {
    const merged = [...trackedRows].sort((a, b) => {
      const aData = a.data ? 1 : 0
      const bData = b.data ? 1 : 0
      if (aData !== bData) return bData - aData
      return String(a.company).localeCompare(String(b.company))
    })
    return merged.slice(0, 5)
  }, [trackedRows])

  const uploadedSectorAgg = useMemo(() => {
    const buckets = {}
    loadedRows.forEach((row) => {
      const key = String(row.industry || 'Other').trim() || 'Other'
      if (!buckets[key]) {
        buckets[key] = { count: 0, sumPct: 0 }
      }
      buckets[key].count += 1
      if (Number.isFinite(row.change_percent)) buckets[key].sumPct += Number(row.change_percent)
    })
    return buckets
  }, [loadedRows])

  const sectorRows = useMemo(
    () =>
      EQUITY_SECTOR_BENCHMARKS.map((item) => {
        const payload = bundleMap[item.ticker]?.data || null
        const pct = Number(payload?.change_percent)
        const price = Number(payload?.price)
        const uploaded = uploadedSectorAgg[item.industry]
        const uploadedPct = uploaded?.count ? uploaded.sumPct / uploaded.count : null
        return {
          industry: item.industry,
          ticker: item.ticker,
          price: Number.isFinite(price) ? price : undefined,
          avgPct: Number.isFinite(pct) ? pct : (Number.isFinite(uploadedPct) ? uploadedPct : undefined),
        }
      }),
    [bundleMap, uploadedSectorAgg],
  )

  const summaryItems = useMemo(() => {
    const gainers = loadedRows.filter((r) => Number(r.change_percent) > 0).length
    const losers = loadedRows.filter((r) => Number(r.change_percent) < 0).length
    const topUp = [...loadedRows].sort((a, b) => Number(b.change_percent) - Number(a.change_percent))[0]
    const topDown = [...loadedRows].sort((a, b) => Number(a.change_percent) - Number(b.change_percent))[0]
    const sectorWithPct = sectorRows.filter((s) => Number.isFinite(Number(s.avgPct)))
    const leadSector = [...sectorWithPct].sort((a, b) => Number(b.avgPct) - Number(a.avgPct))[0]
    const weakSector = [...sectorWithPct].sort((a, b) => Number(a.avgPct) - Number(b.avgPct))[0]

    const items = []
    items.push({
      title: `Tracked breadth: ${gainers} gainers vs ${losers} losers`,
      body: `This summary uses ${loadedRows.length} uploaded or pinned companies with available market data.`
    })
    if (topUp) {
      items.push({
        title: `${topUp.company} leads movers at ${fmtPct(topUp.change_percent)}`,
        body: `${topUp.ticker} is currently the strongest move in your tracked set.`
      })
    }
    if (topDown) {
      items.push({
        title: `${topDown.company} is the weakest at ${fmtPct(topDown.change_percent)}`,
        body: `Consider checking the related filing year and risk deltas for this name.`
      })
    }
    if (leadSector || weakSector) {
      items.push({
        title: `Sector snapshot: ${leadSector?.industry || 'N/A'} strongest, ${weakSector?.industry || 'N/A'} weakest`,
        body: `Sector moves use benchmark ETFs, with uploaded-company averages as fallback when live sector quotes are unavailable.`
      })
    }
    if (filingSummary) {
      items.push({
        title: `10-K context for ${selectedDisplayName || selectedTicker}`,
        body: `Found ${filingSummary.count} filing records across ${filingSummary.years.length} years. Avg risk items: ${Math.round(filingSummary.avgRiskItems || 0)}.`
      })
    }
    return items.slice(0, 6)
  }, [loadedRows, sectorRows, filingSummary, selectedDisplayName, selectedTicker])

  const heatmapTiles = useMemo(() => {
    const rows = [...loadedRows]
      .filter((r) => r.data)
      .sort((a, b) => Number(b.market_cap || 0) - Number(a.market_cap || 0))
    if (!rows.length) return []

    const caps = rows.map((r) => Number(r.market_cap || 0)).filter((n) => Number.isFinite(n) && n > 0)
    const maxCap = caps.length ? Math.max(...caps) : 0
    return rows.map((row, idx) => {
      const cap = Math.max(0, Number(row.market_cap || 0))
      const ratio = maxCap > 0 ? cap / maxCap : Math.max(0.02, 1 - idx / Math.max(1, rows.length))
      const size = ratio >= 0.22 ? 'xxl' : ratio >= 0.11 ? 'xl' : ratio >= 0.05 ? 'lg' : ratio >= 0.02 ? 'md' : 'sm'
      const intensity = Math.max(1, Math.min(5, Math.ceil(Math.abs(Number(row.change_percent || 0)) / 1)))
      return {
        ...row,
        size,
        intensity,
      }
    })
  }, [loadedRows])

  const spotlightRows = useMemo(() => {
    const top = [...loadedRows]
      .sort((a, b) => Math.abs(Number(b.change_percent || 0)) - Math.abs(Number(a.change_percent || 0)))
      .slice(0, 3)

    return top.map((row) => {
      const hist = clipHistory(row.data?.history || [], '1M')
      const closes = numericSeries(hist, 'close')
      const vols = numericSeries(hist, 'volume')
      const sector = sectorRows.find((s) => s.industry === row.industry)
      const sectorText = sector ? `${sector.industry} is averaging ${fmtPct(sector.avgPct)}.` : 'Sector trend is mixed.'
      return {
        ...row,
        closes,
        vols,
        narrative: makeSpotlightSummary(row, sectorText),
      }
    })
  }, [loadedRows, sectorRows])

  const miniTickerCards = useMemo(() => {
    return loadedRows
      .map((row) => {
        const hist = clipHistory(row.data?.history || [], MINI_CARD_RANGE)
        const closes = numericSeries(hist, 'close')
        const lastClose = closes.length ? closes[closes.length - 1] : null
        return {
          ...row,
          closes,
          lastClose,
        }
      })
      .filter((row) => row.closes.length >= 2)
      .sort((a, b) => Number(Math.abs(b.change_percent || 0)) - Number(Math.abs(a.change_percent || 0)))
      .slice(0, 6)
  }, [loadedRows])

  const selectedFromUpload = companyMapByTicker[selectedTicker] || null
  const routeSymbol = normalizeTicker(routeTicker || '')
  const isCompanyView = Boolean(routeSymbol)
  const trackedRowByTicker = useMemo(() => {
    const map = {}
    trackedRows.forEach((row) => {
      map[row.ticker] = row
    })
    return map
  }, [trackedRows])

  const openDetail = useCallback(
    (rawTicker) => {
      const sym = normalizeTicker(rawTicker || selectedTicker)
      if (!sym) return
      setSelectedTicker(sym)
      navigate(`/stock/${encodeURIComponent(sym)}`)
    },
    [selectedTicker, navigate],
  )

  const closeDetail = useCallback(() => {
    navigate('/stock')
  }, [navigate])

  const detailSymbol = routeSymbol || selectedTicker
  const detailRow = trackedRowByTicker[detailSymbol] || null
  const detailData = detailRow?.data || data
  const detailCompany = detailRow?.company || detailData?.name || detailSymbol
  const detailIndustry = detailRow?.industry || 'Other'
  const detailProfileIndustry = normalizeSectorName(detailData?.industry) || detailIndustry || '—'
  const detailDescription = String(detailData?.description || '').trim()
  const detailIntro = detailDescription || `${detailCompany || detailSymbol} (${detailSymbol || 'N/A'}) is a listed company in ${detailProfileIndustry || 'its sector'} on ${detailData?.exchange || 'US exchanges'}${detailData?.country ? `, based in ${detailData.country}` : ''}.`
  const detailHistory = Array.isArray(detailData?.history) ? detailData.history : []
  const lastHistory = detailHistory.length ? detailHistory[detailHistory.length - 1] : null
  const prevHistory = detailHistory.length > 1 ? detailHistory[detailHistory.length - 2] : null
  const prevClose = Number.isFinite(Number(detailData?.previous_close)) ? Number(detailData?.previous_close) : Number(prevHistory?.close)
  const openPrice = Number.isFinite(Number(detailData?.open)) ? Number(detailData?.open) : null
  const dayHigh = Number.isFinite(Number(detailData?.day_high)) ? Number(detailData?.day_high) : null
  const dayLow = Number.isFinite(Number(detailData?.day_low)) ? Number(detailData?.day_low) : null
  const volumeNow = Number.isFinite(Number(detailData?.volume)) ? Number(detailData?.volume) : Number(lastHistory?.volume)
  const fullTimeEmployees = Number(detailData?.full_time_employees)
  const detailRecords = useMemo(() => {
    const list = Array.isArray(filingRecordsMap[selectedCompanyQuery]) ? filingRecordsMap[selectedCompanyQuery] : []
    return list
      .filter((r) => Number.isFinite(Number(r?.year)) && String(r?.record_id || '').trim())
      .slice(0, 6)
  }, [filingRecordsMap, selectedCompanyQuery])

  useEffect(() => {
    if (!isCompanyView) return
    if (!detailRecords.length) {
      setDetailActiveRecordId('')
      return
    }
    const firstId = String(detailRecords[0]?.record_id || '')
    if (!detailActiveRecordId || !detailRecords.some((r) => String(r?.record_id || '') === detailActiveRecordId)) {
      setDetailActiveRecordId(firstId)
    }
  }, [isCompanyView, detailRecords, detailActiveRecordId])

  useEffect(() => {
    if (!isCompanyView) return
    if (!detailRecords.length) return
    const pending = detailRecords.filter((r) => {
      const rid = String(r?.record_id || '')
      return rid && !Object.prototype.hasOwnProperty.call(detailTablesMap, rid)
    })
    if (!pending.length) return

    let alive = true
    setDetailTableLoading(true)
    Promise.all(
      pending.map(async (rec) => {
        const company = String(rec?.company || '').trim()
        const year = Number(rec?.year || 0)
        const filingType = String(rec?.filing_type || '10-K').trim() || '10-K'
        const rid = String(rec?.record_id || '')
        if (!company || !year || !rid) return { rid, result: null }
        try {
          const res = await get(
            `/api/tables/result?company=${encodeURIComponent(company)}&year=${encodeURIComponent(String(year))}&filing_type=${encodeURIComponent(filingType)}`,
          )
          const result = res?.result && typeof res.result === 'object' ? res.result : null
          return { rid, result }
        } catch {
          return { rid, result: null }
        }
      }),
    )
      .then((pairs) => {
        if (!alive) return
        setDetailTablesMap((prev) => {
          const next = { ...prev }
          pairs.forEach((item) => {
            if (!item?.rid) return
            next[item.rid] = item.result
          })
          return next
        })
      })
      .finally(() => {
        if (!alive) return
        setDetailTableLoading(false)
      })

    return () => {
      alive = false
    }
  }, [isCompanyView, detailRecords, detailTablesMap])

  const activeDetailRecord = useMemo(
    () => detailRecords.find((r) => String(r?.record_id || '') === detailActiveRecordId) || detailRecords[0] || null,
    [detailRecords, detailActiveRecordId],
  )
  const activeTableResult = activeDetailRecord ? detailTablesMap[String(activeDetailRecord?.record_id || '')] : null
  const activeTableBlock = activeTableResult && detailTableSection ? activeTableResult[detailTableSection] : null
  const activeTableHeaders = Array.isArray(activeTableBlock?.headers) ? activeTableBlock.headers : []
  const activeTableRows = Array.isArray(activeTableBlock?.rows) ? activeTableBlock.rows : []
  const detailPeers = useMemo(() => {
    const sameSector = loadedRows
      .filter((row) => row.ticker !== detailSymbol && row.industry === detailIndustry)
      .sort((a, b) => Number(b.market_cap || 0) - Number(a.market_cap || 0))
      .slice(0, 5)
    if (sameSector.length >= 3) return sameSector
    const fallback = loadedRows
      .filter((row) => row.ticker !== detailSymbol)
      .sort((a, b) => Number(Math.abs(b.change_percent || 0)) - Number(Math.abs(a.change_percent || 0)))
      .slice(0, 5)
    return sameSector.length ? [...sameSector, ...fallback.filter((r) => !sameSector.some((s) => s.ticker === r.ticker))].slice(0, 5) : fallback
  }, [loadedRows, detailSymbol, detailIndustry])

  useEffect(() => {
    if (!routeSymbol) return
    if (selectedTicker !== routeSymbol) setSelectedTicker(routeSymbol)
  }, [routeSymbol, selectedTicker])

  useEffect(() => {
    if (!isCompanyView) {
      setDetailMainTab('overview')
      return
    }
    setHeatmapHover(null)
  }, [isCompanyView, routeSymbol])

  const addTicker = () => {
    const next = normalizeTicker(addTickerInput)
    if (!next) return
    setSelectedTicker(next)
    setWatchlist((prev) => mergeTickers([next], prev, uploadedCompanies.map((c) => c.ticker), DEFAULT_TICKERS).slice(0, 14))
    setAddTickerInput('')
    setShowAddTicker(false)
  }

  const refreshSelected = () => {
    if (!selectedTicker) return
    fetchBundle(selectedTicker, { preferCache: true, force: true })
  }

  return (
    <div className="rl-page-shell rl-up-page rl-stock-page">
      <section className="rl-up-header">
        {!isCompanyView ? (
          <div className="page-header !mb-0">
            <div className="page-header-left rl-up-title-block">
              <span className="page-icon">📊</span>
              <div>
                <p className="page-title">Stock</p>
                <p className="page-subtitle">Market board for your tracked companies, grounded in uploaded 10-K context</p>
              </div>
            </div>
            <button className="btn-secondary" onClick={refreshSelected} disabled={loadingTicker === selectedTicker}>
              {loadingTicker === selectedTicker ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        ) : (
          <div className="page-header !mb-0">
            <div className="page-header-left rl-up-title-block">
              <CompanyLogo ticker={detailSymbol} company={detailCompany} />
              <div>
                <p className="page-title">{detailCompany || detailSymbol}</p>
                <p className="page-subtitle">{detailSymbol} · {detailData?.exchange || detailIndustry || 'US Equities'}</p>
              </div>
            </div>
            <div className="rl-stock-detail-topline">
              <button className="btn-secondary rl-stock-back-btn" onClick={closeDetail}>Back</button>
            </div>
          </div>
        )}
      </section>

      {!isCompanyView ? (
      <>
      <section className="rl-stock-command rl-stock-command-v2">
        <div className="rl-stock-command-head">
          <div>
            <p className="rl-stock-command-title">Tracked Companies</p>
            <span>
              {recordsLoading
                ? 'Loading uploaded company universe…'
                : `${uploadedCompanies.length} companies from uploaded filings · showing ${featuredCompanies.length} random cards`}
            </span>
          </div>
          <button className="btn-secondary" onClick={() => setShowAddTicker((v) => !v)}>
            {showAddTicker ? 'Cancel' : '+ Add Ticker'}
          </button>
        </div>

        <div className="rl-stock-chip-row">
          {featuredCompanies.map((c) => {
            const payload = bundleMap[c.ticker]?.data
            const pct = Number(payload?.change_percent)
            return (
              <button
                key={`${c.ticker}-${c.company}`}
                className={`rl-stock-chip ${selectedTicker === c.ticker ? 'active' : ''}`}
                onClick={() => openDetail(c.ticker)}
                title={`${c.company} · ${c.industry}`}
              >
                <span>{c.company}</span>
                <em className={toneClass(pct)}>{Number.isFinite(pct) ? fmtPct(pct) : c.ticker}</em>
              </button>
            )
          })}
        </div>

        {showAddTicker ? (
          <div className="rl-stock-input-row rl-stock-add-row">
            <input className="input" value={addTickerInput} onChange={(e) => setAddTickerInput(normalizeTicker(e.target.value))} placeholder="e.g. TSLA" />
            <button className="btn-primary" onClick={addTicker}>Add & View</button>
          </div>
        ) : null}

        <p className="rl-stock-cache-note">
          {selectedEntry?.savedAt ? `Instant view from cache (${timeAgoFrom(selectedEntry.savedAt)}), then background refresh.` : 'Loading data and caching for faster next visit.'}
        </p>
        {statusHint ? <p className="rl-stock-cache-note rl-stock-status-note">{statusHint}</p> : null}
      </section>

      {error ? <div className="rl-up-inline-error">{error}</div> : null}

      <section className="rl-stock-metrics-grid rl-stock-metrics-grid-v2">
        <div className="metric-card rl-stock-metric-card">
          <p className="metric-label">Selected</p>
          <p className="metric-value">{selectedTicker || '—'}</p>
          <span className="rl-stock-metric-sub">{data?.name || selectedFromUpload?.company || '—'}</span>
        </div>
        <div className="metric-card rl-stock-metric-card">
          <p className="metric-label">Current Price</p>
          <p className="metric-value">{fmtPrice(data?.price)}</p>
          <span className="rl-stock-metric-sub">{data?.exchange || 'US Equities'}</span>
        </div>
        <div className="metric-card rl-stock-metric-card">
          <p className="metric-label">Today</p>
          <p className={`metric-value ${Number(data?.change_percent || 0) >= 0 ? 'rl-stock-up' : 'rl-stock-down'}`}>{fmtPct(data?.change_percent)}</p>
          <span className="rl-stock-metric-sub">Change {fmtPrice(data?.change)}</span>
        </div>
        <div className="metric-card rl-stock-metric-card">
          <p className="metric-label">Market Cap</p>
          <p className="metric-value !text-[1.05rem]">{fmtCompact(data?.market_cap)}</p>
          <span className="rl-stock-metric-sub">PE {data?.pe_ratio ? Number(data.pe_ratio).toFixed(2) : '—'}</span>
        </div>
        <div className="metric-card rl-stock-metric-card">
          <p className="metric-label">Uploaded Scope</p>
          <p className="metric-value !text-[1.05rem]">{uploadedCompanies.length}</p>
          <span className="rl-stock-metric-sub">companies with filing context</span>
        </div>
      </section>
      </>
      ) : null}

      {isCompanyView && error ? <div className="rl-up-inline-error">{error}</div> : null}

      {!isCompanyView ? (
      <section className="rl-stock-workbench rl-stock-workbench-v2">
        <div className="rl-stock-left">
          <div className="rl-stock-chart-grid">
            {miniTickerCards.map((card) => (
              <button key={`mini-card-${card.ticker}`} className={`rl-stock-chart-tile ${selectedTicker === card.ticker ? 'active' : ''}`} onClick={() => openDetail(card.ticker)}>
                <div className="rl-stock-chart-tile-top">
                  <p>{card.company}</p>
                  <span className={toneClass(card.change_percent)}>{fmtPct(card.change_percent)}</span>
                </div>
                <small>{card.ticker} · {fmtPrice(card.lastClose)} · {card.data?.exchange || card.industry || 'US'}</small>
                <MiniChart values={card.closes} kind="line" color={chartColorFor(card.closes, '#22c55e', '#ef4444')} />
              </button>
            ))}
            {!miniTickerCards.length ? <p className="rl-stock-muted">No tracked ticker charts yet.</p> : null}
          </div>

          <section className="rl-stock-side-card rl-stock-summary-card">
            <div className="rl-stock-side-head">
              <p>Market Summary</p>
              <span>{loadedRows.length ? `Updated from ${loadedRows.length} tracked stocks` : 'Waiting for quotes'}</span>
            </div>
            <div className="rl-stock-accordion-list">
              {summaryItems.map((item, idx) => {
                const open = idx === summaryOpenIdx
                return (
                  <div key={`${item.title}-${idx}`} className={`rl-stock-accordion-item ${open ? 'open' : ''}`}>
                    <button className="rl-stock-accordion-head" onClick={() => setSummaryOpenIdx(open ? -1 : idx)}>
                      <span>{item.title}</span>
                      <strong>{open ? '−' : '+'}</strong>
                    </button>
                    {open ? <p className="rl-stock-accordion-body">{item.body}</p> : null}
                  </div>
                )
              })}
            </div>
          </section>

          <section className="rl-stock-side-card rl-stock-heatmap-card">
            <div className="rl-stock-side-head">
              <p>Tracked Heatmap</p>
              <span>Color = daily move · size = market cap</span>
            </div>
            <div className="rl-stock-heatmap-unified-wrap" onMouseLeave={() => setHeatmapHover(null)}>
              <div className="rl-stock-heatmap-grid rl-stock-heatmap-grid-unified">
                {heatmapTiles.map((row) => (
                  <button
                    key={`heat-${row.ticker}`}
                    className={`rl-stock-heatmap-tile tone-${toneClass(row.change_percent)} size-${row.size} intensity-${row.intensity}`}
                    onClick={() => openDetail(row.ticker)}
                    onMouseEnter={(e) => {
                      setHeatmapHover({
                        x: e.currentTarget.offsetLeft + e.currentTarget.offsetWidth / 2,
                        y: e.currentTarget.offsetTop - 8,
                        row,
                      })
                    }}
                    onMouseMove={(e) => {
                      setHeatmapHover((prev) => {
                        if (!prev || prev.row?.ticker !== row.ticker) {
                          return {
                            x: e.currentTarget.offsetLeft + e.currentTarget.offsetWidth / 2,
                            y: e.currentTarget.offsetTop - 8,
                            row,
                          }
                        }
                        return { ...prev, x: e.currentTarget.offsetLeft + e.currentTarget.offsetWidth / 2, y: e.currentTarget.offsetTop - 8 }
                      })
                    }}
                    title={`${row.company} · ${fmtPct(row.change_percent)}`}
                  >
                    <span>{row.ticker}</span>
                    <small>{row.company}</small>
                    <em>{fmtPct(row.change_percent)}</em>
                  </button>
                ))}
                {!heatmapTiles.length ? <p className="rl-stock-muted">Load tracked quotes to render heatmap.</p> : null}
              </div>
              {heatmapHover?.row ? (
                <div
                  className="rl-stock-heatmap-tooltip"
                  style={{
                    left: `${heatmapHover.x}px`,
                    top: `${heatmapHover.y}px`,
                  }}
                >
                  <p>{heatmapHover.row.industry || 'Other'}</p>
                  <strong>{heatmapHover.row.ticker} · {heatmapHover.row.company}</strong>
                  <span>{fmtPrice(heatmapHover.row.data?.price)} · {fmtPct(heatmapHover.row.change_percent)}</span>
                  <em>Cap {fmtCompact(heatmapHover.row.market_cap)} · Vol {fmtCompact(heatmapHover.row.volume)}</em>
                </div>
              ) : null}
            </div>
          </section>

          <section className="rl-stock-side-card rl-stock-spotlight-card">
            <div className="rl-stock-side-head">
              <p>Spotlight Stocks</p>
              <span>High-impact movers from your tracked universe</span>
            </div>
            <div className="rl-stock-spotlight-list">
              {spotlightRows.map((row) => (
                <article key={`spot-${row.ticker}`} className="rl-stock-spotlight-item">
                  <div className="rl-stock-spotlight-head">
                    <div className="rl-stock-company-mini" onClick={() => openDetail(row.ticker)}>
                      <CompanyLogo ticker={row.ticker} company={row.company} />
                      <div>
                        <p>{row.company}</p>
                        <span>{row.ticker} · {row.data?.exchange || 'US'}</span>
                      </div>
                    </div>
                    <div className="rl-stock-company-price">
                      <strong>{fmtPrice(row.data?.price)}</strong>
                      <em className={toneClass(row.change_percent)}>{fmtPct(row.change_percent)}</em>
                    </div>
                  </div>

                  <div className="rl-stock-spotlight-body">
                    <MiniChart values={row.closes} kind="line" color={chartColorFor(row.closes, '#22c55e', '#ef4444')} compact={false} />
                    <div className="rl-stock-spotlight-stats">
                      <span><b>Volume</b>{fmtCompact(row.volume)}</span>
                      <span><b>Market Cap</b>{fmtCompact(row.market_cap)}</span>
                      <span><b>PE</b>{row.data?.pe_ratio ? Number(row.data.pe_ratio).toFixed(2) : '—'}</span>
                      <span><b>52W</b>{fmtPrice(row.data?.low_52)} - {fmtPrice(row.data?.high_52)}</span>
                    </div>
                  </div>

                  <p className="rl-stock-spotlight-note">{row.narrative}</p>
                </article>
              ))}
              {!spotlightRows.length ? <p className="rl-stock-muted">No spotlight yet. Select/upload companies with tickers first.</p> : null}
            </div>
          </section>
        </div>

        <aside className="rl-stock-side">
          <section className="rl-stock-side-card">
            <div className="rl-stock-side-head">
              <p>Popular Companies</p>
              <span>{popularRows.length} names</span>
            </div>
            <div className="rl-stock-company-list">
              {popularRows.map((row) => {
                const pct = Number(row.data?.change_percent)
                return (
                  <button key={`popular-${row.ticker}`} className="rl-stock-company-item" onClick={() => openDetail(row.ticker)}>
                    <div className="rl-stock-company-mini">
                      <CompanyLogo ticker={row.ticker} company={row.company} />
                      <div>
                        <p>{row.company}</p>
                        <span>{row.ticker} · {row.data?.exchange || row.industry || 'US'}</span>
                      </div>
                    </div>
                    <div className="rl-stock-company-price">
                      <strong>{fmtPrice(row.data?.price)}</strong>
                      <em className={toneClass(pct)}>{Number.isFinite(pct) ? fmtPct(pct) : '—'}</em>
                    </div>
                  </button>
                )
              })}
              {!popularRows.length ? <p className="rl-stock-muted">No uploaded companies yet.</p> : null}
            </div>
          </section>

          <section className="rl-stock-side-card">
            <div className="rl-stock-side-head">
              <p>Leaders Board</p>
            </div>
            <div className="rl-stock-board-tabs">
              {[
                { key: 'gainers', label: 'Gainers' },
                { key: 'losers', label: 'Losers' },
                { key: 'active', label: 'Active' },
              ].map((tab) => (
                <button key={tab.key} className={boardTab === tab.key ? 'active' : ''} onClick={() => setBoardTab(tab.key)}>{tab.label}</button>
              ))}
            </div>
            <div className="rl-stock-board-list">
              {boardRows.map((row) => (
                <button key={`board-${row.ticker}`} className="rl-stock-board-item" onClick={() => openDetail(row.ticker)}>
                  <div className="rl-stock-company-mini">
                    <CompanyLogo ticker={row.ticker} company={row.company} />
                    <div>
                      <p>{row.company}</p>
                      <span>{row.ticker} · {row.data?.exchange || 'US'}</span>
                    </div>
                  </div>
                  <div className="rl-stock-company-price">
                    <strong>{fmtPrice(row.data?.price)}</strong>
                    <em className={toneClass(row.change_percent)}>{fmtPct(row.change_percent)}</em>
                  </div>
                </button>
              ))}
              {!boardRows.length ? <p className="rl-stock-muted">Load tracked quotes to populate board.</p> : null}
            </div>
          </section>

          <section className="rl-stock-side-card">
            <div className="rl-stock-side-head">
              <p>Equity Sectors</p>
            </div>
            <div className="rl-stock-sector-list">
              {sectorRows.map((row) => (
                <div key={`sector-${row.industry}`} className="rl-stock-sector-item">
                  <span>{row.industry}</span>
                  <strong>{fmtPrice(row.price)}</strong>
                  <em className={toneClass(row.avgPct)}>{fmtPct(row.avgPct)}</em>
                </div>
              ))}
              {!sectorRows.length ? <p className="rl-stock-muted">No sector data yet.</p> : null}
            </div>
          </section>

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
                      <span>{rec.year || '—'} · {rec.filing_type || '10-K'} · risks {Number(rec.risk_items || 0)}</span>
                    </div>
                  ))}
                  {!filingSummary.recent?.length ? <p className="rl-stock-muted">No linked filing records yet.</p> : null}
                </div>
              </>
            ) : null}
          </section>
        </aside>
      </section>
      ) : (
      <section className="rl-stock-workbench rl-stock-workbench-v2 rl-stock-detail-layout">
        <div className="rl-stock-left">
          <section className="rl-stock-side-card rl-stock-detail-main-card">
            <div className="rl-stock-detail-main-tabs">
              <button className={detailMainTab === 'overview' ? 'active' : ''} onClick={() => setDetailMainTab('overview')}>Overview</button>
              <button className={detailMainTab === 'financials' ? 'active' : ''} onClick={() => setDetailMainTab('financials')}>Financial Data</button>
            </div>

            {detailMainTab === 'overview' ? (
              <div className="rl-stock-detail-market-panel">
                <div className="rl-stock-quote-strip">
                  <div className="rl-stock-quote-cell">
                    <p className="rl-stock-quote-price">
                      {fmtPrice(detailData?.price)} <span className={toneClass(detailData?.change_percent)}>{fmtSigned(detailData?.change)} ({fmtPctPlain(detailData?.change_percent)})</span>
                    </p>
                    <span>Regular close · {fmtDateTime(detailData?.regular_market_time)}</span>
                  </div>
                  <div className="rl-stock-quote-cell">
                    <p className="rl-stock-quote-price">
                      {fmtPrice(detailData?.post_market_price)}{' '}
                      <span className={toneClass(detailData?.post_market_change_percent)}>
                        {fmtSigned(detailData?.post_market_change)} {fmtPct(detailData?.post_market_change_percent)}
                      </span>
                    </p>
                    <span>After hours · {fmtDateTime(detailData?.post_market_time)}</span>
                  </div>
                </div>

                <div className="rl-stock-detail-chart-shell">
                  <div className="rl-stock-focus-card rl-stock-focus-card-formal">
                    <FocusChart
                      title=""
                      subtitle=""
                      values={closeValues || []}
                      rows={chartRows}
                      kind="line"
                      color={chartColorFor(closeValues, '#15803d', '#b91c1c')}
                      dateRange={dateRange}
                      rangeKey={rangeKey}
                      formal
                      hideTitle
                      showRangeSelector
                      onSelectRange={setRangeKey}
                    />
                  </div>
                </div>

                <div className="rl-stock-kpi-table">
                  <div><span>Previous Close</span><strong>{fmtPrice(prevClose)}</strong></div>
                  <div><span>Market Cap</span><strong>{fmtCompact(detailData?.market_cap)}</strong></div>
                  <div><span>Open</span><strong>{fmtPrice(openPrice)}</strong></div>
                  <div><span>PE Ratio</span><strong>{detailData?.pe_ratio ? Number(detailData.pe_ratio).toFixed(2) : '—'}</strong></div>
                  <div><span>Day Range</span><strong>{fmtRange(dayLow, dayHigh)}</strong></div>
                  <div><span>Dividend Yield</span><strong>{fmtYield(detailData?.dividend_yield)}</strong></div>
                  <div><span>52W Range</span><strong>{fmtRange(detailData?.low_52, detailData?.high_52)}</strong></div>
                  <div><span>EPS (TTM)</span><strong>{fmtPrice(detailData?.eps)}</strong></div>
                  <div><span>Volume</span><strong>{fmtCompact(volumeNow)}</strong></div>
                </div>
              </div>
            ) : (
              <div className="rl-stock-financial-card rl-stock-financial-panel">
                <div className="rl-stock-side-head">
                  <p>Financial Data</p>
                  <span>{activeDetailRecord ? `${activeDetailRecord.year} · ${activeDetailRecord.filing_type || '10-K'}` : 'No extracted tables'}</span>
                </div>

                <div className="rl-stock-fin-year-select-row">
                  <label htmlFor="rl-stock-fin-year">Year</label>
                  <select
                    id="rl-stock-fin-year"
                    className="rl-stock-fin-year-select"
                    value={detailActiveRecordId || String(detailRecords[0]?.record_id || '')}
                    onChange={(e) => setDetailActiveRecordId(String(e.target.value || ''))}
                  >
                    {detailRecords.map((rec) => {
                      const rid = String(rec?.record_id || '')
                      return (
                        <option key={`fin-year-${rid}`} value={rid}>
                          {rec?.year || '—'} · {rec?.filing_type || '10-K'}
                        </option>
                      )
                    })}
                  </select>
                </div>

                <div className="rl-stock-fin-section-tabs">
                  {TABLE_SECTIONS.map((section) => (
                    <button
                      key={`fin-section-${section.key}`}
                      className={detailTableSection === section.key ? 'active' : ''}
                      onClick={() => setDetailTableSection(section.key)}
                    >
                      {section.label}
                    </button>
                  ))}
                </div>

                {detailTableLoading ? <p className="rl-stock-muted">Loading extracted tables…</p> : null}
                {!detailTableLoading && !activeTableResult ? <p className="rl-stock-muted">No extracted table bundle for this filing year yet.</p> : null}
                {!detailTableLoading && activeTableResult && !activeTableBlock?.found ? (
                  <p className="rl-stock-muted">This statement was not found in the selected filing.</p>
                ) : null}
                {!detailTableLoading && activeTableBlock?.found ? (
                  <>
                    {String(activeTableBlock?.unit || '').trim() ? <p className="rl-stock-fin-unit">Unit: {String(activeTableBlock.unit)}</p> : null}
                    <div className="rl-stock-fin-table-wrap">
                      <table className="rl-stock-fin-table">
                        {activeTableHeaders.length ? (
                          <thead>
                            <tr>
                              {activeTableHeaders.map((h, idx) => (
                                <th key={`fin-head-${idx}`}>{/^col\s*\d+$/i.test(String(h || '')) ? '' : String(h || '')}</th>
                              ))}
                            </tr>
                          </thead>
                        ) : null}
                        <tbody>
                          {activeTableRows.slice(0, 60).map((row, rIdx) => (
                            <tr key={`fin-row-${rIdx}`}>
                              {(Array.isArray(row) ? row : [row]).map((cell, cIdx) => (
                                <td key={`fin-cell-${rIdx}-${cIdx}`}>{String(cell ?? '')}</td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                ) : null}
              </div>
            )}
          </section>
        </div>

        <aside className="rl-stock-side">
          <section className="rl-stock-side-card rl-stock-profile-card">
              <div className="rl-stock-profile-list">
                <div><span>Symbol</span><strong>{detailSymbol || '—'}</strong></div>
                <div><span>IPO Date</span><strong>{fmtDateOnly(detailData?.ipo_date)}</strong></div>
                <div><span>CEO</span><strong>{detailData?.ceo || '—'}</strong></div>
                <div><span>Full-time Employees</span><strong>{Number.isFinite(fullTimeEmployees) ? fmtWhole(fullTimeEmployees) : '—'}</strong></div>
                <div><span>Industry</span><strong>{detailProfileIndustry}</strong></div>
                <div><span>Country/Region</span><strong>{detailData?.country || '—'}</strong></div>
                <div><span>Exchange</span><strong>{detailData?.exchange || 'US'}</strong></div>
              </div>
            <p className="rl-stock-profile-desc">{detailIntro}</p>
          </section>

          <section className="rl-stock-side-card">
            <div className="rl-stock-side-head">
              <p>Peers</p>
              <span>{detailPeers.length} names</span>
            </div>
            <div className="rl-stock-company-list">
              {detailPeers.map((row) => (
                <button key={`peer-${row.ticker}`} className="rl-stock-company-item" onClick={() => openDetail(row.ticker)}>
                  <div className="rl-stock-company-mini">
                    <CompanyLogo ticker={row.ticker} company={row.company} />
                    <div>
                      <p>{row.company}</p>
                      <span>{row.ticker} · {row.data?.exchange || row.industry || 'US'}</span>
                    </div>
                  </div>
                  <div className="rl-stock-company-price">
                    <strong>{fmtPrice(row.data?.price)}</strong>
                    <em className={toneClass(row.change_percent)}>{fmtPct(row.change_percent)}</em>
                  </div>
                </button>
              ))}
            </div>
          </section>

          <section className="rl-stock-side-card">
            <div className="rl-stock-side-head">
              <p>Leaders Board</p>
            </div>
            <div className="rl-stock-board-tabs">
              {[
                { key: 'gainers', label: 'Gainers' },
                { key: 'losers', label: 'Losers' },
                { key: 'active', label: 'Active' },
              ].map((tab) => (
                <button key={tab.key} className={boardTab === tab.key ? 'active' : ''} onClick={() => setBoardTab(tab.key)}>{tab.label}</button>
              ))}
            </div>
            <div className="rl-stock-board-list">
              {boardRows.map((row) => (
                <button key={`board-detail-${row.ticker}`} className="rl-stock-board-item" onClick={() => openDetail(row.ticker)}>
                  <div className="rl-stock-company-mini">
                    <CompanyLogo ticker={row.ticker} company={row.company} />
                    <div>
                      <p>{row.company}</p>
                      <span>{row.ticker} · {row.data?.exchange || 'US'}</span>
                    </div>
                  </div>
                  <div className="rl-stock-company-price">
                    <strong>{fmtPrice(row.data?.price)}</strong>
                    <em className={toneClass(row.change_percent)}>{fmtPct(row.change_percent)}</em>
                  </div>
                </button>
              ))}
              {!boardRows.length ? <p className="rl-stock-muted">Load tracked quotes to populate board.</p> : null}
            </div>
          </section>
        </aside>
      </section>
      )}
    </div>
  )
}
