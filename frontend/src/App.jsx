import React from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import HomePage from './pages/HomePage'
import DashboardPage from './pages/DashboardPage'
import LibraryPage from './pages/LibraryPage'
import AnalyzePage from './pages/AnalyzePage'
import ComparePage from './pages/ComparePage'
import NewsPage from './pages/NewsPage'
import StockPage from './pages/StockPage'
import AgentPage from './pages/AgentPage'

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/analyze" element={<AnalyzePage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/stock" element={<StockPage />} />
        <Route path="/agent" element={<AgentPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  )
}
