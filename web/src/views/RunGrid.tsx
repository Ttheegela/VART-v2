import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import { Shell, goneOn404, type ViewProps } from "../components/Shell";
import { Button, ErrorLine, Kbd, LabelChip } from "../components/ui";
import { ApiError, api, messageOf, type Label, type RunRow, type RunRowsOut, type StepOut } from "../lib/api";
import { useKeys } from "../lib/keys";
import { FILTER_KEY, LABELS, approvalText, confidenceText } from "../lib/labels";
import { go } from "../lib/route";
import EvidenceDrawer from "./EvidenceDrawer";

/** Unchanged rows keep their identity, so memoized rows skip rendering when a step answers others. */
export function mergeRows(rows: RunRow[], answered: RunRow[]): RunRow[] {
  const by = new Map(answered.map((r) => [r.item.id, r]));
  return rows.map((r) => by.get(r.item.id) ?? r);
}

const IDLE_FIRST_MS = 2000;
const IDLE_MAX_MS = 10_000;

/** Calls step while the run is running. A step with no answers while still running (another tab holds the
 * claims) waits 2 s, doubling to 10 s, until answers arrive. A 429 with Retry-After waits as told and shows the
 * scope sentence meanwhile; a 404 calls `onGone` when given; any other error stops the loop and is shown in words.
 * A step that returns is always merged, even after a cleanup (the server has claimed those items), and a remount
 * (StrictMode, or a status flip) awaits the call already in flight instead of sending a second one. */
