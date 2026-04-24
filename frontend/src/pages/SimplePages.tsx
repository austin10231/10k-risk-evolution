import { PlaceholderPage } from "./PlaceholderPage";

export function DashboardPage() {
  return (
    <PlaceholderPage
      icon="📈"
      title="Dashboard"
      subtitle="Risk metrics and trend cards"
      endpointSuggestion="GET /dashboard"
    />
  );
}

export function StockPage() {
  return (
    <PlaceholderPage
      icon="💹"
      title="Stock"
      subtitle="Market overlays and risk linkage"
      endpointSuggestion="GET /stock?symbol=AAPL"
    />
  );
}

export function NewsPage() {
  return (
    <PlaceholderPage
      icon="📰"
      title="News"
      subtitle="Latest headline intelligence"
      endpointSuggestion="GET /news?company=Apple"
    />
  );
}

export function TablesPage() {
  return (
    <PlaceholderPage
      icon="📊"
      title="Tables"
      subtitle="Financial table extraction results"
      endpointSuggestion="POST /tables/extract"
    />
  );
}

export function AgentPage() {
  return (
    <PlaceholderPage
      icon="🤖"
      title="Agent"
      subtitle="Agent report generation"
      endpointSuggestion="POST /agent/run"
    />
  );
}
