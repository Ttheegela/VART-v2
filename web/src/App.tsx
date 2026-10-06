import { useEffect, useState } from "react";
import ErrorBoundary from "./components/ErrorBoundary";
import { ExpiredNotice } from "./components/Shell";
import Tour from "./components/Tour";
import { ErrorLine } from "./components/ui";
import { ensureWorkspace, messageOf, type Workspace } from "./lib/api";
import { useRoute } from "./lib/route";
import AuditLog from "./views/AuditLog";
import ExportView from "./views/Export";
import GapCheck from "./views/GapCheck";
import Home from "./views/Home";
import Questions from "./views/Questions";
import RunGrid from "./views/RunGrid";
import WorkspaceView from "./views/Workspace";

export default function App() {
  const route = useRoute();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    ensureWorkspace().then(setWorkspace, (e) => setError(messageOf(e)));
  }, []);

  const onGone = () => setGone(true);
  if (gone) return <ExpiredNotice />;
  if (route.view !== "home" && !workspace && !error) {
    // a deep link waits for its workspace here instead of flashing Home
    return <p role="status" className="m-4 text-xs text-ink-3">Opening your workspace…</p>;
  }
  if (route.view === "home" || !workspace) {
    return (
      <ErrorBoundary>
        <Home workspace={workspace} startError={error} />
        <Tour />
      </ErrorBoundary>
    );
  }
  const props = { workspace, onGone };
  return (
    <ErrorBoundary>
      {route.view === "workspace" && <WorkspaceView {...props} />}
      {route.view === "run" && route.run && <RunGrid {...props} runId={route.run} itemId={route.item} />}
      {route.view === "questions" && route.run && <Questions {...props} runId={route.run} />}
      {route.view === "export" && route.run && <ExportView {...props} runId={route.run} />}
      {route.view === "audit" && <AuditLog {...props} />}
      {route.view === "gap" && <GapCheck {...props} scope={route.scope} outcome={route.item} />}
      {!route.run && ["run", "questions", "export"].includes(route.view) && <ErrorLine message="No run is selected; start one from the workspace." />}
      <Tour />
    </ErrorBoundary>
  );
}
