import React, { createContext, useContext, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { post } from './api'
import { useGlobalConfig } from './globalConfig'
import { useChatMemory } from './chatMemory'

function detectLang(text) {
  return /[\u4e00-\u9fff]/.test(text || '') ? 'Chinese' : 'English'
}

function plannedTools(query, hasConfig, pathname) {
  const q = String(query || '').toLowerCase()
  const route = String(pathname || '')
  const tools = ['Risk Synthesis']

  if (q.includes('compare') || q.includes('对比') || route.includes('/compare')) tools.push('Cross-Filing Compare')
  if (route.includes('/tables')) tools.push('Financial Tables')
  if (route.includes('/upload') || q.includes('upload')) tools.push('Filing Ingestion')

  if (
    q.includes('stock') ||
    q.includes('market') ||
    q.includes('price') ||
    q.includes('ticker') ||
    q.includes('股') ||
    q.includes('市场') ||
    route.includes('/stock')
  ) {
    tools.push('Market Context')
  }

  if (q.includes('news') || q.includes('headline') || q.includes('新闻') || route.includes('/news')) {
    tools.push('News Scan')
  }

  if (hasConfig) tools.push('Global Config Memory')
  return Array.from(new Set(tools))
}

function parseContextFromSearch(search = '') {
  const params = new URLSearchParams(search || '')
  return {
    recordId: String(params.get('record_id') || '').trim(),
    compareRecordId: String(params.get('compare_record_id') || '').trim(),
  }
}

const WorkspaceChatContext = createContext({
  query: '',
  setQuery: () => {},
  send: async () => null,
  loading: false,
  error: '',
  clearError: () => {},
  isConversationStarted: false,
  lastAssistantMessage: null,
  startNewThread: () => '',
})

export function WorkspaceChatProvider({ children }) {
  const location = useLocation()
  const { config } = useGlobalConfig()
  const { currentThread, currentThreadId, appendMessage, createThread } = useChatMemory()

  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const messages = currentThread?.messages || []

  const isConversationStarted = useMemo(
    () => messages.some((m) => m.role === 'user' && String(m.text || '').trim()),
    [messages],
  )

  const lastAssistantMessage = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === 'assistant' && String(messages[i].text || '').trim()) return messages[i]
    }
    return null
  }, [messages])

  const clearError = () => setError('')

  const send = async (forcedQuery, options = {}) => {
    const userText = String(forcedQuery ?? query).trim()
    if (!userText || loading) return null

    const lang = detectLang(userText)
    const hasGlobalConfig = Boolean(config.company || config.year || config.ticker || config.industry)
    const routePath = options.pathname || location.pathname || '/agent'
    const routeSearch = options.search ?? location.search ?? ''
    const context = parseContextFromSearch(routeSearch)
    const tools = plannedTools(userText, hasGlobalConfig, routePath)

    const createdId = !currentThreadId ? createThread() : ''
    const targetThreadId = currentThreadId || currentThread?.id || createdId
    if (!targetThreadId) return null

    appendMessage(targetThreadId, {
      role: 'user',
      text: userText,
      report: null,
      meta: { lang, timestamp: Date.now(), route: routePath },
    })

    setQuery('')
    setLoading(true)
    setError('')

    try {
      const payload = {
        user_query: userText,
        company: config.company || '',
        year: config.year ? Number(config.year) : 0,
        record_id: options.recordId || context.recordId || '',
        compare_record_id: options.compareRecordId || context.compareRecordId || '',
      }
      const res = await post('/api/agent/query', payload)
      const report = res?.report || res?.result || {}
      const answer =
        report?.direct_answer ||
        report?.executive_summary ||
        'I completed the analysis, but no direct answer text was returned.'

      appendMessage(targetThreadId, {
        role: 'assistant',
        text: answer,
        report,
        meta: { lang, tools, timestamp: Date.now(), route: routePath },
      })
      return targetThreadId
    } catch (e) {
      const msg = e.message || 'Agent request failed'
      setError(msg)
      appendMessage(targetThreadId, {
        role: 'assistant',
        text: `I could not complete this run: ${msg}`,
        report: null,
        meta: { lang, tools, timestamp: Date.now(), route: routePath },
      })
      return targetThreadId
    } finally {
      setLoading(false)
    }
  }

  const startNewThread = () => {
    const id = createThread()
    setQuery('')
    setError('')
    return id
  }

  const value = {
    query,
    setQuery,
    send,
    loading,
    error,
    clearError,
    isConversationStarted,
    lastAssistantMessage,
    startNewThread,
  }

  return <WorkspaceChatContext.Provider value={value}>{children}</WorkspaceChatContext.Provider>
}

export function useWorkspaceChat() {
  return useContext(WorkspaceChatContext)
}
