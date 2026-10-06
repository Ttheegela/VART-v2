import { useEffect, useRef, useState } from "react";
import { Shell, goneOn404, type ViewProps } from "../components/Shell";
import { ErrorLine, Kbd } from "../components/ui";
import { api, type AuditEventOut } from "../lib/api";
import { useKeys } from "../lib/keys";

export default function AuditLog({ workspace, onGone }: ViewProps) {
  const [events, setEvents] = useState<AuditEventOut[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const search = useRef<HTMLInputElement>(null);
  useEffect(() => {
    let alive = true;
    api.audit().then(
      (l) => { if (alive) setEvents([...l].sort((a, b) => b.at.localeCompare(a.at))); },
      (e) => { if (alive) setError(goneOn404(e, onGone)); },
    );
    return () => { alive = false; };
  }, [onGone]);
  useKeys({ "/": () => search.current?.focus() });
  const shown = events.filter((e) => !query || e.action.includes(query.trim()));
  return (
    <Shell mode="AUDIT" cursor={`${shown.length} events`} hints={[["/", "search"], ["?", "all keys"]]} expiresAt={workspace.expires_at}>
      <div className="p-4">
        <div className="flex items-center gap-2 border-b border-ink pb-1">
          <h1 className="text-xs font-medium text-ink-2">audit log</h1>
          <label className="ml-auto flex items-center gap-1 text-xs"><Kbd>/</Kbd>
            <input ref={search} aria-label="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="action" className="h-6 w-48 max-w-full border border-rule-strong bg-paper px-2 text-sm placeholder:text-ink-3" />
          </label>
        </div>
        <ErrorLine message={error} />
        <div className="overflow-x-auto">
          <table data-tour="audit" className="w-full min-w-[40rem] table-fixed text-sm">
            <thead className="text-xs text-ink-2"><tr className="h-6"><th className="w-48 text-left">time</th><th className="w-20 text-left">actor</th><th className="w-56 text-left">action</th><th className="text-left">ref</th></tr></thead>
            <tbody>
              {shown.map((e, i) => (
                <tr key={i} className="h-7 border-b border-rule">
                  <td className="tabular-nums text-ink-3">{new Date(e.at).toISOString().replace("T", " ").slice(0, 19)} UTC</td>
                  <td>{e.actor}</td><td>{e.action}</td><td className="truncate text-ink-3">{e.ref ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Shell>
  );
}
