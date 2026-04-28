const STORAGE_KEY = 'risklens_pending_chat_v1'

export function stashPendingChat(payload) {
  if (typeof window === 'undefined') return
  try {
    const next = {
      text: String(payload?.text || '').trim(),
      originPath: String(payload?.originPath || '/agent'),
      originSearch: String(payload?.originSearch || ''),
      ts: Date.now(),
    }
    if (!next.text) return
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {
    // ignore storage failures
  }
}

export function popPendingChat() {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    window.sessionStorage.removeItem(STORAGE_KEY)
    const parsed = JSON.parse(raw)
    const text = String(parsed?.text || '').trim()
    if (!text) return null
    return {
      text,
      originPath: String(parsed?.originPath || '/agent'),
      originSearch: String(parsed?.originSearch || ''),
      ts: Number(parsed?.ts || 0),
    }
  } catch {
    return null
  }
}
