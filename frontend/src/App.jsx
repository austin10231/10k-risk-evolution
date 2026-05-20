import React from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppShell from './components/AppShell'
import FloatingChatWidget from './components/FloatingChatWidget'
import DashboardPage from './pages/DashboardPage'
import LibraryPage from './pages/LibraryPage'
import UploadPage from './pages/UploadPage'
import AnalyzePage from './pages/AnalyzePage'
import ComparePage from './pages/ComparePage'
import NewsPage from './pages/NewsPage'
import StockPage from './pages/StockPage'
import AgentPage from './pages/AgentPage'
import TablesPage from './pages/TablesPage'
import AuthPage from './pages/AuthPage'
import { GlobalConfigProvider } from './lib/globalConfig'
import { ChatMemoryProvider } from './lib/chatMemory'
import { WorkspaceChatProvider } from './lib/workspaceChat'

function RedirectToAgent() {
  const location = useLocation()
  const params = new URLSearchParams(location.search || '')
  if (params.get('code') && !params.get('legacy_redirect_uri') && typeof window !== 'undefined') {
    params.set('legacy_redirect_uri', `${window.location.origin}${location.pathname || '/'}`)
  }
  const search = params.toString()
  return <Navigate to={{ pathname: '/agent', search: search ? `?${search}` : '' }} replace />
}

function ProductRoutes() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<RedirectToAgent />} />
        <Route path="/home" element={<RedirectToAgent />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/analyze" element={<AnalyzePage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/tables" element={<TablesPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/stock" element={<StockPage />} />
        <Route path="/stock/:ticker" element={<StockPage />} />
        <Route path="/agent" element={<AgentPage />} />
        <Route path="*" element={<Navigate to="/agent" replace />} />
      </Routes>
    </AppShell>
  )
}

function AppBody() {
  const location = useLocation()
  const isAuthRoute = location.pathname === '/auth'
  return (
    <>
      <Routes>
        <Route path="/auth" element={<AuthPage />} />
        <Route path="*" element={<ProductRoutes />} />
      </Routes>
      {!isAuthRoute ? <FloatingChatWidget /> : null}
    </>
  )
}

export default function App() {
  return (
    <GlobalConfigProvider>
      <ChatMemoryProvider>
        <WorkspaceChatProvider>
          <AppBody />
        </WorkspaceChatProvider>
      </ChatMemoryProvider>
    </GlobalConfigProvider>
  )
}
