import type { components } from "./api-types";

type S = components["schemas"];
export type Health = S["HealthOut"];
export type Workspace = S["WorkspaceOut"];
export type DocumentOut = S["DocumentOut"];
export type DocumentPatch = S["DocumentPatch"];
export type DocumentUpdated = S["DocumentUpdated"];
export type Mapping = S["Mapping"];
export type QuestionnaireOut = S["QuestionnaireOut"];
export type QuestionnaireDetail = S["QuestionnaireDetail"];
export type RunOut = S["RunOut"];
export type RunRow = S["RunRow"];
export type RunRowsOut = S["RunRowsOut"];
export type StepOut = S["StepOut"];
export type AnswerSummary = S["AnswerSummary"];
export type AnswerDetail = S["AnswerDetail"];
export type CitationOut = S["CitationOut"];
export type QuestionOut = S["QuestionOut"];
export type AnswerQuestionOut = S["AnswerQuestionOut"];
export type SuggestionOut = S["SuggestionOut"];
export type AuditEventOut = S["AuditEventOut"];
export type LinesOut = S["LinesOut"];
export type Label = AnswerSummary["label"];

export class ApiError extends Error {
  status: number;
  retryAfter: number | null;
  constructor(status: number, message: string, retryAfter: number | null = null) {
    super(message);
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export async function errorMessage(res: Response): Promise<string> {
  // CONTRACTS.md: a body over Vercel's 4.5 MB limit gets the platform's own 413, which is not JSON.
  if (res.status === 413) return "Files must be 4 MB or smaller.";
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join("; ");
  } catch {
    // not JSON
  }
  return `Request failed (${res.status})`;
}

export function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/** `T` defaults to void for endpoints that answer 204 with no body. */
export async function request<T = void>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin", ...init });
  if (!res.ok) {
    const retry = Number(res.headers.get("Retry-After"));
    throw new ApiError(res.status, await errorMessage(res), Number.isFinite(retry) && retry > 0 ? retry : null);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function upload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  return request<T>(path, { method: "POST", body: form });
}

let workspace: Promise<Workspace> | undefined;

/** Test-only: forget the memoized workspace. */
export function resetWorkspaceForTests() {
  workspace = undefined;
}

/** Creates (or loads) this browser's workspace. Must resolve before any workspace call (app/api/deps.py). */
export function ensureWorkspace(): Promise<Workspace> {
  workspace ??= request<Workspace>("/api/workspace").catch((e) => {
    workspace = undefined;
    throw e;
  });
  return workspace;
}

/** Health answers 503 with a body when the database is down; both are readable states, not errors. */
export async function getHealth(): Promise<Health> {
  const res = await fetch("/api/health", { credentials: "same-origin" });
  if (res.status === 200 || res.status === 503) {
    const body = await res.clone().json().catch(() => undefined);
    if (body !== undefined) return body as Health;
  }
  throw new ApiError(res.status, await errorMessage(res));
}

const enc = encodeURIComponent;

export const api = {
  documents: () => request<DocumentOut[]>("/api/documents"),
  uploadDocument: (file: File) => upload<DocumentOut>("/api/documents", file),
  loadSampleDocuments: () => send<DocumentOut[]>("/api/documents/sample", "POST"),
  updateDocument: (id: string, patch: DocumentPatch) => send<DocumentUpdated>(`/api/documents/${enc(id)}`, "PATCH", patch),
  deleteDocument: (id: string) => send<void>(`/api/documents/${enc(id)}`, "DELETE"),
  documentLines: (id: string, from: number, to: number) =>
    request<LinesOut>(`/api/documents/${enc(id)}/lines?from=${from}&to=${to}`),
  questionnaires: () => request<QuestionnaireOut[]>("/api/questionnaires"),
  uploadQuestionnaire: (file: File) => upload<QuestionnaireOut>("/api/questionnaires", file),
  loadSampleQuestionnaire: (name: "vsq-a" | "mvsp-b") => send<QuestionnaireDetail>(`/api/questionnaires/sample/${name}`, "POST"),
  confirmMapping: (id: string, mapping: Mapping) => send<QuestionnaireDetail>(`/api/questionnaires/${enc(id)}/mapping`, "PUT", mapping),
  deleteQuestionnaire: (id: string) => send<void>(`/api/questionnaires/${enc(id)}`, "DELETE"),
  questionnaire: (id: string) => request<QuestionnaireDetail>(`/api/questionnaires/${enc(id)}`),
  createRun: (questionnaireId: string) => send<RunOut>(`/api/questionnaires/${enc(questionnaireId)}/runs`, "POST"),
  step: (runId: string) => send<StepOut>(`/api/runs/${enc(runId)}/step`, "POST"),
  run: (runId: string) => request<RunOut>(`/api/runs/${enc(runId)}`),
  runAnswers: (runId: string) => request<RunRowsOut>(`/api/runs/${enc(runId)}/answers`),
  approveVerified: (runId: string) => send<S["ApprovedCount"]>(`/api/runs/${enc(runId)}/approve-verified`, "POST"),
  exportUrl: (runId: string) => `/api/runs/${enc(runId)}/export`,
  answer: (id: string) => request<AnswerDetail>(`/api/answers/${enc(id)}`),
  editAnswer: (id: string, text: string) => send<AnswerSummary>(`/api/answers/${enc(id)}`, "PATCH", { text }),
  approve: (id: string) => send<AnswerSummary>(`/api/answers/${enc(id)}/approve`, "POST"),
  notApplicable: (id: string, reason: string) => send<AnswerSummary>(`/api/answers/${enc(id)}/not-applicable`, "POST", { reason }),
  questions: (runId: string) => request<QuestionOut[]>(`/api/runs/${enc(runId)}/questions`),
  answerQuestion: (id: string, text: string) => send<AnswerQuestionOut>(`/api/questions/${enc(id)}/answer`, "POST", { text }),
  skipQuestion: (id: string) => send<QuestionOut>(`/api/questions/${enc(id)}/skip`, "POST"),
  acceptSuggestion: (id: string) => send<AnswerSummary>(`/api/suggestions/${enc(id)}/accept`, "POST"),
  audit: () => request<AuditEventOut[]>("/api/audit"),
  resetWorkspace: () => send<void>("/api/workspace/reset", "POST"),
};
