import { useEffect, useState } from "react";
import { getHealth, messageOf, type Health } from "../lib/api";
import { ErrorLine } from "./ui";

function modelCheck(health: Health): string {
  if (health.db !== "ok") return "Unknown"; // the last check is stored in the database
  if (!health.canary) return "Not run yet";
  return health.canary.ok ? `OK (${new Date(health.canary.at).toLocaleDateString()})` : "Failing";
}

export default function StatusPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealth().then(setHealth, (e) => setError(messageOf(e)));
  }, []);

  return (
    <section aria-label="system status" className="border border-rule-strong p-3">
      <h2 className="mb-2 border-b border-ink pb-1 text-xs font-medium text-ink-2">system status</h2>
      {error ? (
        <ErrorLine message={`the status check failed: ${error}`} />
      ) : !health ? (
        <p role="status" className="text-sm text-ink-3">checking…</p>
      ) : (
        <dl className="grid grid-cols-[14ch_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-sm">
          <dt className="text-ink-3">overall</dt>
          <dd>{health.status === "ok" ? "OK" : "Degraded"}</dd>
          <dt className="text-ink-3">database</dt>
          <dd>{health.db === "ok" ? "OK" : "Unavailable"}</dd>
          <dt className="text-ink-3">model check</dt>
          <dd>{modelCheck(health)}</dd>
        </dl>
      )}
    </section>
  );
}
