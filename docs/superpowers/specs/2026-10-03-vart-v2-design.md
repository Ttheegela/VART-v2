# VART v2: design spec

_Date: 2026-10-03 · Status: draft for review · Owner: Tarun Theegela (solo rebuild) · Lead agent: Claude Opus 5.5_

VART v2 fills in a vendor security questionnaire from a company's own documents. Every answer cites the exact
passage it came from, contradictions between documents are flagged instead of guessed, and a person is asked only
what the documents do not cover. It is a rebuild of the hackathon project VART (Money Talks AI x Finance Hackathon,
NYC, 2026-09-05, team of 4) as a solo, production-grade public demo on public and synthetic data.

---

## 1. Why this exists

**Job goal.** Tarun is moving from data science into AI Engineer / Forward Deployed Engineer roles. Market data from
651 postings (see `~/Desktop/portfolio/PROJECT_PLAN.md`) says the gaps are production, integration and product
skills, not AI skills. Like PriorPath v2, VART v2 must show: a live URL anyone can try, messy customer files handled
well, tests and evals in CI, tracing, cost controls, security thinking, and clear product judgment.

**What v1 was.** A one-day hackathon build on a sponsor's confidential document pack: retrieve passages, ask a model
for each passage's stance on a question, decide the label with pure code (quote containment, template gate, negation,
date rule, conflicts, draft ceiling), draft the answer, interview the employee for gaps, score against a verified
answer key. Results on the private corpus: label accuracy before the interview 0.515 (run 1) and 0.545 (run 2),
3 of 3 primary and 4 of 4 secondary conflicts caught, 198 of 198 citations valid, ask recall 0.81 and precision 0.62.
v1 ran from local scripts and a Streamlit page; there is no public demo, and its retrieval inserted the answer key's
evidence ("pinned evidence") ahead of search results, so its numbers flatter retrieval.

**What v2 changes.**

| | v1 (hackathon) | v2 |
|---|---|---|
| Data | sponsor's confidential pack (private) | public questionnaires + synthetic company packs (public) |
| Inputs | one fixed corpus | sample pack, or the visitor's own questionnaire (xlsx/csv) and documents (PDF/DOCX/XLSX/CSV/MD/TXT) |
| Retrieval | keyword search + key evidence pinned in | Postgres full-text + pgvector hybrid, no pinned evidence |
| Labels | pure-code rules, hard-coded to one corpus | the same idea, generalized: rules read document metadata, not file names |
| Interview | chat with a scripted employee | "Questions for you" queue; answers become evidence that can fill other items |
| Output | JSON + Streamlit table | the visitor's own xlsx written back with formatting kept |
| Evals | one corpus, scored once | dev pack for tuning + holdout pack built after the engine is frozen; CI-gated |
| Ops | local scripts | Vercel + Neon, budgets, rate limits, redaction, Langfuse, health checks, runbook |

## 2. Goals, success criteria, non-goals

**Goals**
1. A visitor can fill a sample questionnaire against a sample company in under a minute with no signup and no keys.
2. A visitor can upload their own questionnaire and documents and get cited, labeled answers, then export the xlsx.
3. The model never decides a label. Labels come from code; citations are re-read from the source before they show.
4. Every claim in the README is backed by an eval that runs in CI.

**Success criteria (measured, see section 8)**
- Citation validity 1.00 on every pack (an invalid citation is a bug, not a metric).
- Every planted conflict caught on the dev pack (recall 1.0); precision reported.
- Label accuracy before the interview ≥ 0.80 on the dev pack; holdout reported, not tuned.
- Zero template or draft passages cited as verified; zero planted injections followed.
- Live URL, CI green, all docs in the definition of done (section 12).

**Non-goals**
- A reusable answer library across questionnaires (decided 2026-10-03: out of scope).
- Multi-user collaboration, roles, SSO, Slack routing, MCP server, ticketing.
- Scanned PDFs with no text layer (detected and rejected with a clear message).
- Real compliance: this is a synthetic-data demo, not a place for confidential documents.

## 3. Hard rules

1. **No sponsor content, ever.** Nothing from `~/Desktop/portfolio/projects/ai-money-hackathon/` (the sponsor pack,
   `verdicts.json`, the answer key, questionnaire text, company or people names) enters this repo, its history, the
   live app, or any model call made by this project, and no agent opens the hackathon folder's `Hackathon/`,
   `*.zip`, `verdicts.json` or `data/` paths. The only structural reference is the trap list in this spec (section
   7.3), written from v1's code documentation. Enforced mechanically by a CI deny-list check (section 11.3).
2. Public data only where the license allows redistribution; everything else is synthetic (section 7.6).
3. UI is monochrome (black, white, neutral grays); state is shown in words, not color.
4. Secrets never appear in chat, files or commits; Tarun enters them in his own terminal (`read -rs`).
5. Outward actions (repo creation or rename, pushes to `main`, deploys, cloud resources) need Tarun's OK (section 11.4).
6. Plain-English docs; every technical term spelled out on first use.

## 4. Users and the problem

