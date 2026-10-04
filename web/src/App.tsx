import { useEffect, useState } from "react";
import ErrorBoundary from "./components/ErrorBoundary";
import StatusPanel from "./components/StatusPanel";
import { ensureWorkspace, messageOf } from "./lib/api";

export default function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ensureWorkspace().then(
      () => setReady(true),
      (e) => setError(messageOf(e)),
    );
  }, []);

  return (
    <div className="min-h-screen bg-neutral-100 text-black">
      <header className="border-b border-black bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-baseline gap-x-6 gap-y-1 px-4 py-3">
          <h1 className="text-xl font-semibold">VART</h1>
          <span className="text-sm text-neutral-600">
            Security questionnaire answering · synthetic demo data · every answer cites its source
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        <ErrorBoundary>
          {error ? (
            <p role="alert" className="border border-black p-3 font-medium">Couldn't start the demo: {error}</p>
          ) : !ready ? (
            <p role="status">Loading…</p>
          ) : (
            <p className="text-sm text-neutral-700">
              The questionnaire workspace arrives in the next build. This page checks that the app, its database and
              its model connection are alive.
            </p>
          )}
          {/* Health needs no workspace, so an outage still shows here when the demo cannot start. */}
          <StatusPanel />
        </ErrorBoundary>
      </main>
    </div>
  );
}
