import { useEffect, useState } from "react";
import { PageHeader } from "../components/common/PageHeader";
import { InfoCard } from "../components/common/InfoCard";
import { ApiHint } from "../components/common/ApiHint";
import { risklensApi } from "../services/risklensApi";
import type { HealthResponse } from "../types/api";

export function HomePage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    risklensApi
      .health()
      .then((data) => {
        setHealth(data);
        setError("");
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Health check failed");
      });
  }, []);

  return (
    <div>
      <PageHeader
        icon="🏠"
        title="Home"
        subtitle="Cloudflare frontend for your existing Railway backend"
      />

      <div className="grid-two">
        <InfoCard title="Backend Health" hint="Checks Railway API connectivity">
          {error ? (
            <p className="text-error">{error}</p>
          ) : (
            <p className="text-body">
              Status: <strong>{health?.status ?? "Checking..."}</strong>
            </p>
          )}
          <ApiHint />
        </InfoCard>

        <InfoCard title="Migration State" hint="Frontend and backend ownership is cleanly separated">
          <ul className="simple-list">
            <li>Frontend: Cloudflare Pages</li>
            <li>Backend: Railway API</li>
            <li>Storage/AI logic: unchanged in Python backend</li>
          </ul>
        </InfoCard>
      </div>
    </div>
  );
}
