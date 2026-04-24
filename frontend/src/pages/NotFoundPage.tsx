import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="card">
      <h1 className="card-title">Page not found</h1>
      <p className="card-hint">The route does not exist in this frontend app.</p>
      <Link to="/home" className="inline-link">
        Back to Home
      </Link>
    </div>
  );
}
