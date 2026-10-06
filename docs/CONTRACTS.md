# VART v2 unit contracts

Frozen at the start of Plan 2 (Plan 2A Task 2) after adversary checkpoint 1. The types live in
`app/contracts.py`; every signature below is in the module named. A module another lane imports starts as a stub
that raises `NotImplementedError` and is replaced by the lane that owns it; `app/ingest/parse.py`, `app/redact.py`
and `app/chunk.py` have no stub, because only the ingest lane uses them. A change needs the lead's OK, a line in
the change log at the end, and a re-recording of the evals when a prompt or a label could change.

| Unit | Module | Public interface | Model call |
|---|---|---|---|
| ingest | `app/ingest/parse.py` (plan2b) | `parse(filename: str, data: bytes) -> ParsedDocument`; `text_lines(text: str) -> list[Line]`; `IngestError` | no |
| redact | `app/redact.py` (plan2b) | `redact_text(text: str) -> str`; `redact_lines(lines) -> tuple[Line, ...]` | no |
| classify | `app/classify.py` (plan2b) | `PROMPT_VERSION = "classify@p1"`; `rules(fmt, texts) -> tuple[DocMeta, bool]`; `classify(filename, parsed, llm, model, spend) -> DocMeta` | fallback only |
| chunk | `app/chunk.py` (plan2b) | `chunk_lines(lines) -> list[ChunkSpec]`; `flags_of(text) -> tuple[Flag, ...]` | no |
| store | `app/ingest/store.py` (plan2b) | `ingest_document(session, workspace_id, filename, data, *, source, llm, model, spend) -> Document`; `store_statement(session, workspace_id, text, *, filename, today) -> Document` | via classify |
| retrieve | `app/retrieve.py` (2A) | `build_query(question, topic) -> str`; `retrieve(session, workspace_id, question, topic) -> Retrieval`; `document_passages(session, workspace_id, document_id) -> tuple[Passage, ...]` | no |
| stance | `app/stance.py` (2A) | `PROMPT_VERSION = "stance@p3"`; `user_prompt(item, passages) -> str`; `stance(llm, item, passages, model, step="stance") -> tuple[Stance, ...]` | yes |
| decide | `app/decide.py` (2A) | `decide(passages, stances, dropped=()) -> Decision` | no |
| draft | `app/draft.py` (2A) | `PROMPT_VERSION = "draft@p2"`; `plain_name(filename: str) -> str`; `user_prompt(item: ItemInput, decision: Decision) -> str`; `check(text, decision, documents) -> list[str]`; `template_answer(decision) -> str`; `write_draft(llm, item, decision, model, spend, documents) -> Draft` | yes |
| pipeline | `app/pipeline.py` (2A) | `answer_item(session, workspace_id, item, llm, models, spend) -> ItemResult`; raises `BudgetExhausted` when `spend("stance")` is refused | via stance, draft |
| interview | `app/interview.py` (2A) | `high_weight(topic) -> bool`; `plan_queue(items) -> list[QueueEntry]`; `follow_up(question, answer) -> str or None`; `recheck(session, workspace_id, statement_id, topic, items, llm, model, spend) -> list[Suggestion]` | recheck only |
| budget | `app/services/llm_budget.py` | `spender(session, workspace_id) -> Spend` | no |

## Rules every unit keeps

- Passage text is data, never instructions; every system prompt says so.
- A citation is one document line and an exact quote (`Citation.line_start == Citation.line_end`); it is re-read from
  `document_lines` before it shows. Labels come only from `decide`.
- `Stance.passage` is a 1-based index into the passages given to `stance()`; `decide` ignores 0, duplicates and
  out-of-range values.
- Prompts carry no database ids, timestamps or run dates, so a recording key is the same on every run and machine.
- Before a model call: `spend(step)`. False means `BudgetExhausted` (stance) or the unit's fallback (classify: the rules;
  draft: the template; recheck: stop). Each unit keeps no transaction open through a model call (`spend` commits
  at once; see its docstring).
- A unit that degrades on `LLMError` always re-raises `ReplayMiss`.
- Statuses and labels use the database's words: labels `verified`, `partial`, `conflict`, `unknown` (plus
  `user_confirmed` and `na`, set by Plan 3); values `Yes`, `No`, `Partial`.

## JSON shapes for Plan 3

`answers.citations` is `[jsonable(c) for c in decision.citations]`, `answers.dropped` is `[jsonable(d) for d in
decision.dropped]`, `answers.conflict` is `jsonable(decision.conflict)` or SQL NULL, `answers.scope_note` is
`decision.scope_note`, `answers.confidence` is `decision.confidence`. `jsonable` writes dates as ISO strings. Spec 6.7
re-runs decide after a metadata override with no model call, so Plan 3 also stores what decide needs: the
passages' chunk ids in order (`[p.chunk_id for p in result.retrieval.passages]`), `jsonable(result.stances)` and
the retrieval drops, decide's third argument (`jsonable(result.retrieval.dropped)`) (new `answers` columns, for
example `stances jsonb`); the passages are rebuilt from those chunks with the documents' current metadata.