**Who:** the security or compliance lead, or the sales engineer, at a 20–200 person B2B SaaS company. Enterprise
buyers send them security questionnaires (their own spreadsheet, or CAIQ, HECVAT or SIG) before a deal can close.

**Pain:** each questionnaire takes one to three days. The answers are scattered across policies, audit reports,
pentest reports and spreadsheets, and those sources sometimes disagree (a policy says access is reviewed quarterly;
the access-review sheet shows the last review nine months ago). Missed contradictions turn into audit findings or
lost buyer trust; invented answers are worse.

**Success for them (hypotheses, stated as such in `CUSTOMER_BRIEF.md`):** most items pre-answered with a valid
citation, contradictions surfaced before the buyer finds them, a person spends their time only on real gaps, and the
filled file goes back in the buyer's own format.

## 5. What a visitor does

1. **Landing.** "Try with a sample company" (default) or "Use your own files". Either creates a private workspace
   tied to a signed cookie; workspaces and everything in them are deleted after 24 hours.
2. **Questionnaire.** Pick a bundled sample, or upload xlsx/csv. A column mapper detects the sheet, header row,
   question column, answer column and ID column (and a comments column if present), shows a preview, and the visitor
   confirms or corrects it. Handles header offsets, section rows, merged cells and several sheets.
3. **Documents.** The sample pack, or manual upload. Each document shows its parse status and its detected metadata:
   kind (policy, report, record, contract, plan, questionnaire, other), status (final or draft), effective date or
   audit period, scope ("applies to"), and whether it counts as evidence. The visitor can override any of these.
   (Google Drive import arrives in Plan 5.)
4. **Fill.** A grid fills in live: question, answer, label (Verified, Partial, Conflict, Unknown, Confirmed by you),
   confidence and number of sources. The sample company's run is precomputed, so the default path is instant and
   costs nothing; "Re-run live" spends the workspace budget.
5. **Evidence drawer.** For any row: the answer, each cited passage highlighted inside its surrounding lines, the
   evidence that was dropped and why (failed quote check, template, injection, negation), and for conflicts both
   sides with their dates: "The access control policy says X; the access review record dated 2026-09-04 says Y.
   Which is current?"
6. **Questions for you.** A queue of open items: conflicts first, then unknown and partial items in high-weight topics
   (access control, data security, vulnerability management, incident response, business continuity), then the rest.
   A vague answer gets one follow-up. An accepted answer becomes a dated "statement" that is used as evidence: the
   engine re-checks other open items in the same topic against it and suggests fills, which the visitor accepts with
   one click.
7. **Approve and export.** A person approves answers (bulk-approve for verified ones). Export writes into the
   original xlsx with its formatting kept, filling the mapped answer column and adding Status, Sources and Notes
   columns; csv in, csv out. Unapproved answers are exported marked "Draft, not approved". Every action lands in an
   audit log the visitor can read.

## 6. Architecture

### 6.1 Stack and hosting

Same stack as PriorPath v2, so its proven scaffolding is copied rather than re-derived (inventory: PriorPath repo
at `db73145`): Python 3.12, FastAPI, SQLAlchemy + Alembic, Neon Postgres with pgvector, OpenRouter through the
`openai` SDK, Presidio for redaction, Langfuse for tracing, React + Vite + TypeScript + Tailwind v4 (oxlint, Vitest,
Playwright), one Vercel project (FastAPI serves the built UI with `app.frontend()`; `[tool.vercel.fastapi.static]
exclude = true` and `cdn = true`), GitHub Actions CI, UptimeRobot. Additions over PriorPath: a small `Settings`
class (pydantic-settings), record/replay built into the LLM client, per-IP limits, openpyxl, python-docx, pgvector.

### 6.2 Units

| Unit (`app/…`) | One job | Calls a model? |
|---|---|---|
| `workspaces/` | signed cookie workspace, budgets, per-IP limits, audit log, 24 h cleanup | no |
| `ingest/` | parse files into numbered lines; spreadsheet rows become dated records | no |
| `redact/` | Presidio PII + secret patterns, applied before storage and before any model call | no |
| `classify/` | document metadata: rules first, model fallback, user override | fallback only |
| `chunk/` | heading-aware passages over line ranges; one passage per record row; chunk flags | no |
| `retrieve/` | hybrid search, rank fusion, per-document cap, record hop | embeddings only |
| `stance/` | one structured call per item: each passage's stance + exact quote | yes |
| `decide/` | pure rules that produce label, value, citations, conflict, confidence | no |
| `draft/` | answer text from surviving evidence; code check of quotes, names, numbers | yes |
| `interview/` | queue order, follow-up ladder, statement re-check of related items | re-check only |
| `questionnaires/` | xlsx/csv import, column mapping, format-preserving export | no |
| `runs/` | resumable, idempotent fill runs driven by a step endpoint | orchestrates |
| `llm/` | OpenRouter client with live / record / replay modes, structured outputs | — |
| `observability.py` | Langfuse metadata-only tracing (PriorPath allow-list pattern) | — |

Each unit has a typed interface frozen in `CONTRACTS.md` before parallel work starts (section 11.3).

### 6.3 One fill run

