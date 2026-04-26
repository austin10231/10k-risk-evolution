import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'

const STORAGE_KEY = 'risklens_chat_threads_v1'
const CURRENT_KEY = 'risklens_current_thread_id_v1'

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
    messages: [
      {
        role: 'assistant',
        text: 'Hi, I am RiskLens Agent. Ask naturally and I will plan the best risk analysis path.',
        meta: { timestamp: Date.now(), lang: 'English', tools: ['Risk Synthesis'] },
      },
    ],
  }
}

const ChatMemoryContext = createContext({
  threads: [],
  currentThreadId: '',
  currentThread: null,
  createThread: () => {},
  switchThread: () => {},
  appendMessage: () => {},
  replaceMessages: () => {},
  updateThreadTitle: () => {},
})

function deriveTitleFromMessages(messages) {
  const firstUser = (messages || []).find((m) => m.role === 'user' && String(m.text || '').trim())
  if (!firstUser) return 'New conversation'
  const text = String(firstUser.text || '').trim().replace(/\s+/g, ' ')
  return text.length > 42 ? `${text.slice(0, 42)}…` : text
}

export function ChatMemoryProvider({ children }) {
  const [threads, setThreads] = useState(() => {
    if (typeof window === 'undefined') return [createSeedThread()]
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY)
      if (!raw) return [createSeedThread()]
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) return [createSeedThread()]
      return parsed
    } catch {
      return [createSeedThread()]
    }
  })

  const [currentThreadId, setCurrentThreadId] = useState(() => {
    if (typeof window === 'undefined') return ''
    return window.localStorage.getItem(CURRENT_KEY) || ''
  })

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
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(threads))
  }, [threads])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!currentThreadId) return
    window.localStorage.setItem(CURRENT_KEY, currentThreadId)
  }, [currentThreadId])

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

  const value = {
    threads,
    currentThreadId,
    currentThread,
    createThread,
    switchThread,
    appendMessage,
    replaceMessages,
    updateThreadTitle,
  }

  return <ChatMemoryContext.Provider value={value}>{children}</ChatMemoryContext.Provider>
}

export function useChatMemory() {
  return useContext(ChatMemoryContext)
}

