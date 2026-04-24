import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "../components/layout/AppLayout";
import { HomePage } from "../pages/HomePage";
import { UploadPage } from "../pages/UploadPage";
import { DashboardPage, StockPage, NewsPage, TablesPage, AgentPage } from "../pages/SimplePages";
import { LibraryPage } from "../pages/LibraryPage";
import { ComparePage } from "../pages/ComparePage";
import { NotFoundPage } from "../pages/NotFoundPage";

export function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<Navigate to="/home" replace />} />
        <Route path="/home" element={<HomePage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/stock" element={<StockPage />} />
        <Route path="/news" element={<NewsPage />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/tables" element={<TablesPage />} />
        <Route path="/agent" element={<AgentPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AppLayout>
  );
}
