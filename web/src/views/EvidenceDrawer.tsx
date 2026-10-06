import { useEffect, useRef, useState, useSyncExternalStore, type KeyboardEvent as ReactKeyboardEvent } from "react";
import { Button, ErrorLine, LabelChip } from "../components/ui";
import { api, type AnswerDetail, type CitationOut } from "../lib/api";
import { useKeys } from "../lib/keys";
import { approvalText, confidenceText } from "../lib/labels";
import { go } from "../lib/route";

const NARROW = "(max-width: 899px)";

export function useNarrow(): boolean {
  return useSyncExternalStore(
    (cb) => { const m = window.matchMedia(NARROW); m.addEventListener("change", cb); return () => m.removeEventListener("change", cb); },
    () => window.matchMedia(NARROW).matches,
  );
}

function quoted(text: string, quote: string) {
  const at = text.indexOf(quote);
  if (at < 0) return <>{text}</>;
  return <>{text.slice(0, at)}<mark className="bg-mark text-ink underline underline-offset-2">{quote}</mark>{text.slice(at + quote.length)}</>;
}

export function Citation({ c, n }: { c: CitationOut; n: number }) {
  const facts = [c.kind, c.status, c.date ?? "undated", c.scope?.replace(/-/g, " ") ?? "no scope declared", c.stance].join(" · ");
  return (
    <figure aria-label={`[${n}] ${c.filename}`} className="border border-rule-strong">
      <figcaption className="bg-chrome-2 px-2 py-1 text-xs text-on-chrome-2">
        <span className="font-bold text-on-chrome">[{n}] {c.filename}</span> <span>{facts}</span>
      </figcaption>
      {!c.found_in_source && <p className="px-2 py-1 text-xs font-medium">Quote not found in the stored source.</p>}
      <ol className="text-xs leading-[1.7]">
        {c.context.map((l) => (
          <li key={l.n} className={`grid grid-cols-[2ch_5ch_minmax(0,1fr)] ${l.cited ? "bg-sunken text-ink" : "text-ink-3"}`}>
            <span aria-hidden="true" className={l.cited ? "font-bold" : ""}>{l.cited ? ">" : ""}</span>
            <span className={`select-none border-r border-rule-strong pr-1 text-right tabular-nums ${l.cited ? "font-bold" : ""}`}>{l.n}</span>
            <span className="min-w-0 pl-2 [overflow-wrap:anywhere]">{l.cited ? quoted(l.text, c.quote) : l.text}</span>
          </li>
        ))}
      </ol>
    </figure>
  );
}

type Props = { answerId: string; code: string; runId: string; onClose: () => void; onChanged: () => void };

