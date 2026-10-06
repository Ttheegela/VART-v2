import { vi } from "vitest";
import type {
  AnswerDetail, AuditEventOut, DocumentOut, Health, QuestionOut, QuestionnaireDetail, RunOut, RunRow, Workspace,
} from "../lib/api";

type Handler = unknown | Response | ((init: RequestInit | undefined, url: URL) => unknown | Response | Promise<unknown>);

/** The mock API: `"METHOD /path"` -> a typed body, a Response, or a function of the request. An unmocked call
 * answers 501 so a test fails loudly. Returns the list of calls made, in order. */
export function mockApi(routes: Record<string, Handler>): string[] {
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://test");
      const key = `${init?.method ?? "GET"} ${url.pathname}`;
      calls.push(key);
      const h = routes[key];
      if (h === undefined) return new Response(JSON.stringify({ detail: `unmocked ${key}` }), { status: 501 });
      const out = typeof h === "function" ? await (h as (i?: RequestInit, u?: URL) => unknown)(init, url) : h;
      if (out instanceof Response) return out.clone();
      return new Response(JSON.stringify(out), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
  return calls;
}

const item = (n: number, topic: string, question: string) => ({
  id: `i${n}`, position: n, row_ref: `Questionnaire!C${n + 6}`, code: `VSQ-${String(n).padStart(2, "0")}`,
  topic, question, csf_id: null,
});

const workspace: Workspace = { created_at: "2026-10-06T10:00:00Z", expires_at: "2026-10-07T10:00:00Z" };
const health: Health = { status: "ok", db: "ok", canary: null };
const run: RunOut = {
  id: "r1", questionnaire_id: "q1", status: "done", total: 3, done: 3, cost_usd: 0.002,
  models: { stance: "deepseek/deepseek-v4-pro" }, prompt_versions: { stance: "stance@p3" },
  started_at: "2026-10-06T10:01:00Z", finished_at: "2026-10-06T10:02:00Z",
};
const rows: RunRow[] = [
  {
    item: item(1, "Access Control", "Is user access reviewed at least quarterly?"),
    answer: { id: "a1", item_id: "i1", label: "conflict", value: null, text: "The policy says quarterly; the log shows reviews overdue. Which is current?", confidence: 0.3, sources: 2, approved: false, edited: false, statement_id: null },
  },
  {
    item: item(2, "Access Control", "Is MFA enforced for all workforce access?"),
    answer: { id: "a2", item_id: "i2", label: "verified", value: "Yes", text: "Yes. The access control policy requires MFA.", confidence: 0.9, sources: 1, approved: false, edited: false, statement_id: null },
  },
  { item: item(3, "Data Security", "Do customers manage their own keys?"), answer: null },
];
const detail: AnswerDetail = {
  ...rows[1].answer!, item: rows[1].item,
  citations: [{
    document_id: "d1", filename: "access-control-policy.docx", kind: "policy", status: "final", date: "2026-01-15",
    scope: null, line: 12, quote: "MFA is required for all workforce access.", stance: "yes", found_in_source: true,
    context: [
      { n: 11, text: "4. Authentication", cited: false },
      { n: 12, text: "MFA is required for all workforce access.", cited: true },
      { n: 13, text: "Exceptions need CISO approval.", cited: false },
    ],
  }],
  dropped: [{ reason: "placeholder", document_id: "d9", filename: "security-policy-template.md", line: 3, sentence: "This passage is unfilled template text." }],
  conflict: null, scope_note: null, statement_lines: [],
};
const documents: DocumentOut[] = [{
  id: "d1", filename: "access-control-policy.docx", source: "sample", kind: "policy", status: "final",
  effective_date: "2026-01-15", scope: null, evidence_allowed: true, metadata_source: "rule", line_count: 48,
  created_at: "2026-10-06T10:00:00Z",
}];
const questionnaire: QuestionnaireDetail = {
  id: "q1", filename: "v05.xlsx", source: "upload", format: "xlsx", sheets: ["Controls"],
  detected: { sheet: "Controls", header_row: 1, id_col: "A", question_col: "B", answer_col: "C", comments_col: "D", topic_col: null },
  mapping: null,
  preview: [{ row: 3, id: "VSQ-01", question: "Does your company run a documented security program?", topic: "GOVERNANCE", answer: null }],
  item_count: 0, latest_run_id: null, created_at: "2026-10-06T10:00:00Z", items: [],
};
const questions: QuestionOut[] = [{
  id: "qq1", run_id: "r1", item_ids: ["i3"], codes: ["VSQ-03"], reason: "unknown",
  text: "Do customers manage their own keys?", follow_up: null, status: "open", asked_count: 0, high_weight: true,
  suggestions: [],
}];
const audit: AuditEventOut[] = [{ at: "2026-10-06T10:02:00Z", actor: "visitor", action: "run.done", ref: "r1", detail: {} }];

export const fixtures = { workspace, health, run, rows, detail, documents, questionnaire, questions, audit };