export function useStepLoop(
  runId: string, data: RunRowsOut | null, onData: (d: RunRowsOut) => void, onGone?: () => void,
) {
  const [failure, setFailure] = useState<{ runId: string; message: string } | null>(null);
  const [stopped, setStopped] = useState<string | null>(null); // the run whose loop an error ended
  const latest = useRef(data);
  const sink = useRef(onData);
  const gone = useRef(onGone);
  const flight = useRef<{ runId: string; p: Promise<StepOut> } | null>(null); // one in-flight step per run
  useLayoutEffect(() => {
    latest.current = data;
    sink.current = onData;
    gone.current = onGone;
  });
  const status = data?.run.status;
  useEffect(() => {
    if (status !== "running") return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const wait = (ms: number) => new Promise<void>((resolve) => { timer = setTimeout(resolve, ms); });
    const step = () => {
      if (flight.current?.runId !== runId) {
        const f = { runId, p: api.step(runId) };
        const clear = () => { if (flight.current === f) flight.current = null; };
        f.p.then(clear, clear);
        flight.current = f;
      }
      return flight.current.p;
    };
    (async () => {
      let idle = 0;
      while (alive) {
        try {
          const out = await step();
          const cur = latest.current;
          if (cur?.run.id === out.run.id) {
            const next = { run: out.run, rows: mergeRows(cur.rows, out.answered) }; // merging twice is harmless
            latest.current = next;
            sink.current(next);
          }
          if (!alive || !cur) return; // only the next call is cancelled, never the merge
          setFailure(null);
          if (out.run.status !== "running") return;
          if (out.answered.length > 0) idle = 0;
          else await wait(Math.min(IDLE_FIRST_MS * 2 ** idle++, IDLE_MAX_MS));
        } catch (e) {
          if (!alive) return;
          if (e instanceof ApiError && e.status === 404 && gone.current) {
            gone.current();
            return setStopped(runId);
          }
          setFailure({ runId, message: messageOf(e) });
          if (e instanceof ApiError && e.status === 429 && e.retryAfter) await wait(e.retryAfter * 1000);
          else return setStopped(runId);
        }
      }
    })();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [runId, status]);
  return {
    error: failure?.runId === runId ? failure.message : null,
    running: status === "running" && stopped !== runId,
  };
}

type RowProps = { row: RunRow; i: number; cursor: boolean; selected: boolean; section: string | null };

/** One 28px line (plus its `# section` line when the topic changes); memoized so a step re-renders only the rows
 * it answered. Clicks and Enter are handled on the tbody. */
const Row = memo(function Row({ row: r, i, cursor, selected, section }: RowProps) {
  const a = r.answer;
  return (
    <>
      {section !== null && (
        <tr className="h-6 border-b border-rule-strong text-xs text-ink-3">
          <td colSpan={8} className="truncate px-2"># {section.toLowerCase()}</td>
        </tr>
      )}
      <tr
        data-i={i}
        tabIndex={cursor ? 0 : -1}
        aria-selected={selected}
        aria-label={`${r.item.code ?? r.item.position} ${r.item.question}`}
        className={`h-7 cursor-pointer border-b border-rule hover:bg-sunken focus-visible:-outline-offset-2 ${selected ? "bg-sunken font-medium outline-2 -outline-offset-2 outline-ink" : ""} ${a ? "" : "text-ink-3"}`}
      >
        <td aria-hidden="true" className="pl-2 font-bold">{cursor ? ">" : ""}</td>
        <td className="truncate px-2">{r.item.code ?? r.item.position}</td>
        <td className="truncate px-2">{a ? <LabelChip label={a.label} /> : null}</td>
        <td className="px-2 text-right tabular-nums">{a ? confidenceText(a) : ""}</td>
        <td className="px-2 text-right tabular-nums">{a ? a.sources : ""}</td>
        <td className="truncate px-2">{r.item.question}</td>
        <td className={`truncate px-2 ${a ? "text-ink-2" : ""}`}>{a ? a.text : "answering…"}</td>
        <td className={`truncate px-2 ${a?.approved ? "" : "text-ink-3"}`}>{a ? approvalText(a.approved) : ""}</td>
      </tr>
    </>
  );
});

export default function RunGrid({ workspace, onGone, runId, itemId }: ViewProps & { runId: string; itemId?: string }) {
  const [loaded, setData] = useState<RunRowsOut | null>(null);
  const data = loaded?.run.id === runId ? loaded : null; // a re-run's new id never shows the old run's rows
  const [name, setName] = useState<string | null>(null);
  const [failedLoad, setLoadError] = useState<{ runId: string; message: string | null } | null>(null);
  const loadError = failedLoad?.runId === runId ? failedLoad.message : null; // a re-run's id starts clean
  const [filters, setFilters] = useState<Set<Label>>(new Set());
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const search = useRef<HTMLInputElement>(null);
  const body = useRef<HTMLTableSectionElement>(null);

  useEffect(() => {
    let alive = true; // a slow load for an old run id never lands
    api.runAnswers(runId).then(
      (d) => { if (alive) setData(d); },
      (e) => { if (alive) setLoadError({ runId, message: goneOn404(e, onGone) }); },
    );
    return () => { alive = false; };
  }, [runId, onGone]);
  const questionnaireId = data?.run.questionnaire_id;
  useEffect(() => {
    if (!questionnaireId) return;
    api.questionnaires().then((qs) => setName(qs.find((q) => q.id === questionnaireId)?.filename ?? null), () => {});
  }, [questionnaireId]);
  const { error: loopError, running } = useStepLoop(runId, data, setData, onGone);

  const rows = data?.rows;
  const counts = useMemo(() => {
    const c = Object.fromEntries(LABELS.map((l) => [l, 0])) as Record<Label, number>;
    for (const r of rows ?? []) if (r.answer) c[r.answer.label] += 1;
    return c;
  }, [rows]);
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (rows ?? []).filter((r) =>
      (filters.size === 0 || (r.answer && filters.has(r.answer.label))) &&
      (!q || r.item.question.toLowerCase().includes(q) || (r.item.code ?? "").toLowerCase().includes(q)));
  }, [rows, filters, query]);
  const sections = useMemo(
    () => visible.map((r, i) => (i === 0 || r.item.topic !== visible[i - 1].item.topic ? r.item.topic : null)),
    [visible],
  );
  const cur = Math.max(0, Math.min(cursor, visible.length - 1));
  const open = itemId ? visible.find((r) => r.item.id === itemId) : undefined;

  useEffect(() => { body.current?.querySelector<HTMLElement>(`tr[data-i="${cur}"]`)?.focus(); }, [cur]);

  const toggle = (l: Label) => setFilters((f) => { const n = new Set(f); if (n.has(l)) n.delete(l); else n.add(l); return n; });
  const openRow = (i: number) => { const r = visible[i]; if (r?.answer) go({ view: "run", run: runId, item: r.item.id }); };
  const rowAt = (e: MouseEvent | KeyboardEvent) => {
    const tr = (e.target as HTMLElement).closest<HTMLElement>("tr[data-i]");
    return tr ? Number(tr.dataset.i) : null;
  };
  const verifiedOpen = (rows ?? []).filter((r) => r.answer?.label === "verified" && !r.answer.approved).length;
  const rerun = async () => {
    if (!data || running || busy) return;
    setBusy("rerun");
    setActionError(null);
    try { const run = await api.createRun(data.run.questionnaire_id); go({ view: "run", run: run.id }); } catch (e) { setActionError(messageOf(e)); }
    setBusy(null);
  };
  const approveAll = async () => {
    if (verifiedOpen === 0 || busy) return;
    setBusy("approve");
    setActionError(null);
    try { await api.approveVerified(runId); setData(await api.runAnswers(runId)); } catch (e) { setActionError(goneOn404(e, onGone)); }
    setBusy(null);
  };
  const exportFile = () => { if (data) window.location.assign(api.exportUrl(runId)); };

  useKeys({
    ...Object.fromEntries(LABELS.map((l) => [FILTER_KEY[l], () => toggle(l)])),
    "/": () => search.current?.focus(),
    j: () => setCursor(Math.min(cur + 1, visible.length - 1)),
    ArrowDown: () => setCursor(Math.min(cur + 1, visible.length - 1)),
    k: () => setCursor(Math.max(cur - 1, 0)),
    ArrowUp: () => setCursor(Math.max(cur - 1, 0)),
    r: () => void rerun(),
    e: exportFile,
    A: () => void approveAll(),
  }, !open);

  const current = visible[cur];
  const status = !data ? "" : running ? "Answering questions." : data.run.status === "done" ? `Run done: ${data.run.done} of ${data.run.total} answered.` : `Run ${data.run.status}.`;
  return (
    <Shell
      mode="RUN"
      cursor={current ? `${current.item.code ?? current.item.position} · ${cur + 1}/${visible.length}` : ""}
      hints={[["j/k", "move"], ["enter", "evidence"], ["/", "search"], ["?", "all keys"]]}
      expiresAt={workspace.expires_at}
      runId={runId}
    >
      <div className={`grid h-full min-h-0 ${open ? "min-[900px]:grid-cols-[minmax(0,1fr)_34rem]" : ""}`}>
        <div className="flex min-h-0 min-w-0 flex-col">
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-rule-strong px-4 py-2">
            <div className="min-w-0">
              <h1 className="text-base font-medium [overflow-wrap:anywhere]">
                {name && <>{name}<span className="px-1 text-ink-3">/</span></>}run {runId.slice(0, 8)}
              </h1>
              <p className="text-xs text-ink-3">
                {data ? `${data.run.done} of ${data.run.total} answered · ${running ? "answering" : data.run.status} · $${data.run.cost_usd.toFixed(4)}` : "loading…"}
              </p>
              <p role="status" className="sr-only">{status}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button k="r" label="Re-run live" onClick={() => void rerun()} busy={busy === "rerun"} busyLabel="Starting…" disabled={!data || running} />
              <Button k="e" label="Export xlsx" onClick={exportFile} disabled={!data} />
              <Button k="A" shortcut="Shift+A" label={`Approve all verified (${verifiedOpen})`} primary onClick={() => void approveAll()} busy={busy === "approve"} busyLabel="Approving…" disabled={verifiedOpen === 0} />
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-rule-strong bg-sunken px-4 py-1">
            <div role="group" aria-label="filter by label" className="flex flex-wrap gap-x-3 gap-y-1">
              {LABELS.map((l) => (
                <button key={l} type="button" aria-pressed={filters.has(l)} aria-keyshortcuts={FILTER_KEY[l]} onClick={() => toggle(l)}
                  className={`flex h-6 items-center gap-1 whitespace-nowrap border px-1 text-xs hover:border-rule-strong hover:bg-paper ${filters.has(l) ? "border-ink bg-paper" : "border-transparent"}`}>
                  <Kbd>{FILTER_KEY[l]}</Kbd><LabelChip label={l} />{" "}<span className="font-bold tabular-nums">{counts[l]}</span>
                </button>
              ))}
            </div>
            <label className="flex min-w-0 max-w-full items-center gap-2 text-xs text-ink-2">
              <Kbd>/</Kbd>
              <span className="sr-only">search</span>
              <input ref={search} type="search" placeholder="question text or ID" value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Escape") { setQuery(""); e.currentTarget.blur(); } }}
                className="h-6 w-64 min-w-0 max-w-full border border-rule-strong bg-paper px-2 text-sm text-ink placeholder:text-ink-3 hover:border-neutral-500" />
            </label>
          </div>
          <div className="px-4"><ErrorLine message={loadError ?? loopError ?? actionError} /></div>
          <div className="min-h-0 flex-1 overflow-auto">
            <table aria-label="answers" aria-rowcount={visible.length + 1} className="w-full min-w-[56rem] table-fixed border-collapse text-sm">
              {/* widths on <col> so ch is measured in the rows' font, not the smaller header's */}
              <colgroup>
                <col className="w-[3ch]" /><col className="w-[10ch]" /><col className="w-[19ch]" /><col className="w-[7ch]" />
                <col className="w-[6ch]" /><col className="w-[23%]" /><col /><col className="w-[22ch]" />
              </colgroup>
              <thead className="sticky top-0 z-[1] bg-paper text-left text-xs font-medium text-ink-2">
                <tr className="h-6 border-b border-ink">
                  <th scope="col"><span className="sr-only">cursor</span></th>
                  <th scope="col" className="px-2">id</th>
                  <th scope="col" className="px-2">label</th>
                  <th scope="col" className="px-2 text-right">conf</th>
                  <th scope="col" className="px-2 text-right">src</th>
                  <th scope="col" className="px-2">question</th>
                  <th scope="col" className="px-2">answer</th>
                  <th scope="col" className="px-2">approval</th>
                </tr>
              </thead>
              <tbody
                ref={body}
                onClick={(e) => { const i = rowAt(e); if (i !== null) { setCursor(i); openRow(i); } }}
                onKeyDown={(e) => { const i = rowAt(e); if (e.key === "Enter" && i !== null) { e.preventDefault(); openRow(i); } }}
              >
                {visible.map((r, i) => (
                  <Row key={r.item.id} row={r} i={i} cursor={i === cur} selected={r.item.id === itemId} section={sections[i]} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
        {open?.answer && (
          <EvidenceDrawer
            answerId={open.answer.id}
            code={open.item.code ?? String(open.item.position)}
            onClose={() => { go({ view: "run", run: runId }); body.current?.querySelector<HTMLElement>(`tr[data-i="${cur}"]`)?.focus(); }}
            onChanged={() => { api.runAnswers(runId).then(setData, (e) => setActionError(goneOn404(e, onGone))); }}
            runId={runId}
          />
        )}
      </div>
    </Shell>
  );
}
