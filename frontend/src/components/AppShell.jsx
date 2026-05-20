import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { setChatMemoryScope, useChatMemory } from '../lib/chatMemory'
import { useWorkspaceChat } from '../lib/workspaceChat'
import { stashPendingChat } from '../lib/pendingChat'
import { exchangeLegacyAuthCode, get, startAuthLogin, startAuthLogout } from '../lib/api'
import brandIcon from '../assets/logo-icon.svg'

const WORKSPACE_TABS = [
  { to: '/upload', label_en: 'Upload & Records', label_zh: '上传与记录' },
  { to: '/stock', label_en: 'Stock', label_zh: '股票' },
  { to: '/news', label_en: 'News', label_zh: '新闻' },
  { to: '/dashboard', label_en: 'Dashboard', label_zh: '仪表盘' },
  { to: '/compare', label_en: 'Compare', label_zh: '对比' },
  { to: '/tables', label_en: 'Tables', label_zh: '表格' },
]

const LANDING_QUICK_PROMPTS = {
  en: [
    'Summarize the biggest risk changes for AAPL this year',
    'Compare NVDA vs AMD risk exposure in one table',
    'What signals matter most for Tesla this week?',
    'Find red flags in the latest 10-K filing quickly',
  ],
  zh: [
    '总结一下 AAPL 今年最大的风险变化',
    '用一张表对比 NVDA 和 AMD 的风险暴露',
    '本周 Tesla 最关键的风险信号是什么？',
    '快速找出最新 10-K 里的风险红旗',
  ],
}

const UI_LANG_KEY = 'risklens_ui_lang_v1'
const UI_THEME_KEY = 'risklens_ui_theme_v1'

const ICONS = {
  plus: (
    <>
      <path d="M12 5V19" />
      <path d="M5 12H19" />
    </>
  ),
  menu: (
    <>
      <path d="M4 7H20" />
      <path d="M4 12H20" />
      <path d="M4 17H20" />
    </>
  ),
  close: (
    <>
      <path d="M6 6L18 18" />
      <path d="M18 6L6 18" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M16 16L20.5 20.5" />
    </>
  ),
  more: (
    <>
      <circle cx="6.5" cy="12" r="1.8" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.8" fill="currentColor" stroke="none" />
      <circle cx="17.5" cy="12" r="1.8" fill="currentColor" stroke="none" />
    </>
  ),
  edit: (
    <>
      <path d="M4.5 19.5L8.4 18.8L18.2 9L15 5.8L5.2 15.6L4.5 19.5Z" />
      <path d="M13.8 7L17 10.2" />
    </>
  ),
  trash: (
    <>
      <path d="M4.5 6.5H19.5" />
      <path d="M8 6.5V4.8C8 4.1 8.6 3.5 9.3 3.5H14.7C15.4 3.5 16 4.1 16 4.8V6.5" />
      <path d="M7 6.5V19C7 20 7.8 20.8 8.8 20.8H15.2C16.2 20.8 17 20 17 19V6.5" />
      <path d="M10 10V17" />
      <path d="M14 10V17" />
    </>
  ),
  check: <path d="M5.5 12.5L10 17L18.5 8.5" />,
  home: (
    <>
      <path d="M4.5 11.2L12 5L19.5 11.2" />
      <path d="M6.7 10.5V19H17.3V10.5" />
    </>
  ),
  chevronLeft: <path d="M14.5 6.5L9 12L14.5 17.5" />,
  chevronRight: <path d="M9.5 6.5L15 12L9.5 17.5" />,
  panelSplit: (
    <>
      <rect x="4.2" y="4.2" width="15.6" height="15.6" rx="2.8" />
      <path d="M11.8 4.2V19.8" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <path d="M3.8 12H20.2" />
      <path d="M12 3.8C14.5 6.1 15.9 9.1 15.9 12C15.9 14.9 14.5 17.9 12 20.2" />
      <path d="M12 3.8C9.5 6.1 8.1 9.1 8.1 12C8.1 14.9 9.5 17.9 12 20.2" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4.1" />
      <path d="M12 2.7V5" />
      <path d="M12 19V21.3" />
      <path d="M2.7 12H5" />
      <path d="M19 12H21.3" />
      <path d="M5.4 5.4L7 7" />
      <path d="M17 17L18.6 18.6" />
      <path d="M17 7L18.6 5.4" />
      <path d="M5.4 18.6L7 17" />
    </>
  ),
  moon: (
    <>
      <path d="M15.7 3.6C13.2 4.2 11.2 6.8 11.2 10C11.2 13.7 13.8 16.7 17.1 17.1C16 18.9 14 20 11.7 20C7.9 20 4.8 16.9 4.8 13.1C4.8 8.9 8.1 5.3 12 5.3C13.4 5.3 14.6 5.8 15.7 6.6V3.6Z" />
    </>
  ),
}

function NavIcon({ name, className = '', strokeWidth = 1.8 }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICONS[name] || ICONS.plus}
    </svg>
  )
}

function SubmitArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 17V7" />
      <path d="M7.5 11.5L12 7L16.5 11.5" />
    </svg>
  )
}

function AttachmentFileIcon() {
  return (
    <span className="rl-dock-attachment-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
        <path d="M7 3.8H13.2L18.2 8.8V20.2H7V3.8Z" />
        <path d="M13 3.8V9H18.2" />
      </svg>
    </span>
  )
}

