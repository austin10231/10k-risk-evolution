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
const STOCK_BUNDLE_PREFIX = 'rl_stock_bundle_v2_'
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
  UBER: 'uber.com',
  LMT: 'lockheedmartin.com',
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

const SIMPLE_ICON_SLUG_BY_TICKER = {
  AAPL: 'apple',
  BA: 'boeing',
  LMT: 'lockheedmartin',
}

const LOGO_FORCE_DOMAIN_BY_TICKER = {
  UBER: 'uber.com',
  LMT: 'lockheedmartin.com',
}

const LOGO_STATIC_BY_TICKER = {
  AMZN: 'https://commons.wikimedia.org/wiki/Special:FilePath/Amazon%20icon.svg',
  UBER: 'https://commons.wikimedia.org/wiki/Special:FilePath/Uber%20logo%202018.svg',
  LMT: 'https://commons.wikimedia.org/wiki/Special:FilePath/Lockheed%20Martin%20logo%20%282011%E2%80%932022%29.svg',
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
  GOOGL: 'Technology',
  GOOG: 'Technology',
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

const SECTOR_BENCHMARK_CANDIDATES = {
  Technology: ['XLK', 'VGT'],
  Energy: ['XLE', 'VDE'],
  'Consumer Cyclical': ['XLY', 'VCR'],
  'Consumer Defensive': ['XLP', 'VDC'],
  'Communication Services': ['XLC', 'VOX'],
  Industrials: ['XLI', 'VIS'],
  'Financial Services': ['XLF', 'VFH'],
  Utilities: ['XLU', 'IDU'],
  'Basic Materials': ['XLB', 'VAW'],
  'Real Estate': ['XLRE', 'IYR'],
  Healthcare: ['XLV', 'VHT'],
}

const MARKET_OVERVIEW_TICKERS = [
  { label: 'S&P 500', ticker: 'SPY' },
  { label: 'Nasdaq 100', ticker: 'QQQ' },
  { label: 'Dow', ticker: 'DIA' },
  { label: 'Russell 2000', ticker: 'IWM' },
  { label: 'Volatility', ticker: 'VIXY' },
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

function parseDateValue(value) {
  const raw = String(value || '').trim()
  if (!raw) return null
  const direct = new Date(raw)
  if (!Number.isNaN(direct.getTime())) return direct
  const numeric = Number(value)
  if (Number.isFinite(numeric) && numeric > 0) {
    const ms = numeric > 1e12 ? numeric : numeric * 1000
    const d = new Date(ms)
    if (!Number.isNaN(d.getTime())) return d
  }
  return null
}

function isIntradayLabel(value) {
  const raw = String(value || '').trim()
  return raw.includes(':') || raw.includes('T')
}

function fmtDateAxis(value, preferTime = false) {
  const parsed = parseDateValue(value)
  if (parsed) {
    if (preferTime) return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
    return `${parsed.getMonth() + 1}/${parsed.getDate()}`
  }
  const raw = String(value || '').trim()
  return raw || '—'
}

function fmtDateTime(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric) || numeric <= 0) return '—'
  const ms = numeric > 1e12 ? numeric : numeric * 1000
  const d = new Date(ms)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString()
}

function resolvePrice(payload) {
  const p = Number(payload?.price)
  if (Number.isFinite(p) && p > 0) return p
  const rows = Array.isArray(payload?.history) ? payload.history : []
  const last = Number(rows[rows.length - 1]?.close)
  return Number.isFinite(last) ? last : null
}

function resolveChange(payload) {
  const direct = Number(payload?.change)
  if (Number.isFinite(direct)) return direct
  const prevClose = Number(payload?.previous_close)
  const price = resolvePrice(payload)
  if (Number.isFinite(price) && Number.isFinite(prevClose) && prevClose !== 0) return price - prevClose

  const rows = Array.isArray(payload?.history) ? payload.history : []
  if (rows.length >= 2) {
    const last = Number(rows[rows.length - 1]?.close)
    const prev = Number(rows[rows.length - 2]?.close)
    if (Number.isFinite(last) && Number.isFinite(prev)) return last - prev
  }
  return null
}

function resolveChangePercent(payload) {
  const direct = Number(payload?.change_percent)
  if (Number.isFinite(direct)) return direct

  const change = resolveChange(payload)
  const prevClose = Number(payload?.previous_close)
  if (Number.isFinite(change) && Number.isFinite(prevClose) && prevClose !== 0) return (change / prevClose) * 100

  const rows = Array.isArray(payload?.history) ? payload.history : []
  if (rows.length >= 2) {
    const last = Number(rows[rows.length - 1]?.close)
    const prev = Number(rows[rows.length - 2]?.close)
    if (Number.isFinite(last) && Number.isFinite(prev) && prev !== 0) return ((last - prev) / prev) * 100
  }
  return null
}

