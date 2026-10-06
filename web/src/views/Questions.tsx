import { useEffect, useRef, useState } from "react";
import { Shell, goneOn404, type ViewProps } from "../components/Shell";
import { Button, ErrorLine, GapChip, LabelChip } from "../components/ui";
import { ApiError, api, messageOf, type GapLabel, type QuestionOut, type SuggestionOut } from "../lib/api";
import { useRoute } from "../lib/route";

const MAX = 4000;
/** A part's fill in the gap check's words (CSF spec 5.3; adversary-2 M4). */
const PART_LABEL: Record<string, GapLabel> = { Yes: "covered", Partial: "partly_covered", No: "not_met" };

export function QuestionCard({ q, focus, onUpdated, onStale }: { q: QuestionOut; focus: boolean; onUpdated: (q: QuestionOut) => void; onStale: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fills, setFills] = useState<SuggestionOut[]>(q.suggestions);
  const [filledNothing, setFilledNothing] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const code = q.codes[0] ?? "item";
  useEffect(() => { if (focus) box.current?.focus(); }, [focus]);
  const fail = (e: unknown, reload = false) => {
    if (e instanceof ApiError && e.status === 429) setError(`Too many answers at once.${e.retryAfter ? ` Try again in ${e.retryAfter} s.` : ""}`);
    else setError(messageOf(e));
    if (reload && e instanceof ApiError && e.status === 409) onStale(); // answered or skipped elsewhere: show the queue as it is now
  };
  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await api.answerQuestion(q.id, text);
      setText("");
      setFills(out.suggestions);
      setFilledNothing(out.question.status === "answered" && out.suggestions.length === 0);
      onUpdated(out.question);
    } catch (e) {
      fail(e, true);
    }
    setBusy(false);
  };
  const skip = async () => {
    setError(null);
    try { onUpdated(await api.skipQuestion(q.id)); } catch (e) { fail(e, true); }
  };
  const accept = async (s: SuggestionOut) => {
    setError(null);
    try {
      await api.acceptSuggestion(s.id);
      setFills((all) => all.map((x) => (x.id === s.id ? { ...x, status: "accepted" } : x)));
    } catch (e) {
      fail(e);
    }
  };
  const open = q.status === "open" || q.status === "follow_up";
  return (
    <li className="space-y-2 border-b border-rule py-3">
      <div className="flex flex-wrap items-baseline gap-2 text-sm">
        <span className="font-bold">{code}</span>
        <span className="text-xs uppercase text-ink-3">{q.reason}{q.high_weight ? " · high weight" : ""}</span>
        {q.status === "answered" && <LabelChip label="user_confirmed" />}
        {q.status === "skipped" && <span className="text-xs text-ink-3">skipped</span>}
      </div>
      <p className="text-base [overflow-wrap:anywhere]">{q.follow_up ?? q.text}</p>
      {/* a skip is final (spec 6.9: never asked twice); say how an item that is still open gets closed */}
      {q.status === "skipped" && <p className="text-xs text-ink-3">Not asked again. If this item is still open, mark it not applicable from the run grid.</p>}
      {open && (
        <div className="space-y-1">
          <textarea
            ref={box}
            aria-label={`your answer to ${code}`}
            maxLength={MAX}
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim() && !busy) void send(); }}
            className="w-full border border-rule-strong bg-paper p-2 text-sm hover:border-neutral-500"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Button k="ctrl+enter" shortcut="Control+Enter" label="Send" primary disabled={!text.trim()} busy={busy} busyLabel="Sending…" onClick={() => void send()} />
            {/* no page-level `s`: with several cards it would be ambiguous, so the hint is not shown */}
            <button type="button" onClick={() => void skip()} className="inline-flex h-7 items-center gap-2 border border-ink bg-paper px-2 text-sm font-medium hover:bg-sunken">Skip</button>
            <span className="ml-auto text-xs text-ink-3 tabular-nums">{text.length} / {MAX}</span>
          </div>
        </div>
      )}
      <ErrorLine message={error} />
      {filledNothing && <p className="text-xs text-ink-2">No other items were filled by this answer.</p>}
      {fills.length > 0 && (
        <ul className="space-y-1 border-l border-ink pl-3 text-sm">
          {fills.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-2">
              <span className="font-bold">{s.code}</span>
              {s.part ? <span className="text-xs text-ink-3">part {s.part}</span> : null /* preflight I3: question is that part's wording */}
              {s.part ? <GapChip label={PART_LABEL[s.value ?? ""] ?? "partly_covered"} /> : <LabelChip label={s.label} />}
              <span className="min-w-0 flex-1 truncate text-ink-2">{s.question}</span>
              {s.status === "open" ? (
                <button type="button" aria-label={`Accept fill for ${s.code}${s.part ? ` part ${s.part}` : ""}`} onClick={() => void accept(s)} className="h-7 border border-ink px-2 text-sm hover:bg-sunken">accept</button>
              ) : (
                <span className="text-xs text-ink-3">{s.status}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

/** Keyed by run, so a new run starts from an empty list and an old run's late response has nowhere to land. */
export default function Questions(props: ViewProps & { runId: string }) {
  return <QuestionsFor key={props.runId} {...props} />;
}

function QuestionsFor({ workspace, onGone, runId }: ViewProps & { runId: string }) {
  const route = useRoute();
  const [list, setList] = useState<QuestionOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const local = useRef(new Map<string, QuestionOut>()); // cards updated here: a later reload must not overwrite them
  useEffect(() => {
    let alive = true;
    api.questions(runId).then(
      (l) => { if (alive) { setError(null); setList(l.map((q) => local.current.get(q.id) ?? q)); } },
      (e) => { if (alive) setError(goneOn404(e, onGone)); },
    );
    return () => { alive = false; };
  }, [runId, onGone, tick]);
  const isOpen = (q: QuestionOut) => q.status === "open" || q.status === "follow_up";
  // ?item= focuses that item's card, never another one: typing into a different item's card would answer it
  const forItem = route.item ? list?.find((q) => q.item_ids.includes(route.item as string)) : undefined;
  const noCard = Boolean(route.item && list && !forItem);
  const focusId = route.item ? forItem?.id : list?.find(isOpen)?.id;
  const open = list?.filter(isOpen).length ?? 0;
  return (
    <Shell mode="ASK" cursor={`${open} open`} hints={[["ctrl+enter", "send"], ["?", "all keys"]]} expiresAt={workspace.expires_at} runId={runId}>
      <div className="mx-auto max-w-3xl p-4">
        <h1 className="border-b border-ink text-xs font-medium text-ink-2">questions for you ({open})</h1>
        <ErrorLine message={error} />
        {noCard && <p role="status" className="py-3 text-sm text-ink-2">No question for this item; mark it not applicable or re-run.</p>}
        {list && list.length === 0 && <p className="py-3 text-sm text-ink-2">Nothing to ask: every item has an answer from the documents, or the run is still filling.</p>}
        <ul>
          {list?.map((q) => (
            <QuestionCard key={q.id} q={q} focus={q.id === focusId} onStale={() => setTick((t) => t + 1)} onUpdated={(nq) => { local.current.set(nq.id, nq); setList((all) => all?.map((x) => (x.id === nq.id ? nq : x)) ?? null); }} />
          ))}
        </ul>
      </div>
    </Shell>
  );
}
