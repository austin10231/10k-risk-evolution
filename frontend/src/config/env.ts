const rawBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;

export const API_BASE_URL = (rawBaseUrl ?? "http://localhost:8000").replace(/\/$/, "");

const rawTimeout = import.meta.env.VITE_REQUEST_TIMEOUT_MS as string | undefined;
const parsedTimeout = rawTimeout ? Number(rawTimeout) : NaN;

export const REQUEST_TIMEOUT_MS = Number.isFinite(parsedTimeout) && parsedTimeout > 0
  ? parsedTimeout
  : 30000;
