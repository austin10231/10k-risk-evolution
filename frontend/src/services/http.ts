import { API_BASE_URL, REQUEST_TIMEOUT_MS } from "../config/env";

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: BodyInit | null;
  headers?: Record<string, string>;
  signal?: AbortSignal;
};

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      body: options.body,
      headers: options.headers,
      signal: options.signal ?? controller.signal
    });

    const text = await response.text();
    const data = text ? safeParseJson(text) : null;

    if (!response.ok) {
      throw new ApiError(
        `Request failed (${response.status})`,
        response.status,
        data ?? text
      );
    }

    return data as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }

    if (error instanceof Error && error.name === "AbortError") {
      throw new ApiError("Request timeout", 408, null);
    }

    throw new ApiError("Network error", 0, error);
  } finally {
    clearTimeout(timeout);
  }
}

function safeParseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