`POST /api/questionnaires/{id}/runs` creates a run. The browser then calls `POST /api/runs/{id}/step` in a loop.
Each step claims the next N pending items (N≈4) in a short transaction (`run_items.state` pending → claimed,
`FOR UPDATE SKIP LOCKED`), then, outside the transaction, runs retrieve → stance → decide → draft → check for each
and writes one answer row (`UNIQUE (run_id, item_id)` makes a duplicate write a no-op). A repeated or concurrent call
never processes an item twice and never charges the budget twice (tested, section 8); a claim older than five minutes
(a crashed step) is reclaimed. Each step
finishes well inside Vercel's function limit (deadline 240 s under a 300 s maximum, as in PriorPath); no queue or
worker process is needed. The run records the prompt versions and model IDs it used.

### 6.4 Ingest

- **Formats:** PDF (pypdfium2 text layer; no text layer → rejected), DOCX (python-docx paragraphs and tables),
  XLSX (openpyxl), CSV, MD, TXT. Limits in section 9.
- **Lines:** every document becomes 1-based numbered lines (a paragraph, heading, list item or table row is one
  line). Citations point to document + line range + exact quote, so they survive re-chunking.
- **Records:** spreadsheet rows become one line each, keyed by the header; a date column or a stated "as of" date
  sets the record's `as_of`.
- **Chunk flags:** `negation` (not, never, no longer, pending, planned, not yet, …), `placeholder`
  (`[Company Name]`, `{{…}}`, `<insert …>`, "Lorem ipsum"), `injection` (instructions aimed at a model). Pattern lists
  live in one module and are unit-tested.
