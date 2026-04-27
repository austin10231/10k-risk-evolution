import React, { useMemo, useState } from 'react'
import { get } from '../lib/api'

const FIXED_WINDOW_DAYS = 7
const DEFAULT_LIMIT = 8
const LOAD_STEP = 4
const HOT_COMPANY_TICKERS = ['NVDA', 'MSFT', 'AMZN', 'AAPL', 'AVGO']
const TRENDING_NEWS_TICKERS = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'TSLA']
const WEATHER_COORD_FALLBACK = {
  latitude: 37.3382,
  longitude: -121.8863,
  location: 'San Jose, California',
}

const STOP_WORDS = new Set([
  'the',
  'and',
  'for',
  'with',
  'that',
  'this',
  'from',
  'into',
  'over',
  'after',
  'amid',
  'will',
  'have',
  'has',
  'new',
  'news',
  'market',
  'markets',
  'stock',
  'stocks',
  'company',
  'companies',
  'says',
  'said',
  'report',
  'reports',
])

const THUMB_PALETTES = [
  ['#1e40af', '#0ea5e9'],
  ['#1d4ed8', '#3b82f6'],
  ['#0f766e', '#06b6d4'],
  ['#4338ca', '#2563eb'],
  ['#0369a1', '#0f766e'],
  ['#0f172a', '#334155'],
]

function formatDate(value) {
  if (!value) return 'N/A'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString()
}

function formatAgo(value) {
  if (!value) return 'N/A'
  const d = new Date(value)
  const ts = d.getTime()
  if (Number.isNaN(ts)) return 'N/A'
  const diffMs = Date.now() - ts
  if (diffMs < 0) return 'Just now'
  const min = Math.floor(diffMs / 60000)
  if (min < 1) return 'Just now'
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  const day = Math.floor(hr / 24)
  return `${day}d ago`
}

function publishedTime(v) {
  const ts = new Date(v || '').getTime()
  return Number.isNaN(ts) ? 0 : ts
}

function mergeNews(primary, secondary, maxCount) {
  const seen = new Set()
  const merged = []

  const append = (row) => {
    if (!row || typeof row !== 'object') return
    const key = String(row.url || '').trim() || `${row.title || ''}|${row.source || ''}|${row.published_at || ''}`
    if (!key || seen.has(key)) return
    seen.add(key)
    merged.push(row)
  }

  ;[...(primary || []), ...(secondary || [])].forEach(append)
  merged.sort((a, b) => publishedTime(b?.published_at) - publishedTime(a?.published_at))
  return merged.slice(0, Math.max(1, Number(maxCount || 1)))
}

function formatPrice(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—'
  return `$${Number(v).toFixed(2)}`
}