function resolveMarketCap(payload) {
  const candidates = [
    payload?.market_cap,
    payload?.marketCap,
    payload?.market_capitalization,
    payload?.marketCapitalization,
  ]
  for (const raw of candidates) {
    const n = Number(raw)
    if (Number.isFinite(n) && n > 0) return n
  }
  return null
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

function clipSpotlightHistory(history) {
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

  const withTs = rows
    .map((row) => ({ ...row, ts: parseDateValue(row.date)?.getTime() || null, hasTime: isIntradayLabel(row.date) }))
    .filter((row) => Number.isFinite(row.ts) && row.hasTime)

  if (withTs.length >= 6) {
    const newestTs = Number(withTs[withTs.length - 1].ts || 0)
    const DAY_MS = 24 * 60 * 60 * 1000
    const recent = withTs.filter((row) => Number(row.ts) >= newestTs - DAY_MS)
    if (recent.length >= 6) return recent.slice(-36).map(({ ts, hasTime, ...rest }) => rest)
    return withTs.slice(-24).map(({ ts, hasTime, ...rest }) => rest)
  }

  return rows.slice(-Math.min(22, rows.length))
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
  const urls = []
  const staticUrl = LOGO_STATIC_BY_TICKER[sym]
  if (staticUrl) {
    urls.push(staticUrl)
  }
  const forceDomain = LOGO_FORCE_DOMAIN_BY_TICKER[sym]
  if (forceDomain) {
    urls.push(`https://api.faviconkit.com/${encodeURIComponent(forceDomain)}/128`)
    urls.push(`https://logo.clearbit.com/${encodeURIComponent(forceDomain)}`)
  }
  const iconSlug = SIMPLE_ICON_SLUG_BY_TICKER[sym]
  if (iconSlug) {
    urls.push(`https://cdn.simpleicons.org/${encodeURIComponent(iconSlug)}`)
  }
  if (sym) {
    urls.push(`https://financialmodelingprep.com/image-stock/${encodeURIComponent(sym)}.png`)
    urls.push(`https://eodhistoricaldata.com/img/logos/US/${encodeURIComponent(sym)}.png`)
  }
  const mappedDomain = LOGO_DOMAIN_BY_TICKER[sym]
  if (mappedDomain) {
    urls.push(`https://www.google.com/s2/favicons?domain=${encodeURIComponent(mappedDomain)}&sz=256`)
  }
  const root = normalizeCompanyRoot(companyName)
  if (root && root.length >= 3) {
    urls.push(`https://www.google.com/s2/favicons?domain=${encodeURIComponent(`${root}.com`)}&sz=256`)
  }
  return Array.from(new Set(urls))
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
          onLoad={(e) => {
            const w = Number(e.currentTarget?.naturalWidth || 0)
            const h = Number(e.currentTarget?.naturalHeight || 0)
            if (w > 0 && h > 0 && (w < 18 || h < 18)) {
              setCursor((idx) => idx + 1)
            }
          }}
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

function companyIdentityKey(row) {
  const fromName = sanitizeCompanyName(row?.company || row?.data?.name || '')
  if (fromName) return fromName
  const ticker = normalizeTicker(row?.ticker || '')
  if (!ticker) return ''
  return ticker.replace(/[.\-]/g, '')
}

function uniqueRowsByCompany(rows, limit = Infinity) {
  const list = Array.isArray(rows) ? rows : []
  const out = []
  const seen = new Set()
  for (const row of list) {
    const key = companyIdentityKey(row)
    if (!key || seen.has(key)) continue
    seen.add(key)
    out.push(row)
    if (out.length >= limit) break
  }
  return out
}

function heatmapSummaryText(row) {
  const raw = String(row?.data?.description || '').trim()
  if (raw) {
    const compact = raw.replace(/\s+/g, ' ').trim()
    if (compact.length <= 180) return compact
    return `${compact.slice(0, 177).trimEnd()}...`
  }
  const company = String(row?.company || row?.ticker || 'This company')
  const industry = String(row?.industry || 'its sector')
  const pct = Number(row?.change_percent)
  const move = Number.isFinite(pct) ? `is ${pct >= 0 ? 'up' : 'down'} ${Math.abs(pct).toFixed(2)}% today` : 'is moving today'
  return `${company} ${move}, with activity centered in ${industry}.`
}

function spotlightNarrativeText(row) {
  const raw = String(row?.data?.description || '').trim()
  if (raw) {
    const compact = raw.replace(/\s+/g, ' ').trim()
    if (compact.length <= 260) return compact
    return `${compact.slice(0, 257).trimEnd()}...`
  }
  const company = String(row?.company || row?.ticker || 'This stock')
  const sector = String(row?.industry || 'its sector')
  const pct = Number(row?.change_percent)
  const pctText = Number.isFinite(pct) ? `${pct >= 0 ? 'rose' : 'fell'} ${Math.abs(pct).toFixed(2)}%` : 'moved'
  return `${company} ${pctText} today and is now one of the notable movers in ${sector}.`
}

function avgVolumeFromHistory(history = []) {
  const rows = Array.isArray(history) ? history : []
  const volumes = rows
    .map((row) => Number(row?.volume))
    .filter((v) => Number.isFinite(v) && v > 0)
  if (!volumes.length) return null
  const sample = volumes.slice(-21, -1)
  const target = sample.length ? sample : volumes
  if (!target.length) return null
  return target.reduce((sum, v) => sum + v, 0) / target.length
}

function spotlightReason({
  volumeSurge,
  distToHighPct,
  distToLowPct,
  absChangePct,
}) {
  if (Number.isFinite(volumeSurge) && volumeSurge >= 1.8) return `Volume surge ${volumeSurge.toFixed(2)}x`
  if (Number.isFinite(distToHighPct) && distToHighPct <= 3.0) return `Near 52W high (${distToHighPct.toFixed(1)}% away)`
  if (Number.isFinite(distToLowPct) && distToLowPct <= 3.0) return `Near 52W low (${distToLowPct.toFixed(1)}% away)`
  if (Number.isFinite(absChangePct) && absChangePct >= 2.2) return `Strong move ${absChangePct.toFixed(2)}%`
  return 'Cross-signal momentum'
}

function MiniChart({ values, kind, color, compact = true, widthOverride, heightOverride, className = '' }) {
  const width = Number(widthOverride) > 0 ? Number(widthOverride) : compact ? 320 : 360
  const height = Number(heightOverride) > 0 ? Number(heightOverride) : compact ? 116 : 132
  const svgClass = `rl-stock-mini-svg ${compact ? '' : 'large'} ${className}`.trim()

  if (!Array.isArray(values) || values.length < 2) {
    return (
      <svg viewBox={`0 0 ${width} ${height}`} className={svgClass} aria-hidden="true">
        <text x="8" y={compact ? '42' : '66'} className="rl-stock-mini-empty">No data</text>
      </svg>
    )
  }

  if (kind === 'bars') {
    const bars = barsGeometry(values, width, height, compact ? 10 : 14)
    return (
      <svg viewBox={`0 0 ${width} ${height}`} className={svgClass} aria-hidden="true">
        {bars.bars.map((bar, idx) => (
          <rect key={`${idx}-${bar.x}`} x={bar.x} y={bar.y} width={bar.w} height={bar.h} rx="2" fill={color} opacity="0.86" />
        ))}
      </svg>
    )
  }

  const line = lineGeometry(values, width, height, compact ? 10 : 14)
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={svgClass} aria-hidden="true">
      <path d={line.areaPath} fill={color} opacity="0.13" />
      <path d={line.path} fill="none" stroke={color} strokeWidth={compact ? '2.2' : '2.6'} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SpotlightHoverChart({ rows, values, color, onOpenDetail }) {
  const [hoverIdx, setHoverIdx] = useState(-1)
  const width = 760
  const height = 220
  const chartRows = Array.isArray(rows) ? rows : []
  const series = Array.isArray(values) && values.length ? values : numericSeries(chartRows, 'close')

  if (!Array.isArray(series) || series.length < 2) {
    return (
      <MiniChart
        values={series}
        kind="line"
        compact={false}
        widthOverride={width}
        heightOverride={height}
        className="spotlight"
        color={color}
      />
    )
  }

  const line = lineGeometry(series, width, height, 12)
  const hasHover = hoverIdx >= 0
  const resolvedHoverIdx = hasHover ? Math.max(0, Math.min(hoverIdx, line.points.length - 1)) : -1
  const hoveredPoint = resolvedHoverIdx >= 0 ? line.points[resolvedHoverIdx] : null
  const hoveredRow = resolvedHoverIdx >= 0 ? (chartRows[resolvedHoverIdx] || null) : null
  const hoveredClose = Number(hoveredPoint?.v)
  const prevClose = resolvedHoverIdx > 0 ? Number(line.points[resolvedHoverIdx - 1]?.v) : Number.NaN
  const pointDelta = Number.isFinite(hoveredClose) && Number.isFinite(prevClose) ? hoveredClose - prevClose : Number.NaN
  const pointDeltaPct = Number.isFinite(pointDelta) && Number.isFinite(prevClose) && prevClose !== 0
    ? (pointDelta / prevClose) * 100
    : Number.NaN

  const onPointerMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const x = e.clientX - rect.left
    const xNorm = Math.max(0, Math.min(1, x / Math.max(1, rect.width)))
    const idx = Math.round(xNorm * (line.points.length - 1))
    setHoverIdx(Math.max(0, Math.min(idx, line.points.length - 1)))
  }

  const leftPct = hoveredPoint ? (hoveredPoint.x / width) * 100 : 50
  const topPct = hoveredPoint ? (hoveredPoint.y / height) * 100 : 24
  const midIndex = Math.floor((line.points.length - 1) / 2)
  const xLeft = chartRows[0]?.date || ''
  const xMid = chartRows[midIndex]?.date || ''
  const xRight = chartRows[chartRows.length - 1]?.date || ''
  const yTop = line.max
  const yMid = (line.max + line.min) / 2
  const yBottom = line.min
  const showTimeAxis = chartRows.some((row) => isIntradayLabel(row?.date))

  return (
    <div className="rl-stock-spotlight-hover-wrap">
      {hasHover && hoveredPoint && hoveredRow ? (
        <div
          className="rl-stock-spotlight-tooltip"
          style={{
            left: `clamp(124px, ${leftPct}%, calc(100% - 124px))`,
            top: `clamp(24px, ${topPct}%, calc(100% - 90px))`,
          }}
        >
          <strong>{hoveredRow.date || '—'}</strong>
          <span>Close {fmtPrice(hoveredClose)}</span>
          <em className={toneClass(pointDelta)}>{Number.isFinite(pointDelta) ? `${fmtSigned(pointDelta)} (${fmtPctPlain(pointDeltaPct)})` : '—'}</em>
          <em>Vol {fmtCompact(hoveredRow.volume)}</em>
        </div>
      ) : null}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="rl-stock-mini-svg spotlight interactive"
        aria-label="spotlight chart"
        onMouseMove={onPointerMove}
        onMouseLeave={() => setHoverIdx(-1)}
        onClick={onOpenDetail}
        role="img"
      >
        <line x1="12" x2={width - 12} y1="12" y2="12" className="rl-stock-spotlight-axis-grid" />
        <line x1="12" x2={width - 12} y1={height / 2} y2={height / 2} className="rl-stock-spotlight-axis-grid" />
        <line x1="12" x2={width - 12} y1={height - 12} y2={height - 12} className="rl-stock-spotlight-axis-line" />
        <line x1="12" x2="12" y1="12" y2={height - 12} className="rl-stock-spotlight-axis-line" />

        <text x="16" y="22" className="rl-stock-spotlight-axis-label">{fmtPrice(yTop)}</text>
        <text x="16" y={(height / 2) + 4} className="rl-stock-spotlight-axis-label">{fmtPrice(yMid)}</text>
        <text x="16" y={height - 18} className="rl-stock-spotlight-axis-label">{fmtPrice(yBottom)}</text>

        <path d={line.areaPath} fill={color} opacity="0.13" />
        <path d={line.path} fill="none" stroke={color} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        {hasHover && hoveredPoint ? (
          <>
            <line
              x1={hoveredPoint.x}
              x2={hoveredPoint.x}
              y1="8"
              y2={height - 8}
              stroke={color}
              strokeOpacity="0.3"
              strokeWidth="1.1"
              strokeDasharray="4 4"
            />
            <circle cx={hoveredPoint.x} cy={hoveredPoint.y} r="4.8" fill="#ffffff" stroke={color} strokeWidth="2.3" />
          </>
        ) : null}
        <text x="12" y={height - 1} className="rl-stock-spotlight-axis-label axis-x" textAnchor="start">{fmtDateAxis(xLeft, showTimeAxis)}</text>
        <text x={width / 2} y={height - 1} className="rl-stock-spotlight-axis-label axis-x" textAnchor="middle">{fmtDateAxis(xMid, showTimeAxis)}</text>
        <text x={width - 12} y={height - 1} className="rl-stock-spotlight-axis-label axis-x" textAnchor="end">{fmtDateAxis(xRight, showTimeAxis)}</text>
      </svg>
    </div>
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

function isInvalidTickerMessage(msg) {
  const s = String(msg || '').toLowerCase()
  if (!s) return false
  return (
    s.includes('symbol') && s.includes('invalid')
  ) || s.includes('figi') || s.includes('provide a valid symbol')
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
  const [unsupportedTickers, setUnsupportedTickers] = useState([])
  const [recordsLoading, setRecordsLoading] = useState(true)
  const [boardTab, setBoardTab] = useState('gainers')
  const [showAddTicker, setShowAddTicker] = useState(false)
  const [addTickerInput, setAddTickerInput] = useState('')
  const [filingRecordsMap, setFilingRecordsMap] = useState({})
  const [detailTablesMap, setDetailTablesMap] = useState({})
  const [detailTableLoading, setDetailTableLoading] = useState(false)
  const [detailTableSection, setDetailTableSection] = useState('income_statement')
  const [detailActiveRecordId, setDetailActiveRecordId] = useState('')
  const [detailMainTab, setDetailMainTab] = useState('overview')
  const [heatmapHover, setHeatmapHover] = useState(null)
  const [marketIntelItems, setMarketIntelItems] = useState([])
  const [marketIntelLoading, setMarketIntelLoading] = useState(false)
  const [marketSummaryOpenIdx, setMarketSummaryOpenIdx] = useState(0)

  const initializedRef = useRef(false)
  const heatmapWrapRef = useRef(null)
  const unsupportedTickerSet = useMemo(
    () => new Set((Array.isArray(unsupportedTickers) ? unsupportedTickers : []).map((t) => normalizeTicker(t)).filter(Boolean)),
    [unsupportedTickers],
  )

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
        const errMsg = String(e?.message || '')
        if (isInvalidTickerMessage(errMsg)) {
          setUnsupportedTickers((prev) => {
            const next = new Set(Array.isArray(prev) ? prev.map((t) => normalizeTicker(t)) : [])
            next.add(sym)
            return Array.from(next)
          })
        }
        if (!hasCached) {
          if (!muteError) setError(errMsg || `Failed to load ${sym}`)
          if (!muteStatus) setStatusHint('')
        } else if (cachedPayload?.data) {
          if (!muteStatus) setStatusHint(buildBundleHint({ ...cachedPayload.data, warning: errMsg || 'refresh failed' }, 'cache'))
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
    if (!marketIntelItems.length) {
      setMarketSummaryOpenIdx(0)
      return
    }
    setMarketSummaryOpenIdx((prev) => (prev >= 0 && prev < marketIntelItems.length ? prev : 0))
  }, [marketIntelItems])

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
    const uploadedTickers = uploadedCompanies.map((c) => c.ticker).filter((tk) => !unsupportedTickerSet.has(tk))
    setWatchlist((prev) => mergeTickers(uploadedTickers, prev, DEFAULT_TICKERS).slice(0, 14))
    if (!normalizeTicker(selectedTicker)) {
      setSelectedTicker(uploadedTickers[0])
    }
  }, [uploadedCompanies, selectedTicker, unsupportedTickerSet])

  const supportedUploadedCompanies = useMemo(
    () => uploadedCompanies.filter((c) => !unsupportedTickerSet.has(c.ticker)),
    [uploadedCompanies, unsupportedTickerSet],
  )

  useEffect(() => {
    if (!supportedUploadedCompanies.length) {
      setFeaturedCompanies([])
      return
    }
    const shuffled = [...supportedUploadedCompanies]
    for (let i = shuffled.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1))
      const tmp = shuffled[i]
      shuffled[i] = shuffled[j]
      shuffled[j] = tmp
    }
    setFeaturedCompanies(shuffled.slice(0, 9))
  }, [supportedUploadedCompanies])

  useEffect(() => {
    if (!selectedTicker) return
    fetchBundle(selectedTicker, { preferCache: true, skipIfFresh: true })
  }, [selectedTicker, fetchBundle])

  useEffect(() => {
    const selected = normalizeTicker(selectedTicker)
    if (!selected || !unsupportedTickerSet.has(selected)) return
    const fallback = supportedUploadedCompanies[0]?.ticker || DEFAULT_TICKERS.find((tk) => !unsupportedTickerSet.has(normalizeTicker(tk))) || ''
    if (fallback && fallback !== selected) setSelectedTicker(fallback)
  }, [selectedTicker, unsupportedTickerSet, supportedUploadedCompanies])

  useEffect(() => {
    const candidates = mergeTickers(
      [selectedTicker],
      featuredCompanies.map((c) => c.ticker),
    )
      .filter((tk) => !unsupportedTickerSet.has(tk))
      .slice(0, 10)

    if (!candidates.length) return

    const timers = []
    candidates.forEach((tk, idx) => {
      if (tk === selectedTicker) return
      const timer = window.setTimeout(() => {
        fetchBundle(tk, {
          preferCache: true,
          silent: true,
          skipIfFresh: true,
          remember: false,
          muteError: true,
          muteStatus: true,
        })
      }, 700 + idx * 500)
      timers.push(timer)
    })

    return () => {
      timers.forEach((id) => window.clearTimeout(id))
    }
  }, [selectedTicker, featuredCompanies, fetchBundle, unsupportedTickerSet])

  useEffect(() => {
    const sectorTickers = mergeTickers(
      ...Object.values(SECTOR_BENCHMARK_CANDIDATES).map((arr) => (Array.isArray(arr) ? arr : [])),
    )
    const timers = []
    sectorTickers.forEach((ticker, idx) => {
      const quick = window.setTimeout(() => {
        fetchBundle(ticker, {
          preferCache: true,
          silent: true,
          skipIfFresh: true,
          remember: false,
          muteError: true,
          muteStatus: true,
          lite: true,
        })
      }, 700 + idx * 260)
      timers.push(quick)

      const retry = window.setTimeout(() => {
        fetchBundle(ticker, {
          preferCache: true,
          silent: true,
          skipIfFresh: false,
          remember: false,
          muteError: true,
          muteStatus: true,
          lite: true,
        })
      }, 10000 + idx * 320)
      timers.push(retry)
    })
    return () => timers.forEach((id) => window.clearTimeout(id))
  }, [fetchBundle])

  useEffect(() => {
    const timers = []
    MARKET_OVERVIEW_TICKERS.forEach((item, idx) => {
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
      }, 500 + idx * 380)
      timers.push(timer)
    })
    return () => timers.forEach((id) => window.clearTimeout(id))
  }, [fetchBundle])

  useEffect(() => {
    let alive = true
    setMarketIntelLoading(true)
    ;(async () => {
      const seeds = [
        { company: 'S&P 500', ticker: 'SPY' },
        { company: 'Nasdaq', ticker: 'QQQ' },
        { company: 'Dow Jones', ticker: 'DIA' },
      ]
      const collected = []
      const seen = new Set()

      for (const seed of seeds) {
        try {
          const q = new URLSearchParams({
            company: seed.company,
            ticker: seed.ticker,
            days: '2',
            limit: '12',
          })
          const res = await get(`/api/news?${q.toString()}`)
          const items = Array.isArray(res?.items) ? res.items : []
          for (const row of items) {
            const title = String(row?.title || '').trim()
            if (!title) continue
            const normalized = {
              title,
              summary: String(row?.summary || '').trim(),
              source: String(row?.source || '').trim(),
              published_at: String(row?.published_at || '').trim(),
              url: String(row?.url || '').trim(),
            }
            const key = String(normalized.url || normalized.title).toLowerCase()
            if (!key || seen.has(key)) continue
            seen.add(key)
            collected.push(normalized)
            if (collected.length >= 5) break
          }
        } catch {
          // Keep going to next seed query so we can still fill 5 rows.
        }
        if (collected.length >= 5) break
      }

      if (!alive) return
      setMarketIntelItems(collected.slice(0, 5))
      if (!collected.length) setMarketSummaryOpenIdx(0)
      setMarketIntelLoading(false)
    })()

    return () => {
      alive = false
    }
  }, [])

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
    const tickers = mergeTickers(uploadedCompanies.map((c) => c.ticker), watchlist)
      .filter((tk) => !unsupportedTickerSet.has(tk))
      .slice(0, 18)
    return tickers.map((tk) => {
      const meta = companyMapByTicker[tk] || {}
      const payload = bundleMap[tk]?.data || null
      const company = meta.company || payload?.name || tk
      const changePercent = resolveChangePercent(payload)
      const marketCap = resolveMarketCap(payload)
      const volume = Number.isFinite(Number(payload?.volume))
        ? Number(payload?.volume)
        : Number((Array.isArray(payload?.history) ? payload.history[payload.history.length - 1]?.volume : 0) || 0)
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
        change_percent: changePercent,
        market_cap: marketCap,
        volume,
        riskItems: Number(filingSummary?.latest?.risk_items || 0),
      }
    })
  }, [uploadedCompanies, watchlist, companyMapByTicker, bundleMap, filingSummary?.latest?.risk_items, unsupportedTickerSet])

  const loadedRows = useMemo(() => trackedRows.filter((r) => r.data), [trackedRows])

  const boardRows = useMemo(() => {
    const rows = [...loadedRows]
    if (boardTab === 'losers') rows.sort((a, b) => Number(a.change_percent) - Number(b.change_percent))
    else if (boardTab === 'active') rows.sort((a, b) => Number(b.volume || 0) - Number(a.volume || 0))
    else rows.sort((a, b) => Number(b.change_percent) - Number(a.change_percent))
    return uniqueRowsByCompany(rows, 5)
  }, [loadedRows, boardTab])

  const popularRows = useMemo(() => {
    const merged = [...trackedRows].sort((a, b) => {
      const aData = a.data ? 1 : 0
      const bData = b.data ? 1 : 0
      if (aData !== bData) return bData - aData
      return String(a.company).localeCompare(String(b.company))
    })
    return uniqueRowsByCompany(merged, 5)
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
        const candidates = Array.isArray(SECTOR_BENCHMARK_CANDIDATES[item.industry])
          ? SECTOR_BENCHMARK_CANDIDATES[item.industry]
          : [item.ticker]
        const pickedTicker = candidates.find((tk) => Boolean(bundleMap[normalizeTicker(tk)]?.data)) || item.ticker
        const payload = bundleMap[normalizeTicker(pickedTicker)]?.data || null
        const pct = resolveChangePercent(payload)
        const price = resolvePrice(payload)
        const uploaded = uploadedSectorAgg[item.industry]
        const uploadedPct = uploaded?.count ? uploaded.sumPct / uploaded.count : null
        return {
          industry: item.industry,
          ticker: pickedTicker,
          price: Number.isFinite(price) ? price : undefined,
          avgPct: Number.isFinite(pct) ? pct : (Number.isFinite(uploadedPct) ? uploadedPct : undefined),
        }
      }),
    [bundleMap, uploadedSectorAgg],
  )

  const marketSummaryRows = useMemo(
    () =>
      MARKET_OVERVIEW_TICKERS.map((item) => {
        const payload = bundleMap[item.ticker]?.data || null
        const pct = resolveChangePercent(payload)
        const price = resolvePrice(payload)
        const change = resolveChange(payload)
        const updatedAt = Number(payload?.regular_market_time || payload?.post_market_time || bundleMap[item.ticker]?.savedAt || 0)
        return {
          ...item,
          hasData: Boolean(payload) && (Number.isFinite(price) || Number.isFinite(pct)),
          price: Number.isFinite(price) ? price : null,
          change: Number.isFinite(change) ? change : null,
          pct: Number.isFinite(pct) ? pct : null,
          updatedAt: Number.isFinite(updatedAt) ? updatedAt : 0,
          source: providerLabel(payload?.quote_source || payload?.history_source || ''),
        }
      }),
    [bundleMap],
  )

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

  const leadersCluster = useMemo(() => {
    const gain = [...loadedRows].sort((a, b) => Number(b.change_percent || 0) - Number(a.change_percent || 0)).slice(0, 5)
    const lose = [...loadedRows].sort((a, b) => Number(a.change_percent || 0) - Number(b.change_percent || 0)).slice(0, 5)
    const active = [...loadedRows].sort((a, b) => Number(b.volume || 0) - Number(a.volume || 0)).slice(0, 5)
    return new Set([...gain, ...lose, ...active].map((row) => normalizeTicker(row?.ticker)))
  }, [loadedRows])

  const spotlightRows = useMemo(() => {
    const scored = loadedRows.map((row) => {
      const price = Number(resolvePrice(row?.data))
      const intradayRows = Array.isArray(row?.data?.intraday_history) ? row.data.intraday_history : []
      const spotlightHistory = clipSpotlightHistory(intradayRows.length ? intradayRows : (row?.data?.history || []))
      const absChangePct = Math.abs(Number(row?.change_percent || 0))
      const volNow = Number(row?.volume || 0)
      const volAvg = Number(avgVolumeFromHistory(row?.data?.history || []))
      const volumeSurge = Number.isFinite(volAvg) && volAvg > 0 ? volNow / volAvg : null
      const high52 = Number(row?.data?.high_52)
      const low52 = Number(row?.data?.low_52)
      const distToHighPct = Number.isFinite(price) && Number.isFinite(high52) && high52 > 0
        ? ((high52 - price) / high52) * 100
        : null
      const distToLowPct = Number.isFinite(price) && Number.isFinite(low52) && low52 > 0
        ? ((price - low52) / low52) * 100
        : null
      const cap = Number(row?.market_cap || 0)
      const largeCapPenalty = cap > 1_000_000_000_000 ? 0.45 : cap > 500_000_000_000 ? 0.24 : 0

      const signalA = Math.min(absChangePct, 8) * 0.55
      const signalB = Number.isFinite(volumeSurge) ? Math.min(Math.max(volumeSurge - 1, 0), 3) * 0.9 : 0
      const signalC = Number.isFinite(distToHighPct) ? Math.max(0, 3.6 - distToHighPct) * 0.28 : 0
      const signalD = Number.isFinite(distToLowPct) ? Math.max(0, 3.6 - distToLowPct) * 0.25 : 0
      const signalE = Number(row?.riskItems || 0) > 0 ? 0.16 : 0
      const score = signalA + signalB + signalC + signalD + signalE - largeCapPenalty

      return {
        ...row,
        price: Number.isFinite(price) ? price : null,
        spotlight_history: spotlightHistory,
        closes: numericSeries(spotlightHistory, 'close'),
        volume_surge: volumeSurge,
        dist_to_high_pct: distToHighPct,
        dist_to_low_pct: distToLowPct,
        highlight_score: score,
        highlight_reason: spotlightReason({
          volumeSurge,
          distToHighPct,
          distToLowPct,
          absChangePct,
        }),
      }
    })
      .filter((row) => Number.isFinite(row.highlight_score))
      .sort((a, b) => Number(b.highlight_score) - Number(a.highlight_score))

    const primary = uniqueRowsByCompany(
      scored.filter((row) => !leadersCluster.has(normalizeTicker(row?.ticker))),
      3,
    )
    if (primary.length >= 3) return primary

    const used = new Set(primary.map((row) => normalizeTicker(row?.ticker)))
    const extra = uniqueRowsByCompany(scored.filter((row) => {
      const sym = normalizeTicker(row?.ticker)
      return sym && !used.has(sym)
    }), Math.max(0, 3 - primary.length))
    return uniqueRowsByCompany([...primary, ...extra], 3)
  }, [loadedRows, leadersCluster])

  const marketSummaryUpdatedAt = useMemo(() => {
    const values = marketSummaryRows.map((row) => Number(row.updatedAt || 0)).filter((n) => Number.isFinite(n) && n > 0)
    return values.length ? Math.max(...values) : 0
  }, [marketSummaryRows])

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

  const selectedChange = resolveChange(data)
  const selectedChangePercent = resolveChangePercent(data)
  const selectedMarketCap = resolveMarketCap(data) || trackedRowByTicker[normalizeTicker(selectedTicker)]?.market_cap || null

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

  const updateHeatmapHover = useCallback((event, row) => {
    if (!row) return
    const target = event?.currentTarget
    if (!target || typeof target.getBoundingClientRect !== 'function') return
    const tileRect = target.getBoundingClientRect()
    const wrapRect = heatmapWrapRef.current && typeof heatmapWrapRef.current.getBoundingClientRect === 'function'
      ? heatmapWrapRef.current.getBoundingClientRect()
      : null
    const wrapLeft = wrapRect?.left || 0
    const wrapTop = wrapRect?.top || 0
    const wrapWidth = wrapRect?.width || 0

    const rawX = Number.isFinite(Number(event?.clientX))
      ? (Number(event.clientX) - wrapLeft)
      : ((tileRect.left + tileRect.width / 2) - wrapLeft)
    const rawY = Number.isFinite(Number(event?.clientY))
      ? (Number(event.clientY) - wrapTop)
      : ((tileRect.top + tileRect.height / 2) - wrapTop)

    const placeBelow = rawY < 170
    const minEdge = 18
    const maxEdge = Math.max(minEdge, wrapWidth - minEdge)
    const x = Math.max(minEdge, Math.min(maxEdge, rawX))
    const y = placeBelow ? rawY + 16 : rawY - 12
    if (!Number.isFinite(x) || !Number.isFinite(y)) return
    setHeatmapHover((prev) => {
      if (
        prev?.row?.ticker === row.ticker
        && prev?.placeBelow === placeBelow
        && Math.abs((prev.x || 0) - x) < 0.6
        && Math.abs((prev.y || 0) - y) < 0.6
      ) {
        return prev
      }
      return { x, y, row, placeBelow }
    })
  }, [])

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
      <section className="rl-stock-main-split">
        <div className="rl-stock-main-col">
          <section className="rl-stock-command rl-stock-command-v2">
            <div className="rl-stock-command-head">
              <div>
                <p className="rl-stock-command-title">Tracked Companies</p>
                <span>
                  {recordsLoading
                    ? 'Loading uploaded company universe…'
                    : `${supportedUploadedCompanies.length} companies from uploaded filings`}
                </span>
              </div>
              <button className="btn-secondary" onClick={() => setShowAddTicker((v) => !v)}>
                {showAddTicker ? 'Cancel' : '+ Add Ticker'}
              </button>
            </div>

            <div className="rl-stock-chip-row">
              {featuredCompanies.map((c) => {
                const payload = bundleMap[c.ticker]?.data
                const pct = resolveChangePercent(payload)
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
              <p className={`metric-value ${Number(selectedChangePercent || 0) >= 0 ? 'rl-stock-up' : 'rl-stock-down'}`}>{fmtPct(selectedChangePercent)}</p>
              <span className="rl-stock-metric-sub">Change {fmtPrice(selectedChange)}</span>
            </div>
            <div className="metric-card rl-stock-metric-card">
              <p className="metric-label">Market Cap</p>
              <p className="metric-value !text-[1.05rem]">{fmtCompact(selectedMarketCap)}</p>
              <span className="rl-stock-metric-sub">PE {data?.pe_ratio ? Number(data.pe_ratio).toFixed(2) : '—'}</span>
            </div>
            <div className="metric-card rl-stock-metric-card">
              <p className="metric-label">Uploaded Scope</p>
              <p className="metric-value !text-[1.05rem]">{uploadedCompanies.length}</p>
              <span className="rl-stock-metric-sub">companies with filing context</span>
            </div>
          </section>

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
              <span>{marketSummaryUpdatedAt ? `Updated ${timeAgoFrom(marketSummaryUpdatedAt)}` : ''}</span>
            </div>
            <div className="rl-stock-market-news">
              {marketIntelLoading ? <span className="rl-stock-market-news-empty">Loading market headlines…</span> : null}
              {!marketIntelLoading && !marketIntelItems.length ? <span className="rl-stock-market-news-empty">No market headlines available right now.</span> : null}
              {!marketIntelLoading && marketIntelItems.slice(0, 5).map((item, idx) => {
                const open = marketSummaryOpenIdx === idx
                return (
                  <article key={`mkt-news-${idx}`} className={`rl-stock-market-news-item ${open ? 'open' : ''}`}>
                    <button
                      type="button"
                      className="rl-stock-market-news-head"
                      onClick={() => setMarketSummaryOpenIdx((prev) => (prev === idx ? -1 : idx))}
                    >
                      <strong>{item.title}</strong>
                      <span>{open ? '▴' : '▾'}</span>
                    </button>
                    {open ? (
                      <div className="rl-stock-market-news-body">
                        <p>{item.summary || 'No summary from upstream feed yet.'}</p>
                        <em>
                          {item.source || 'Market feed'} · {item.published_at ? fmtDateOnly(item.published_at) : 'today'}
                          {item.url ? (
                            <>
                              {' '}·{' '}
                              <a href={item.url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                                Open source
                              </a>
                            </>
                          ) : null}
                        </em>
                      </div>
                    ) : null}
                  </article>
                )
              })}
            </div>
          </section>

          <section className="rl-stock-side-card rl-stock-heatmap-card">
            <div className="rl-stock-side-head">
              <p>Tracked Heatmap</p>
              <span>Click any tile to open company detail</span>
            </div>
            <div ref={heatmapWrapRef} className="rl-stock-heatmap-unified-wrap" onMouseLeave={() => setHeatmapHover(null)}>
              <div className="rl-stock-heatmap-grid rl-stock-heatmap-grid-unified">
                {heatmapTiles.map((row) => (
                  <button
                    type="button"
                    key={`heat-${row.ticker}`}
                    className={`rl-stock-heatmap-tile tone-${toneClass(row.change_percent)} size-${row.size} intensity-${row.intensity}`}
                    onClick={() => openDetail(row.ticker)}
                    onMouseEnter={(e) => updateHeatmapHover(e, row)}
                    onMouseMove={(e) => updateHeatmapHover(e, row)}
                    title={`${row.ticker} · ${fmtPct(row.change_percent)} · click to open`}
                  >
                    <span>{row.ticker}</span>
                    <em>{fmtPct(row.change_percent)}</em>
                  </button>
                ))}
                {!heatmapTiles.length ? <p className="rl-stock-muted">Load tracked quotes to render heatmap.</p> : null}
              </div>
              {heatmapHover?.row ? (
                <div
                  className={`rl-stock-heatmap-tooltip ${heatmapHover.placeBelow ? 'below' : 'above'}`}
                  style={{
                    left: `${heatmapHover.x}px`,
                    top: `${heatmapHover.y}px`,
                  }}
                >
                  <p>{heatmapHover.row.industry || 'Other'}</p>
                  <div className="rl-stock-heatmap-tooltip-head">
                    <CompanyLogo ticker={heatmapHover.row.ticker} company={heatmapHover.row.company} />
                    <div>
                      <strong>{heatmapHover.row.ticker} · {heatmapHover.row.company}</strong>
                      <small>{heatmapHover.row.data?.exchange || 'US'} · Cap {fmtCompact(heatmapHover.row.market_cap)}</small>
                    </div>
                  </div>
                  <span>
                    {fmtPrice(heatmapHover.row.data?.price)} ·{' '}
                    <b className={toneClass(heatmapHover.row.change_percent)}>{fmtPct(heatmapHover.row.change_percent)}</b>
                    {' '}· Vol {fmtCompact(heatmapHover.row.volume)}
                  </span>
                  <em>{heatmapSummaryText(heatmapHover.row)}</em>
                  <i>Click to open company detail</i>
                </div>
              ) : null}
            </div>
          </section>

          <section className="rl-stock-side-card rl-stock-spotlight-card">
            <div className="rl-stock-side-head">
              <p>Spotlight Stocks</p>
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
                      <strong>{fmtPrice(row.price ?? row.data?.price)}</strong>
                      <em className={toneClass(row.change_percent)}>{fmtPct(row.change_percent)}</em>
                    </div>
                  </div>

                  <div className="rl-stock-spotlight-body rl-stock-spotlight-body-rich">
                    <div className="rl-stock-spotlight-chart rl-stock-spotlight-chart-large">
                      <SpotlightHoverChart
                        rows={Array.isArray(row.spotlight_history) ? row.spotlight_history : []}
                        values={Array.isArray(row.closes) ? row.closes : []}
                        color={chartColorFor(row.closes, '#22c55e', '#ef4444')}
                        onOpenDetail={() => openDetail(row.ticker)}
                      />
                    </div>
                    <div className="rl-stock-spotlight-stats rl-stock-spotlight-stats-rich">
                      <span><b>Highlight</b>{row.highlight_reason || 'Notable move'}</span>
                      <span><b>Industry</b>{row.industry || 'Other'}</span>
                      <span><b>Volume</b>{fmtCompact(row.volume)}</span>
                      <span><b>Market Cap</b>{fmtCompact(row.market_cap)}</span>
                    </div>
                  </div>
                  <p className="rl-stock-spotlight-note">{spotlightNarrativeText(row)}</p>
                </article>
              ))}
              {!spotlightRows.length ? <p className="rl-stock-muted">Spotlight is loading from your tracked company set.</p> : null}
            </div>
          </section>
          </div>
        </div>

        <aside className="rl-stock-side">
          <section className="rl-stock-side-card">
            <div className="rl-stock-side-head">
              <p>Popular Companies</p>
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
                  <strong>{Number.isFinite(Number(row.price)) ? fmtPrice(row.price) : row.ticker}</strong>
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
      <>
      {isCompanyView && error ? <div className="rl-up-inline-error">{error}</div> : null}
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
      </>
      )}
    </div>
  )
}
