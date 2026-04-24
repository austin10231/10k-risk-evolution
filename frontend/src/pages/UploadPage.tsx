import { useState } from "react";
import { PageHeader } from "../components/common/PageHeader";
import { InfoCard } from "../components/common/InfoCard";
import { risklensApi } from "../services/risklensApi";

export function UploadPage() {
  const [company, setCompany] = useState("");
  const [industry, setIndustry] = useState("Technology");
  const [year, setYear] = useState(new Date().getFullYear().toString());
  const [filingType, setFilingType] = useState("10-K");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!company.trim()) {
      setError("Company is required.");
      return;
    }

    if (!file) {
      setError("File is required.");
      return;
    }

    setSubmitting(true);
    setError("");
    setResult("");

    try {
      const formData = new FormData();
      formData.append("company", company.trim());
      formData.append("industry", industry);
      formData.append("year", year);
      formData.append("filing_type", filingType);
      formData.append("file", file);

      const response = await risklensApi.uploadFiling(formData);
      setResult(response.record_id ? `Uploaded. Record ID: ${response.record_id}` : "Upload completed.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <PageHeader
        icon="➕"
        title="Upload"
        subtitle="Upload filing and send to backend ingestion pipeline"
      />

      <InfoCard title="Manual Upload" hint="Endpoint: POST /upload">
        <form className="form-grid" onSubmit={handleSubmit}>
          <label>
            Company
            <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Apple Inc." />
          </label>

          <label>
            Industry
            <select value={industry} onChange={(e) => setIndustry(e.target.value)}>
              <option>Technology</option>
              <option>Finance</option>
              <option>Healthcare</option>
              <option>Energy</option>
              <option>Consumer</option>
            </select>
          </label>

          <label>
            Year
            <input value={year} onChange={(e) => setYear(e.target.value)} />
          </label>

          <label>
            Filing Type
            <select value={filingType} onChange={(e) => setFilingType(e.target.value)}>
              <option>10-K</option>
              <option>10-Q</option>
            </select>
          </label>

          <label className="file-input">
            Filing File (HTML/PDF)
            <input
              type="file"
              accept=".html,.htm,.pdf"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>

          <button type="submit" disabled={submitting}>
            {submitting ? "Uploading..." : "Extract & Save"}
          </button>
        </form>

        {error && <p className="text-error">{error}</p>}
        {result && <p className="text-success">{result}</p>}
      </InfoCard>
    </div>
  );
}
