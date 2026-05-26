import React, { createContext, useContext, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { post } from './api'
import { useGlobalConfig } from './globalConfig'
import { useChatMemory } from './chatMemory'

const MAX_CHAT_UPLOAD_BYTES = 40 * 1024 * 1024
const CHAT_UPLOAD_ACCEPT_EXT = new Set(['html', 'htm', 'pdf'])

function detectLang(text) {
  return /[\u4e00-\u9fff]/.test(text || '') ? 'Chinese' : 'English'
}

function toBase64DataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('Failed to read file'))
    reader.readAsDataURL(file)
  })
}

function fileExt(name = '') {
  const n = String(name || '').trim().toLowerCase()
  const idx = n.lastIndexOf('.')
  return idx >= 0 ? n.slice(idx + 1) : ''
}

function inferYearFromName(name = '') {
  const m = String(name || '').match(/\b(19|20)\d{2}\b/)
  if (!m) return 0
  const y = Number(m[0])
  return Number.isFinite(y) ? y : 0
}

function inferCompanyFromName(name = '') {
  const base = String(name || '').replace(/\.[^.]+$/, '')
  const cleaned = base
    .replace(/[_\-]+/g, ' ')
    .replace(/\b(10k|10-k|annual report|form)\b/gi, ' ')
    .replace(/\b(19|20)\d{2}\b/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (!cleaned) return ''
  return cleaned
    .split(' ')
    .map((token) => token.slice(0, 1).toUpperCase() + token.slice(1))
    .join(' ')
}

function plannedTools(query, hasConfig, pathname, hasAttachment = false) {
  const q = String(query || '').toLowerCase()
  const route = String(pathname || '')
  const tools = []

  if (q.includes('compare') || q.includes('对比') || route.includes('/compare')) tools.push('Cross-Filing Compare')
  if (route.includes('/tables')) tools.push('Financial Tables')
  if (hasAttachment || route.includes('/upload') || q.includes('upload')) tools.push('Filing Ingestion')
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
  // Keep stock/news answers in chat even if backend returns legacy navigate actions.
  if (target === 'stock_page' || target === 'news_page') return ''
  const params = response.params && typeof response.params === 'object' ? response.params : {}

  const baseMap = {
    compare_page: '/compare',
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
  pendingAttachment: null,
  attachFile: () => ({ ok: false, error: '' }),
  clearPendingAttachment: () => {},
})

export function WorkspaceChatProvider({ children }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { config } = useGlobalConfig()
  const { currentThread, currentThreadId, appendMessage, createThread, addThreadRecordId, updateMessageMeta } = useChatMemory()

  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [pendingAttachment, setPendingAttachment] = useState(null)

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

  const attachFile = (file) => {
    if (!file) return { ok: false, error: 'No file selected.' }
    const size = Number(file.size || 0)
    const ext = fileExt(file.name)
    if (!CHAT_UPLOAD_ACCEPT_EXT.has(ext)) {
      return { ok: false, error: 'Chat upload supports 10-K/10-Q HTML, HTM, or PDF files.' }
    }
    if (size <= 0) return { ok: false, error: 'File is empty.' }
    if (size > MAX_CHAT_UPLOAD_BYTES) {
      return { ok: false, error: 'File too large for chat upload (max 40MB).' }
    }
    setPendingAttachment({
      id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      file,
      name: String(file.name || 'upload.html'),
      size,
      ext,
    })
    return { ok: true, error: '' }
  }

  const clearPendingAttachment = () => setPendingAttachment(null)

  const send = async (forcedQuery, options = {}) => {
    const userText = String(forcedQuery ?? query).trim()
    if (!userText || loading) return null

    const lang = detectLang(userText)
    const hasGlobalConfig = Boolean(config.company || config.year || config.ticker || config.industry)
    const routePath = options.pathname || location.pathname || '/agent'
    const routeSearch = options.search ?? location.search ?? ''
    const context = parseContextFromSearch(routeSearch)
    const threadRecordId = String(currentThread?.context?.recordIds?.[0] || '').trim()
    const attachment = options.attachment || pendingAttachment
    const tools = plannedTools(userText, hasGlobalConfig, routePath, Boolean(attachment?.file))

    const createdId = !currentThreadId ? createThread() : ''
    const targetThreadId = currentThreadId || currentThread?.id || createdId
    if (!targetThreadId) return null

    let uploadedRecordId = ''
    const userMessageId = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const optimisticAttachmentMeta = attachment?.file
      ? {
          name: attachment.name,
          size: Number(attachment.size || 0),
          ext: attachment.ext,
          recordId: '',
          company: String(config.company || inferCompanyFromName(attachment.name) || '').trim(),
          year: Number(config.year || inferYearFromName(attachment.name) || 0),
          status: 'uploading',
        }
      : null

    setQuery('')
    if (attachment?.file) clearPendingAttachment()
    setLoading(true)
    setError('')

    appendMessage(targetThreadId, {
      role: 'user',
      text: userText,
      report: null,
      meta: { messageId: userMessageId, lang, timestamp: Date.now(), route: routePath, attachment: optimisticAttachmentMeta },
    })

    if (attachment?.file) {
      try {
        const companyGuess = String(config.company || inferCompanyFromName(attachment.name) || '').trim()
        const company = companyGuess || 'Uploaded Filing'
        const yearGuess = Number(config.year || inferYearFromName(attachment.name) || new Date().getFullYear())
        const industry = String(config.industry || 'Other').trim() || 'Other'
        const dataUrl = await toBase64DataUrl(attachment.file)
        const fileB64 = dataUrl.includes(',') ? dataUrl.split(',', 2)[1] : dataUrl
        const uploadRes = await post('/api/upload/manual', {
          company,
          ticker: String(config.ticker || '').trim().toUpperCase(),
          industry,
          year: yearGuess,
          filing_type: '10-K',
          file_name: attachment.name,
          file_b64: fileB64,
        })
        uploadedRecordId = String(uploadRes?.record?.record_id || '').trim()
        if (!uploadedRecordId) {
          throw new Error('The file uploaded, but no filing record was returned. Please try again.')
        }
        if (uploadedRecordId) addThreadRecordId(targetThreadId, uploadedRecordId)
        updateMessageMeta(targetThreadId, userMessageId, (currentMeta) => ({
          attachment: {
            ...(currentMeta?.attachment || {}),
            name: attachment.name,
            size: Number(attachment.size || 0),
            ext: attachment.ext,
            recordId: uploadedRecordId,
            company: String(uploadRes?.record?.company || company),
            year: Number(uploadRes?.record?.year || yearGuess),
            status: 'ready',
          },
        }))
      } catch (uploadErr) {
        const msg = uploadErr?.message || 'File upload failed'
        updateMessageMeta(targetThreadId, userMessageId, (currentMeta) => ({
          attachment: {
            ...(currentMeta?.attachment || {}),
            status: 'failed',
          },
        }))
        setError(msg)
        setQuery(userText)
        setPendingAttachment(attachment)
        appendMessage(targetThreadId, {
          role: 'assistant',
          text: `I could not upload the attached file: ${msg}`,
          report: null,
          meta: { lang, tools, timestamp: Date.now(), route: routePath },
        })
        setLoading(false)
        return targetThreadId
      }
    }

    try {
      const historyPayload = [...messages, { role: 'user', text: userText }]
        .filter((m) => (m?.role === 'user' || m?.role === 'assistant') && String(m?.text || '').trim())
        .slice(-16)
        .map((m) => ({ role: m.role, text: String(m.text || '').trim() }))

      const payload = {
        user_query: userText,
        company: config.company || '',
        year: config.year ? Number(config.year) : 0,
        record_id: options.recordId || uploadedRecordId || context.recordId || threadRecordId || '',
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
    clearPendingAttachment()
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
    pendingAttachment,
    attachFile,
    clearPendingAttachment,
  }

  return <WorkspaceChatContext.Provider value={value}>{children}</WorkspaceChatContext.Provider>
}

export function useWorkspaceChat() {
  return useContext(WorkspaceChatContext)
}