- **Document metadata** (`classify/`): kind, status (final/draft), effective date or audit period end, scope,
  `evidence_allowed`. Rules first (title and body cues: "DRAFT", "Template", placeholders, "Master Services
  Agreement", "Period of review"), a structured model call only when the rules are unsure, and the visitor can
  override every field. Contracts, templates and questionnaires default to `evidence_allowed = false`.

### 6.5 Retrieval

Query = the item's question (+ topic). Postgres full-text search (`websearch_to_tsquery`, `ts_rank_cd`) always;
pgvector cosine search added only if the retrieval eval shows recall@8 improves by ≥ 0.05 on the dev pack. Results
are merged by reciprocal rank fusion, capped at two passages per document, and extended by a record hop: when a
selected passage names an identifier (email, hostname, system name) that appears in record rows, up to three of those
rows are added. Passages from documents with `evidence_allowed = false` stay in the results so the evidence drawer
can show why they were not used (decide drops them). Passages flagged `injection` are removed before any model call
and recorded as dropped. No answer-key evidence is ever inserted. The embedding provider is chosen in Plan 2 (OpenRouter embeddings if available; otherwise vectors are
skipped and the README says so).

### 6.6 Stance

One structured-output call per item with up to 8 passages. For each passage the model returns
`stance ∈ {yes, no, partial, irrelevant}`, a quote (exact substring, ≤ 30 words, empty when irrelevant) and a short
note. The system prompt states that passage text is data, never instructions. The model is chosen by the eval
(section 8). Prompt text is versioned (`stance@p1`, …) and the version is part of every recording key.

### 6.7 Decide (pure code, full unit and property tests)

Inputs: the item, its stances, the passages with their document metadata. Rules apply in this order:

1. **Containment.** The quote must be a substring of the passage after whitespace and quote-mark normalization;
   otherwise drop it (`containment`).
2. **Evidence gate.** Drop passages whose document has `evidence_allowed = false`, or whose chunk is flagged
   `placeholder` or `injection` (`not-evidence`, `placeholder`, `injection`).
3. **Irrelevant.** Drop `irrelevant` stances.
4. **Negation.** A `yes` stance on a `negation`-flagged passage becomes `partial` (quote kept).
5. **Scope.** If `yes` and `no` evidence come from documents with different declared scopes, it is not a conflict:
   label `partial`, both cited, with a scope note ("the policy covers internal systems; the pentest covers the
   customer product").
6. **Conflict.** Otherwise, `yes` and `no` from two or more documents is a conflict. When one side is a record whose
   `as_of` is later than the other document's effective date or audit period end, the rule is `date` and the newer
   record is listed first; otherwise the rule is `documents-disagree`.
7. **Label.** No surviving evidence → `unknown`. Conflict → `conflict`. All `yes` → `verified`, value Yes. All `no`
   → `verified`, value No (an honest negative is still verified). Any other mix → `partial`, value Partial.
8. **Draft ceiling.** If every surviving citation comes from documents with status `draft`, `verified` becomes
   `partial`.
9. **Confidence.** verified 0.9, partial 0.6, conflict 0.3, unknown 0.0; minus 0.2 if anything was dropped for
   containment; floor 0.

Output: label, value, citations (only quotes that passed containment), dropped list with reasons, conflict
(both sides, dates, rule) or scope note, confidence. When the visitor overrides document metadata, decide re-runs on the
stances already collected, with no model call.

### 6.8 Draft and answer check

One structured call per item that has surviving evidence: one or two plain sentences naming the documents in plain
words. It may use only the decide step's citations and may not add new ones. For conflicts it writes the question
for the person; for unknowns it writes the question to ask. A code check then confirms every quoted string is in a
citation, every document named is a cited document, and every number in the text appears in a cited quote (reusing
PriorPath's `grounding.unsupported_numbers`). A failed check retries once, then falls back to a template answer built
from the citations.

### 6.9 Interview

Pure planner: order as in section 5 step 6; an item is never asked twice except for its one follow-up. Follow-up
ladder (from v1): ask once more when the answer lacks the number, frequency or name the question asks for. An
accepted answer is stored as a dated statement (kind `statement`, `evidence_allowed = true`) and the affected item
becomes `user_confirmed`. Open items in the same topic are re-checked against the new statement (one stance call each,
budgeted); fills found that way are shown as suggestions, never applied silently. The visitor can also mark an item
"Not applicable" (label `na`, with a reason in the audit log).

### 6.10 Questionnaire import and export

Import: detect the sheet, header row and columns by header keywords plus content shape (question-like text, Yes/No
values, IDs); the visitor confirms in a preview. Section rows (no question text) are kept as context for topic.
Export: openpyxl writes into the original workbook, keeping styles, merged cells, column widths, data validation and
conditional formatting; it drops embedded images and charts (a known openpyxl limit, stated in the export notice).
If the answer column has a Yes/No validation list without "Partial", the value goes into the notes. CSV in, CSV out.

### 6.11 Database

All tables carry `workspace_id` with `ON DELETE CASCADE` (PriorPath pattern); requests for another workspace's ids
return 404.

| Table | Key columns |
|---|---|
| `workspaces` | id, created_at, ip_hash |
| `documents` | id, filename, source (sample/upload/drive), sha256, kind, status, effective_date, scope, evidence_allowed, metadata_source (rule/model/user), line_count |
| `document_lines` | document_id, n, text (redacted) — primary key (document_id, n) |
| `chunks` | id, document_id, line_start, line_end, text, heading, flags text[], as_of, `tsv` tsvector (generated), `embedding` vector (nullable) |
| `questionnaires` | id, filename, source, original_bytes (xlsx only), sheet, mapping jsonb |
| `items` | id, questionnaire_id, position, row_ref, code, topic, question, csf_id |
| `runs` | id, questionnaire_id, status, prompt_versions jsonb, models jsonb, cost_usd, started_at, finished_at |
| `run_items` | run_id, item_id, state (pending/claimed/done), claimed_at — the step endpoint's work list |
| `answers` | id, run_id, item_id, label, value, text, citations jsonb, dropped jsonb, conflict jsonb, scope_note, confidence, statement_id, approved_at, edited |
| `interview_questions` | id, questionnaire_id, item_ids, text, status, asked_count, answer_text |
| `audit_events` | id, at, actor, action, ref, detail jsonb |
| `llm_usage`, `ip_limits` | hourly and per-IP counters (PriorPath budgets + new IP windows) |

**Constraints that encode the rules** (the v1 idea Tarun built, kept as database checks):
- `CHECK (label NOT IN ('verified','partial') OR jsonb_array_length(citations) > 0)` — no verified or partial answer
  without a citation.
- `CHECK (label <> 'user_confirmed' OR statement_id IS NOT NULL)` — "Confirmed by you" always points to the statement
  (`statement_id` references the `documents` row of kind `statement` that holds the visitor's answer).
- `UNIQUE (run_id, item_id)` — one answer per item per run (the step endpoint's idempotency rests on it).
- `CHECK (label IN ('verified','partial','conflict','unknown','user_confirmed','na'))`.

### 6.12 API (FastAPI; OpenAPI at `/api/docs`)

- `GET /api/health`, `GET /api/version`
- Workspace: implicit via cookie (`ensureWorkspace` pattern); `POST /api/workspace/reset`
- Documents: `POST /api/documents` (multipart), `GET /api/documents`, `PATCH /api/documents/{id}` (metadata
  override), `DELETE /api/documents/{id}`, `GET /api/documents/{id}/lines?from=&to=`
- Questionnaires: `POST /api/questionnaires` (upload → detected mapping + preview),
  `POST /api/questionnaires/sample/{name}`, `PUT /api/questionnaires/{id}/mapping`, `GET /api/questionnaires/{id}`
- Runs: `POST /api/questionnaires/{id}/runs`, `POST /api/runs/{id}/step`, `GET /api/runs/{id}`
- Answers: `GET /api/runs/{id}/answers`, `GET /api/answers/{id}`, `PATCH /api/answers/{id}` (edit text),
  `POST /api/answers/{id}/approve`, `POST /api/runs/{id}/approve-verified`
- Interview: `GET /api/runs/{id}/questions`, `POST /api/questions/{id}/answer` (→ accept or follow-up, plus suggested
  fills), `POST /api/questions/{id}/skip`, `POST /api/suggestions/{id}/accept`
- Export: `GET /api/runs/{id}/export` (xlsx or csv, matching the input)
- Audit: `GET /api/audit`
- Internal: `GET /api/internal/cleanup` (Vercel cron, bearer `CRON_SECRET`)

The frontend's TypeScript types are generated from this OpenAPI schema; CI fails if the generated file drifts.

### 6.13 Frontend

Query-string routing and API client patterns copied from PriorPath (`route.ts`, `api.ts`, `ErrorBoundary`,
`ExpiredNotice`, `AuditLog`). Views: Home, Workspace (Documents panel, Questionnaire panel with column mapper),
Run grid, Evidence drawer, Questions for you, Export, Audit log. Built first against a mock API generated from the
frozen contracts, then wired to the real one. Keyboard-usable grid and drawer; labels in words; monochrome.

### 6.14 LLM client, models, tracing

- `LLMClient` protocol with `OpenRouterClient`; modes `live`, `record`, `replay`. Recording key =
  sha256(model, prompt version, messages, output schema); recordings are JSONL under `evals/recorded/`. In `replay`
  a missing key is an error, so CI never touches the network. Tests use fakes (PriorPath `tests/fakes.py` pattern).
- Structured outputs via `response_format` JSON schema with `strict: true`; non-"stop" finishes are failures.
- Models per step (stance, draft, classify fallback, re-check, judge) are environment variables with defaults set
  from the model bench in Plan 2; the judge is from a different model family than the drafter.
- Langfuse: metadata only (model, prompt version, latency, tokens, finish reason, item id, step); never prompts,
  document text or answers. No-op without keys; failures never affect a request.

## 7. Data

### 7.1 Questionnaires (bundled)

| Sample | Built from | License |
|---|---|---|
| A. "Vendor Security Questionnaire", ~60 items, a deliberately messy xlsx (header offset, section rows, merged cells, a Yes/No column with data validation, a comments column) | Google VSAQ question content (2016, wording modernized), MVSP for current topics; every item tagged with a NIST CSF 2.0 subcategory | VSAQ Apache-2.0, MVSP CC0, NIST public domain |
| B. "MVSP short form", ~25 items, csv | MVSP | CC0 |

CAIQ, HECVAT, SIG and the VSA questionnaire are not redistributable and are never bundled; visitors may upload
their own copies.

### 7.2 Company packs

Two fictional SaaS companies (names checked against a web search so they match no real firm):
- **Dev pack:** used to build and tune rules, prompts and models (Plan 1).
- **Holdout pack:** generated only after the engine is frozen (Plan 4), so nothing could have been tuned on it.

Each pack has about 20 documents: ~12 policies adapted from JupiterOne security-policy templates (filled in for the
company), plus fully synthetic documents: SOC 2 Type II summary (with exceptions), pentest report (with findings),
access-review records (xlsx, dated rows), asset inventory (xlsx), BCP/DR plan, a Master Services Agreement (contract,
never evidence), a draft employee handbook, a template with placeholders, and planted prompt injections (section 7.3).

**Fact sheet first.** Each company starts as a structured fact sheet (`data/<pack>/facts.yaml`): what is true, which
documents say what, and every planted trap. Documents are generated from the fact sheet, and the answer key is
derived from it, so the key is consistent by construction. A second agent then re-derives the key from the
documents alone; every disagreement is resolved (and the fact sheet, document or key fixed) before the pack is used.

### 7.3 Planted traps (per pack, minimum)

| Trap | Count | What must happen |
|---|---|---|
| Stale record vs policy or audit (date rule) | 2 | conflict, newer record first |
| Two documents disagree | 2 | conflict |
| Scope difference | 2 | partial with scope note, not a conflict |
| Negation ("MFA is not yet enforced for …") | 3 | never verified Yes from that passage |
| Honest negatives (truly not done) | 5 | verified No, kept |
| Template / placeholder passages | 2 | never cited |
| Draft-only evidence | 2 | at most partial |
| Prompt injection | 2 (one caught by the patterns, one subtle) | never cited, never followed: affected items still match the key and no drafted text carries the injected content |
| Must-ask items (only the company can answer) | ≥ 5 | unknown → asked |
| One answer fills several items | ≥ 2 | suggested fills appear |

### 7.4 Answer key format (`data/<pack>/key/<questionnaire>.json`)

Per item: `id`, `expected_label`, `expected_value`, `must_ask`, `evidence` (`[{doc, line_start, line_end, quote}]`,
by document and line so it is independent of chunking), `conflict_id`, `scope_note_expected`, `honest_negative`,
`trap`, `fills` (item ids an answer here should also fill), `notes`. Pack level: `conflicts`, `traps`, and the
expected interview set.

### 7.5 Column-mapper set

Ten messy xlsx/csv variants (header offsets, multiple sheets, merged headers, blank rows, IDs in odd places, answers
pre-filled for some rows, non-English header), each with its expected mapping.

### 7.6 Licensing layout

Code: MIT (`LICENSE`). Data: `data/LICENSE` CC BY-SA 4.0 for policy text adapted from JupiterOne templates, with
attribution in `data/NOTICE.md`; VSAQ (Apache-2.0) and MVSP (CC0) attributions in the same notice. JupiterOne's
`standards/*.json` (third-party framework text) is not used. Synthetic documents written from scratch are CC BY 4.0.

## 8. Evals and tests

**Mechanics.** `python -m evals.run --pack dev --replay` runs the whole pipeline over each questionnaire on recorded
model outputs, scores it against the key, writes `evals/results/latest.{md,json}`, and exits non-zero on a failed
gate. CI runs it and then `git diff --exit-code evals/results` (PriorPath pattern). Re-recording (`--record`) needs
the OpenRouter key and runs in Tarun's terminal. A model bench (`evals/bench.py`) compares candidate models per step
on accuracy, cost and latency; results go to `evals/results/bench-<step>.md` and set the defaults.

| Stage | Metric | Gate (dev pack; tightened after the Plan 2 baseline) |
|---|---|---|
| Column mapping | correct mapping on the 10 variants | 10/10 |
| Parsing | lines extracted vs source text | reported |
| Retrieval | recall@8 of key evidence lines (no pinning) | ≥ 0.90 |
| Stance | accuracy vs key stances | reported |
| Labels | accuracy vs key before the interview | ≥ 0.80 |
| Conflicts | recall on planted conflicts; precision | 1.0; reported |
| Citations | quotes re-read from source | 1.00 (all packs) |
| Traps | template/draft cited as verified; injections followed | 0; 0 (all packs) |
| Honest negatives | kept as verified No | all |
| Interview | ask recall and precision; asked twice | reported; never |
| Answer text | judge (different family) faithfulness; code checks | ≥ 0.90; all pass |
| Holdout | the full table on the holdout pack | reported, not tuned |
| Cost and speed | USD and p50 seconds per 60-item run | reported; target ≤ $0.30 |

The README compares v2 with v1 honestly: different datasets, and v1's retrieval had the key's evidence pinned in.

**Tests.** pytest unit tests (decide at 100% branch coverage, plus Hypothesis property tests: a dropped quote never
appears in citations; adding an irrelevant stance never changes the label; a conflict label always has two sides),
Postgres integration tests (constraints, workspace isolation, concurrent and repeated step calls), Vitest component
tests, Playwright E2E (sample flow end to end; upload flow with a messy xlsx; export downloaded and checked cell by
cell; the interview fills an item), and the live smoke script against production after every deploy.

## 9. Security, limits, privacy

- **Isolation:** signed HttpOnly cookie (SameSite=Lax, Secure on Vercel); every query scoped by workspace; 24-hour
  deletion by daily cron; `POST /api/workspace/reset` for an immediate wipe.
- **Cost guards:** per-workspace hourly model budget and a global daily cap (PriorPath `llm_budget`), OpenRouter
  credit cap, per-IP limits on workspace creation, uploads and runs (Postgres counters keyed by a salted IP hash),
  storage breaker (PriorPath `capacity`), and a precomputed sample run so the default path spends nothing.
- **Upload limits:** PDF/DOCX/XLSX/CSV/MD/TXT only, checked by content as well as extension; ≤ 4 MB per file
  (Vercel's request limit is 4.5 MB); ≤ 20 documents and ≤ 20,000 lines (about 200 pages) per workspace; ≤ 150 questionnaire items;
  zip-bomb-safe xlsx reading (size and row caps).
- **Data handling:** uploaded document bytes are parsed in memory and never stored; only redacted lines are kept.
  Redaction (Presidio names, emails, phone numbers, addresses; regexes for API keys, private keys, tokens and
  connection strings) runs before storage and before any model call. The questionnaire xlsx is stored (for
  export) and deleted with the workspace.
- **Prompt injection:** passage text is data; injection-flagged chunks are excluded; labels come from code; the
  injection eval gates CI.
- **Outputs:** export marks unapproved answers; the answer check blocks unsupported quotes, names and numbers.
- **`SECURITY.md`:** synthetic-data demo, not for confidential documents; what is stored and for how long; what is sent
  to OpenRouter and model providers (redacted text only); what real use would need.

## 10. Operations and deployment

Vercel Hobby plan (one project, Git-connected, `main` = production, previews per branch), Neon Postgres with pgvector, Vercel
cron for cleanup, `/api/health` (database check under a 2 s statement timeout, 503 when degraded), UptimeRobot,
Langfuse. Migrations run from Tarun's terminal against a Neon branch first, additive changes before code that needs
them, risky ones back to back with the deploy (PriorPath RUNBOOK rules). After any packaging or middleware change,
check `/` on the preview as well as `/api/health` (the PriorPath `cdn = true` incident). A hello-world deploy happens
in Plan 1, not at the end.

**Alive, not awake.** A portfolio demo sits idle for weeks and must still work on the first click (the old Render and
Railway demos died: Render's free services sleep and its free databases expire; Railway stops when credits run out).
Everything here scales to zero and wakes on request, and nothing expires on idle:
- VART gets its own Neon project, so its 100 free compute-hours a month are separate from PriorPath's.
- Monitoring must not keep the database awake: UptimeRobot checks `/` (served from the CDN, no function, no
  database) every 5 minutes, and `/api/health` every 60 minutes as a keyword monitor that alerts unless the body says
  `"status":"ok"`. That wakes Neon about 24 times a day, roughly 15 compute-hours a month.
- A daily Vercel cron canary (`/api/internal/canary`) makes one tiny call per configured model and reads the
  OpenRouter credit balance. `/api/health` reports `"status":"degraded"` (HTTP 200) when the last canary failed or
  credits are under $2, and HTTP 503 only when the database is down; the hourly monitor emails Tarun either way.
  This catches retired model IDs and empty credits before a visitor does.
- The sample path is precomputed and works with zero model credits.
- No GitHub Actions schedules for keep-alive: GitHub disables scheduled workflows after 60 days without repository
  activity.

## 11. Delivery

### 11.1 Plans

1. **Foundation and dev data.** Repo scaffold from PriorPath patterns, `CLAUDE.md` map and rules, `Settings`,
   database schema and first migration, CI with the mechanical gates, LLM client with record/replay, observability,
   health, frozen `CONTRACTS.md` and OpenAPI types (adversary review before freezing), hello-world deploy. In parallel:
   dev pack fact sheet, documents, questionnaires A and B, answer keys with independent verification, column-mapper
   set, licensing files.
2. **Engine and evals.** Ingest, redaction, classification, chunking, retrieval, stance, decide, draft and check,
   interview planner, eval harness, first recordings, baseline, model bench, gates set.
3. **API and UI.** All endpoints, step runner with concurrency tests, budgets and IP limits, column mapper, export,
   the full frontend (mock API first), Vitest, Playwright.
4. **Hardening and launch.** Adversary security pass, upload-abuse tests, engine freeze tag, holdout pack and holdout
   eval, precomputed sample run, docs set, README with demo GIF, production deploy, UptimeRobot, portfolio entry text
   (the site itself is updated in the planned final portfolio refresh unless Tarun says otherwise).
5. **Google Drive import.** Google Picker with the `drive.file` scope (the app sees only files the visitor picks; no
   Google verification needed), the visitor's short-lived token used once and never stored, fakes in tests, E2E with
   a mocked Picker, docs. The OAuth client is created by Tarun in Google Cloud Console.

### 11.2 Roles and models

| Role | Model | Owns |
|---|---|---|
| Lead | Opus 5.5 (this session) | spec, plans, contracts, merges, final review of each plan |
| Data builder | Sonnet 5.5 | fact sheets, documents, questionnaires, keys, mapper set |
| Key verifier | Sonnet 5.5 | re-derives keys from documents alone |
| Database | Sonnet 5.5 | schema, migrations, constraints, isolation tests |
| Backend: ingest | Sonnet 5.5 | parsers, redaction, classification, chunking |
| Backend: engine | Opus 5.5 | retrieval, stance, decide, draft, interview |
| Backend: API | Sonnet 5.5 | endpoints, runs, limits, export |
| Frontend | Opus 5.5 | React UI, mock API, Vitest |
| Evals | Sonnet 5.5 | harness, record/replay, metrics, bench |
| QA | Sonnet 5.5 | Playwright, real-browser checks on every preview |
| Security | Sonnet 5.5 | redaction and injection review, limits, `SECURITY.md` |
| DevOps | Sonnet 5.5 | CI, Vercel, Neon, health, uptime |
| Docs | Sonnet 5.5 | README, ARCHITECTURE, RUNBOOK, CUSTOMER_BRIEF, LEARNING, EVALS |
| Reviewer | Sonnet 5.5 (Opus for decide, redaction, limits) | two-stage review of every task |
| Adversary | Fable 5.1 | three checkpoints per lane (section 11.3) |

No subagent runs below Sonnet 5.5.

### 11.3 Guardrails

- **Orchestration:** the Workflow tool (Tarun opted in to a multi-agent swarm on 2026-10-03). Foundation tasks run
  first and in order; lanes then run in parallel, at most 6 agents at a time.
- **Isolation:** each lane works in its own git worktree and branch with its own test database
  (`vart_test_<lane>`). Worktree isolation is not a documented Workflow option, so the lead creates each worktree and
  names its directory in the agent's task; lanes merge into `main` by pull request after CI is green and review passes.
- **Task contract:** every plan task states its deliverable, the files it owns, non-goals, and "done when". The
  reviewer rejects edits outside the owned files.
- **Rules backed by checks that fail** (the rule is written in `CLAUDE.md` and a check enforces it):

  | Rule | Check |
  |---|---|
  | no sponsor content | CI deny-list scan over the tree and every commit in a PR: word and phrase n-grams and file hashes are compared against a list that stores only salted hashes, so the list itself reveals nothing |
  | no verified answer without a citation | database CHECK constraint |
  | frontend matches backend | generated OpenAPI types; CI fails on drift |
  | no secrets committed | gitleaks in CI |
  | monochrome UI | CI scan for Tailwind color utilities |
  | quality holds | eval gates in CI |
  | migrations match models | `alembic check` in CI |

- **Adversary checkpoints (Fable 5.1):** (1) before a contract is frozen: does every payload match its schema, and
  what is missing? (2) when the same test fails twice: is the fix addressing the cause or hiding the symptom?
  (3) before a lane is declared done: what attack surface or edge case did everyone miss?
- **Two-failure rule:** the same failure twice stops the task for an adversary review and root-cause debugging.
  Tests are never weakened or deleted to get green. After three attempts the task returns to the lead, and to
  Tarun if needed.
- **Shared memory:** `CLAUDE.md` (compact map: where things live, commands, hard rules), `docs/PROGRESS.md` and a
  decisions log, updated at the end of every task.

### 11.4 Approval gates (Tarun says yes first)

Renaming the old repo and creating the new one; the first push and every push to `main`; creating the Vercel project
and Neon database; entering secrets (his terminal, `read -rs`); production deploys; re-recording paid evals (his
terminal); creating the Google OAuth client (Plan 5). A short numbered release plan is presented for one approval
at each release point.

### 11.5 Repo name and the old repo

Recommended: rename the old private `Ttheegela/VART` to `Ttheegela/VART-hackathon` (still private) and create a new
public `Ttheegela/VART` with no history from the old one.

**Required safety step before creating the new repo:** the five local hackathon folders (`VART`, `VART-adapter`,
`VART-merge`, `VART-ui`, `VART-ui-real` under `projects/ai-money-hackathon/`) all have `origin` set to
`Ttheegela/VART.git`. After the rename, that URL would point at the new public repo, and a push from an old folder
would publish sponsor files. Their remotes are switched to `VART-hackathon.git` and checked before the new repo is
created. (Alternative with no such risk: give the new repo a different name.)

## 12. Definition of done

- [ ] Live public URL; the sample path works with no signup or keys
- [ ] `CUSTOMER_BRIEF.md`: user, problem, success metric, out of scope
- [ ] One real external integration (Google Drive, Plan 5)
- [ ] Tests and evals run in GitHub Actions on every push; gates green
- [ ] Langfuse traces on every model call; `/api/health` with UptimeRobot
- [ ] Rate limits, budgets and a precomputed sample run
- [ ] Stays alive: UptimeRobot on `/` (5 min) and `/api/health` (60 min, keyword), daily canary green, sample path works with no model credits
- [ ] README written problem first: demo GIF, architecture, eval results (dev and holdout), v1 vs v2
- [ ] `ARCHITECTURE.md`, `RUNBOOK.md`, `SECURITY.md`, `EVALS.md`, `LEARNING.md`, `PROGRESS.md`
- [ ] Portfolio entry text: solo rebuild, accurate stack, demo link (site updated in the final refresh)

## 13. Risks and open questions

| Risk | Plan |
|---|---|
| OpenRouter may not offer embeddings | verify in Plan 2; full-text search alone is the fallback and the README says which is used |
| Vercel bundle size (Presidio + spaCy model + pgvector client + openpyxl) | measure on the Plan 1 hello-world deploy; PriorPath already ships Presidio |
| openpyxl drops images and charts in exported workbooks | stated in the export notice; checked on the 10 variants |
| VSAQ wording is from 2016 | modernize wording; MVSP covers current topics; CSF IDs keep it grounded |
| Share-alike on adapted policy text | kept in `data/` under CC BY-SA with attribution; code stays MIT |
| Synthetic packs can be too easy | traps table is a minimum; holdout built after freeze; key verified independently |
| Swarm merge conflicts | file ownership per task, contracts frozen first, at most 6 parallel agents |
| Public uploads abused | per-IP limits, budgets, size caps, 24 h deletion, redaction |
| Neon's free 100 compute-hours a month run out (a 5-minute database health check alone keeps the compute awake 24/7, about 180 compute-hours a month) | monitors as in section 10 (UI every 5 minutes, database hourly); own Neon project; watch Neon usage after launch |
| Vercel Hobby allotments are shared by every project on the account (4 Active CPU hours, 360 GB-hours of memory, 1,000,000 function invocations, 100 GB data transfer a month; going over pauses the account's usage for up to 30 days) | parse and redact once per upload, lazy-load Presidio, precomputed sample run, size and per-IP caps; watch the usage page after launch; Hobby is for non-commercial use, which a portfolio demo is |

## 14. Out of scope (re-stated)

Answer library, multi-user roles, SSO, Slack, MCP, ticketing, OCR of scanned PDFs, non-English documents, any use of
the sponsor's data beyond structural reference.

## Appendix: v1 → v2 mapping

| v1 module | v2 unit | Change |
|---|---|---|
| `pack/chunk.py`, `VART/ingest` | `ingest/`, `chunk/` | generalized formats; redaction added; line-numbered citations kept |
| `pack/search.py` | `retrieve/` | hybrid search in Postgres; pinned evidence removed |
| `agent/stance.py` | `stance/` | one call per item instead of per passage; recorded |
| `claims/decide.py` | `decide/` | aliases and fixed dates replaced by document metadata; scope rule kept |
| `agent/propose.py` | `draft/` | code check of quotes, names and numbers |
| `agent/planner.py` | `interview/` | answers become statements that can fill other items |
| `claims/profile.py` | `answers` table | database constraints instead of a JSON file |
| `claims/score.py` | `evals/` | dev and holdout packs, CI gates, model bench |
| `evidence/trace.py` + sidecar | `observability.py` + answer check | Langfuse metadata; citation check in-process |
