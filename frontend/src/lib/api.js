const rawBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080'
export const API_BASE_URL = rawBase.replace(/\/$/, '')
const AUTH_TOKEN_KEYS = ['risklens_id_token', 'id_token', 'access_token', 'token']

function captureAuthTokenFromLocation() {
  if (typeof window === 'undefined') return
  try {
    const hash = String(window.location.hash || '')
    const rawQuery = hash.startsWith('#') ? hash.slice(1) : ''
    if (!rawQuery.includes('=')) return
    const params = new URLSearchParams(rawQuery)
    const idToken = String(params.get('id_token') || '').trim()
    const accessToken = String(params.get('access_token') || '').trim()
    const token = idToken || accessToken
    if (!token) return
    window.localStorage.setItem('risklens_id_token', token)
  } catch {}
}

function resolveAuthToken() {
  if (typeof window === 'undefined') return ''
  captureAuthTokenFromLocation()
  for (const key of AUTH_TOKEN_KEYS) {
    const val = String(window.localStorage.getItem(key) || '').trim()
    if (val) return val
    const sessionVal = String(window.sessionStorage.getItem(key) || '').trim()
    if (sessionVal) return sessionVal
  }
  return ''
}

async function request(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const timeoutMs = Number(options.timeoutMs || 0)
  const init = { ...options }
  delete init.timeoutMs

  const baseHeaders = { ...(options.headers || {}) }
  if (method !== 'GET' && method !== 'HEAD') {
    baseHeaders['Content-Type'] = baseHeaders['Content-Type'] || 'application/json'
  }
  const token = resolveAuthToken()
  if (token && !baseHeaders.Authorization) {
    baseHeaders.Authorization = `Bearer ${token}`
  }

  const controller = timeoutMs > 0 ? new AbortController() : null
  const timer = controller
    ? setTimeout(() => {
        try {
          controller.abort()
        } catch {}
      }, timeoutMs)
    : null

  let res
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      headers: baseHeaders,
      ...(controller ? { signal: controller.signal } : {}),
      ...init,
    })
  } catch (err) {
    if (controller && err?.name === 'AbortError') {
      throw new Error('Request timed out. Please try again.')
    }
    throw err
  } finally {
    if (timer) clearTimeout(timer)
  }

  const text = await res.text()
  let payload = {}
  try {
    payload = text ? JSON.parse(text) : {}
  } catch {
    payload = { raw: text }
  }

  if (!res.ok) {
    const msg = payload?.error || payload?.message || `HTTP ${res.status}`
    throw new Error(msg)
  }

  return payload
}

export function get(path, options = {}) {
  return request(path, { method: 'GET', ...options })
}

export function post(path, body = {}, options = {}) {
  return request(path, { method: 'POST', body: JSON.stringify(body), ...options })
}
