import React from 'react'
import { NavLink } from 'react-router-dom'

const NAV = [
  { to: '/', label: 'Home' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/library', label: 'Library' },
  { to: '/analyze', label: 'Analyze' },
  { to: '/compare', label: 'Compare' },
  { to: '/news', label: 'News' },
  { to: '/stock', label: 'Stock' },
  { to: '/agent', label: 'Agent' },
]

export default function AppShell({ children }) {
  return (
    <div className="min-h-screen">
      <div className="mx-auto flex max-w-[1400px] gap-4 px-4 py-4 lg:px-6">
        <aside className="sticky top-4 hidden h-[calc(100vh-2rem)] w-64 flex-col rounded-2xl border border-slate-200 bg-slate-900 p-4 text-slate-100 shadow-card lg:flex">
          <div className="mb-5 border-b border-slate-700 pb-4">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">RiskLens</p>
            <h1 className="mt-1 text-2xl font-extrabold leading-tight">Product Suite</h1>
            <p className="mt-2 text-xs text-slate-400">Frontend decoupled from backend runtime</p>
          </div>

          <nav className="space-y-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `block rounded-xl px-3 py-2 text-sm font-semibold transition ${
                    isActive
                      ? 'bg-white/15 text-white'
                      : 'text-slate-300 hover:bg-white/10 hover:text-white'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-auto rounded-xl border border-slate-700 bg-slate-800/80 p-3 text-xs text-slate-300">
            Ask in English or Chinese. UI stays English by design.
          </div>
        </aside>

        <main className="min-w-0 flex-1">
          <header className="card mb-4 flex items-center justify-between px-5 py-4">
            <div>
              <h2 className="text-xl font-extrabold text-slate-900">Risk Intelligence Workspace</h2>
              <p className="text-sm text-slate-500">Chat-first agent + records + market context</p>
            </div>
            <span className="rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-bold text-brand-700">
              API mode
            </span>
          </header>
          {children}
        </main>
      </div>
    </div>
  )
}
