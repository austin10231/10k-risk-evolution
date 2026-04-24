import { API_BASE_URL } from "../../config/env";

export function ApiHint() {
  return (
    <p className="api-hint">
      API Base URL: <code>{API_BASE_URL}</code>
    </p>
  );
}
