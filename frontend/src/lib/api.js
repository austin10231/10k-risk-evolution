const rawBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080'
export const API_BASE_URL = rawBase.replace(/\/$/, '')

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

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

export function get(path) {
  return request(path, { method: 'GET' })
}

export function post(path, body = {}) {
  return request(path, { method: 'POST', body: JSON.stringify(body) })
}
