import { NavLink } from "react-router-dom";
import { NAV_GROUPS } from "../../config/navigation";

type SidebarProps = {
  collapsed: boolean;
  onToggle: () => void;
};

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  return (
    <aside className={`app-sidebar ${collapsed ? "collapsed" : ""}`}>
      <div className="brand-block">
        <div className="brand-icon">📊</div>
        {!collapsed && (
          <div>
            <p className="brand-title">
              RiskLens<span>AI</span>
            </p>
            <p className="brand-subtitle">10-K Risk Intelligence</p>
          </div>
        )}
      </div>

      <div className="nav-scroll">
        {NAV_GROUPS.map((group) => (
          <section key={group.title} className="nav-group">
            {!collapsed && <p className="nav-group-title">{group.title}</p>}
            <div className="nav-items">
              {group.items.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    `nav-item ${isActive ? "active" : ""}`
                  }
                  title={collapsed ? item.label : undefined}
                >
                  <span className="nav-item-icon" aria-hidden="true">
                    {item.icon}
                  </span>
                  {!collapsed && <span>{item.label}</span>}
                </NavLink>
              ))}
            </div>
          </section>
        ))}
      </div>

      <div className="sidebar-footer">
        <button className="sidebar-toggle" onClick={onToggle} type="button">
          {collapsed ? "Expand" : "Collapse"}
        </button>
        {!collapsed && <p>© 2026 RiskLens</p>}
      </div>
    </aside>
  );
}
