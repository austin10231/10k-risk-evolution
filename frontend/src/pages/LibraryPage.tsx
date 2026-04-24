import { useEffect, useState } from "react";
import { PageHeader } from "../components/common/PageHeader";
import { InfoCard } from "../components/common/InfoCard";
import { risklensApi } from "../services/risklensApi";
import type { FilingRecord } from "../types/api";

export function LibraryPage() {
  const [rows, setRows] = useState<FilingRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    risklensApi
      .listRecords()
      .then((data) => {
        setRows(data ?? []);
        setError("");
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load records");
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader
        icon="📚"
        title="Library"
        subtitle="Read indexed filing records from backend"
      />

      <InfoCard title="Filing Records" hint="Endpoint: GET /records">
        {loading && <p className="text-muted">Loading records...</p>}
        {!loading && error && <p className="text-error">{error}</p>}
        {!loading && !error && rows.length === 0 && (
          <p className="text-muted">No records available yet.</p>
        )}

        {!loading && !error && rows.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Record ID</th>
                  <th>Company</th>
                  <th>Year</th>
                  <th>Type</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.record_id}>
                    <td>{row.record_id}</td>
                    <td>{row.company}</td>
                    <td>{row.year}</td>
                    <td>{row.filing_type}</td>
                    <td>{row.created_at ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </InfoCard>
    </div>
  );
}
