import { useEffect, useId, useState } from "react";
import { getHealth, messageOf, type Health } from "../lib/api";

function modelCheck(health: Health): string {
  if (health.db !== "ok") return "Unknown"; // the last check is stored in the database
  if (!health.canary) return "Not run yet";
  return health.canary.ok ? `OK (${new Date(health.canary.at).toLocaleDateString()})` : "Failing";
}

export default function StatusPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();

  useEffect(() => {
    getHealth().then(setHealth, (e) => setError(messageOf(e)));
  }, []);

  if (error) return <p role="alert" className="border border-black p-3">Status check failed: {error}</p>;
  if (!health) return <p role="status">Checking status…</p>;
  return (
    <section aria-labelledby={titleId} className="border border-black bg-white p-4">
      <h2 id={titleId} className="font-semibold">System status</h2>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
        <dt>Overall</dt>
        <dd>{health.status === "ok" ? "OK" : "Degraded"}</dd>
        <dt>Database</dt>
        <dd>{health.db === "ok" ? "OK" : "Unavailable"}</dd>
        <dt>Model check</dt>
        <dd>{modelCheck(health)}</dd>
      </dl>
    </section>
  );
}
