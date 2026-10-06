import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Shell, goneOn404, resetAndReload, type ViewProps } from "../components/Shell";
import { Button, ErrorLine } from "../components/ui";
import { api, messageOf, type DocumentOut, type DocumentPatch, type Mapping, type QuestionnaireOut } from "../lib/api";
import { useKeys } from "../lib/keys";
import { go } from "../lib/route";
import { NOTICE_URL } from "./Home";

/** Tarun's approved wording (2026-10-06): the documents input. */
export const UPLOAD_NOTICE =
  "Names and secrets are replaced before anything reaches a model. Known gaps: a single first name, names in lower case, names written 'Last, First', and names in all capitals with accents may not be caught. Remove anything sensitive you can't share.";
/** Questionnaires are not redacted (only their file name is). */
export const QUESTIONNAIRE_NOTICE =
  "Questionnaires are stored and sent to the model as written, without redaction. Don't upload one that contains personal data.";
const KINDS = ["policy", "report", "record", "contract", "plan", "questionnaire", "statement", "other"] as const;
const SCOPES = ["internal-systems", "customer-product", "production", "employees", "vendors-and-contractors"] as const;
/** design.md: Enter submits a form from any of its fields, a focused select included (browsers skip selects). */
function enterSubmits(e: KeyboardEvent<HTMLFormElement>) {
  if (e.key === "Enter" && e.target instanceof HTMLSelectElement) {
    e.preventDefault();
    e.currentTarget.requestSubmit();
  }
}
/** A..AZ: the questionnaire reader's last column (52). */
const COLUMNS = Array.from({ length: 52 }, (_, i) => (i < 26 ? "" : "A") + String.fromCharCode(65 + (i % 26)));
const INVALID = "aria-[invalid=true]:border-2 aria-[invalid=true]:border-ink";
const FIELD = `h-7 border border-rule-strong bg-paper px-2 text-sm hover:border-neutral-500 ${INVALID}`;
const FILE =
  `max-w-full text-sm ${INVALID} file:mr-2 file:h-7 file:cursor-pointer file:border file:border-ink file:bg-paper file:px-2 file:font-mono file:text-sm file:font-medium file:text-ink hover:file:bg-sunken`;

