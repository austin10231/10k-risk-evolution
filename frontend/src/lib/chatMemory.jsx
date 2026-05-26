import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { getChatHistory, saveChatHistory } from './api'

const STORAGE_KEY = 'risklens_chat_threads_v1'
const CURRENT_KEY = 'risklens_current_thread_id_v1'
const SCOPE_KEY = 'risklens_chat_scope_v1'
const SCOPE_EVENT = 'risklens-chat-scope-changed'

function uid() {
  return `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

function createSeedThread() {
  const id = uid()
  return {
    id,
    title: 'New conversation',
    createdAt: Date.now(),
    updatedAt: Date.now(),
    messages: [],
    context: { recordIds: [] },
  }
}

function normalizeThread(raw) {
  const base = raw && typeof raw === 'object' ? raw : {}
  const context = base.context && typeof base.context === 'object' ? base.context : {}
  const recordIds = Array.isArray(context.recordIds)
    ? context.recordIds.map((v) => String(v || '').trim()).filter(Boolean)
    : []
  return {
    ...base,
    id: String(base.id || uid()),
    title: String(base.title || 'New conversation'),
    createdAt: Number(base.createdAt || Date.now()),
    updatedAt: Number(base.updatedAt || Date.now()),
    messages: Array.isArray(base.messages) ? base.messages : [],
    context: { ...context, recordIds },
  }
}

function normalizeScope(raw) {
  const txt = String(raw || '').trim()
  if (!txt) return 'guest'
  return txt.slice(0, 128)
}

function scopeStorageKey(scope) {
  return `${STORAGE_KEY}:${normalizeScope(scope)}`
}

function scopeCurrentKey(scope) {
  return `${CURRENT_KEY}:${normalizeScope(scope)}`
}

function readScopeFromStorage() {
  if (typeof window === 'undefined') return 'guest'
  try {
    return normalizeScope(window.localStorage.getItem(SCOPE_KEY) || 'guest')
  } catch {
    return 'guest'
  }
}

function readThreadsForScope(scope) {
  if (typeof window === 'undefined') return [createSeedThread()]
  try {
    const normalizedScope = normalizeScope(scope)
    let raw = window.localStorage.getItem(scopeStorageKey(normalizedScope))
    if (!raw && normalizedScope === 'guest') {
      raw = window.localStorage.getItem(STORAGE_KEY)
    }
    if (!raw) return [createSeedThread()]
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || parsed.length === 0) return [createSeedThread()]
    return parsed.map(normalizeThread)
  } catch {
    return [createSeedThread()]
  }
}

function readCurrentThreadIdForScope(scope) {
  if (typeof window === 'undefined') return ''
  try {
    const normalizedScope = normalizeScope(scope)
    let value = String(window.localStorage.getItem(scopeCurrentKey(normalizedScope)) || '').trim()
    if (!value && normalizedScope === 'guest') {
      value = String(window.localStorage.getItem(CURRENT_KEY) || '').trim()
    }
    return value
  } catch {
    return ''
  }
}

function isUserScope(scope) {
  return normalizeScope(scope).startsWith('user:')
}

function isMeaningfulThread(thread) {
  if (!thread || typeof thread !== 'object') return false
  if (Array.isArray(thread.messages) && thread.messages.length > 0) return true
  if (Array.isArray(thread.context?.recordIds) && thread.context.recordIds.length > 0) return true
  return String(thread.title || '').trim() && String(thread.title || '').trim() !== 'New conversation'
}

function normalizeThreadList(rawThreads) {
  const list = Array.isArray(rawThreads) ? rawThreads : []
  const seen = new Set()
  const out = []
  for (const item of list) {
    const thread = normalizeThread(item)
    if (!thread.id || seen.has(thread.id)) continue
    seen.add(thread.id)
    out.push(thread)
  }
  return out
}

function mergeThreadLists(primaryThreads, secondaryThreads) {
  const byId = new Map()
  for (const thread of [...normalizeThreadList(primaryThreads), ...normalizeThreadList(secondaryThreads)]) {
    const previous = byId.get(thread.id)
    if (!previous || Number(thread.updatedAt || 0) >= Number(previous.updatedAt || 0)) {
      byId.set(thread.id, thread)
    }
  }
  let merged = Array.from(byId.values()).sort((a, b) => Number(b.updatedAt || 0) - Number(a.updatedAt || 0))
  if (merged.some(isMeaningfulThread)) {
    merged = merged.filter(isMeaningfulThread)
  }
  return merged.length ? merged.slice(0, 120) : [createSeedThread()]
}

function buildHistoryPayload(threads, currentThreadId) {
  const normalizedThreads = normalizeThreadList(threads).slice(0, 120)
  const validCurrent = normalizedThreads.some((thread) => thread.id === currentThreadId)
    ? currentThreadId
    : normalizedThreads[0]?.id || ''
  return {
    version: 1,
    savedAt: Date.now(),
    currentThreadId: validCurrent,
    threads: normalizedThreads,
  }
}

function historySignature(threads, currentThreadId) {
  try {
    const payload = buildHistoryPayload(threads, currentThreadId)
    return JSON.stringify({
      currentThreadId: payload.currentThreadId,
      threads: payload.threads,
    })
  } catch {
    return ''
  }
}

export function setChatMemoryScope(scope) {
  if (typeof window === 'undefined') return
  const nextScope = normalizeScope(scope)
  try {
    window.localStorage.setItem(SCOPE_KEY, nextScope)
  } catch {}
  try {
    window.dispatchEvent(new CustomEvent(SCOPE_EVENT, { detail: { scope: nextScope } }))
  } catch {}
}

const ChatMemoryContext = createContext({
  threads: [],
  currentThreadId: '',
  currentThread: null,
  createThread: () => {},
  switchThread: () => {},
  deleteThread: () => {},
  appendMessage: () => {},
  replaceMessages: () => {},
  updateMessageMeta: () => {},
  updateThreadTitle: () => {},
  addThreadRecordId: () => {},
})

function deriveTitleFromMessages(messages) {
  const firstUser = (messages || []).find((m) => m.role === 'user' && String(m.text || '').trim())
  if (!firstUser) return 'New conversation'
  const text = String(firstUser.text || '').trim().replace(/\s+/g, ' ')
  return text.length > 42 ? `${text.slice(0, 42)}…` : text
}

export function ChatMemoryProvider({ children }) {
  const initialScope = readScopeFromStorage()
  const [scope, setScope] = useState(initialScope)
  const [threads, setThreads] = useState(() => readThreadsForScope(initialScope))
  const [currentThreadId, setCurrentThreadId] = useState(() => readCurrentThreadIdForScope(initialScope))
  const scopeRef = useRef(initialScope)
  const cloudReadyScopeRef = useRef(isUserScope(initialScope) ? '' : initialScope)
  const cloudLoadSeqRef = useRef(0)
  const lastSavedCloudSignatureRef = useRef('')

  useEffect(() => {
    scopeRef.current = scope
  }, [scope])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const onScopeEvent = (event) => {
      const next = normalizeScope(event?.detail?.scope || readScopeFromStorage())
      setScope((prev) => (prev === next ? prev : next))
    }
    const onStorage = (event) => {
      if (!event || event.key !== SCOPE_KEY) return
      const next = normalizeScope(event.newValue || readScopeFromStorage())
      setScope((prev) => (prev === next ? prev : next))
    }
    window.addEventListener(SCOPE_EVENT, onScopeEvent)
    window.addEventListener('storage', onStorage)
    return () => {
      window.removeEventListener(SCOPE_EVENT, onScopeEvent)
      window.removeEventListener('storage', onStorage)
    }
  }, [])

  useEffect(() => {
    cloudReadyScopeRef.current = isUserScope(scope) ? '' : scope
    lastSavedCloudSignatureRef.current = ''
    const nextThreads = readThreadsForScope(scope)
    const nextCurrentId = readCurrentThreadIdForScope(scope)
    setThreads(nextThreads)
    if (nextCurrentId && nextThreads.some((t) => t.id === nextCurrentId)) {
      setCurrentThreadId(nextCurrentId)
    } else {
      setCurrentThreadId(nextThreads[0]?.id || '')
    }

    if (!isUserScope(scope)) return undefined

    const loadSeq = cloudLoadSeqRef.current + 1
    cloudLoadSeqRef.current = loadSeq
    let cancelled = false
    getChatHistory()
      .then((res) => {
        if (cancelled || cloudLoadSeqRef.current !== loadSeq || scopeRef.current !== scope) return
        const remoteThreads = normalizeThreadList(res?.threads)
        const localThreads = readThreadsForScope(scope)
        const mergedThreads = mergeThreadLists(remoteThreads, localThreads)
        const remoteCurrent = String(res?.currentThreadId || '').trim()
        const localCurrent = readCurrentThreadIdForScope(scope)
        const nextCurrent =
          (remoteCurrent && mergedThreads.some((t) => t.id === remoteCurrent) && remoteCurrent)
          || (localCurrent && mergedThreads.some((t) => t.id === localCurrent) && localCurrent)
          || mergedThreads[0]?.id
          || ''
        lastSavedCloudSignatureRef.current = historySignature(remoteThreads, remoteCurrent)
        setThreads(mergedThreads)
        setCurrentThreadId(nextCurrent)
        cloudReadyScopeRef.current = scope
      })
      .catch(() => {
        if (cancelled || cloudLoadSeqRef.current !== loadSeq || scopeRef.current !== scope) return
        cloudReadyScopeRef.current = scope
      })
    return () => {
      cancelled = true
    }
  }, [scope])

  useEffect(() => {
    if (!threads.length) {
      const seed = createSeedThread()
      setThreads([seed])
      setCurrentThreadId(seed.id)
      return
    }
    if (!currentThreadId || !threads.some((t) => t.id === currentThreadId)) {
      setCurrentThreadId(threads[0].id)
    }
  }, [threads, currentThreadId])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(scopeStorageKey(scope), JSON.stringify(threads))
  }, [threads, scope])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!currentThreadId) return
    window.localStorage.setItem(scopeCurrentKey(scope), currentThreadId)
  }, [currentThreadId, scope])

  useEffect(() => {
    if (!isUserScope(scope)) return undefined
    if (cloudReadyScopeRef.current !== scope) return undefined
    const signature = historySignature(threads, currentThreadId)
    if (!signature || signature === lastSavedCloudSignatureRef.current) return undefined
    const timer = window.setTimeout(() => {
      const payload = buildHistoryPayload(threads, currentThreadId)
      saveChatHistory(payload)
        .then(() => {
          if (scopeRef.current === scope) {
            lastSavedCloudSignatureRef.current = historySignature(payload.threads, payload.currentThreadId)
          }
        })
        .catch(() => {})
    }, 700)
    return () => window.clearTimeout(timer)
  }, [threads, currentThreadId, scope])

  const currentThread = useMemo(
    () => threads.find((t) => t.id === currentThreadId) || threads[0] || null,
    [threads, currentThreadId],
  )

  const createThread = () => {
    const t = createSeedThread()
    setThreads((prev) => [t, ...prev])
    setCurrentThreadId(t.id)
    return t.id
  }

  const switchThread = (id) => {
    setCurrentThreadId(id)
  }

  const deleteThread = (id) => {
    const nextThreads = (threads || []).filter((t) => t.id !== id)
    if (!nextThreads.length) {
      const seed = createSeedThread()
      setThreads([seed])
      setCurrentThreadId(seed.id)
      return
    }
    setThreads(nextThreads)
    if (currentThreadId === id) {
      setCurrentThreadId(nextThreads[0].id)
    }
  }

  const appendMessage = (threadId, message) => {
    setThreads((prev) =>
      prev.map((t) => {
        if (t.id !== threadId) return t
        const nextMessages = [...(t.messages || []), message]
        return {
          ...t,
          updatedAt: Date.now(),
          title: deriveTitleFromMessages(nextMessages),
          messages: nextMessages,
          context: t.context && typeof t.context === 'object' ? t.context : { recordIds: [] },
        }
      }),
    )
  }

  const replaceMessages = (threadId, messages) => {
    setThreads((prev) =>
      prev.map((t) => {
        if (t.id !== threadId) return t
        return {
          ...t,
          updatedAt: Date.now(),
          title: deriveTitleFromMessages(messages),
          messages,
          context: t.context && typeof t.context === 'object' ? t.context : { recordIds: [] },
        }
      }),
    )
  }

  const updateMessageMeta = (threadId, messageId, nextMeta) => {
    const targetId = String(messageId || '').trim()
    if (!targetId) return
    setThreads((prev) =>
      prev.map((t) => {
        if (t.id !== threadId) return t
        let changed = false
        const nextMessages = (t.messages || []).map((message) => {
          if (String(message?.meta?.messageId || '') !== targetId) return message
          const currentMeta = message.meta && typeof message.meta === 'object' ? message.meta : {}
          const patch = typeof nextMeta === 'function' ? nextMeta(currentMeta) : nextMeta
          const mergedMeta = patch && typeof patch === 'object' ? { ...currentMeta, ...patch } : currentMeta
          changed = true
          return { ...message, meta: mergedMeta }
        })
        if (!changed) return t
        return {
          ...t,
          updatedAt: Date.now(),
          messages: nextMessages,
          context: t.context && typeof t.context === 'object' ? t.context : { recordIds: [] },
        }
      }),
    )
  }

  const updateThreadTitle = (threadId, title) => {
    setThreads((prev) =>
      prev.map((t) => {
        if (t.id !== threadId) return t
        return { ...t, title: title || t.title, updatedAt: Date.now() }
      }),
    )
  }

  const addThreadRecordId = (threadId, recordId) => {
    const nextId = String(recordId || '').trim()
    if (!nextId) return
    setThreads((prev) =>
      prev.map((t) => {
        if (t.id !== threadId) return t
        const current = Array.isArray(t.context?.recordIds) ? t.context.recordIds : []
        const merged = [nextId, ...current.filter((v) => String(v || '').trim() !== nextId)].slice(0, 8)
        return {
          ...t,
          updatedAt: Date.now(),
          context: { ...(t.context || {}), recordIds: merged },
        }
      }),
    )
  }

  const value = {
    threads,
    currentThreadId,
    currentThread,
    createThread,
    switchThread,
    deleteThread,
    appendMessage,
    replaceMessages,
    updateMessageMeta,
    updateThreadTitle,
    addThreadRecordId,
  }

  return <ChatMemoryContext.Provider value={value}>{children}</ChatMemoryContext.Provider>
}

export function useChatMemory() {
  return useContext(ChatMemoryContext)
}
