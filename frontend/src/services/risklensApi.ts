import { apiRequest } from "./http";
import type {
  CompareResponse,
  FilingRecord,
  HealthResponse,
  UploadResponse
} from "../types/api";

export const risklensApi = {
  health: () => apiRequest<HealthResponse>("/health"),

  listRecords: () => apiRequest<FilingRecord[]>("/records"),

  uploadFiling: (formData: FormData) =>
    apiRequest<UploadResponse>("/upload", {
      method: "POST",
      body: formData
    }),

  compare: (payload: { left_record_id: string; right_record_id: string }) =>
    apiRequest<CompareResponse>("/compare", {
      method: "POST",
      body: JSON.stringify(payload),
      headers: {
        "Content-Type": "application/json"
      }
    })
};
