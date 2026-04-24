import type { ReactNode } from "react";

type PageHeaderProps = {
  icon: string;
  title: string;
  subtitle: string;
  right?: ReactNode;
};

export function PageHeader({ icon, title, subtitle, right }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-header-left">
        <div className="page-icon" aria-hidden="true">
          {icon}
        </div>
        <div>
          <h1 className="page-title">{title}</h1>
          <p className="page-subtitle">{subtitle}</p>
        </div>
      </div>
      {right && <div>{right}</div>}
    </header>
  );
}
