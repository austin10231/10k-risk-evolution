import React, { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useChatMemory } from '../lib/chatMemory'
import { useWorkspaceChat } from '../lib/workspaceChat'
import brandIcon from '../assets/logo-icon.svg'

const WORKSPACE_TABS = [
  { to: '/upload', label: 'Upload' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/library', label: 'Library' },
  { to: '/compare', label: 'Compare' },
  { to: '/tables', label: 'Tables' },
  { to: '/news', label: 'News' },
  { to: '/stock', label: 'Stock' },
]

const LANDING_QUICK_PROMPTS = [
  'Summarize the biggest risk changes for AAPL this year',
  'Compare NVDA vs AMD risk exposure in one table',
  'What signals matter most for Tesla this week?',
  'Find red flags in the latest 10-K filing quickly',
]

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
      <circle cx="6.5" cy="12" r="1.1" />
      <circle cx="12" cy="12" r="1.1" />
      <circle cx="17.5" cy="12" r="1.1" />
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

function dockPlaceholder(pathname) {
  if (pathname === '/compare') return 'Ask about comparison changes, deltas, or risk shifts…'
  if (pathname === '/stock') return 'Ask about this ticker movement or risk implications…'
  if (pathname === '/news') return 'Ask how this headline changes risk outlook…'
  if (pathname === '/tables') return 'Ask what this financial table implies for risk…'
  if (pathname === '/upload') return 'Ask how to ingest or parse a filing quickly…'
  if (pathname === '/dashboard') return 'Ask what to prioritize from this dashboard snapshot…'
  if (pathname === '/library') return 'Ask what this filing history suggests…'
  return 'Ask any risk question…'
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
  } = useWorkspaceChat()

  const workspaceAppRef = useRef(null)
  const dockRef = useRef(null)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [threadQuery, setThreadQuery] = useState('')
  const [activeMenuThreadId, setActiveMenuThreadId] = useState('')
  const [activeMenuPosition, setActiveMenuPosition] = useState({ top: 0, left: 0 })
  const [editingThreadId, setEditingThreadId] = useState('')
  const [editingTitle, setEditingTitle] = useState('')
  const [dockFocused, setDockFocused] = useState(false)

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem('risklens_sidebar_collapsed_v2') === '1'
  })

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
    return historyItems.filter((t) => String(t.title || 'New conversation').toLowerCase().includes(needle))
  }, [historyItems, threadQuery])

  const isAgentRoute = location.pathname === '/agent'
  const showLandingComposer = isAgentRoute && !isConversationStarted && !loading
  const dockExpanded = dockFocused || loading || Boolean(String(query || '').trim())
  const activeMenuThread = useMemo(
    () => filteredHistoryItems.find((t) => t.id === activeMenuThreadId) || null,
    [filteredHistoryItems, activeMenuThreadId],
  )

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem('risklens_sidebar_collapsed_v2', sidebarCollapsed ? '1' : '0')
  }, [sidebarCollapsed])

  useEffect(() => {
    setMobileNavOpen(false)
    setActiveMenuThreadId('')
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
  }

  const openThread = (threadId) => {
    switchThread(threadId)
    navigate('/agent')
    setDockFocused(false)
    setMobileNavOpen(false)
    setActiveMenuThreadId('')
    setEditingThreadId('')
  }

  const startRenameThread = (thread) => {
    setEditingThreadId(thread.id)
    setEditingTitle(thread.title || 'New conversation')
    setActiveMenuThreadId('')
  }

  const cancelRenameThread = () => {
    setEditingThreadId('')
    setEditingTitle('')
  }

  const saveRenameThread = (threadId) => {
    const nextTitle = String(editingTitle || '').trim()
    updateThreadTitle(threadId, nextTitle || 'New conversation')
    cancelRenameThread()
  }

  const handleDeleteThread = (threadId) => {
    if (typeof window !== 'undefined' && !window.confirm('Delete this conversation?')) return
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
    await send(text)
    setDockFocused(false)
  }

  const handleBrandClick = () => {
    if (sidebarCollapsed) {
      setSidebarCollapsed(false)
      return
    }
    navigate('/agent')
  }

  const openLandingPage = () => {
    if (typeof window === 'undefined') return
    const currentLang = new URLSearchParams(window.location.search).get('lang')
    const inferredLang = /^zh/i.test(window.navigator?.language || '') ? 'zh' : 'en'
    const lang = currentLang || inferredLang
    window.location.assign(`/?lang=${lang}`)
  }

  const SidebarContent = () => (
    <>
      <div className="rl-sidebar-scroll">
        <div className="rl-brand">
          <div className="rl-brand-left">
            <button
              className={`rl-brand-icon-btn ${sidebarCollapsed ? 'collapsed' : ''}`}
              onClick={handleBrandClick}
              aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Go to chat home'}
              title={sidebarCollapsed ? 'Expand sidebar' : 'Go to chat home'}
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
            aria-label="Toggle conversation sidebar"
            title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <NavIcon name="panelSplit" strokeWidth={1.6} />
          </button>
        </div>

        <button className="rl-primary-action" onClick={handleNewChat} title={sidebarCollapsed ? 'New chat' : undefined}>
          <span className="rl-primary-action-icon">
            <NavIcon name="plus" />
          </span>
          <span className="rl-primary-action-text">New Chat</span>
        </button>

        <div className="rl-chat-nav-block">
          <div className="rl-chat-nav-head">
            <p>History</p>
          </div>

          <label className="rl-chat-search" aria-label="Search conversations">
            <NavIcon name="search" className="rl-chat-search-icon" />
            <input
              type="text"
              value={threadQuery}
              onChange={(e) => setThreadQuery(e.target.value)}
              placeholder="Search conversations"
            />
          </label>

          <div className="rl-history-list">
            {filteredHistoryItems.length === 0 && (
              <p className="rl-history-empty">{threadQuery ? 'No matching conversations' : 'No conversations yet'}</p>
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
                      <span className="text">{t.title || 'New conversation'}</span>
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
        <div className="rl-sidebar-footer-copy">
          <div className="dot" />
          <p>© 2026 SCU · AWS Team 1</p>
        </div>
        <button
          className="rl-footer-landing-btn"
          onClick={openLandingPage}
          aria-label="Back to landing page"
          title="Back to landing page"
        >
          <NavIcon name="home" />
        </button>
      </div>
    </>
  )

  return (
    <div ref={workspaceAppRef} className={`rl-app rl-workspace-app ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
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
        <button className="rl-mobile-icon-btn" onClick={handleNewChat} aria-label="Start new chat">
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

      <main className={`rl-main rl-workspace-main ${showLandingComposer ? 'landing' : ''}`}>
        <div className="rl-workspace-tabs-wrap">
          <nav className="rl-workspace-tabs">
            {WORKSPACE_TABS.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={({ isActive }) => `rl-workspace-tab ${isActive ? 'active' : ''}`}
                aria-label={tab.label}
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
        </div>

        <div className={`rl-main-inner rl-workspace-content ${showLandingComposer ? 'landing' : ''}`}>
          {children}
          {showLandingComposer ? (
            <>
              <div className="rl-landing-bubbles" aria-hidden="true" />
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
                  <textarea
                    value={query}
                    onChange={(e) => {
                      if (error) clearError()
                      setQuery(e.target.value)
                    }}
                    placeholder="Ask about any company, filing, comparison, stock, or news signal…"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault()
                        submitQuery()
                      }
                    }}
                  />
                  <button
                    className={`btn-primary rl-chat-submit-btn rl-landing-send ${loading ? 'loading' : ''}`}
                    type="submit"
                    disabled={!String(query || '').trim() || loading}
                    aria-label={loading ? 'Thinking' : 'Send'}
                  >
                    <SubmitArrowIcon />
                  </button>
                </form>
                <div className="rl-landing-support">
                  <div className="rl-landing-chips" aria-label="Quick prompt suggestions">
                    {LANDING_QUICK_PROMPTS.map((prompt) => (
                      <button key={prompt} type="button" className="rl-landing-chip" onClick={() => submitQuery(prompt)} disabled={loading}>
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
                {error ? <p className="rl-global-dock-error">{error}</p> : null}
              </section>
            </>
          ) : null}
        </div>
      </main>

      {!showLandingComposer ? (
        <div ref={dockRef} className={`rl-global-dock ${dockExpanded ? 'expanded' : 'compact'}`} aria-live="polite">
          <div className="rl-global-dock-inner">
            {error ? <p className="rl-global-dock-error">{error}</p> : null}

            <form
              className="rl-global-dock-composer"
              onSubmit={(e) => {
                e.preventDefault()
                submitQuery()
              }}
            >
              <textarea
                value={query}
                onChange={(e) => {
                  if (error) clearError()
                  setQuery(e.target.value)
                }}
                onFocus={() => setDockFocused(true)}
                onBlur={() => setDockFocused(false)}
                placeholder={dockPlaceholder(location.pathname)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    submitQuery()
                  }
                }}
              />
              <button
                className={`btn-primary rl-global-dock-send rl-chat-submit-btn ${loading ? 'loading' : ''}`}
                type="submit"
                disabled={!String(query || '').trim() || loading}
                aria-label={loading ? 'Thinking' : 'Send'}
              >
                <SubmitArrowIcon />
              </button>
            </form>
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
                <span>Rename</span>
              </button>
              <button className="rl-history-menu-item danger" onClick={() => handleDeleteThread(activeMenuThread.id)}>
                <NavIcon name="trash" />
                <span>Delete</span>
              </button>
            </div>,
            document.body,
          )
        : null}
    </div>
  )
}
