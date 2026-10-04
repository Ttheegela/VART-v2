import { useEffect, useState } from "react";
import { getHealth, messageOf, type Health } from "../lib/api";

export default function StatusPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealth().then(setHealth, (e) => setError(messageOf(e)));
  }, []);

  if (error) return <p role="alert" className="border border-black p-3">Status check failed: {error}</p>;
  if (!health) return <p>Checking status…</p>;
  const canary = health.canary;
  return (
    <section aria-label="System status" className="border border-black bg-white p-4">
      <h2 className="font-semibold">System status</h2>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
        <dt>Overall</dt>
        <dd>{health.status === "ok" ? "OK" : "Degraded"}</dd>
        <dt>Database</dt>
        <dd>{health.db === "ok" ? "OK" : "Unavailable"}</dd>
        <dt>Model check</dt>
        <dd>{!canary ? "Not run yet" : canary.ok ? `OK (${new Date(canary.at).toLocaleDateString()})` : "Failing"}</dd>
      </dl>
    </section>
  );
}
