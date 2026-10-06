import { useEffect, useState } from "react";
import ErrorBoundary from "./components/ErrorBoundary";
import { ExpiredNotice } from "./components/Shell";
import { ErrorLine } from "./components/ui";
import { ensureWorkspace, messageOf, type Workspace } from "./lib/api";
import { useRoute } from "./lib/route";
import AuditLog from "./views/AuditLog";
import ExportView from "./views/Export";
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
  if (route.view === "home" || !workspace) {
    return (
      <ErrorBoundary>
        <Home workspace={workspace} startError={error} />
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
      {!route.run && ["run", "questions", "export"].includes(route.view) && <ErrorLine message="No run is selected; start one from the workspace." />}
    </ErrorBoundary>
  );
}
