import React, { createContext, useContext, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { post } from './api'
import { useGlobalConfig } from './globalConfig'
import { useChatMemory } from './chatMemory'

function detectLang(text) {
  return /[\u4e00-\u9fff]/.test(text || '') ? 'Chinese' : 'English'
}

function plannedTools(query, hasConfig, pathname) {
  const q = String(query || '').toLowerCase()
  const route = String(pathname || '')
  const tools = []

  if (q.includes('compare') || q.includes('对比') || route.includes('/compare')) tools.push('Cross-Filing Compare')
  if (route.includes('/tables')) tools.push('Financial Tables')
  if (route.includes('/upload') || q.includes('upload')) tools.push('Filing Ingestion')
  if (q.includes('10-k') || q.includes('10k') || q.includes('risk factor') || q.includes('风险')) tools.push('10-K Risk Analysis')

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
  const unique = Array.from(new Set(tools))
  if (!unique.length) unique.push('General Chat')
  return unique
}

function parseContextFromSearch(search = '') {
  const params = new URLSearchParams(search || '')
  return {
    recordId: String(params.get('record_id') || '').trim(),
    compareRecordId: String(params.get('compare_record_id') || '').trim(),
  }
}

function buildActionPath(response) {
  if (!response || response.type !== 'action' || response.action !== 'navigate') return ''
  const target = String(response.target || '').trim()
  const params = response.params && typeof response.params === 'object' ? response.params : {}

  const baseMap = {
    compare_page: '/compare',
    stock_page: '/stock',
    news_page: '/news',
    upload_page: '/upload',
    analyze_page: '/analyze',
    risk_page: '/analyze',
    chat_page: '/agent',
    agent_page: '/agent',
  }
  let path = baseMap[target] || ''
  if (!path) return ''

  if (path === '/stock' && String(params.ticker || '').trim()) {
    return `/stock/${encodeURIComponent(String(params.ticker).trim().toUpperCase())}`
  }

  const query = new URLSearchParams()
  const allowedKeys = ['record_id', 'compare_record_id', 'company', 'year', 'ticker']
  allowedKeys.forEach((k) => {
    const v = String(params[k] ?? '').trim()
    if (v) query.set(k, v)
  })
  const qs = query.toString()
  return qs ? `${path}?${qs}` : path
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
  const navigate = useNavigate()
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
      const historyPayload = [...messages, { role: 'user', text: userText }]
        .filter((m) => (m?.role === 'user' || m?.role === 'assistant') && String(m?.text || '').trim())
        .slice(-16)
        .map((m) => ({ role: m.role, text: String(m.text || '').trim() }))

      const payload = {
        user_query: userText,
        company: config.company || '',
        year: config.year ? Number(config.year) : 0,
        record_id: options.recordId || context.recordId || '',
        compare_record_id: options.compareRecordId || context.compareRecordId || '',
        history: historyPayload,
        source_page: routePath,
      }
      const res = await post('/api/agent/query', payload)
      const report = res?.report || res?.result || {}
      const structured = report?.response || {}
      const answer =
        (structured?.type === 'text' ? structured?.content : '') ||
        (structured?.type === 'action' ? structured?.message : '') ||
        report?.direct_answer ||
        report?.executive_summary ||
        'I completed the analysis, but no direct answer text was returned.'

      appendMessage(targetThreadId, {
        role: 'assistant',
        text: answer,
        report,
        meta: { lang, tools, timestamp: Date.now(), route: routePath, intent: report?.intent || '', response: structured || null },
      })
      if (options.navigateOnAction !== false) {
        const actionPath = buildActionPath(structured)
        if (actionPath) navigate(actionPath)
      }
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