## HTTP contract (Plan 3)

Frozen after Plan 3's adversary checkpoint 1 (plan3a Task 2). The models live in `app/api/schemas.py`; the
operations are pinned by `tests/test_openapi.py::test_the_frozen_contract_is_exactly_these_operations`;
`web/src/lib/api-types.ts` is generated from `openapi.json`. After the freeze, an added optional field needs only a
change-log line; changing or removing a path, a field or a status needs the lead's OK and a change-log line.

- Workspace: the signed cookie. Only `GET /api/workspace` creates a workspace and sets the cookie; every other
  endpoint without a live workspace is a 404 with the "reload the page" sentence (`errors.GONE`) and sets no
  cookie. `POST /api/workspace/reset` clears the cookie only when it found a workspace (otherwise a quiet 204).
  The frontend calls `GET /api/workspace` before any other call. `WorkspaceOut.expires_at` is `created_at` + 24 h.
- Cross-site writes: a POST, PUT, PATCH or DELETE under `/api/` with `Sec-Fetch-Site: cross-site`, or with an
  `Origin` whose host is not the request's `Host` (including `Origin: null`), is a 403 before any route runs
  (`errors.SameOriginWrites`). Reads are not checked; there is no CORS.
- Errors: `{"detail": "<sentence>"}`. 403 cross-site write; 404 unknown or foreign id, a missing workspace, or a
  workspace gone mid-request (a foreign-key violation); 409 state conflict; 422 refused input, in two shapes: a
  sentence (`IngestError`, mapping, caps; the operations listed in `SENTENCE_422` declare both) or FastAPI's
  list form for schema validation; 429 per-network limit or model budget, with `Retry-After`; 503 demo full or
  model calls off; 501 for a stub (Part 0 only). A body over Vercel's 4.5 MB limit gets the platform's 413 (not
  JSON); the UI shows "Files must be 4 MB or smaller." for it. The handlers are `app.api.errors.install`.
- Model budget 429: `llm_budget.Refused(step, scope)` names the cap; a plain `BudgetExhausted` reads as
  `workspace`. `workspace`, `network` and `hour` say so and retry at the next hour; `day` says the demo's budget
  for today is used up and `Retry-After` runs to midnight UTC. `llm_budget.refusal_scope(...)` tells which cap
  refused after the spender returned False.
