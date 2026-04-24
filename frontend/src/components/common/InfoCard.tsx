import type { PropsWithChildren, ReactNode } from "react";

type InfoCardProps = PropsWithChildren<{
  title: string;
  hint?: string;
  action?: ReactNode;
}>;

export function InfoCard({ title, hint, action, children }: InfoCardProps) {
  return (
    <section className="card">
      <div className="card-header">
        <div>
          <h2 className="card-title">{title}</h2>
          {hint && <p className="card-hint">{hint}</p>}
        </div>
        {action}
      </div>
      <div>{children}</div>
    </section>
  );
}
