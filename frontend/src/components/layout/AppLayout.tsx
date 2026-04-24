import { useState } from "react";
import type { PropsWithChildren } from "react";
import { Sidebar } from "./Sidebar";

export function AppLayout({ children }: PropsWithChildren) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="app-shell">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((prev) => !prev)} />
      <main className="app-main">{children}</main>
    </div>
  );
}
