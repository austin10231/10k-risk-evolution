export type NavItem = {
  label: string;
  path: string;
  icon: string;
};

export type NavGroup = {
  title: string;
  items: NavItem[];
};

export const NAV_GROUPS: NavGroup[] = [
  {
    title: "DATA",
    items: [
      { label: "Home", path: "/home", icon: "🏠" },
      { label: "Upload", path: "/upload", icon: "➕" },
      { label: "Dashboard", path: "/dashboard", icon: "📈" },
      { label: "Stock", path: "/stock", icon: "💹" },
      { label: "News", path: "/news", icon: "📰" },
      { label: "Library", path: "/library", icon: "📚" }
    ]
  },
  {
    title: "ANALYSIS",
    items: [
      { label: "Compare", path: "/compare", icon: "⚖️" },
      { label: "Tables", path: "/tables", icon: "📊" }
    ]
  },
  {
    title: "INTELLIGENCE",
    items: [{ label: "Agent", path: "/agent", icon: "🤖" }]
  }
];
