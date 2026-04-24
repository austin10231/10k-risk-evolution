import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "../components/common/PageHeader";
import { InfoCard } from "../components/common/InfoCard";
import { risklensApi } from "../services/risklensApi";
import type { FilingRecord } from "../types/api";

export function ComparePage() {
  const [records, setRecords] = useState<FilingRecord[]>([]);
  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");
  const [output, setOutput] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    risklensApi
      .listRecords()
      .then((data) => {
        setRecords(data ?? []);
        if (data && data.length >= 2) {
          setLeftId(data[0].record_id);
          setRightId(data[1].record_id);
        }
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load record list");
      });
  }, []);

  const options = useMemo(
    () =>
      records.map((row) => ({
        value: row.record_id,
        label: `${row.company} ${row.year} (${row.filing_type})`
      })),
    [records]
  );

  async function handleCompare(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!leftId || !rightId) {
      setError("Please select two records.");
      return;
    }

    if (leftId === rightId) {
      setError("Please select different records.");
      return;
    }

    setLoading(true);
    setError("");
    setOutput("");

    try {
      const data = await risklensApi.compare({
        left_record_id: leftId,
        right_record_id: rightId
      });
      setOutput(JSON.stringify(data, null, 2));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Compare failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <PageHeader
        icon="⚖️"
        title="Compare"
        subtitle="Compare two filing records via backend"
      />

      <InfoCard title="Record Compare" hint="Endpoint: POST /compare">
        <form className="form-grid" onSubmit={handleCompare}>
          <label>
            Left Record
            <select value={leftId} onChange={(e) => setLeftId(e.target.value)}>
              <option value="">Select record</option>
              {options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Right Record
            <select value={rightId} onChange={(e) => setRightId(e.target.value)}>
              <option value="">Select record</option>
              {options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <button type="submit" disabled={loading}>
            {loading ? "Comparing..." : "Run Compare"}
          </button>
        </form>

        {error && <p className="text-error">{error}</p>}
        {output && (
          <pre className="json-box">
            <code>{output}</code>
          </pre>
        )}
      </InfoCard>
    </div>
  );
}
