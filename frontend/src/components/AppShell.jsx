import React, { useEffect, useMemo, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import FloatingChatWidget from './FloatingChatWidget'
import { useChatMemory } from '../lib/chatMemory'

const NAV_GROUPS = [
  {
    label: 'DATA',
    items: [
      { to: '/home', icon: '🏠', label: 'Home' },
      { to: '/upload', icon: '➕', label: 'Upload' },
      { to: '/dashboard', icon: '📈', label: 'Dashboard' },
      { to: '/stock', icon: '💹', label: 'Stock' },
      { to: '/news', icon: '📰', label: 'News' },
      { to: '/library', icon: '📚', label: 'Library' },
    ],
  },
  {
    label: 'ANALYSIS',
    items: [
      { to: '/compare', icon: '⚖️', label: 'Compare' },
      { to: '/tables', icon: '📊', label: 'Tables' },
    ],
  },
  {
    label: 'INTELLIGENCE',
    items: [{ to: '/agent', icon: '🤖', label: 'Agent' }],
  },
]

export default function AppShell({ children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const { threads, currentThreadId, switchThread, createThread } = useChatMemory()

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem('risklens_sidebar_collapsed_v1') === '1'
  })

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem('risklens_sidebar_collapsed_v1', sidebarCollapsed ? '1' : '0')
  }, [sidebarCollapsed])

  const historyItems = useMemo(
    () =>
      (threads || [])
        .slice()
        .sort((a, b) => Number(b.updatedAt || 0) - Number(a.updatedAt || 0))
        .slice(0, 10),
    [threads],
  )

  return (
    <div className="rl-app">
      <aside className={`rl-sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="rl-sidebar-scroll">
          <div className="rl-brand">
            <div className="rl-brand-icon" aria-hidden="true">
              <span className="bar b1" />
              <span className="bar b2" />
              <span className="bar b3" />
            </div>
            <div>
              <p className="rl-brand-title">
                RiskLens<span>AI</span>
              </p>
              <p className="rl-brand-sub">10-K Risk Intelligence</p>
            </div>
          </div>

          <div className="rl-chat-nav-block">
            <div className="rl-chat-nav-head">
              <p>Conversations</p>
              <button
                className="rl-new-chat-btn"
                onClick={() => {
                  createThread()
                  navigate('/agent')
                }}
              >
                + New
              </button>
            </div>

            <div className="rl-history-list">
              {historyItems.map((t) => (
                <button
                  key={t.id}
                  className={`rl-history-item ${currentThreadId === t.id && location.pathname === '/agent' ? 'active' : ''}`}
                  onClick={() => {
                    switchThread(t.id)
                    navigate('/agent')
                  }}
                >
                  <span className="dot" />
                  <span className="text">{t.title || 'New conversation'}</span>
                </button>
              ))}
            </div>
          </div>

          <nav className="rl-nav">
            {NAV_GROUPS.map((group) => (
              <div key={group.label} className="rl-nav-group">
                <p className="rl-nav-group-label">{group.label}</p>
                {group.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={({ isActive }) =>
                      `rl-nav-item ${isActive ? 'active' : ''}`
                    }
                  >
                    <span className="rl-nav-item-inner">
                      <span className="rl-nav-icon">{item.icon}</span>
                      <span className="rl-nav-label">{item.label}</span>
                    </span>
                  </NavLink>
                ))}
              </div>
            ))}
          </nav>
        </div>

        <div className="rl-sidebar-footer">
          <div className="dot" />
          <p>© 2026 SCU · AWS Team 1</p>
        </div>
      </aside>

      <button
        className={`rl-sidebar-toggle ${sidebarCollapsed ? 'collapsed' : ''}`}
        onClick={() => setSidebarCollapsed((v) => !v)}
        aria-label="Toggle navigation sidebar"
      >
        <span>{sidebarCollapsed ? '›' : '‹'}</span>
      </button>

      <main className="rl-main">
        <div className="rl-main-inner">
          {children}
        </div>
      </main>
      <FloatingChatWidget />
    </div>
  )
}
