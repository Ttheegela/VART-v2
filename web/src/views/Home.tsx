import { useState } from "react";
import { KeySheet } from "../components/Shell";
import StatusPanel from "../components/StatusPanel";
import { Button, ErrorLine, Kbd, LabelChip } from "../components/ui";
import { api, ensureWorkspace, messageOf, type Label, type Workspace } from "../lib/api";
import { useKeys } from "../lib/keys";
import { go } from "../lib/route";

export const NOTICE_URL = "https://github.com/Ttheegela/VART-v2/blob/main/data/NOTICE.md";

/** design/mockups/home.html: the label, when it is set, and the value it exports. */
const HOW: [Label, string, string][] = [
  ["verified", "Every surviving quote says the same thing, from a final document.", "Yes / No"],
  ["partial", "Mixed evidence, a negation in the quote, a scope difference, or draft documents only.", "Partial"],
  ["conflict", "Two documents disagree. A newer record is listed first, and you are asked which is current.", "—"],
  ["unknown", "No evidence survived the checks. The item goes to Questions for you.", "—"],
  ["user_confirmed", "You answered it; your answer is kept as a dated statement and cited.", "Yours"],
  ["na", "You marked it so, with a reason in the audit log.", "N/A"],
];

/** Load the sample company's documents and questionnaire A, start a run; resolves the run id. */
export async function startSample(): Promise<string> {
  await ensureWorkspace();
  await api.loadSampleDocuments();
  const q = await api.loadSampleQuestionnaire("vsq-a");
  const run = await api.createRun(q.id);
  return run.id;
}

export default function Home({ workspace, startError }: { workspace: Workspace | null; startError: string | null }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sheet, setSheet] = useState(false);
  const sample = async () => {
    setBusy(true);
    setError(null);
    try {
      go({ view: "run", run: await startSample() });
    } catch (e) {
      setError(messageOf(e));
      setBusy(false);
    }
  };
  const own = () => go({ view: "workspace" });
  // design.md: a disabled control's key does nothing.
  useKeys({
    s: () => { if (workspace && !busy) void sample(); },
    o: () => { if (workspace) own(); },
    "?": () => setSheet(true),
  });
  return (
    <div className="grid min-h-dvh grid-rows-[36px_1fr_28px] bg-paper text-ink">
      <header data-chrome className="flex h-9 items-center justify-between gap-4 bg-chrome px-4 text-xs text-on-chrome-2">
        <span className="font-bold tracking-[0.12em] text-on-chrome">VART</span>
        <span className="hidden whitespace-nowrap min-[480px]:inline">synthetic demo data</span>
      </header>
      <main className="mx-auto w-full min-w-0 max-w-3xl space-y-10 px-4 py-10">
        <section className="space-y-3">
          <h1 className="text-base font-medium [overflow-wrap:anywhere]">Questionnaires answered from your own documents</h1>
          <p className="max-w-[72ch] text-sm text-ink-2">
            VART reads a company's policies, reports and records, answers each item of a vendor security
            questionnaire with the exact passage it came from, flags documents that disagree, and asks you only
            what the documents do not cover. Labels are decided by code, never by the model.
          </p>
          {!workspace && !startError && <p role="status" className="text-xs text-ink-3">Opening your workspace…</p>}
          <ErrorLine message={startError ?? error} />
          <ul className="border-t border-ink">
            <li className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-rule-strong px-2 py-3">
              <Button k="s" label="Try with a sample company" primary busy={busy} busyLabel="Starting…" onClick={sample} disabled={!workspace} />
              <span className="min-w-0 text-sm text-ink-2 [overflow-wrap:anywhere]">
                Kestrelyn, a fictional SaaS company: 22 documents and the bundled Vendor Security Questionnaire. The
                run fills in live as each item is answered.
              </span>
            </li>
            <li className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-rule-strong px-2 py-3">
              <Button k="o" label="Use your own files" onClick={own} disabled={!workspace} />
              <span className="min-w-0 text-sm text-ink-2 [overflow-wrap:anywhere]">
                An xlsx or csv questionnaire, plus documents in pdf, docx, xlsx, csv, md or txt. Your workspace is
                private and stops working after 24 hours.
              </span>
            </li>
          </ul>
        </section>
        <section aria-labelledby="how-h">
          <h2 id="how-h" className="mb-2 border-b border-ink pb-1 text-xs font-medium text-ink-2">how a label is decided</h2>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-sm">
              <thead>
                <tr className="h-6 border-b border-ink text-left text-xs font-medium text-ink-2">
                  <th scope="col" className="w-[19ch] px-2">label</th>
                  <th scope="col" className="px-2">when</th>
                  <th scope="col" className="w-[8ch] px-2">value</th>
                </tr>
              </thead>
              <tbody>
                {HOW.map(([label, when, value]) => (
                  <tr key={label} className="border-b border-rule align-top">
                    <td className="whitespace-nowrap px-2 py-1"><LabelChip label={label} /></td>
                    <td className="px-2 py-1">{when}</td>
                    <td className="whitespace-nowrap px-2 py-1">{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-ink-3">
            A quote that is not found word for word in its source, or that comes from a template, a contract or a
            flagged injection, is dropped before any label is set. Every answer stays "Draft, not approved" until a
            person approves it.
          </p>
        </section>
        {/* contract: GET /api/workspace goes first, so the health check waits for it */}
        {(workspace || startError) && <StatusPanel />}
        <p className="text-xs text-ink-3">
          Sample policies adapted from JupiterOne security policy templates (CC BY-SA 4.0); questions informed by
          Google VSAQ (Apache-2.0) and MVSP (CC0). See the <a className="underline" href={NOTICE_URL}>data NOTICE</a>.
        </p>
      </main>
      <footer data-chrome className="flex h-7 items-center gap-3 overflow-hidden whitespace-nowrap bg-chrome px-4 text-xs text-on-chrome-2">
        <span className="bg-on-chrome px-1 font-bold text-ink">HOME</span>
        <span><Kbd>s</Kbd> sample</span>
        <span><Kbd>o</Kbd> own files</span>
        <span className="hidden min-[480px]:inline"><Kbd>?</Kbd> all keys</span>
        <span className="ml-auto hidden min-[900px]:inline">VART · labels decided by code · synthetic demo data · MIT</span>
      </footer>
      {sheet && <KeySheet onClose={() => setSheet(false)} />}
    </div>
  );
}
