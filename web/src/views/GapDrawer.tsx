import { useEffect, useRef, useState } from "react";
import { ErrorLine, GapChip, LabelChip } from "../components/ui";
import { api, messageOf, type AnswerDetail, type CitationOut, type GapRow, type QuestionOut } from "../lib/api";
import { GAP_REVIEW } from "../lib/labels";
import { DrawerFrame, DroppedList, Sources } from "./EvidenceDrawer";
import { QuestionCard } from "./Questions";

const TO_REVIEW = new Set(["partly_covered", "not_met", "documents_disagree", "gap"]); // CSF spec 2: possible gaps
const STATEMENT = "Your answer is saved as a dated statement and can be cited in your questionnaires."; // adversary-1 M9

type Props = { row: GapRow; runId: string | null; controlsUrl: string; onClose: () => void; onChanged: () => void };

/** Keyed by outcome and answer, so a quick switch never shows another outcome's evidence. */
export default function GapDrawer(p: Props) {
  return <Inspector key={`${p.row.csf_id}:${p.row.answer_id ?? ""}`} {...p} />;
}

const same = (x: CitationOut, c: CitationOut) =>
  x.document_id === c.document_id && x.line === c.line && x.quote === c.quote && x.stance === c.stance;

function labelOf(row: GapRow) {
  if (row.not_applicable) return <LabelChip label="na" />; // adversary-1 I1: wins over the tier's label
  if (row.label) return <GapChip label={row.label} />;
  if (row.tier === "not_checked") return "not checked in this version"; // CSF spec 5.5
  return row.answer_id ? "—" : "not run yet"; // an answer with no label failed; its sentence is the explanation (M4)
}

function Inspector({ row, runId, controlsUrl, onClose, onChanged }: Props) {
  const root = useRef<HTMLElement>(null);
  const [a, setA] = useState<AnswerDetail | null>(null);
  const [question, setQuestion] = useState<QuestionOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0); // a 409 on the card reloads the inspector (Task 6 review M2)
  const { answer_id: answerId, item_id: itemId, tier } = row;
  const titleId = `gap-${row.csf_id}`;

  useEffect(() => {
    let alive = true; // a late answer for a closed or switched inspector never lands
    const fail = (e: unknown) => { if (alive) setError(messageOf(e)); };
    if (answerId) api.answer(answerId).then((d) => { if (alive) setA(d); }, fail);
    if (tier === "ask" && runId && itemId) {
      api.questions(runId).then((qs) => { if (alive) setQuestion(qs.find((q) => q.item_ids.includes(itemId)) ?? null); }, fail);
    }
    return () => { alive = false; };
  }, [answerId, itemId, tier, runId, tick]);

  const parts = a?.parts ?? [];
  const ref = (c: CitationOut) => (a?.citations.findIndex((x) => same(x, c)) ?? -1) + 1; // footnote into sources
  return (
    <DrawerFrame root={root} title={`${row.csf_id} · gap check`} titleId={titleId} onClose={onClose}>
      <ErrorLine message={error} />
      <h2 id={titleId} className="text-base font-medium [overflow-wrap:anywhere]">{row.outcome}</h2>
      <p className="text-xs text-ink-3">
        NIST's text, verbatim ·{" "}
        <a href={row.source_url} target="_blank" rel="noreferrer" className="text-ink underline underline-offset-2">NIST CSF 2.0 reference tool</a>
      </p>
      <dl className="grid grid-cols-[11ch_minmax(0,1fr)] gap-y-1">
        <dt className="text-ink-3">label</dt>
        <dd>{labelOf(row)}</dd>
        <dt className="text-ink-3">function</dt><dd>{row.function}</dd>
        <dt className="text-ink-3">category</dt><dd>{row.category}</dd>
        <dt className="text-ink-3">800-53</dt>
        <dd className="flex flex-wrap gap-x-2">
          {row.related_controls.length === 0 ? "—" : row.related_controls.map((c) => (
            <a key={c} href={controlsUrl} target="_blank" rel="noreferrer" className="underline underline-offset-2">{c}</a>
          ))}
        </dd>
      </dl>
      {row.label && !row.not_applicable && TO_REVIEW.has(row.label) && <p className="font-medium">{GAP_REVIEW}</p>}
      {row.explanation && <div className="border border-rule-strong p-2 text-ink-2 [overflow-wrap:anywhere]">{row.explanation}</div>}
      {parts.length > 0 && (
        <section>
          <h3 className="border-b border-ink text-xs font-medium text-ink-2">parts ({parts.length})</h3>
          <ol className="divide-y divide-rule">
            {parts.map((p) => (
              <li key={p.n} className="flex flex-wrap items-baseline gap-2 py-1">
                <span className="font-bold">part {p.n}</span>
                <GapChip label={p.label} />
                <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{p.question}</span>
                {p.citations.map((c, i) => ref(c) > 0 && <sup key={i} className="font-bold">[{ref(c)}]</sup>)}
                {p.from_statement && <span className="text-xs text-ink-3">from your answer</span>}
              </li>
            ))}
          </ol>
        </section>
      )}
      {a && a.citations.length > 0 && <Sources a={a} />}
      {a && a.dropped.length > 0 && <DroppedList dropped={a.dropped} />}
      {tier === "ask" && !row.not_applicable && (question ? (
        <>
          <ul>
            <QuestionCard q={question} focus={false} onUpdated={(q) => { setQuestion(q); onChanged(); }} onStale={() => { onChanged(); setTick((t) => t + 1); }} />
          </ul>
          <p className="text-xs text-ink-3">{STATEMENT}</p>
        </>
      ) : (
        <p className="text-ink-2">{runId ? "This question opens when the gap check is done." : "Run the gap check first, then answer this here."}</p>
      ))}
    </DrawerFrame>
  );
}
