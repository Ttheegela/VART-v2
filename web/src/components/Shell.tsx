import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, api, messageOf, type Workspace } from "../lib/api";
import { useKeys } from "../lib/keys";
import { go, href, useRoute, type View } from "../lib/route";
import { Button, Kbd } from "./ui";

const VIEWS: [View, string][] = [
  ["workspace", "workspace"],
  ["run", "run"],
  ["questions", "questions for you"],
  ["export", "export"],
  ["audit", "audit log"],
];

export const KEY_TABLE: [string, string][] = [
  ["s / o", "try with a sample company / use your own files (Home)"],
  ["1–5", "workspace · run · questions for you · export · audit log"],
  ["v p c u y x", "toggle a label filter (Run)"],
  ["/", "focus search"],
  ["j / k", "move down / up a row (and ↓ / ↑)"],
  ["enter", "open the evidence drawer"],
  ["esc", "close the drawer or this sheet; clear search"],
  ["r", "re-run live"],
  ["e", "export xlsx"],
  ["A", "approve all verified"],
  ["i", "answer this question"],
  ["a", "approve"],
  ["n", "mark not applicable"],
  ["l / q / w", "load the sample documents / sample questionnaire A / B (Workspace)"],
  ["R", "reset the workspace: delete everything now (Workspace)"],
  ["ctrl+enter", "send an answer (Questions for you)"],
  ["?", "show all keys"],
];

function remaining(expiresAt: string | null): string | null {
  if (!expiresAt) return null;
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) return "expired";
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return `expires ${h}h${String(m).padStart(2, "0")}m`;
}

/** A modal layer: while open it owns the keyboard (Esc closes it, Tab stays inside, every other unmodified key is
 * inert), takes focus on open and gives it back on close. A window capture listener runs before every `useKeys`. */
export function KeySheet({ onClose }: { onClose: () => void }) {
  const box = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  useLayoutEffect(() => {
    close.current = onClose;
  });
  useEffect(() => {
    const opener = document.activeElement;
    box.current?.querySelector<HTMLElement>("button")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Tab") {
        const els = [...(box.current?.querySelectorAll<HTMLElement>("button, a[href], input, [tabindex]") ?? [])];
        const i = els.indexOf(document.activeElement as HTMLElement);
        e.preventDefault();
        els[(i + (e.shiftKey ? -1 : 1) + els.length) % els.length]?.focus();
      } else if (e.key === "Escape") {
        e.preventDefault();
        close.current();
      } else if (e.ctrlKey || e.metaKey || e.altKey) {
        return; // browser shortcuts stay the browser's
      }
      e.stopImmediatePropagation();
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, []);
  return (
    <div ref={box} role="dialog" aria-modal="true" aria-label="keys" className="fixed inset-0 z-20 overflow-auto bg-paper p-4">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-center justify-between border-b border-ink pb-1">
          <h2 className="text-xs font-medium">all keys</h2>
          <Button k="esc" shortcut="Escape" label="Close" onClick={onClose} />
        </div>
        <table className="mt-2 w-full text-xs">
          <tbody>
            {KEY_TABLE.map(([k, what]) => (
              <tr key={k} className="border-b border-rule">
                <td className="w-32 py-1 font-medium">{k}</td>
                <td className="py-1 text-ink-2">{what}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export type ViewProps = { workspace: Workspace; onGone: () => void };

/** A 404 on an id the page remembered means the workspace changed under it (expired or reset). */
export function goneOn404(e: unknown, onGone: () => void): string | null {
  if (e instanceof ApiError && e.status === 404) {
    onGone();
    return null;
  }
  return messageOf(e);
}

export function ExpiredNotice() {
  useKeys({ Enter: () => window.location.assign("/") });
  return (
    <div role="alert" className="m-4 border border-rule-strong p-4">
      <p className="text-base font-medium">This workspace has expired or was reset.</p>
      <p className="mt-1 text-sm text-ink-2">Workspaces stop working after 24 hours. Start again to get a new one.</p>
      <div className="mt-3">
        <Button k="enter" shortcut="Enter" label="Start again" primary onClick={() => { window.location.assign("/"); }} />
      </div>
    </div>
  );
}

type ShellProps = {
  mode: string;
  cursor: string;
  hints: [string, string][];
  runId?: string;
  expiresAt: string | null;
  children: ReactNode;
};

/** design.md Workbench: inverted top bar (numbered views), the view, inverted status line. */
export function Shell({ mode, cursor, hints, runId, expiresAt, children }: ShellProps) {
  const route = useRoute();
  const [sheet, setSheet] = useState(false);
  const target = (v: View) => (v === "workspace" || v === "audit" ? { view: v } : runId ? { view: v, run: runId } : null);
  useKeys({
    "?": () => setSheet(true), // the open sheet handles its own Esc, so a drawer's Esc is never taken here
    ...Object.fromEntries(
      VIEWS.map(([v], i) => [String(i + 1), () => { const t = target(v); if (t) go(t); }]),
    ),
  });
  const left = remaining(expiresAt);
  return (
    <div className="grid h-dvh grid-rows-[36px_minmax(0,1fr)_28px] bg-paper text-ink">
      <header data-chrome className="flex h-9 items-center gap-4 overflow-hidden bg-chrome px-4 text-on-chrome-2">
        <a href="/" className="font-bold tracking-[0.12em] text-on-chrome">VART</a>
        <nav aria-label="views" className="flex min-w-0 flex-1 gap-1 overflow-x-auto p-1 text-xs">
          {VIEWS.map(([v, name], i) => {
            const t = target(v);
            const current = route.view === v;
            return t ? (
              <a
                key={v}
                href={href(t)}
                onClick={(e) => { e.preventDefault(); go(t); }}
                aria-current={current ? "page" : undefined}
                aria-keyshortcuts={String(i + 1)}
                className={`flex h-6 items-center gap-1 whitespace-nowrap px-2 ${current ? "bg-on-chrome font-medium text-ink" : "hover:bg-chrome-2 hover:text-on-chrome"}`}
              >
                <Kbd>{i + 1}</Kbd> {name}
              </a>
            ) : (
              <span key={v} aria-disabled="true" className="flex h-6 items-center gap-1 whitespace-nowrap px-2 opacity-60">
                <Kbd>{i + 1}</Kbd> {name}
              </span>
            );
          })}
        </nav>
        {left && <span className="hidden text-xs min-[900px]:inline">{left}</span>}
      </header>
      <main className="min-h-0 overflow-auto">{children}</main>
      <footer data-chrome className="flex h-7 items-center gap-3 overflow-hidden bg-chrome px-4 text-xs text-on-chrome-2">
        <span className="bg-on-chrome px-1 font-bold text-ink">{mode}</span>
        {cursor && <span>{cursor}</span>}
        {/* not <Kbd>: these hints are not on a control with aria-keyshortcuts, so the key must stay readable */}
        {hints.map(([k, what], i) => (
          <span key={k} className={i > 1 ? "hidden min-[480px]:inline" : ""}><kbd>{k}</kbd> {what}</span>
        ))}
        <span className="ml-auto hidden min-[900px]:inline">VART · labels decided by code · synthetic demo data · MIT</span>
      </footer>
      {sheet && <KeySheet onClose={() => setSheet(false)} />}
    </div>
  );
}

/** Wipe now (POST /api/workspace/reset); the workspace view's `R` action calls this after a confirm. */
export async function resetAndReload() {
  await api.resetWorkspace();
  window.location.assign("/");
}
