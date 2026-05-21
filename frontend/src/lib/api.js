const rawBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080'
export const API_BASE_URL = rawBase.replace(/\/$/, '')
const LEGACY_AUTH_TOKEN_KEYS = ['risklens_id_token', 'id_token', 'access_token', 'token']

function clearLegacyAuthTokens() {
  if (typeof window === 'undefined') return
  for (const key of LEGACY_AUTH_TOKEN_KEYS) {
    try {
      window.localStorage.removeItem(key)
    } catch {}
    try {
      window.sessionStorage.removeItem(key)
    } catch {}
  }
}

export function clearClientAuthState() {
  clearLegacyAuthTokens()
}

async function request(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const timeoutMs = Number(options.timeoutMs || 0)
  const init = { ...options }
  delete init.timeoutMs
  delete init.headers

  const baseHeaders = { ...(options.headers || {}) }
  if (method !== 'GET' && method !== 'HEAD') {
    baseHeaders['Content-Type'] = baseHeaders['Content-Type'] || 'application/json'
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
      credentials: init.credentials || 'include',
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

export function getChatHistory(options = {}) {
  return get('/api/chat/history', { timeoutMs: 12000, cache: 'no-store', ...options })
}

export function saveChatHistory(payload = {}, options = {}) {
  return post('/api/chat/history', payload, { timeoutMs: 12000, cache: 'no-store', ...options })
}

export function exchangeLegacyAuthCode({ code = '', state = '', redirectUri = '', returnTo = '' } = {}) {
  return post(
    '/api/auth/legacy-callback',
    {
      code,
      state,
      redirect_uri: redirectUri,
      return_to: returnTo,
    },
    { timeoutMs: 15000, cache: 'no-store' },
  )
}

function currentReturnTo() {
  if (typeof window === 'undefined') return ''
  return `${window.location.origin}${window.location.pathname}${window.location.search}`
}

function buildAuthUrl(endpoint, returnTo = '', options = {}) {
  const url = new URL(`${API_BASE_URL}${endpoint}`)
  const target = String(returnTo || currentReturnTo()).trim()
  if (target) url.searchParams.set('return_to', target)
  const idp = String(options.idp || options.identityProvider || '').trim()
  const prompt = String(options.prompt || '').trim()
  const loginHint = String(options.loginHint || options.login_hint || '').trim()
  if (idp) url.searchParams.set('idp', idp)
  if (prompt) url.searchParams.set('prompt', prompt)
  if (loginHint) url.searchParams.set('login_hint', loginHint)
  return url.toString()
}

export function startAuthLogin(returnTo = '', options = {}) {
  if (typeof window === 'undefined') return
  clearLegacyAuthTokens()
  window.location.assign(buildAuthUrl('/api/auth/login', returnTo, options))
}

export function startAuthLogout(returnTo = '') {
  if (typeof window === 'undefined') return
  clearLegacyAuthTokens()
  window.location.assign(buildAuthUrl('/api/auth/logout', returnTo))
}