function dockPlaceholder(pathname, lang = 'en') {
  const zh = lang === 'zh'
  if (pathname === '/compare') return zh ? '可问对比变化、差异和风险迁移…' : 'Ask about comparison changes, deltas, or risk shifts…'
  if (String(pathname || '').startsWith('/stock')) return zh ? '可问该股票波动或风险影响…' : 'Ask about this ticker movement or risk implications…'
  if (pathname === '/news') return zh ? '可问这条新闻如何影响风险判断…' : 'Ask how this headline changes risk outlook…'
  if (pathname === '/tables') return zh ? '可问财务表格反映了哪些风险信号…' : 'Ask what this financial table implies for risk…'
  if (pathname === '/upload') return zh ? '可问如何快速上传和解析 filing…' : 'Ask how to ingest or parse a filing quickly…'
  if (pathname === '/dashboard') return zh ? '可问仪表盘里应该优先关注什么…' : 'Ask what to prioritize from this dashboard snapshot…'
  if (pathname === '/library') return zh ? '可问历史 filing 反映了什么趋势…' : 'Ask what this filing history suggests…'
  return zh ? '问任何风险问题…' : 'Ask any risk question…'
}

function formatBytes(bytes) {
  const n = Number(bytes || 0)
  if (!Number.isFinite(n) || n <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let idx = 0
  let value = n
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  return `${value >= 10 ? value.toFixed(0) : value.toFixed(1)} ${units[idx]}`
}

function buildAgentHref(search = '') {
  const src = new URLSearchParams(search || '')
  const next = new URLSearchParams()
  const recordId = String(src.get('record_id') || '').trim()
  const compareRecordId = String(src.get('compare_record_id') || '').trim()
  if (recordId) next.set('record_id', recordId)
  if (compareRecordId) next.set('compare_record_id', compareRecordId)
  const query = next.toString()
  return `/agent${query ? `?${query}` : ''}`
}

function getHistoryMenuPosition(rect) {
  if (typeof window === 'undefined') {
    return { top: rect.bottom + 6, left: rect.left }
  }
  const menuWidth = 148
  const menuHeight = 84
  const viewportPadding = 8
  let left = rect.right - menuWidth
  left = Math.min(Math.max(viewportPadding, left), window.innerWidth - menuWidth - viewportPadding)
  let top = rect.bottom + 6
  if (top + menuHeight > window.innerHeight - viewportPadding) {
    top = Math.max(viewportPadding, rect.top - menuHeight - 6)
  }
  return { top: Math.round(top), left: Math.round(left) }
}

export default function AppShell({ children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { threads, currentThreadId, currentThread, switchThread, deleteThread, updateThreadTitle } = useChatMemory()
  const {
    query,
    setQuery,
    send,
    loading,
    error,
    clearError,
    isConversationStarted,
    startNewThread,
    pendingAttachment,
    attachFile,
    clearPendingAttachment,
  } = useWorkspaceChat()

  const workspaceAppRef = useRef(null)
  const dockRef = useRef(null)
  const isComposingRef = useRef(false)
  const lastCompositionEndAtRef = useRef(0)
  const ignoreNextEnterRef = useRef(false)
  const compositionEndTimerRef = useRef(0)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [threadQuery, setThreadQuery] = useState('')
  const [activeMenuThreadId, setActiveMenuThreadId] = useState('')
  const [activeMenuPosition, setActiveMenuPosition] = useState({ top: 0, left: 0 })
  const [editingThreadId, setEditingThreadId] = useState('')
  const [editingTitle, setEditingTitle] = useState('')
  const [dockFocused, setDockFocused] = useState(false)
  const [dockInlineStyle, setDockInlineStyle] = useState(null)
  const [attachMenuOpen, setAttachMenuOpen] = useState(false)
  const [attachError, setAttachError] = useState('')
  const [authMenuOpen, setAuthMenuOpen] = useState(false)
  const legacyAuthBridgeTriedRef = useRef(false)
  const [viewer, setViewer] = useState({ loading: true, authenticated: false, user: null })
  const fileInputRef = useRef(null)
  const attachMenuRef = useRef(null)
  const attachBtnRef = useRef(null)
  const authMenuRef = useRef(null)

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem('risklens_sidebar_collapsed_v2') === '1'
  })
  const [uiLang, setUiLang] = useState(() => {
    if (typeof window === 'undefined') return 'en'
    const saved = String(window.localStorage.getItem(UI_LANG_KEY) || '').trim().toLowerCase()
    return saved === 'zh' ? 'zh' : 'en'
  })
  const [uiTheme, setUiTheme] = useState(() => {
    if (typeof window === 'undefined') return 'light'
    const saved = String(window.localStorage.getItem(UI_THEME_KEY) || '').trim().toLowerCase()
    return saved === 'dark' ? 'dark' : 'light'
  })

  const i18n = useMemo(() => (uiLang === 'zh'
    ? {
      newChat: '新建聊天',
      history: '历史会话',
      searchConversations: '搜索会话',
      noMatch: '没有匹配会话',
      noConversation: '暂无会话',
      rename: '重命名',
      delete: '删除',
      addFile: '添加文件',
      modelNote: 'RiskLens 可能会犯错，请核实关键信息。',
      topLang: '中文',
      topThemeLight: '浅色',
      topThemeDark: '深色',
      topExpandSidebar: '展开侧栏',
      topCollapseSidebar: '收起侧栏',
      topStartNewChat: '新建聊天',
      authMenu: '账号菜单',
      authSignIn: '登录',
      authSignOut: '退出',
      askLanding: '可问公司、filing、对比、股票或新闻信号…',
      quickPromptsLabel: '快捷问题建议',
      quickPrompts: LANDING_QUICK_PROMPTS.zh,
    }
    : {
      newChat: 'New Chat',
      history: 'History',
      searchConversations: 'Search conversations',
      noMatch: 'No matching conversations',
      noConversation: 'No conversations yet',
      rename: 'Rename',
      delete: 'Delete',
      addFile: 'Add file',
      modelNote: 'RiskLens may make mistakes. Please verify important information.',
      topLang: 'EN',
      topThemeLight: 'Light',
      topThemeDark: 'Dark',
      topExpandSidebar: 'Expand sidebar',
      topCollapseSidebar: 'Collapse sidebar',
      topStartNewChat: 'Start new chat',
      authMenu: 'Account menu',
      authSignIn: 'Sign in',
      authSignOut: 'Sign out',
      askLanding: 'Ask about any company, filing, comparison, stock, or news signal…',
      quickPromptsLabel: 'Quick prompt suggestions',
      quickPrompts: LANDING_QUICK_PROMPTS.en,
    }), [uiLang])

  const historyItems = useMemo(
    () =>
      (threads || [])
        .slice()
        .sort((a, b) => Number(b.updatedAt || 0) - Number(a.updatedAt || 0))
        .slice(0, 50),
    [threads],
  )

  const filteredHistoryItems = useMemo(() => {
    const needle = String(threadQuery || '').trim().toLowerCase()
    if (!needle) return historyItems
    return historyItems.filter((t) => String(t.title || i18n.newChat).toLowerCase().includes(needle))
  }, [historyItems, threadQuery, i18n.newChat])

  const isAgentRoute = location.pathname === '/agent'
  const isNewsRoute = location.pathname === '/news'
  const isStockRoute = String(location.pathname || '').startsWith('/stock')
  const isNewsStyleDockRoute = isNewsRoute || isStockRoute
  const isFocusDockRoute = ['/upload', '/compare', '/dashboard', '/tables'].includes(location.pathname)
  const showLandingComposer = isAgentRoute && !isConversationStarted && !loading
  const dockExpanded = dockFocused || loading || Boolean(String(query || '').trim())
  const activeMenuThread = useMemo(
    () => filteredHistoryItems.find((t) => t.id === activeMenuThreadId) || null,
    [filteredHistoryItems, activeMenuThreadId],
  )

  const markCompositionStart = () => {
    if (compositionEndTimerRef.current && typeof window !== 'undefined') {
      window.clearTimeout(compositionEndTimerRef.current)
      compositionEndTimerRef.current = 0
    }
    isComposingRef.current = true
    ignoreNextEnterRef.current = false
  }

  const markCompositionEnd = () => {
    // Swallow only the IME confirm Enter, then allow immediate submit on next Enter.
    lastCompositionEndAtRef.current = Date.now()
    ignoreNextEnterRef.current = true
    if (typeof window !== 'undefined') {
      if (compositionEndTimerRef.current) window.clearTimeout(compositionEndTimerRef.current)
      compositionEndTimerRef.current = window.setTimeout(() => {
        isComposingRef.current = false
        compositionEndTimerRef.current = 0
      }, 0)
    } else {
      isComposingRef.current = false
    }
  }

  const shouldIgnoreEnterSubmit = (event) => {
    const nativeEvent = event?.nativeEvent || {}
    const key = String(event?.key || nativeEvent.key || '')
    const isEnterKey = key === 'Enter' || key === 'NumpadEnter'
    if (key && key !== 'Enter' && key !== 'NumpadEnter' && key !== 'Process') {
      // User kept typing after composition, do not consume next Enter anymore.
      ignoreNextEnterRef.current = false
      return false
    }
    const keyCode = Number(nativeEvent.keyCode || nativeEvent.which || nativeEvent.charCode || 0)
    const isProcessKey = key === 'Process' || String(nativeEvent.code || '') === 'Process'
    if (isComposingRef.current) return true
    if (nativeEvent.isComposing || event?.isComposing || keyCode === 229 || isProcessKey) return true
    // Some browsers emit compositionend right before Enter keydown.
    const justEndedComposition = Date.now() - Number(lastCompositionEndAtRef.current || 0) < 18
    if (isEnterKey && justEndedComposition && ignoreNextEnterRef.current) {
      ignoreNextEnterRef.current = false
      return true
    }
    return false
  }

  useEffect(() => () => {
    if (compositionEndTimerRef.current && typeof window !== 'undefined') {
      window.clearTimeout(compositionEndTimerRef.current)
      compositionEndTimerRef.current = 0
    }
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem('risklens_sidebar_collapsed_v2', sidebarCollapsed ? '1' : '0')
  }, [sidebarCollapsed])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(UI_LANG_KEY, uiLang)
    try {
      document.documentElement.setAttribute('lang', uiLang === 'zh' ? 'zh-CN' : 'en')
    } catch {}
  }, [uiLang])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(UI_THEME_KEY, uiTheme)
    try {
      document.body.classList.toggle('rl-dark-mode', uiTheme === 'dark')
    } catch {}
  }, [uiTheme])

  const refreshViewer = useCallback(() => {
    let alive = true
    setViewer((prev) => ({ ...prev, loading: true }))
    get('/api/me', { timeoutMs: 9000, cache: 'no-store' })
      .then((res) => {
        if (!alive) return
        const authenticated = Boolean(res?.authenticated)
        const user = res?.user && typeof res.user === 'object' ? res.user : null
        const userId = String(user?.user_id || '').trim()
        setChatMemoryScope(authenticated && userId ? `user:${userId}` : 'guest')
        setViewer({
          loading: false,
          authenticated,
          user,
        })
      })
      .catch(() => {
        if (!alive) return
        setChatMemoryScope('guest')
        setViewer({ loading: false, authenticated: false, user: null })
      })
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    const cleanup = refreshViewer()
    return cleanup
  }, [refreshViewer, location.pathname, location.search])

  useEffect(() => {
    const authState = new URLSearchParams(location.search || '').get('auth')
    if (!authState) return
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(location.search || '')
    params.delete('auth')
    params.delete('reason')
    const next = `${location.pathname}${params.toString() ? `?${params.toString()}` : ''}`
    window.history.replaceState({}, '', next)
  }, [location.pathname, location.search])

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (viewer.loading || viewer.authenticated) return
    if (legacyAuthBridgeTriedRef.current) return
    const params = new URLSearchParams(location.search || '')
    const code = String(params.get('code') || '').trim()
    const state = String(params.get('state') || '').trim()
    const legacyRedirectUri = String(params.get('legacy_redirect_uri') || '').trim()
    const hasLegacyCode = Boolean(code)
    const hasAuthState = Boolean(params.get('auth'))
    if (!hasLegacyCode || hasAuthState) return
    legacyAuthBridgeTriedRef.current = true
    params.delete('code')
    params.delete('state')
    params.delete('scope')
    params.delete('legacy_redirect_uri')
    const cleanReturnTo = `${window.location.origin}${location.pathname}${params.toString() ? `?${params.toString()}` : ''}`
    const cleanPath = `${location.pathname}${params.toString() ? `?${params.toString()}` : ''}`
    window.history.replaceState({}, '', cleanPath)
    exchangeLegacyAuthCode({
      code,
      state,
      redirectUri: legacyRedirectUri || `${window.location.origin}${location.pathname}`,
      returnTo: cleanReturnTo,
    })
      .then((res) => {
        if (res?.authenticated) {
          refreshViewer()
          return
        }
        startAuthLogin(cleanReturnTo, { prompt: 'login select_account' })
      })
      .catch(() => {
        startAuthLogin(cleanReturnTo, { prompt: 'login select_account' })
      })
  }, [location.pathname, location.search, refreshViewer, viewer.loading, viewer.authenticated])

  useEffect(() => {
    if (typeof window === 'undefined') return undefined
    const onFocusOrVisible = () => {
      if (document.visibilityState && document.visibilityState !== 'visible') return
      refreshViewer()
    }
    window.addEventListener('focus', onFocusOrVisible)
    document.addEventListener('visibilitychange', onFocusOrVisible)
    return () => {
      window.removeEventListener('focus', onFocusOrVisible)
      document.removeEventListener('visibilitychange', onFocusOrVisible)
    }
  }, [refreshViewer])

  useEffect(() => {
    setMobileNavOpen(false)
    setActiveMenuThreadId('')
    setAuthMenuOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!activeMenuThreadId) return undefined
    const closeMenu = (event) => {
      const target = event.target
      if (target instanceof Element && (target.closest('.rl-history-actions') || target.closest('.rl-floating-history-menu'))) return
      setActiveMenuThreadId('')
    }
    document.addEventListener('pointerdown', closeMenu)
    return () => document.removeEventListener('pointerdown', closeMenu)
  }, [activeMenuThreadId])

  useEffect(() => {
    if (!activeMenuThreadId) return undefined
    const closeMenu = () => setActiveMenuThreadId('')
    window.addEventListener('resize', closeMenu)
    window.addEventListener('scroll', closeMenu, true)
    return () => {
      window.removeEventListener('resize', closeMenu)
      window.removeEventListener('scroll', closeMenu, true)
    }
  }, [activeMenuThreadId])

  useEffect(() => {
    if (!sidebarCollapsed) return
    setActiveMenuThreadId('')
    setEditingThreadId('')
    setEditingTitle('')
    setAuthMenuOpen(false)
  }, [sidebarCollapsed])

  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    const { body } = document
    const previousOverflow = body.style.overflow
    if (mobileNavOpen) body.style.overflow = 'hidden'
    return () => {
      body.style.overflow = previousOverflow
    }
  }, [mobileNavOpen])

  useEffect(() => {
    if (!attachMenuOpen || typeof document === 'undefined') return undefined
    const closeMenu = (event) => {
      const target = event.target
      if (!(target instanceof Element)) {
        setAttachMenuOpen(false)
        return
      }
      if (target.closest('.rl-dock-attach-menu') || target.closest('.rl-dock-attach-trigger')) return
      setAttachMenuOpen(false)
    }
    document.addEventListener('pointerdown', closeMenu)
    return () => document.removeEventListener('pointerdown', closeMenu)
  }, [attachMenuOpen])

  useEffect(() => {
    if (!authMenuOpen || typeof document === 'undefined') return undefined
    const closeMenu = (event) => {
      const target = event.target
      if (!(target instanceof Element)) {
        setAuthMenuOpen(false)
        return
      }
      if (authMenuRef.current && authMenuRef.current.contains(target)) return
      setAuthMenuOpen(false)
    }
    document.addEventListener('pointerdown', closeMenu)
    return () => document.removeEventListener('pointerdown', closeMenu)
  }, [authMenuOpen])

  useEffect(() => {
    const host = workspaceAppRef.current
    if (!host) return undefined

    const setDockHeight = (value) => {
      host.style.setProperty('--dock-height', `${Math.max(0, Math.round(value))}px`)
    }

    if (showLandingComposer || !dockRef.current) {
      setDockHeight(0)
      return undefined
    }

    const dockElement = dockRef.current
    const updateDockHeight = () => {
      setDockHeight(dockElement.getBoundingClientRect().height)
    }

    updateDockHeight()
    window.addEventListener('resize', updateDockHeight)

    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(updateDockHeight)
      observer.observe(dockElement)
      return () => {
        observer.disconnect()
        window.removeEventListener('resize', updateDockHeight)
      }
    }

    return () => {
      window.removeEventListener('resize', updateDockHeight)
    }
  }, [showLandingComposer, dockExpanded, error, location.pathname, loading, query])

  useEffect(() => {
    if (showLandingComposer || typeof window === 'undefined' || typeof document === 'undefined') {
      setDockInlineStyle(null)
      return undefined
    }

    const resolveAnchorSelectors = () => {
      if (String(location.pathname || '').startsWith('/stock')) {
        return ['.rl-stock-main-col', '.rl-stock-detail-main-card', '.rl-stock-page']
      }
      if (location.pathname === '/news') {
        return ['.rl-news-v2-feed', '.rl-news-v2-page']
      }
      if (location.pathname === '/agent') {
        return ['.rl-ask-shell']
      }
      return ['.rl-page-shell', '.rl-workspace-content']
    }

    const updateDockBounds = () => {
      if (window.innerWidth <= 1080) {
        setDockInlineStyle(null)
        return
      }
      const anchor = resolveAnchorSelectors()
        .map((selector) => document.querySelector(selector))
        .find((node) => node instanceof Element)
      if (!anchor) {
        setDockInlineStyle(null)
        return
      }
      const rect = anchor.getBoundingClientRect()
      if (!Number.isFinite(rect.left) || !Number.isFinite(rect.right) || rect.width < 120) {
        setDockInlineStyle(null)
        return
      }
      const left = Math.max(10, Math.round(rect.left))
      const right = Math.max(10, Math.round(window.innerWidth - rect.right))
      setDockInlineStyle({ left: `${left}px`, right: `${right}px` })
    }

    const runUpdate = () => window.requestAnimationFrame(updateDockBounds)
    runUpdate()

    const rootObserver = typeof ResizeObserver !== 'undefined' && workspaceAppRef.current
      ? new ResizeObserver(runUpdate)
      : null
    if (rootObserver && workspaceAppRef.current) rootObserver.observe(workspaceAppRef.current)

    const anchorObserver = typeof ResizeObserver !== 'undefined'
      ? new ResizeObserver(runUpdate)
      : null
    resolveAnchorSelectors().forEach((selector) => {
      const node = document.querySelector(selector)
      if (anchorObserver && node) anchorObserver.observe(node)
    })

    window.addEventListener('resize', runUpdate)

    return () => {
      window.removeEventListener('resize', runUpdate)
      if (rootObserver) rootObserver.disconnect()
      if (anchorObserver) anchorObserver.disconnect()
    }
  }, [showLandingComposer, location.pathname, sidebarCollapsed, isConversationStarted, loading, dockExpanded])

  const handleNewChat = () => {
    const hasAskedQuestion = (currentThread?.messages || []).some(
      (message) => message.role === 'user' && String(message.text || '').trim(),
    )
    if (hasAskedQuestion) {
      startNewThread()
    }
    navigate('/agent')
    setDockFocused(false)
    setMobileNavOpen(false)
    setThreadQuery('')
    setActiveMenuThreadId('')
    setEditingThreadId('')
    setEditingTitle('')
    clearPendingAttachment()
    setAttachError('')
  }

  const openThread = (threadId) => {
    switchThread(threadId)
    navigate('/agent')
    setDockFocused(false)
    setMobileNavOpen(false)
    setActiveMenuThreadId('')
    setEditingThreadId('')
    clearPendingAttachment()
    setAttachError('')
  }

  const startRenameThread = (thread) => {
    setEditingThreadId(thread.id)
    setEditingTitle(thread.title || i18n.newChat)
    setActiveMenuThreadId('')
  }

  const cancelRenameThread = () => {
    setEditingThreadId('')
    setEditingTitle('')
  }

  const saveRenameThread = (threadId) => {
    const nextTitle = String(editingTitle || '').trim()
    updateThreadTitle(threadId, nextTitle || i18n.newChat)
    cancelRenameThread()
  }

  const handleDeleteThread = (threadId) => {
    deleteThread(threadId)
    setActiveMenuThreadId('')
    if (editingThreadId === threadId) cancelRenameThread()
  }

  const toggleHistoryMenu = (threadId, triggerElement) => {
    if (activeMenuThreadId === threadId) {
      setActiveMenuThreadId('')
      return
    }
    setActiveMenuPosition(getHistoryMenuPosition(triggerElement.getBoundingClientRect()))
    setActiveMenuThreadId(threadId)
  }

  const submitQuery = async (forced) => {
    const text = String(forced ?? query).trim()
    if (!text || loading) return
    const originPath = location.pathname || '/agent'
    const originSearch = location.search || ''
    const targetHref = buildAgentHref(originSearch)
    const needsJump = `${location.pathname || ''}${location.search || ''}` !== targetHref
    if (needsJump) {
      stashPendingChat({ text, originPath, originSearch })
      setQuery('')
      navigate(targetHref)
      setDockFocused(false)
      return
    }
    await send(text, { pathname: originPath, search: originSearch })
    setDockFocused(false)
    setAttachMenuOpen(false)
    setAttachError('')
  }

  const triggerFilePicker = () => {
    if (!fileInputRef.current) return
    fileInputRef.current.click()
  }

  const handleAttachmentPicked = (event) => {
    const file = event?.target?.files?.[0]
    if (!file) return
    const attached = attachFile(file)
    if (!attached?.ok) {
      setAttachError(attached?.error || 'Failed to attach file.')
    } else {
      setAttachError('')
      if (error) clearError()
    }
    event.target.value = ''
    setAttachMenuOpen(false)
  }

  const handleBrandClick = () => {
    if (sidebarCollapsed) {
      setSidebarCollapsed(false)
      return
    }
    handleNewChat()
  }

  const toggleUiLang = () => {
    setUiLang((prev) => (prev === 'en' ? 'zh' : 'en'))
  }

  const toggleUiTheme = () => {
    setUiTheme((prev) => (prev === 'light' ? 'dark' : 'light'))
  }

  const openLandingPage = () => {
    if (typeof window === 'undefined') return
    window.location.assign('https://risklens.pages.dev/')
  }

  const handleAuthToggle = () => {
    if (typeof window === 'undefined' || viewer.loading) return
    setAuthMenuOpen(false)
    const returnTo = `${window.location.origin}/agent`
    if (viewer.authenticated) {
      startAuthLogout(returnTo)
      return
    }
    startAuthLogin(returnTo, { prompt: 'login select_account' })
  }

  const viewerDisplay = useMemo(() => {
    if (viewer.loading) return { name: 'Loading...', detail: '', initials: '…' }
    if (!viewer.authenticated || !viewer.user) return { name: 'Guest', detail: '', initials: 'G' }
    const email = String(viewer.user.email || '').trim()
    const userId = String(viewer.user.user_id || '').trim()
    const name = email || userId || 'User'
    const detail = ''
    const initials = name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase() || '')
      .join('') || 'U'
    return { name, detail, initials }
  }, [viewer])

  const SidebarContent = () => (
    <>
      <div className="rl-sidebar-scroll">
        <div className="rl-brand">
          <div className="rl-brand-left">
            <button
              className={`rl-brand-icon-btn ${sidebarCollapsed ? 'collapsed' : ''}`}
              onClick={handleBrandClick}
              aria-label={sidebarCollapsed ? i18n.topExpandSidebar : i18n.topStartNewChat}
              title={sidebarCollapsed ? i18n.topExpandSidebar : i18n.topStartNewChat}
            >
              <span className="rl-brand-icon" aria-hidden="true">
                <img src={brandIcon} alt="" className="rl-brand-icon-image" />
              </span>
            </button>
            <div className="rl-brand-copy">
              <p className="rl-brand-title">
                RiskLens<span>AI</span>
              </p>
              <p className="rl-brand-sub">10-K Risk Intelligence</p>
            </div>
          </div>
          <button
            className="rl-sidebar-toggle-inline"
            onClick={() => setSidebarCollapsed((v) => !v)}
            aria-label={sidebarCollapsed ? i18n.topExpandSidebar : i18n.topCollapseSidebar}
            title={sidebarCollapsed ? i18n.topExpandSidebar : i18n.topCollapseSidebar}
          >
            <NavIcon name="panelSplit" strokeWidth={1.6} />
          </button>
        </div>

        <button className="rl-primary-action" onClick={handleNewChat} title={sidebarCollapsed ? i18n.newChat : undefined}>
          <span className="rl-primary-action-icon">
            <NavIcon name="plus" />
          </span>
          <span className="rl-primary-action-text">{i18n.newChat}</span>
        </button>

        <div className="rl-chat-nav-block">
          <div className="rl-chat-nav-head">
            <p>{i18n.history}</p>
          </div>

          <label className="rl-chat-search" aria-label={i18n.searchConversations}>
            <NavIcon name="search" className="rl-chat-search-icon" />
            <input
              type="text"
              value={threadQuery}
              onChange={(e) => setThreadQuery(e.target.value)}
              placeholder={i18n.searchConversations}
            />
          </label>

          <div className="rl-history-list">
            {filteredHistoryItems.length === 0 && (
              <p className="rl-history-empty">{threadQuery ? i18n.noMatch : i18n.noConversation}</p>
            )}
            {filteredHistoryItems.map((t) => {
              const isCurrent = currentThreadId === t.id
              const isEditing = editingThreadId === t.id
              const isMenuOpen = activeMenuThreadId === t.id
              return (
                <div key={t.id} className={`rl-history-item ${isCurrent ? 'active' : ''}`}>
                  {isEditing ? (
                    <input
                      className="rl-history-rename-input"
                      value={editingTitle}
                      autoFocus
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => setEditingTitle(e.target.value)}
                      onBlur={() => saveRenameThread(t.id)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          saveRenameThread(t.id)
                        }
                        if (e.key === 'Escape') {
                          e.preventDefault()
                          cancelRenameThread()
                        }
                      }}
                    />
                  ) : (
                    <button className="rl-history-main" onClick={() => openThread(t.id)}>
                      <span className="dot" />
                      <span className="text">{t.title || i18n.newChat}</span>
                    </button>
                  )}

                  <div className={`rl-history-actions ${isMenuOpen ? 'open' : ''}`} onClick={(e) => e.stopPropagation()}>
                    {isEditing ? (
                      <button
                        className="rl-history-action-btn"
                        onClick={() => saveRenameThread(t.id)}
                        aria-label="Save conversation title"
                        title="Save"
                      >
                        <NavIcon name="check" />
                      </button>
                    ) : (
                      <button
                        className="rl-history-menu-btn"
                        onClick={(e) => toggleHistoryMenu(t.id, e.currentTarget)}
                        aria-label="Conversation options"
                        title="Options"
                      >
                        <NavIcon name="more" />
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <div className="rl-sidebar-footer">
        <div className="rl-sidebar-footer-left">
          <div className="rl-sidebar-auth" ref={authMenuRef}>
            <button
              className="rl-sidebar-user rl-sidebar-user-trigger"
              onClick={() => setAuthMenuOpen((open) => !open)}
              aria-label={i18n.authMenu}
            >
              <span className="rl-sidebar-user-avatar">{viewerDisplay.initials}</span>
              <div className="rl-sidebar-user-copy">
                <strong>{viewerDisplay.name}</strong>
              </div>
            </button>
            {authMenuOpen ? (
              <div className="rl-auth-menu">
                <button className="rl-auth-menu-btn" onClick={handleAuthToggle} disabled={viewer.loading}>
                  {viewer.authenticated ? i18n.authSignOut : i18n.authSignIn}
                </button>
              </div>
            ) : null}
          </div>
        </div>
        <div className="rl-sidebar-footer-right">
          <button
            className="rl-footer-landing-btn"
            onClick={openLandingPage}
            aria-label="Back to landing page"
            title="Back to landing page"
          >
            <NavIcon name="home" />
          </button>
        </div>
      </div>
    </>
  )

  return (
    <div
      ref={workspaceAppRef}
      className={`rl-app rl-workspace-app ${sidebarCollapsed ? 'sidebar-collapsed' : ''} ${uiTheme === 'dark' ? 'rl-theme-dark' : 'rl-theme-light'}`}
    >
      <div className="rl-mobile-topbar">
        <button className="rl-mobile-icon-btn" onClick={() => setMobileNavOpen(true)} aria-label="Open conversation menu">
          <NavIcon name="menu" />
        </button>
        <button className="rl-mobile-brand" onClick={() => navigate('/agent')} aria-label="Go to Ask workspace">
          <span className="rl-mobile-brand-dot" aria-hidden="true">
            <img src={brandIcon} alt="" className="rl-mobile-brand-logo" />
          </span>
          <span>RiskLens AI</span>
        </button>
        <button className="rl-mobile-icon-btn" onClick={handleNewChat} aria-label={i18n.topStartNewChat}>
          <NavIcon name="plus" />
        </button>
      </div>

      <div
        className={`rl-mobile-nav-backdrop ${mobileNavOpen ? 'open' : ''}`}
        onClick={() => setMobileNavOpen(false)}
        aria-hidden={!mobileNavOpen}
      />

      <aside className={`rl-mobile-nav-drawer ${mobileNavOpen ? 'open' : ''}`} aria-hidden={!mobileNavOpen}>
        <div className="rl-mobile-nav-head">
          <p>Conversations</p>
          <button className="rl-mobile-icon-btn" onClick={() => setMobileNavOpen(false)} aria-label="Close conversation menu">
            <NavIcon name="close" />
          </button>
        </div>
        <div className="rl-mobile-drawer-inner">
          <SidebarContent />
        </div>
      </aside>

      <aside className={`rl-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <SidebarContent />
      </aside>
      <input
        ref={fileInputRef}
        type="file"
        accept=".html,.htm,.pdf"
        className="rl-hidden-file-input"
        onChange={handleAttachmentPicked}
      />

      <main className={`rl-main rl-workspace-main ${showLandingComposer ? 'landing' : ''}`}>
        <div className="rl-workspace-tabs-wrap">
          <nav className="rl-workspace-tabs">
            {WORKSPACE_TABS.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={({ isActive }) => `rl-workspace-tab ${isActive ? 'active' : ''}`}
                aria-label={uiLang === 'zh' ? tab.label_zh : tab.label_en}
              >
                {uiLang === 'zh' ? tab.label_zh : tab.label_en}
              </NavLink>
            ))}
          </nav>
          <div className="rl-workspace-top-controls">
            <button
              className="rl-top-mini-tab"
              type="button"
              onClick={toggleUiLang}
              aria-label={uiLang === 'zh' ? '切换到英文' : 'Switch to Chinese'}
              title={uiLang === 'zh' ? '切换语言' : 'Switch language'}
            >
              <NavIcon name="globe" className="rl-top-mini-icon" strokeWidth={1.85} />
              <span>{i18n.topLang}</span>
            </button>
            <button
              className="rl-top-mini-tab"
              type="button"
              onClick={toggleUiTheme}
              aria-label={uiTheme === 'dark' ? (uiLang === 'zh' ? '切换浅色' : 'Switch to light') : (uiLang === 'zh' ? '切换深色' : 'Switch to dark')}
              title={uiTheme === 'dark' ? i18n.topThemeLight : i18n.topThemeDark}
            >
              <NavIcon name={uiTheme === 'dark' ? 'moon' : 'sun'} className="rl-top-mini-icon" strokeWidth={1.85} />
              <span>{uiTheme === 'dark' ? i18n.topThemeDark : i18n.topThemeLight}</span>
            </button>
          </div>
        </div>

        <div className={`rl-main-inner rl-workspace-content ${showLandingComposer ? 'landing' : ''}`}>
          {children}
          {showLandingComposer ? (
            <>
              <section className="rl-landing-center">
                <p className="rl-landing-brand">
                  <span className="brand-main">RiskLens</span>
                  <span className="brand-ai">AI</span>
                </p>
                <form
                  className="rl-landing-composer"
                  onSubmit={(e) => {
                    e.preventDefault()
                    submitQuery()
                  }}
                >
                  {pendingAttachment ? (
                    <div className="rl-dock-attachment-chip">
                      <AttachmentFileIcon />
                      <div className="rl-dock-attachment-copy">
                        <span>{pendingAttachment.name}</span>
                        <em>{String(pendingAttachment.ext || '').toUpperCase()} · {formatBytes(pendingAttachment.size)}</em>
                      </div>
                      <button
                        type="button"
                        className="rl-dock-attachment-remove"
                        onClick={() => {
                          clearPendingAttachment()
                          setAttachError('')
                        }}
                        aria-label="Remove attached file"
                        title="Remove attached file"
                      >
                        ×
                      </button>
                    </div>
                  ) : null}
                  <div className="rl-landing-input-row">
                    <div className="rl-dock-attach-wrap">
                      <button
                        ref={attachBtnRef}
                        type="button"
                        className="rl-dock-attach-trigger"
                        onClick={() => setAttachMenuOpen((v) => !v)}
                        aria-label={i18n.addFile}
                        title={i18n.addFile}
                      >
                        <NavIcon name="plus" strokeWidth={2.35} />
                      </button>
                      {attachMenuOpen ? (
                        <div ref={attachMenuRef} className="rl-dock-attach-menu" role="menu">
                          <button
                            type="button"
                            className="rl-dock-attach-menu-item"
                            onClick={triggerFilePicker}
                          >
                            {i18n.addFile}
                          </button>
                        </div>
                      ) : null}
                    </div>
                    <textarea
                      rows={1}
                      value={query}
                      onChange={(e) => {
                        if (error) clearError()
                        setQuery(e.target.value)
                      }}
                      onCompositionStart={markCompositionStart}
                      onCompositionEnd={markCompositionEnd}
                      placeholder={i18n.askLanding}
                      onKeyDown={(e) => {
                        if (shouldIgnoreEnterSubmit(e)) {
                          if (e.key === 'Enter' && !e.shiftKey) e.preventDefault()
                          return
                        }
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          submitQuery()
                        }
                      }}
                    />
                    <button
                      className={`rl-chat-submit-btn rl-landing-send ${loading ? 'loading' : ''}`}
                      type="submit"
                      disabled={!String(query || '').trim() || loading}
                      aria-label={loading ? 'Thinking' : 'Send'}
                    >
                      <SubmitArrowIcon />
                    </button>
                  </div>
                </form>
                <div className="rl-landing-support">
                  <div className="rl-landing-chips" aria-label={i18n.quickPromptsLabel}>
                    {i18n.quickPrompts.map((prompt) => (
                      <button key={prompt} type="button" className="rl-landing-chip" onClick={() => submitQuery(prompt)} disabled={loading}>
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
                {error ? <p className="rl-global-dock-error">{error}</p> : null}
                {attachError ? <p className="rl-global-dock-error">{attachError}</p> : null}
              </section>
            </>
          ) : null}
        </div>
      </main>

      {!showLandingComposer ? (
        <div
          ref={dockRef}
          className={`rl-global-dock ${dockExpanded ? 'expanded' : 'compact'} ${isAgentRoute ? 'agent' : ''} ${isNewsStyleDockRoute ? 'news' : ''} ${isFocusDockRoute ? 'focus' : ''}`}
          style={dockInlineStyle || undefined}
          aria-live="polite"
        >
          <div className="rl-global-dock-inner">
            {error ? <p className="rl-global-dock-error">{error}</p> : null}
            {attachError ? <p className="rl-global-dock-error">{attachError}</p> : null}

            <form
              className="rl-global-dock-composer"
              onSubmit={(e) => {
                e.preventDefault()
                submitQuery()
              }}
            >
              {pendingAttachment ? (
                <div className="rl-dock-attachment-chip">
                  <AttachmentFileIcon />
                  <div className="rl-dock-attachment-copy">
                    <span>{pendingAttachment.name}</span>
                    <em>{String(pendingAttachment.ext || '').toUpperCase()} · {formatBytes(pendingAttachment.size)}</em>
                  </div>
                  <button
                    type="button"
                    className="rl-dock-attachment-remove"
                    onClick={() => {
                      clearPendingAttachment()
                      setAttachError('')
                    }}
                    aria-label="Remove attached file"
                    title="Remove attached file"
                  >
                    ×
                  </button>
                </div>
              ) : null}
              <div className="rl-global-dock-row">
                <div className="rl-dock-attach-wrap">
                  <button
                    ref={attachBtnRef}
                    type="button"
                    className="rl-dock-attach-trigger"
                    onClick={() => setAttachMenuOpen((v) => !v)}
                    aria-label={i18n.addFile}
                    title={i18n.addFile}
                  >
                    <NavIcon name="plus" strokeWidth={2.35} />
                  </button>
                  {attachMenuOpen ? (
                    <div ref={attachMenuRef} className="rl-dock-attach-menu" role="menu">
                      <button
                        type="button"
                        className="rl-dock-attach-menu-item"
                        onClick={triggerFilePicker}
                      >
                        {i18n.addFile}
                      </button>
                    </div>
                  ) : null}
                </div>
              <textarea
                rows={1}
                value={query}
                onChange={(e) => {
                  if (error) clearError()
                  setQuery(e.target.value)
                }}
                onCompositionStart={markCompositionStart}
                onCompositionEnd={markCompositionEnd}
                onFocus={() => setDockFocused(true)}
                onBlur={() => setDockFocused(false)}
                placeholder={dockPlaceholder(location.pathname, uiLang)}
                onKeyDown={(e) => {
                  if (shouldIgnoreEnterSubmit(e)) {
                    if (e.key === 'Enter' && !e.shiftKey) e.preventDefault()
                    return
                  }
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    submitQuery()
                  }
                }}
              />
              <button
                className={`rl-global-dock-send rl-chat-submit-btn ${loading ? 'loading' : ''}`}
                type="submit"
                disabled={!String(query || '').trim() || loading}
                aria-label={loading ? 'Thinking' : 'Send'}
              >
                <SubmitArrowIcon />
              </button>
              </div>
            </form>
            {isAgentRoute ? (
              <p className="rl-global-dock-note">{i18n.modelNote}</p>
            ) : null}
          </div>
        </div>
      ) : null}

      {activeMenuThread && typeof document !== 'undefined'
        ? createPortal(
            <div
              className="rl-history-menu rl-floating-history-menu"
              role="menu"
              style={{ top: `${activeMenuPosition.top}px`, left: `${activeMenuPosition.left}px` }}
            >
              <button className="rl-history-menu-item" onClick={() => startRenameThread(activeMenuThread)}>
                <NavIcon name="edit" />
                <span>{i18n.rename}</span>
              </button>
              <button className="rl-history-menu-item danger" onClick={() => handleDeleteThread(activeMenuThread.id)}>
                <NavIcon name="trash" />
                <span>{i18n.delete}</span>
              </button>
            </div>,
            document.body,
          )
        : null}
    </div>
  )
}