export default function EvidenceDrawer({ answerId, code, runId, onClose, onChanged }: Props) {
  const narrow = useNarrow();
  const [a, setA] = useState<AnswerDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const root = useRef<HTMLElement>(null);
  const titleId = `q-${answerId}`;

  useEffect(() => { api.answer(answerId).then(setA, (e) => setError((e as Error).message)); }, [answerId]);
  useEffect(() => { if (narrow) root.current?.querySelector<HTMLElement>("button")?.focus(); }, [narrow]); // the close control exists before the answer loads

  const approve = async () => { try { await api.approve(answerId); setA(await api.answer(answerId)); onChanged(); } catch (e) { setError((e as Error).message); } };
  const markNa = async () => { try { await api.notApplicable(answerId, reason); setAsking(false); setA(await api.answer(answerId)); onChanged(); } catch (e) { setError((e as Error).message); } };
  const canApprove = a !== null && a.label !== "conflict" && a.label !== "unknown" && !a.approved;
  useKeys({
    Escape: onClose,
    a: () => { if (canApprove) void approve(); },
    i: () => go({ view: "questions", run: runId, item: a?.item_id }),
    n: () => setAsking(true),
  });

  const trap = (e: ReactKeyboardEvent) => {
    if (!narrow || e.key !== "Tab" || !root.current) return;
    const items = Array.from(root.current.querySelectorAll<HTMLElement>("button:not([disabled]), input, textarea, select, a[href]"));
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  const rule = a?.conflict ? (a.conflict.rule === "date" ? "date rule · newer record first" : "documents disagree") : a?.scope_note ? "scope difference" : "—";
  return (
    <aside
      ref={root}
      aria-labelledby={titleId}
      role={narrow ? "dialog" : undefined}
      aria-modal={narrow ? true : undefined}
      onKeyDown={trap}
      className={`${narrow ? "fixed inset-0 z-10" : "border-l border-ink"} flex min-h-0 flex-col overflow-auto bg-paper transition duration-200 ease-out`}
    >
      <div data-chrome className="flex h-8 items-center justify-between bg-chrome px-3 text-xs">
        <span className="font-bold text-on-chrome">{code} · evidence</span>
        <Button k="esc" shortcut="Escape" label="close" quiet onClick={onClose} />
      </div>
      <div className="space-y-4 p-3 text-sm">
        <ErrorLine message={error} />
        {a && (
          <>
            <h2 id={titleId} className="text-base font-medium">{a.item.question}</h2>
            <dl className="grid grid-cols-[11ch_minmax(0,1fr)] gap-y-1 text-sm">
              <dt className="text-ink-3">label</dt><dd><LabelChip label={a.label} /></dd>
              <dt className="text-ink-3">value</dt><dd>{a.value ?? "—"}</dd>
              <dt className="text-ink-3">confidence</dt><dd className="tabular-nums">{confidenceText(a)}</dd>
              <dt className="text-ink-3">approval</dt><dd className={a.approved ? "" : "text-ink-3"}>{approvalText(a.approved)}</dd>
              <dt className="text-ink-3">rule</dt><dd>{rule}</dd>
            </dl>
            <div className="border border-rule-strong p-2 text-ink-2 [overflow-wrap:anywhere]">{a.text || "No answer yet."}</div>
            {a.scope_note && <p className="text-ink-2">{a.scope_note}</p>}
            {a.statement_lines.length > 0 && (
              <section>
                <h3 className="border-b border-ink text-xs font-medium text-ink-2">your answer (dated statement)</h3>
                {a.statement_lines.map((l) => <p key={l.n} className="text-sm">{l.text}</p>)}
              </section>
            )}
            <section className="space-y-2">
              <h3 className="border-b border-ink text-xs font-medium text-ink-2">sources ({a.citations.length})</h3>
              {(a.conflict ? a.conflict.sides.flatMap((s) => s.citations) : a.citations.map((_, i) => i)).map((i) => (
                <Citation key={i} c={a.citations[i]} n={i + 1} />
              ))}
            </section>
            <section>
              <h3 className="border-b border-ink text-xs font-medium text-ink-2">dropped evidence ({a.dropped.length})</h3>
              <ul className="divide-y divide-rule">
                {a.dropped.map((d, i) => (
                  <li key={i} className="py-1 text-xs">
                    <span className="font-bold">{d.reason.replace(/-/g, " ").toUpperCase()}</span>{" "}
                    <span>{d.filename}{d.line ? `:${d.line}` : ""}</span>{" "}
                    <span className="text-ink-2">{d.sentence}</span>
                  </li>
                ))}
              </ul>
            </section>
            {asking && (
              <form onSubmit={(e) => { e.preventDefault(); if (reason.trim()) void markNa(); }} className="flex flex-wrap items-end gap-2">
                <label className="flex min-w-0 flex-1 flex-col text-xs">reason
                  <input autoFocus maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} className="h-7 border border-rule-strong bg-paper px-2 text-sm" />
                </label>
                <Button k="enter" shortcut="Enter" label="Mark not applicable" primary submit disabled={!reason.trim()} />
              </form>
            )}
            <div className="flex flex-wrap gap-2">
              <Button k="a" label="Approve" primary disabled={!canApprove} onClick={() => void approve()} />
              <Button k="i" label="Answer this question" onClick={() => go({ view: "questions", run: runId, item: a.item_id })} />
              <Button k="n" label="Mark not applicable" onClick={() => setAsking(true)} />
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