function formatPct(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—'
  const n = Number(v)
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(2)}%`
}

function weatherTextByCode(code) {
  const n = Number(code)
  if (n === 0) return 'Clear'
  if (n >= 1 && n <= 3) return 'Cloudy'
  if (n >= 45 && n <= 48) return 'Fog'
  if (n >= 51 && n <= 67) return 'Drizzle / Rain'
  if (n >= 71 && n <= 77) return 'Snow'
  if (n >= 80 && n <= 82) return 'Rain Showers'
  if (n >= 95 && n <= 99) return 'Thunderstorm'
  return 'Unknown'
}

function weatherIconByCode(code) {
  const n = Number(code)
  if (n === 0) return '☀️'
  if (n >= 1 && n <= 3) return '⛅'
  if (n >= 45 && n <= 48) return '🌫️'
  if (n >= 51 && n <= 67) return '🌧️'
  if (n >= 71 && n <= 77) return '❄️'
  if (n >= 80 && n <= 82) return '🌦️'
  if (n >= 95 && n <= 99) return '⛈️'
  return '🌡️'
}

async function fetchJsonSafe(url) {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`Request failed: ${resp.status}`)
  return resp.json()
}

function formatGeoLocation(city, region) {
  return [city, region]
    .map((v) => String(v || '').trim())
    .filter(Boolean)
    .join(', ')
}

function getBrowserCoords() {
  return new Promise((resolve, reject) => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      reject(new Error('Geolocation unavailable'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        resolve({
          latitude: Number(pos?.coords?.latitude),
          longitude: Number(pos?.coords?.longitude),
        })
      },
      (err) => reject(err || new Error('Geolocation denied')),
      { enableHighAccuracy: false, timeout: 3200, maximumAge: 5 * 60 * 1000 },
    )
  })
}

async function resolveWeatherGeo() {
  try {
    const fromBrowser = await getBrowserCoords()
    if (Number.isFinite(fromBrowser.latitude) && Number.isFinite(fromBrowser.longitude)) return fromBrowser
  } catch {}

  try {
    const ipWho = await fetchJsonSafe('https://ipwho.is/')
    const lat = Number(ipWho?.latitude)
    const lon = Number(ipWho?.longitude)
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      return {
        latitude: lat,
        longitude: lon,
        location: formatGeoLocation(ipWho?.city, ipWho?.region) || WEATHER_COORD_FALLBACK.location,
      }
    }
  } catch {}

  try {
    const ipApi = await fetchJsonSafe('https://ipapi.co/json/')
    const lat = Number(ipApi?.latitude)
    const lon = Number(ipApi?.longitude)
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      return {
        latitude: lat,
        longitude: lon,
        location: formatGeoLocation(ipApi?.city, ipApi?.region) || WEATHER_COORD_FALLBACK.location,
      }
    }
  } catch {}

  return WEATHER_COORD_FALLBACK
}

async function resolveLocationLabel() {
  try {
    const ipWho = await fetchJsonSafe('https://ipwho.is/')
    const label = formatGeoLocation(ipWho?.city, ipWho?.region)
    if (label) return label
  } catch {}

  try {
    const ipApi = await fetchJsonSafe('https://ipapi.co/json/')
    const label = formatGeoLocation(ipApi?.city, ipApi?.region)
    if (label) return label
  } catch {}

  return WEATHER_COORD_FALLBACK.location
}

function hashSeed(text) {
  let h = 0
  const str = String(text || '')
  for (let i = 0; i < str.length; i += 1) {
    h = (h * 31 + str.charCodeAt(i)) >>> 0
  }
  return h
}

function visualKeyword(item) {
  const source = String(item?.source || '').trim()
  const title = String(item?.title || '').trim()
  const summary = String(item?.summary || '').trim()
  const raw = `${title} ${summary}`.toLowerCase()
  const words = raw
    .split(/[^a-z0-9]+/)
    .filter((w) => w.length >= 4 && !STOP_WORDS.has(w))
    .slice(0, 20)

  const best = words.sort((a, b) => b.length - a.length)[0]
  if (best) return best
  if (source) return source.split(/\s+/)[0]
  return 'news'
}

function makeThumbSvg(label, seed) {
  const hash = hashSeed(seed)
  const palette = THUMB_PALETTES[hash % THUMB_PALETTES.length]
  const accent = (hash % 2 === 0 ? '#ffffff' : '#dbeafe')
  const safeLabel = String(label || 'NEWS').slice(0, 18).toUpperCase()

  const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1200 700'>
    <defs>
      <linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>
        <stop offset='0%' stop-color='${palette[0]}'/>
        <stop offset='100%' stop-color='${palette[1]}'/>
      </linearGradient>
      <filter id='b'>
        <feGaussianBlur stdDeviation='42'/>
      </filter>
    </defs>
    <rect width='1200' height='700' fill='url(#g)'/>
    <circle cx='980' cy='90' r='170' fill='${accent}' fill-opacity='0.12' filter='url(#b)'/>
    <circle cx='220' cy='620' r='210' fill='${accent}' fill-opacity='0.1' filter='url(#b)'/>
    <rect x='74' y='74' width='236' height='44' rx='12' fill='${accent}' fill-opacity='0.2'/>
    <text x='96' y='104' font-size='24' font-family='Inter,Arial,sans-serif' fill='${accent}' fill-opacity='0.95'>RISKLENS NEWS</text>
    <text x='74' y='598' font-size='86' font-weight='700' letter-spacing='3' font-family='Inter,Arial,sans-serif' fill='${accent}' fill-opacity='0.9'>${safeLabel}</text>
  </svg>`

  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`
}

function imageUrlFor(item, idx) {
  const raw =
    String(item?.image_url || '').trim() ||
    String(item?.image || '').trim() ||
    String(item?.thumbnail || '').trim() ||
    String(item?.imageUrl || '').trim()

  if (raw) return raw

  const key = visualKeyword(item)
  return makeThumbSvg(key, `${key}-${idx}`)
}

function NewsImage({ item, idx, alt, className }) {
  const fallback = makeThumbSvg(visualKeyword(item), `fallback-${idx}`)
  return (
    <img
      className={className}
      src={imageUrlFor(item, idx)}
      alt={alt}
      loading="lazy"
      onError={(e) => {
        if (e.currentTarget.src !== fallback) e.currentTarget.src = fallback
      }}
    />
  )
}

function timelineVariant(idx) {
  const step = idx % 7
  if (step === 0 || step === 3) return 'row'
  if (step === 1 || step === 2 || step === 5) return 'tile'
  if (step === 4) return 'row-reverse'
  return 'wide'
}

export default function NewsPage() {
  const [company, setCompany] = useState('')
  const [ticker, setTicker] = useState('')
  const [limit, setLimit] = useState(DEFAULT_LIMIT)
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [keyword, setKeyword] = useState('')
  const [weather, setWeather] = useState(null)
  const [weatherLoading, setWeatherLoading] = useState(false)
  const [hotCompanies, setHotCompanies] = useState([])
  const [hotLoading, setHotLoading] = useState(false)

  React.useEffect(() => {
    let active = true

    const loadWeather = async () => {
      setWeatherLoading(true)
      try {
        const [geo, locationLabel] = await Promise.all([resolveWeatherGeo(), resolveLocationLabel()])
        const lat = Number(geo?.latitude)
        const lon = Number(geo?.longitude)

        const weatherResp = await fetch(
          `https://api.open-meteo.com/v1/forecast?latitude=${encodeURIComponent(String(lat))}&longitude=${encodeURIComponent(String(lon))}&current=temperature_2m,weather_code,wind_speed_10m&timezone=auto`,
        )
        if (!weatherResp.ok) throw new Error(`Open-Meteo error: ${weatherResp.status}`)
        const weatherData = await weatherResp.json()
        const current = weatherData?.current || {}

        if (active) {
          setWeather({
            location: String(locationLabel || WEATHER_COORD_FALLBACK.location),
            temperature: Number(current?.temperature_2m),
            weatherCode: Number(current?.weather_code),
            windSpeed: Number(current?.wind_speed_10m),
          })
        }
      } catch {
        if (active) {
          setWeather({
            location: WEATHER_COORD_FALLBACK.location,
            temperature: Number.NaN,
            weatherCode: Number.NaN,
            windSpeed: Number.NaN,
          })
        }
      } finally {
        if (active) setWeatherLoading(false)
      }
    }

    const loadHotCompanies = async () => {
      setHotLoading(true)
      try {
        const rows = await Promise.all(
          HOT_COMPANY_TICKERS.map(async (sym) => {
            try {
              const res = await get(`/api/stock/quote?ticker=${encodeURIComponent(sym)}`)
              const data = res?.data || {}
              return {
                ticker: sym,
                name: String(data?.name || sym),
                price: data?.price,
                changePercent: data?.change_percent,
              }
            } catch {
              return null
            }
          }),
        )

        if (active) setHotCompanies(rows.filter(Boolean))
      } finally {
        if (active) setHotLoading(false)
      }
    }

    loadWeather()
    loadHotCompanies()

    return () => {
      active = false
    }
  }, [])

  const run = async (nextLimit = limit) => {
    setLoading(true)
    setError('')
    try {
      const companyNorm = String(company || '').trim()
      const tickerNorm = String(ticker || '').trim().toUpperCase()

      if (!companyNorm && !tickerNorm) {
        const generalQ = new URLSearchParams({
          days: String(FIXED_WINDOW_DAYS),
          limit: String(nextLimit),
        })
        const perTickerLimit = Math.max(4, Math.ceil(nextLimit / 2))
        const hotTasks = TRENDING_NEWS_TICKERS.map((sym) => {
          const qHot = new URLSearchParams({
            company: '',
            ticker: sym,
            days: String(FIXED_WINDOW_DAYS),
            limit: String(perTickerLimit),
          })
          return get(`/api/news?${qHot.toString()}`)
        })
        const settled = await Promise.allSettled([get(`/api/news?${generalQ.toString()}`), ...hotTasks])
        const mergedRaw = settled.flatMap((res) =>
          res.status === 'fulfilled' && Array.isArray(res.value?.items) ? res.value.items : [],
        )
        setItems(mergeNews(mergedRaw, [], nextLimit))
      } else {
        const qPrimary = new URLSearchParams({
          company: companyNorm,
          ticker: tickerNorm,
          days: String(FIXED_WINDOW_DAYS),
          limit: String(nextLimit),
        })
        const shouldRunFallback = Boolean(companyNorm && tickerNorm)
        const tasks = [get(`/api/news?${qPrimary.toString()}`)]

        if (shouldRunFallback) {
          const qFallback = new URLSearchParams({
            company: companyNorm,
            ticker: '',
            days: String(FIXED_WINDOW_DAYS),
            limit: String(Math.max(nextLimit * 2, 12)),
          })
          tasks.push(get(`/api/news?${qFallback.toString()}`))
        }

        const settled = await Promise.allSettled(tasks)
        const primaryItems =
          settled[0]?.status === 'fulfilled' && Array.isArray(settled[0].value?.items) ? settled[0].value.items : []
        const fallbackItems =
          settled[1]?.status === 'fulfilled' && Array.isArray(settled[1].value?.items) ? settled[1].value.items : []

        setItems(mergeNews(primaryItems, fallbackItems, nextLimit))
      }

      setLimit(nextLimit)
    } catch (e) {
      setError(e.message || 'Failed to load news')
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  React.useEffect(() => {
    run(DEFAULT_LIMIT)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const keywordNorm = String(keyword || '').trim().toLowerCase()

  const filteredItems = useMemo(() => {
    if (!keywordNorm) return items
    return items.filter((item) => {
      const target = `${item?.title || ''} ${item?.summary || ''} ${item?.source || ''}`.toLowerCase()
      return target.includes(keywordNorm)
    })
  }, [items, keywordNorm])

  const sourceStats = useMemo(() => {
    const map = new Map()
    filteredItems.forEach((item) => {
      const k = String(item.source || 'Unknown')
      map.set(k, (map.get(k) || 0) + 1)
    })
    return Array.from(map.entries()).sort((a, b) => b[1] - a[1])
  }, [filteredItems])

  const featured = filteredItems[0] || null
  const spotlight = filteredItems.slice(1, 4)
  const timeline = filteredItems.slice(4)

  const latestHeadlineTime = featured ? formatDate(featured.published_at) : 'N/A'

  return (
    <div className="rl-page-shell rl-news-v2-page">
      <section className="rl-news-v2-hero">
        <div className="rl-news-v2-hero-left">
          <span className="page-icon">📰</span>
          <div>
            <p className="page-title">News</p>
            <p className="page-subtitle">Discover recent market headlines and scan risk-relevant signals quickly.</p>
          </div>
        </div>
      </section>

      {error ? <div className="rl-news-v2-error">{error}</div> : null}

      <section className="rl-news-v2-command">
        <div className="rl-news-v2-input-group">
          <label className="section-title">Company</label>
          <input className="input mt-2" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="e.g. Apple" />
        </div>

        <div className="rl-news-v2-input-group">
          <label className="section-title">Ticker</label>
          <input
            className="input mt-2"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            placeholder="e.g. AAPL"
          />
        </div>

        <div className="rl-news-v2-input-group rl-news-v2-keyword">
          <label className="section-title">Keyword Filter</label>
          <input
            className="input mt-2"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="Filter by keyword in title / summary / source"
          />
        </div>

        <div className="rl-news-v2-command-action">
          <button className="btn-primary w-full" onClick={() => run(DEFAULT_LIMIT)} disabled={loading}>
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </section>

      <section className="rl-news-v2-layout">
        <div className="rl-news-v2-feed">
          {!loading && filteredItems.length === 0 ? (
            <article className="rl-news-v2-empty">
              <h4>No matching headlines yet</h4>
              <p>
                {items.length
                  ? 'Try another keyword, or clear the filter to see all fetched headlines.'
                  : 'Run a query to load headlines, then refine with a keyword filter.'}
              </p>
            </article>
          ) : null}

          {featured ? (
            <article className="rl-news-v2-feature-card">
              <div className="rl-news-v2-feature-copy">
                <div className="rl-news-v2-meta-row">
                  <span className="rl-news-v2-source">{featured.source || 'Unknown'}</span>
                  <div className="rl-news-v2-meta-stack">
                    <span className="rl-news-v2-time">{formatAgo(featured.published_at)}</span>
                    {featured.url ? (
                      <a className="rl-news-v2-meta-link" href={featured.url} target="_blank" rel="noreferrer">
                        Open source ↗
                      </a>
                    ) : null}
                  </div>
                </div>
                <h3>{featured.title || 'Untitled'}</h3>
                <p>{featured.summary || 'No summary available.'}</p>
                <div className="rl-news-v2-link-row">
                  <span>{formatDate(featured.published_at)}</span>
                </div>
              </div>
              <NewsImage
                item={featured}
                idx={0}
                alt={featured.title || 'headline'}
                className="rl-news-v2-feature-image"
              />
            </article>
          ) : null}

          {spotlight.length ? (
            <div className="rl-news-v2-spot-grid">
              {spotlight.map((item, idx) => (
                <article key={`${item.url || item.title}-spot-${idx}`} className="rl-news-v2-tile-card">
                  <NewsImage item={item} idx={idx + 1} alt={item.title || 'headline'} className="rl-news-v2-tile-image" />
                  <div className="rl-news-v2-tile-body">
                    <div className="rl-news-v2-meta-row">
                      <span className="rl-news-v2-source">{item.source || 'Unknown'}</span>
                      <span className="rl-news-v2-time">{formatAgo(item.published_at)}</span>
                    </div>
                    <h4>{item.title || 'Untitled'}</h4>
                    <p>{item.summary || 'No summary available.'}</p>
                    {item.url ? (
                      <a href={item.url} target="_blank" rel="noreferrer">
                        Open source ↗
                      </a>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          ) : null}

          {timeline.length ? (
            <div className="rl-news-v2-mixed-list">
              {timeline.map((item, idx) => {
                const variant = timelineVariant(idx)
                return (
                  <article key={`${item.url || item.title}-timeline-${idx}`} className={`rl-news-v2-mix-card ${variant}`}>
                    <NewsImage
                      item={item}
                      idx={idx + 20}
                      alt={item.title || 'headline'}
                      className={`rl-news-v2-mix-image ${variant === 'tile' ? 'tile' : 'row'}`}
                    />
                    <div className="rl-news-v2-mix-body">
                      <div className="rl-news-v2-meta-row">
                        <span className="rl-news-v2-source">{item.source || 'Unknown'}</span>
                        <span className="rl-news-v2-time">{formatDate(item.published_at)}</span>
                      </div>
                      <h4>{item.title || 'Untitled'}</h4>
                      <p>{item.summary || 'No summary available.'}</p>
                      {item.url ? (
                        <a href={item.url} target="_blank" rel="noreferrer">
                          Open source ↗
                        </a>
                      ) : null}
                    </div>
                  </article>
                )
              })}
            </div>
          ) : null}

          {filteredItems.length > 0 ? (
            <div className="rl-news-v2-load-row">
              <button className="btn-secondary" onClick={() => run(limit + LOAD_STEP)} disabled={loading}>
                {loading ? 'Loading…' : 'Load More'}
              </button>
              <p>Marketaux free tier may return fewer items per request. Loading more extends the combined feed.</p>
            </div>
          ) : null}
        </div>

        <aside className="rl-news-v2-side">
          <article className="rl-news-v2-side-card">
            <p className="section-title">Focus</p>
            <div className="rl-news-v2-kpi-grid">
              <div>
                <span>Loaded</span>
                <strong>{items.length}</strong>
              </div>
              <div>
                <span>Shown</span>
                <strong>{filteredItems.length}</strong>
              </div>
              <div>
                <span>Top Source</span>
                <strong>{sourceStats[0]?.[0] || '—'}</strong>
              </div>
              <div>
                <span>Latest</span>
                <strong>{latestHeadlineTime === 'N/A' ? '—' : formatAgo(featured?.published_at)}</strong>
              </div>
            </div>
            <p className="rl-news-v2-side-note">Keyword filter updates instantly and keeps your feed focused.</p>
          </article>

          <article className="rl-news-v2-side-card">
            <p className="section-title">Weather</p>
            {weatherLoading ? (
              <p className="rl-news-v2-side-note">Loading local weather…</p>
            ) : weather ? (
              <div className="rl-news-v2-weather-box">
                <div className="rl-news-v2-weather-main">
                  <span>{weatherIconByCode(weather.weatherCode)}</span>
                  <strong>{Number.isFinite(weather.temperature) ? `${Math.round(weather.temperature)}°C` : '—'}</strong>
                </div>
                <p>{weather.location || 'Current location'}</p>
                <p>
                  {weatherTextByCode(weather.weatherCode)}
                  {Number.isFinite(weather.windSpeed) ? ` · Wind ${Math.round(weather.windSpeed)} km/h` : ''}
                </p>
              </div>
            ) : (
              <p className="rl-news-v2-side-note">Weather unavailable right now.</p>
            )}
          </article>

          <article className="rl-news-v2-side-card">
            <p className="section-title">Hot Companies</p>
            <div className="rl-news-v2-hot-list">
              {hotLoading ? (
                <div>
                  <span>Loading quotes…</span>
                  <strong>—</strong>
                </div>
              ) : (
                hotCompanies.slice(0, 5).map((row) => (
                  <div key={row.ticker}>
                    <span title={row.name}>{row.name}</span>
                    <strong>{row.ticker}</strong>
                    <em>{formatPrice(row.price)}</em>
                    <b className={Number(row.changePercent || 0) >= 0 ? 'up' : 'down'}>{formatPct(row.changePercent)}</b>
                  </div>
                ))
              )}
            </div>
          </article>

          <article className="rl-news-v2-side-card">
            <p className="section-title">Top Sources</p>
            <div className="rl-news-v2-source-list">
              {sourceStats.slice(0, 6).map(([name, count]) => (
                <div key={name}>
                  <span>{name}</span>
                  <strong>{count}</strong>
                </div>
              ))}
              {!sourceStats.length ? (
                <div>
                  <span>No source stats yet</span>
                  <strong>—</strong>
                </div>
              ) : null}
            </div>
          </article>
        </aside>
      </section>
    </div>
  )
}
