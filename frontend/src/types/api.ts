export type HealthResponse = {
  status: string;
  time_of_last_update?: number;
};

export type FilingRecord = {
  record_id: string;
  company: string;
  industry: string;
  year: number;
  filing_type: string;
  file_ext?: "html" | "pdf";
  created_at?: string;
};

export type UploadResponse = {
  record_id: string;
  result?: unknown;
};

export type CompareResponse = {
  compare_id?: string;
  result?: unknown;
};