function DocumentRow({ d, onSaved }: { d: DocumentOut; onSaved: (n: number, d: DocumentOut) => void }) {
  const [editing, setEditing] = useState(false);
  const [patch, setPatch] = useState<DocumentPatch>({});
  const [error, setError] = useState<string | null>(null);
  const edit = useRef<HTMLButtonElement>(null);
  const errId = useId();
  const toggle = () => {
    setEditing(!editing);
    setPatch({}); // closing without saving discards the change
    setError(null);
  };
  const save = async () => {
    setError(null);
    try {
      const { redecided, ...out } = await api.updateDocument(d.id, patch);
      setEditing(false);
      setPatch({});
      edit.current?.focus();
      onSaved(redecided, out);
    } catch (e) {
      setError(messageOf(e));
    }
  };
  return (
    <>
      <tr className="h-7 border-b border-rule" aria-label={d.filename}>
        <td className="truncate px-2">{d.filename}</td>
        <td className="px-2">{d.kind}</td>
        <td className="px-2">{d.status}</td>
        <td className="px-2 text-ink-3">{d.effective_date ?? "—"}</td>
        <td className="truncate px-2 text-ink-3">{d.scope?.replace(/-/g, " ") ?? "—"}</td>
        <td className="px-2">{d.evidence_allowed ? "evidence" : "not evidence"}</td>
        <td className="truncate px-2 text-ink-3">{d.source}{d.metadata_source === "user" ? " · edited" : ""}</td>
        <td className="px-2 text-right tabular-nums">{d.line_count}</td>
        <td className="px-2">
          <button ref={edit} type="button" aria-label={`Edit ${d.filename}`} aria-expanded={editing} className="text-xs underline" onClick={toggle}>edit</button>
        </td>
      </tr>
      {editing && (
        <tr className="border-b border-rule bg-sunken">
          <td colSpan={9} className="p-0">
            {/* sticky and viewport-wide, so at 320px the form wraps in view instead of scrolling with the table */}
            <div className="sticky left-0 max-w-[calc(100vw-2rem)] p-2">
            <form aria-label={`metadata of ${d.filename}`} aria-describedby={errId} onKeyDown={enterSubmits} onSubmit={(e) => { e.preventDefault(); void save(); }} className="flex flex-wrap items-end gap-3 text-xs">
              <label className="flex flex-col">kind
                <select aria-label="kind" defaultValue={d.kind} onChange={(e) => setPatch({ ...patch, kind: e.target.value as DocumentPatch["kind"] })} className={FIELD}>
                  {KINDS.map((k) => <option key={k}>{k}</option>)}
                </select>
              </label>
              <label className="flex flex-col">status
                <select aria-label="status" defaultValue={d.status} onChange={(e) => setPatch({ ...patch, status: e.target.value as "final" | "draft" })} className={FIELD}>
                  <option>final</option><option>draft</option>
                </select>
              </label>
              <label className="flex flex-col">date
                <input aria-label="date" type="date" defaultValue={d.effective_date ?? ""} onChange={(e) => setPatch({ ...patch, effective_date: e.target.value || null })} className={FIELD} />
              </label>
              <label className="flex flex-col">scope
                <select aria-label="scope" defaultValue={d.scope ?? ""} onChange={(e) => setPatch({ ...patch, scope: (e.target.value || null) as DocumentPatch["scope"] })} className={FIELD}>
                  <option value="">none declared</option>
                  {SCOPES.map((s) => <option key={s} value={s}>{s.replace(/-/g, " ")}</option>)}
                </select>
              </label>
              <label className="flex h-7 items-center gap-1">
                <input type="checkbox" defaultChecked={d.evidence_allowed} onChange={(e) => setPatch({ ...patch, evidence_allowed: e.target.checked })} /> counts as evidence
              </label>
              <Button k="enter" shortcut="Enter" label="Save" primary submit disabled={Object.keys(patch).length === 0} />
            </form>
            <div id={errId} className="mt-1"><ErrorLine message={error} /></div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function Mapper({ q, onConfirmed }: { q: QuestionnaireOut; onConfirmed: (q: QuestionnaireOut) => void }) {
  const start = q.mapping ?? q.detected;
  const [m, setM] = useState<Mapping>(start ?? { sheet: q.sheets[0] ?? null, header_row: 1, id_col: null, question_col: "A", answer_col: "B", comments_col: null, topic_col: null });
  const [row, setRow] = useState(String(m.header_row)); // the raw text, so clearing the field does not snap to 1
  const [error, setError] = useState<string | null>(null);
  const errId = useId();
  const col = (key: keyof Mapping, label: string, optional: boolean) => (
    <label className="flex flex-col text-xs">{label}
      <select aria-label={label} value={(m[key] as string | null) ?? ""} onChange={(e) => setM({ ...m, [key]: e.target.value || null })} aria-invalid={error ? true : undefined} className={FIELD}>
        {optional && <option value="">none</option>}
        {COLUMNS.map((c) => <option key={c}>{c}</option>)}
      </select>
    </label>
  );
  const confirm = async () => {
    setError(null);
    try {
      onConfirmed(await api.confirmMapping(q.id, { ...m, header_row: Number(row) }));
    } catch (e) {
      setError(messageOf(e));
    }
  };
  return (
    <div className="space-y-2">
      <p className="text-sm text-ink-2">
        {q.detected ? "Check the columns VART found, then confirm." : "No question column was found; pick the columns below."}
      </p>
      <form aria-label="column mapping" aria-describedby={errId} onKeyDown={enterSubmits} onSubmit={(e) => { e.preventDefault(); void confirm(); }} className="flex flex-wrap items-end gap-3">
        {q.sheets.length > 0 && (
          <label className="flex flex-col text-xs">sheet
            <select aria-label="sheet" value={m.sheet ?? ""} onChange={(e) => setM({ ...m, sheet: e.target.value })} className={FIELD}>
              {q.sheets.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
        )}
        <label className="flex flex-col text-xs">header row
          <input aria-label="header row" type="number" required min={1} max={1000} value={row} onChange={(e) => setRow(e.target.value)} aria-invalid={error ? true : undefined} className={`${FIELD} w-20`} />
        </label>
        {col("question_col", "question column", false)}
        {col("answer_col", "answer column", false)}
        {col("id_col", "id column", true)}
        {col("comments_col", "comments column", true)}
        {col("topic_col", "topic column", true)}
        <Button k="enter" shortcut="Enter" label="Confirm mapping" primary submit />
      </form>
      <div id={errId}><ErrorLine message={error} /></div>
      <div className="overflow-x-auto">
        <table aria-label="preview of the detected mapping" className="w-full min-w-[40rem] table-fixed text-sm">
          <thead>
            <tr className="h-6 border-b border-ink text-left text-xs font-medium text-ink-2">
              <th scope="col" className="w-14 px-2">row</th><th scope="col" className="w-24 px-2">id</th><th scope="col" className="px-2">question</th><th scope="col" className="w-40 px-2">topic</th>
            </tr>
          </thead>
          <tbody>
            {q.preview.map((p) => (
              <tr key={p.row} className="h-7 border-b border-rule">
                <td className="px-2 tabular-nums text-ink-3">{p.row}</td>
                <td className="truncate px-2">{p.id ?? "—"}</td>
                <td className="truncate px-2" title={p.question}>{p.question}</td>
                <td className="truncate px-2 text-ink-3">{p.topic ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function WorkspaceView({ workspace, onGone }: ViewProps) {
  const [docs, setDocs] = useState<DocumentOut[]>([]);
  const [qs, setQs] = useState<QuestionnaireOut[]>([]);
  const [current, setCurrent] = useState<QuestionnaireOut | null>(null);
  const [docError, setDocError] = useState<string | null>(null);
  const [qError, setQError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [uploading, setUploading] = useState("");
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(false);
  const ids = { docNotice: useId(), qNotice: useId(), docErr: useId(), qErr: useId(), listErr: useId() };
  const list = useRef<HTMLTableElement>(null);
  const qInput = useRef<HTMLInputElement>(null);
  const confirmed = useRef(false); // the mapper unmounts on confirm; focus moves to Start run

  useEffect(() => {
    api.documents().then(setDocs, (e) => setDocError(goneOn404(e, onGone)));
    api.questionnaires().then((list) => { setQs(list); setCurrent(list[0] ?? null); }, (e) => setQError(goneOn404(e, onGone)));
  }, [onGone]);

  /** Newest first; a sample loaded again comes back with the same id (idempotent), so it replaces its row. */
  const show = (q: QuestionnaireOut) => {
    setQs((all) => [q, ...all.filter((x) => x.id !== q.id)]);
    setCurrent(q);
  };
  const uploadDocs = async (input: HTMLInputElement) => {
    setDocError(null);
    const refused: string[] = [];
    for (const file of Array.from(input.files ?? [])) {
      setUploading(`uploading ${file.name}…`);
      try {
        const d = await api.uploadDocument(file);
        setDocs((all) => [...all, d]);
      } catch (e) {
        refused.push(`${messageOf(e)} (${file.name})`);
        setDocError(refused.join(" "));
      }
    }
    setUploading("");
    input.value = ""; // the same file can be chosen again
  };
  const uploadQ = async (input: HTMLInputElement) => {
    const file = input.files?.[0];
    if (!file) return;
    setQError(null);
    try {
      show(await api.uploadQuestionnaire(file));
    } catch (e) {
      setQError(messageOf(e));
    }
    input.value = "";
  };
  const sampleDocs = async () => {
    if (busy) return;
    setBusy(true);
    setDocError(null);
    try { await api.loadSampleDocuments(); setDocs(await api.documents()); } catch (e) { setDocError(messageOf(e)); }
    setBusy(false);
  };
  const sampleQ = async (name: "vsq-a" | "mvsp-b") => {
    setQError(null);
    try { show(await api.loadSampleQuestionnaire(name)); } catch (e) { setQError(messageOf(e)); }
  };
  const remove = async (q: QuestionnaireOut) => {
    if (!window.confirm(`Delete ${q.filename} and its items?`)) return;
    setListError(null);
    try {
      await api.deleteQuestionnaire(q.id);
    } catch (e) {
      setListError(messageOf(e)); // 409: a run used it
      return;
    }
    const rest = qs.filter((x) => x.id !== q.id);
    setQs(rest);
    if (current?.id === q.id) setCurrent(rest[0] ?? null);
    // the pressed button is gone; focus the list's first remaining control, or the upload input
    requestAnimationFrame(() => (list.current?.querySelector("button") ?? qInput.current)?.focus());
  };
  const start = async () => {
    if (!current || current.item_count === 0 || starting) return;
    setStarting(true);
    setRunError(null);
    try {
      const run = await api.createRun(current.id);
      go({ view: "run", run: run.id });
    } catch (e) {
      setRunError(messageOf(e));
      setStarting(false);
    }
  };
  const reset = () => {
    if (window.confirm("Delete this workspace and everything in it now?")) void resetAndReload();
  };
  useKeys({ r: () => void start(), l: () => void sampleDocs(), q: () => void sampleQ("vsq-a"), w: () => void sampleQ("mvsp-b"), R: reset });

  return (
    <Shell mode="WORKSPACE" cursor={note} hints={[["r", "start run"], ["?", "all keys"]]} expiresAt={workspace.expires_at} runId={current?.latest_run_id ?? undefined}>
      <div className="space-y-6 p-4">
        <h1 className="sr-only">workspace</h1>
        <section aria-labelledby="docs-h" className="space-y-2">
          <h2 id="docs-h" className="border-b border-ink pb-1 text-xs font-medium text-ink-2">documents ({docs.length})</h2>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex min-w-0 flex-col text-xs">upload documents
              <input type="file" multiple accept=".pdf,.docx,.xlsx,.csv,.md,.txt" aria-describedby={docError ? `${ids.docNotice} ${ids.docErr}` : ids.docNotice} aria-invalid={docError ? true : undefined} onChange={(e) => void uploadDocs(e.currentTarget)} className={FILE} />
            </label>
            <Button k="l" label="Load sample documents" onClick={sampleDocs} busy={busy} busyLabel="Loading…" />
          </div>
          <p id={ids.docNotice} className="max-w-[72ch] text-xs text-ink-2">{UPLOAD_NOTICE}</p>
          {uploading && <p role="status" className="text-xs text-ink-3">{uploading}</p>}
          <div id={ids.docErr}><ErrorLine message={docError} /></div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[56rem] table-fixed text-sm">
              <thead>
                <tr className="h-6 border-b border-ink text-left text-xs font-medium text-ink-2">
                  <th scope="col" className="px-2">file</th><th scope="col" className="w-28 px-2">kind</th><th scope="col" className="w-20 px-2">status</th><th scope="col" className="w-28 px-2">date</th><th scope="col" className="w-40 px-2">scope</th><th scope="col" className="w-28 px-2">evidence</th><th scope="col" className="w-32 px-2">source</th><th scope="col" className="w-16 px-2 text-right">lines</th><th scope="col" className="w-14 px-2"><span className="sr-only">edit</span></th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <DocumentRow key={d.id} d={d} onSaved={(n, out) => { setDocs((all) => all.map((x) => (x.id === out.id ? out : x))); setNote(`${n} answer${n === 1 ? "" : "s"} decided again`); }} />
                ))}
              </tbody>
            </table>
          </div>
          {docs.length === 0 && <p className="text-sm text-ink-3">No documents yet. Upload some, or load the sample company's.</p>}
          {docs.some((d) => d.source === "sample") && (
            <p className="text-xs text-ink-3">Sample policies adapted from JupiterOne templates, CC BY-SA 4.0 (<a className="underline" href={NOTICE_URL}>NOTICE</a>).</p>
          )}
        </section>
        <section aria-labelledby="q-h" className="space-y-2">
          <h2 id="q-h" className="border-b border-ink pb-1 text-xs font-medium text-ink-2">questionnaire</h2>
          <div className="flex flex-wrap items-end gap-3">
            <label className="flex min-w-0 flex-col text-xs">upload a questionnaire
              <input ref={qInput} type="file" accept=".xlsx,.csv" aria-describedby={qError ? `${ids.qNotice} ${ids.qErr}` : ids.qNotice} aria-invalid={qError ? true : undefined} onChange={(e) => void uploadQ(e.currentTarget)} className={FILE} />
            </label>
            <Button k="q" label="Sample questionnaire A (xlsx)" onClick={() => void sampleQ("vsq-a")} />
            <Button k="w" label="Sample questionnaire B (csv)" onClick={() => void sampleQ("mvsp-b")} />
          </div>
          <p id={ids.qNotice} className="max-w-[72ch] text-xs text-ink-2">{QUESTIONNAIRE_NOTICE}</p>
          <div id={ids.qErr}><ErrorLine message={qError} /></div>
          {current && (
            <div className="space-y-2">
              <p className="text-sm [overflow-wrap:anywhere]">{current.filename} · <span>{current.item_count} questions</span></p>
              {current.item_count === 0 ? (
                <Mapper key={current.id} q={current} onConfirmed={(q) => { confirmed.current = true; show(q); }} />
              ) : (
                <div ref={(el) => { if (el && confirmed.current) { confirmed.current = false; el.querySelector("button")?.focus(); } }} className="space-y-2">
                  <Button k="r" label="Start run" primary busy={starting} busyLabel="Starting…" onClick={() => void start()} />
                  <ErrorLine message={runError} />
                </div>
              )}
            </div>
          )}
          {qs.length > 0 && (
            <div className="space-y-1">
              <div className="overflow-x-auto">
                <table ref={list} aria-label={`questionnaires (${qs.length} of 5)`} aria-describedby={listError ? ids.listErr : undefined} className="w-full table-fixed text-sm">
                  <thead>
                    <tr className="h-6 border-b border-ink text-left text-xs font-medium text-ink-2">
                      <th scope="col" className="truncate px-2">questionnaires ({qs.length} of 5)</th><th scope="col" className="w-20 px-2 text-right">questions</th><th scope="col" className="w-28 px-2"><span className="sr-only">actions</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {qs.map((q) => {
                      const shown = q.id === current?.id;
                      return (
                        <tr key={q.id} aria-label={q.filename} aria-current={shown ? "true" : undefined} className={`h-7 border-b border-rule ${shown ? "bg-sunken font-medium" : ""}`}>
                          <td className="truncate px-2">{q.filename}</td>
                          <td className="px-2 text-right tabular-nums">{q.item_count}</td>
                          <td className="space-x-3 whitespace-nowrap px-2 text-xs">
                            {/* one button that stays mounted, so focus survives opening its row */}
                            <button type="button" aria-label={`Open ${q.filename}`} aria-disabled={shown ? "true" : undefined} className={shown ? "text-ink-3" : "underline"} onClick={() => { if (shown) return; setListError(null); setRunError(null); setCurrent(q); }}>{shown ? "shown" : "open"}</button>
                            <button type="button" aria-label={`Delete ${q.filename}`} className="underline" onClick={() => void remove(q)}>delete</button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <div id={ids.listErr}><ErrorLine message={listError} /></div>
            </div>
          )}
        </section>
        <section aria-label="reset" className="flex flex-wrap items-center gap-3 border-t border-rule-strong pt-3">
          <Button k="R" shortcut="Shift+R" label="Reset workspace" onClick={reset} />
          <span className="min-w-0 text-xs text-ink-3">Deletes every document, questionnaire and run now.</span>
        </section>
      </div>
    </Shell>
  );
}
