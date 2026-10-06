import { memo, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import { Shell, goneOn404, type ViewProps } from "../components/Shell";
import { Button, ErrorLine, GapChip, Kbd, LabelChip } from "../components/ui";
import { api, messageOf, type GapLabel, type GapOut, type GapRow, type GapScope, type RunRowsOut } from "../lib/api";
import { useKeys } from "../lib/keys";
import { GAP_FOOTER, GAP_LABELS, GAP_REVIEW, SCOPES, SCOPE_KEY } from "../lib/labels";
import { go } from "../lib/route";
import { useStepLoop } from "./RunGrid";

const NOT_CHECKED = "not checked in this version"; // CSF spec 5.5
const NOTHING_CHANGED = "Nothing changed since the last check."; // adversary-1 M7
type Filter = GapLabel | "not_applicable" | "no_result" | "not_checked";
const FILTERS: readonly Filter[] = [...GAP_LABELS, "not_applicable", "no_result", "not_checked"];
const TEXT_FILTER = { no_result: "no result", not_checked: "not checked" } as const;

/** The status line (CSF spec 7): counted from the rows, never typed in, so coverage is never overstated. */
export function coverage(rows: GapRow[]): string {
  const n = (tier: GapRow["tier"]) => rows.filter((r) => r.tier === tier).length;
  return `checked ${n("checked")} · ask me ${n("ask")} · not checked ${n("not_checked")} · of ${rows.length}`;
}

// adversary-1 I1: a visitor's N/A wins over the tier's label ("not answered" on Ask me, none on Checked).
// No label otherwise is "no result" (not run yet, or failed: adversary-1 M4), so every row has exactly one filter.
const filterOf = (r: GapRow): Filter =>
  r.tier === "not_checked" ? "not_checked" : r.not_applicable ? "not_applicable" : (r.label ?? "no_result");
const group = (r: GapRow) => `${r.function} / ${r.category}`.toLowerCase();

type RowProps = { row: GapRow; i: number; cursor: boolean; selected: boolean; section: string | null; pending: boolean };

/** One 28px line per outcome (design.md List row), under a `# function / category` line when that changes. */
const Row = memo(function Row({ row: r, i, cursor, selected, section, pending }: RowProps) {
  const quiet = r.tier === "not_checked" || r.not_applicable || !r.label;
  // a FAILED outcome has no label and carries its failure sentence as the explanation (adversary-1 M4)
  const note =
    r.tier === "not_checked" ? NOT_CHECKED : (r.explanation ?? (pending ? "checking…" : r.answer_id ? "" : "not run yet"));
  const chip = r.not_applicable ? <LabelChip label="na" /> : r.label ? <GapChip label={r.label} /> : r.tier === "not_checked" ? "not checked" : "";
  return (
    <>
      {section !== null && (
        <tr className="h-6 border-b border-rule-strong text-xs text-ink-3">
          <td colSpan={6} className="truncate px-2"># {section}</td>
        </tr>
      )}
      <tr
        data-i={i}
        tabIndex={cursor ? 0 : -1}
        aria-selected={selected}
        aria-label={`${r.csf_id} ${r.outcome}`}
        className={`h-7 cursor-pointer border-b border-rule hover:bg-sunken focus-visible:-outline-offset-2 ${selected ? "bg-sunken font-medium outline-2 -outline-offset-2 outline-ink" : ""} ${quiet ? "text-ink-3" : ""}`}
      >
        <td aria-hidden="true" className="pl-2 font-bold">{cursor ? ">" : ""}</td>
        <td className="truncate px-2">{r.csf_id}</td>
        <td className="truncate px-2">{chip}</td>
        <td className="px-2 text-right tabular-nums">{r.label && !r.not_applicable ? r.sources : ""}</td>
        <td className="truncate px-2">{r.outcome}</td>
        <td className={`truncate px-2 ${quiet ? "" : "text-ink-2"}`}>{note}</td>
      </tr>
    </>
  );
});

export default function GapCheck({ workspace, onGone, scope, outcome }: ViewProps & { scope?: string; outcome?: string }) {
  const current: GapScope = SCOPES.find((s) => s === scope) ?? "core";
  const [loaded, setData] = useState<GapOut | null>(null);
  const data = loaded?.scope === current ? loaded : null; // another scope's rows never show
  const [tick, setTick] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Set<Filter>>(new Set());
  const [cursorAt, setCursorAt] = useState({ scope: current, i: 0 });
  const cursor = cursorAt.scope === current ? cursorAt.i : 0; // a scope switch starts at the first row
  const setCursor = (i: number) => setCursorAt({ scope: current, i });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ scope: GapScope; text: string } | null>(null);
  const download = useRef<HTMLAnchorElement>(null);
  const body = useRef<HTMLTableSectionElement>(null);

  useEffect(() => {
    let alive = true; // a slow answer for an old scope or tick never lands
    api.gap(current).then(
      (d) => { if (alive) { setData(d); setError(null); } },
      (e) => { if (alive) setError(goneOn404(e, onGone)); },
    );
    return () => { alive = false; };
  }, [current, onGone, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);

  // The Run grid's loop drives the steps; after each one the rows are read again from GET /api/gap/{scope}.
  const run = data?.run ?? null;
  const loop = useMemo<RunRowsOut | null>(() => (run ? { run, rows: [] } : null), [run]);
  const { error: loopError, running } = useStepLoop(run?.id ?? "", loop, reload, onGone);

  const rows = data?.rows;
  const counts = useMemo(() => {
    const c = Object.fromEntries(FILTERS.map((l) => [l, 0])) as Record<Filter, number>;
    for (const r of rows ?? []) c[filterOf(r)] += 1;
    return c;
  }, [rows]);
  const visible = useMemo(
    () => (rows ?? []).filter((r) => filters.size === 0 || filters.has(filterOf(r))),
    [rows, filters],
  );
  const sections = useMemo(
    () => visible.map((r, i) => (i === 0 || group(r) !== group(visible[i - 1]) ? group(r) : null)),
    [visible],
  );
  const cur = Math.max(0, Math.min(cursor, visible.length - 1));
  useEffect(() => { body.current?.querySelector<HTMLElement>(`tr[data-i="${cur}"]`)?.focus(); }, [cur]);

  const toggle = (l: Filter) => setFilters((f) => { const n = new Set(f); if (n.has(l)) n.delete(l); else n.add(l); return n; });
  const openRow = (i: number) => { const r = visible[i]; if (r) go({ view: "gap", scope: current, item: r.csf_id }); };
  const rowAt = (e: MouseEvent | KeyboardEvent) => {
    const tr = (e.target as HTMLElement).closest<HTMLElement>("tr[data-i]");
    return tr ? Number(tr.dataset.i) : null;
  };
  const start = async () => {
    if (!data || busy || running) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const out = await api.startGap(current);
      if (out.status === "done") setNotice({ scope: current, text: NOTHING_CHANGED });
      reload();
    } catch (e) { setError(messageOf(e)); }
    setBusy(false);
  };
  const exportFile = () => { if (run && !running) download.current?.click(); }; // a running check's sheet is partial
  const down = () => setCursor(Math.min(cur + 1, visible.length - 1));
  const up = () => setCursor(Math.max(cur - 1, 0));

  useKeys({
    ...Object.fromEntries(SCOPES.map((s) => [SCOPE_KEY[s], () => go({ view: "gap", scope: s })])),
    j: down,
    ArrowDown: down,
    k: up,
    ArrowUp: up,
    r: () => void start(),
    e: exportFile,
  });

  const said = notice?.scope === current ? notice.text : null;
  const status = running ? "Checking." : run?.status === "done" ? `Gap check done: ${run.done} of ${run.total} checked.` : "";
  // no scope hint in the status line: the keys sit on the scope line, and the coverage line keeps the room
  return (
    <Shell
      mode="GAP"
      cursor={data ? coverage(data.rows) : ""}
      hints={[["r", "run"], ["e", "export"], ["?", "all keys"]]}
      expiresAt={workspace.expires_at}
    >
      <div className="grid h-full min-h-0">
        <div className="flex min-h-0 min-w-0 flex-col">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-rule-strong px-4 py-2">
            <div className="min-w-0">
              <h1 className="text-base font-medium [overflow-wrap:anywhere]">
                workspace<span className="px-1 text-ink-3">/</span>csf 2.0<span className="px-1 text-ink-3">/</span>{current}
              </h1>
              <p className="text-xs text-ink-3">
                {GAP_REVIEW} · labels decided by code
                {run ? ` · ${run.done} of ${run.total} checked · ${running ? "checking" : run.status} · $${run.cost_usd.toFixed(4)}` : " · not run yet"}
              </p>
              {data && <p aria-hidden="true" className="text-xs text-ink-2">{coverage(data.rows)}</p>}
              <p role="status" className={said ? "text-xs text-ink-2" : "sr-only"}>{said ?? status}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button k="r" label={run ? "Check again" : "Run gap check"} primary onClick={() => void start()} busy={busy} busyLabel="Starting…" disabled={!data || running} />
              <Button k="e" label="Export xlsx" onClick={exportFile} disabled={!run || running} />
              {running && <span className="self-center text-xs text-ink-3">export when the check is done</span>}
              {run && <a ref={download} href={api.exportUrl(run.id)} download hidden tabIndex={-1} aria-hidden="true" />}
            </div>
          </div>
          <div role="group" aria-label="scope" className="flex flex-wrap gap-x-3 gap-y-1 border-b border-rule-strong px-4 py-1 text-xs">
            {SCOPES.map((s) => (
              <button key={s} type="button" aria-pressed={s === current} aria-keyshortcuts={SCOPE_KEY[s]} onClick={() => go({ view: "gap", scope: s })}
                className={`flex h-6 items-center gap-1 whitespace-nowrap border px-1 hover:border-rule-strong ${s === current ? "border-ink font-medium" : "border-transparent"}`}>
                <Kbd>{SCOPE_KEY[s]}</Kbd>{s === "core" ? "all core" : s}
              </button>
            ))}
          </div>
          {/* no single keys: g i p d s o a r e are taken (plan 6B note 11); Tab reaches each toggle */}
          <div role="group" aria-label="filter by label" className="flex flex-wrap gap-x-3 gap-y-1 border-b border-rule-strong bg-sunken px-4 py-1">
            {FILTERS.map((l) => (
              <button key={l} type="button" aria-pressed={filters.has(l)} onClick={() => toggle(l)}
                className={`flex h-6 items-center gap-1 whitespace-nowrap border px-1 text-xs hover:border-rule-strong hover:bg-paper ${filters.has(l) ? "border-ink bg-paper" : "border-transparent"}`}>
                {l === "no_result" || l === "not_checked" ? <span className="px-1 text-ink-3">{TEXT_FILTER[l]}</span> : l === "not_applicable" ? <LabelChip label="na" /> : <GapChip label={l} />}{" "}
                <span className="font-bold tabular-nums">{counts[l]}</span>
              </button>
            ))}
          </div>
          <div className="px-4"><ErrorLine message={error ?? loopError} /></div>
          <div className="min-h-0 flex-1 overflow-auto">
            <table aria-label="outcomes" aria-rowcount={visible.length + sections.filter((x) => x !== null).length + 1} className="w-full min-w-[56rem] table-fixed border-collapse text-sm">
              <colgroup>
                <col className="w-[3ch]" /><col className="w-[12ch]" /><col className="w-[19ch]" /><col className="w-[6ch]" />
                <col className="w-[40%]" /><col />
              </colgroup>
              <thead className="sticky top-0 z-[1] bg-paper text-left text-xs font-medium text-ink-2">
                <tr className="h-6 border-b border-ink">
                  <th scope="col"><span className="sr-only">cursor</span></th>
                  <th scope="col" className="px-2">id</th>
                  <th scope="col" className="px-2">label</th>
                  <th scope="col" className="px-2 text-right">src</th>
                  <th scope="col" className="px-2">nist outcome</th>
                  <th scope="col" className="px-2">explanation</th>
                </tr>
              </thead>
              <tbody
                ref={body}
                onClick={(e) => { const i = rowAt(e); if (i !== null) { setCursor(i); openRow(i); } }}
                onKeyDown={(e) => { const i = rowAt(e); if (e.key === "Enter" && i !== null) { e.preventDefault(); openRow(i); } }}
              >
                {visible.map((r, i) => (
                  <Row key={r.csf_id} row={r} i={i} cursor={i === cur} selected={r.csf_id === outcome} section={sections[i]}
                    pending={running && r.tier !== "not_checked" && !r.answer_id} />
                ))}
              </tbody>
            </table>
          </div>
          <p className="border-t border-rule-strong px-4 py-1 text-xs text-ink-3">{GAP_FOOTER}</p>
        </div>
      </div>
    </Shell>
  );
}