- Free text: every request text is cleaned of NUL and lone surrogates; the three bounded bodies (`AnswerEdit.text`
  4,000, `NotApplicableIn.reason` 500, `AnswerQuestionIn.text` 4,000 characters) are cleaned and stripped before
  their bounds, so blank text is a 422. `Mapping.sheet` is at most 31 characters (Excel's limit).
  `DocumentPatch` fields may be left out; `kind`, `status` and `evidence_allowed` may not be null.
- Questionnaires: at most 5 per workspace (`MAX_QUESTIONNAIRES`, 422) and 1 MB per file
  (`MAX_QUESTIONNAIRE_BYTES`, 422). `DELETE /api/questionnaires/{id}` is 204, or 409 when a run used it.
  `POST /api/questionnaires/sample/{name}` is idempotent (the existing sample of that name is answered again);
  a new one counts under `upload`, the storage breaker and the cap. The sheet names are stored at upload, so
  listing never re-parses the file.
- Export: every cell written is inert text. A value starting with `=`, `+`, `-`, `@`, tab or CR gets a `'`
  prefix in csv; xlsx cells are written with `data_type = 's'`. The response is a download:
  `Content-Disposition: attachment; filename="<ASCII letters, digits, - _ .>-filled.<xlsx|csv>"`, plus a
  percent-encoded `filename*=UTF-8''...` when the file name had anything else; no raw user text in the header.
- Step runner: create a run (`POST /api/questionnaires/{id}/runs`, all items pending), then call
  `POST /api/runs/{id}/step` while `status == "running"`. A step claims up to 4 items (`FOR UPDATE SKIP LOCKED`;
  claims older than 5 minutes are taken again), answers them outside any transaction, writes one answer per item
  (`UNIQUE (run_id, item_id)`, conflicting inserts do nothing), stops claiming after 240 s, and returns
  unstarted items to pending. A refused budget is a 429 with the unstarted items returned. An item whose model
  call fails twice is `unknown` with a sentence saying so; its cost still counts. A repeated or concurrent step
  never processes an item twice or spends twice.
- Caps: per network an hour `workspace` 20, `upload` 60, `run` 20 (each through the one helper
  `app.api.errors.limit(request, session, kind)`, called before any write), and `llm` 400 model calls, counted
  per call by `llm_budget.spender(session, workspace_id, network=errors.network(request))` (steps and interview
  rechecks; never through `limit`), `interview` 60 answers (through `limit`, before any write); per workspace an hour per step (`llm_budget.CAPS`); globally 1,500 model calls
  an hour and 4,000 a day.
- Plan 6B room: `QuestionnaireOut.source` includes `csf` (with `format` `builtin`, `detected` null, and the
  scope in `Mapping.scope`); `ItemOut.csf_id`; runs scoped by questionnaire; `GET /api/questionnaires` lists
  built-in questionnaires. The seam is per-item dispatch in `app/runs.py` on `Questionnaire.source` /
  `Item.csf_id`; 6B may change the internals of `_answer`, `_values` and `step` (they are not frozen), and may
  add paths and optional fields (extending `CONTRACT` with a change-log line), but not change or remove ones
  defined here.

## Change log

- 2026-10-04: frozen (Plan 2A Task 2).
- 2026-10-05: `stance@p1` -> `stance@p2` (Plan 2C Task 4 Step 7, tune round 1, Ruling 9): partial only for a limit the
  passage states; another subject or audience is irrelevant; a record row's failing status field (Overdue, Expired,
  Failed, Open) is no, quoted with that field. Signatures unchanged; re-record.
  Revised before acceptance (round 2, Ruling 10; still `stance@p2`, the round-1 recordings were never accepted):
  no "narrower scope" in partial (scope stays decide's rule 5); only a missing actor reads yes, a missing
  threshold stays partial; another subject means clearly different, and a claim for one of several groups is
  judged on that group.
- 2026-10-05: `stance@p2` -> `stance@p3` (Plan 2C Task 4 Step 7, tune round 3, adversary checkpoint 2): a weaker
  standard, a longer interval or a shorter period than the question states is no, not partial; a record row's failing
  status is no only on a row about the question (another row is irrelevant); each passage header carries the
  document's declared scope (`DocInfo.scope`, "none declared" when empty) and the passage is judged for that coverage
  (comparing scopes stays decide's rule 5); the missing-threshold sentence is dropped, and a missing actor still reads
  yes unless the question requires an independent or third party. `user_prompt` output changes; signatures
  unchanged; re-record.
- 2026-10-05: `draft@p1` -> `draft@p2` (same round): no number taken from the question, punctuation outside the
  quotation marks, no comment on a document's status. `check` now ignores trailing `,;:` inside quotation marks
  (round 2, Ruling 10: revised before acceptance from `,;:.`; still `draft@p2`).
  Signatures unchanged; re-record.
- 2026-10-06: HTTP contract frozen (Plan 3A Task 2) after adversary checkpoint 1.
- 2026-10-06: HTTP contract fix round 1 (review I-1..I-3, P8; adversary-1 C1, C2, I1-I5) before the freeze:
  only `GET /api/workspace` creates a workspace (others 404 `GONE`), reset clears the cookie only when it found
  one, cross-site writes 403; 422 documents both shapes; `Mapping.scope` and `sheet` <= 31; `DocumentPatch`
  refuses null for NOT NULL fields; `DELETE /api/questionnaires/{id}`, 5 questionnaires and 1 MB per file,
  idempotent counted sample questionnaire; inert export cells; `llm` counted per model call in the spender;
  scoped budget 429 (`llm_budget.Refused`, `refusal_scope`). Added optional fields are allowed after the freeze.
- 2026-10-06: Plan 3A Task 9 (added optional field, allowed after the freeze): `ApprovedCount.skipped_edited` (int, default 0)
  counts the edited verified answers `approve-verified` leaves for a look (adversary-1 M5). New per-network cap kind
  `interview` (60 an hour) on `POST /api/questions/{id}/answer` (adversary-1 N2); no path or status changed.
- 2026-10-06: Plan 3A Task 9 fix round 1 (wording only, no path, field or status changed): `POST /api/questions/{id}/answer`
  keeps the answer and returns no suggestions when the re-check's model budget is refused (200); only the `interview`
  cap is a 429; 409 also when the item was answered since. `store_statement(..., commit=False)` lets the interview
  write statement, answer and question in one transaction (Ruling 9).
- 2026-10-06: Plan 3A adversary-3 fix round (wording and behaviour inside existing statuses; no path or field changed):
  `POST /api/runs/{id}/step` answers 503 with `Retry-After: 60` when the model provider is failing (401, 402, 408, 429,
  5xx, connection errors); the items stay pending, nothing is written as failed, the cost is kept. Schema mismatches
  and other 4xx are still the failed answer. A reset between two reads of one row is the `GONE` 404.
- 2026-10-06: inputs lane, adversary-3 fix round (no path, field or status changed; limits only): a document
  delete answers 409 while a run in the workspace is `running`; a document over 1,000,000 characters of text, a
  question over 2,000 or a topic over 200 characters, an xlsx over 4 MB unpacked, and a csv over 2,000 rows or
  52 columns are refused with the existing 422 sentence; `lines?from=&to=` is at most 20,000 (422); questionnaire
  file names are normalised; hidden sheets are skipped on import; the export's added columns sit past every
  mapped column.
- 2026-10-06: Plan 3 final review fix (no path or field changed; the 429 shape every limit already uses):
  `PUT /api/questionnaires/{id}/mapping` counts under the per-network `upload` limit, and `GET /api/runs/{id}/export`
  under a new `export` kind (60 an hour). An upload refuses only a too-long question; other mapping refusals wait for
  the PUT. `GET /api/runs/{id}/questions` also plans questions for items that became open after the first visit
  (a metadata override's re-decide), ranked after the existing ones.
