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
| retrieve | `app/retrieve.py` (2A) | `build_query(question, topic) -> str`; `retrieve(session, workspace_id, question, topic, exclude_sources=()) -> Retrieval` (6B: documents from `exclude_sources` are neither candidates nor hopped to, and count in neither the IDF nor the chunk total; the default is unchanged); `document_passages(session, workspace_id, document_id) -> tuple[Passage, ...]` | no |
| stance | `app/stance.py` (2A) | `PROMPT_VERSION = "stance@p3"`; `user_prompt(item, passages) -> str`; `stance(llm, item, passages, model, step="stance") -> tuple[Stance, ...]` | yes |
| decide | `app/decide.py` (2A) | `decide(passages, stances, dropped=()) -> Decision` | no |
| draft | `app/draft.py` (2A) | `PROMPT_VERSION = "draft@p2"`; `plain_name(filename: str) -> str`; `user_prompt(item: ItemInput, decision: Decision) -> str`; `check(text, decision, documents) -> list[str]`; `template_answer(decision) -> str`; `write_draft(llm, item, decision, model, spend, documents) -> Draft` | yes |
| pipeline | `app/pipeline.py` (2A) | `answer_item(session, workspace_id, item, llm, models, spend) -> ItemResult`; `answer_retrieved(session, workspace_id, item, retrieval, llm, models, spend) -> ItemResult` (answer_item after its retrieval); raises `BudgetExhausted` when `spend("stance")` is refused | via stance, draft |
| interview | `app/interview.py` (2A) | `high_weight(topic) -> bool`; `plan_queue(items) -> list[QueueEntry]`; `follow_up(question, answer) -> str or None`; `recheck(session, workspace_id, statement_id, topic, items, llm, model, spend) -> list[Suggestion]` | recheck only |
| csf | `app/csf.py` (6A) | `framework() -> Framework`; `in_scope(scope) -> tuple[Outcome, ...]`; `item_input(o) -> ItemInput`; `gap_label(o, label, value=None, statement_id=None) -> GapLabel or None`; `questionnaire_for(session, workspace_id, scope) -> Questionnaire`; `part_inputs(o) -> tuple[ItemInput, ...]`; `evidence(session, workspace_id, item) -> Retrieval`; `check_parts(session, workspace_id, o, llm, models, spend) -> list[ItemResult]`; `part_label(r) -> PartLabel`; `combine(labels) -> PartLabel`; `explain(o, parts, filled=()) -> str`; `aggregate(o, parts) -> ItemResult`; `check_outcome(session, workspace_id, o, llm, models, spend) -> ItemResult or None`; `ask_queue(outcomes, asked) -> list[QueueEntry]`; `current_mapping(scope) -> dict[str, str]`; `check_part(session, workspace_id, o, n, llm, models, spend) -> ItemResult`; `part_result(o, n, raw) -> ItemResult`; `CONTROLS_URL` | via answer_retrieved (stance only; a part's draft is never written) |
| runs | `app/runs.py` (6B; only these names) | `STEP_PARTS = 8`; `outcome_values(o, parts) -> dict[str, Any]`; `reopen_changed(session, workspace_id, run_id, models=None) -> int` | no |
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
- Plan 6A (shipped): `QuestionnaireOut.source` includes `csf` (with `format` `builtin` and `detected` null);
  `ItemOut.csf_id`; runs are scoped by questionnaire. The seam is per-item dispatch in `app/runs.py` on
  `Questionnaire.source` / `Item.csf_id`; 6B may change the internals of `_answer`, `_values` and `step` (they
  are not frozen), and may add paths and optional fields (extending `CONTRACT` with a change-log line), but not
  change or remove ones defined here.
- Gap check (Plan 6B): `GET /api/gap/{scope}` (`core` or one CSF function, lowercase) answers `GapOut`: every
  outcome of the scope's functions in NIST's order with its tier, and the label (`app.csf.gap_label`) and
  explanation from the latest run of the scope's current built-in questionnaire; it writes nothing. An outcome
  the visitor marked not applicable has `GapRow.not_applicable`, no label and its reason as the explanation, on
  either tier, and the gap sheet writes "Not applicable". An outcome whose model call failed twice has no label
  and the failure sentence as its explanation (never Gap); the sheet writes "Failed".
  `POST /api/gap/{scope}/run` creates or reuses that questionnaire (Plan 3 Ruling 5: built-in ones are never
  counted, listed or deleted), locks it, and answers the run to step: a new one, the running one, or the done
  one with every outcome whose evidence changed (compared as sets of passages) or whose answer failed re-opened
  in full (`app.runs.reopen_changed`, CSF spec 5.6; none changed: it stays done). Two presses at once answer the
  same run. It is counted under `run`, and 503 when the demo is full.
  A step claims csf items until their parts add up to `STEP_PARTS` (8), stores each part's result in
  `run_items.parts` as it lands, and checks its deadline before each part not yet stored: an outcome cut off
  there is released with its stored parts kept and no attempt counted, and the next step resumes it.
  A Checked part's evidence never includes statements (`retrieve(..., exclude_sources=("statement",))`, keyed on
  `Document.source`, so no kind the visitor sets lets one in); a statement's metadata cannot be patched (409).
  `AnswerDetail.parts` lists a Checked outcome's parts; `SuggestionOut.part` names the part a fill is for (0:
  the whole item); on a gap-check run an answer is re-checked against the open parts in its CSF function, and
  a re-open keeps the open per-part fills. An accepted per-part fill reads "Confirmed by you: part n" in the
  explanation when its part is Covered (otherwise its label's words "in your answer", e.g. "Partly evidenced in
  your answer: part n") and "(your answer)" in the sheet's quotes (keyed on `Document.source`), and the outcome is Confirmed by you only when it would
  otherwise read Covered (an Ask-me outcome the visitor answered reads "Answered by you", Ruling 14) (one filled part with Gaps left stays Partly covered); accepting one fill never
  closes the others.
  On a gap-check run, `GET /api/runs/{id}/export` answers the gap-report workbook (it was a 409), and Questions
  for you holds the Ask-me outcomes only. An xlsx questionnaire export carries the latest done gap check as a
  `Gap report` sheet. `Mapping.scope` stays unused.

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
- 2026-10-05: Plan 6A Task 6 fix round 1, lead Ruling 9 (CSF Checked outcomes are judged on documents only):
  `DropReason` gains `"statement"`; `app.pipeline.answer_retrieved` is added (`answer_item` is now retrieve plus
  `answer_retrieved`, behaviour and signature unchanged); `app.csf.check_outcome` drops statement passages before
  stance. No prompt changes; no questionnaire label can change, so no re-recording.
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
- 2026-10-06: csf unit added (Plan 6A, lead's OK under rule 10): framework, built-in questionnaire, per-part checks
  (`check_parts`, `part_label`, `combine`, `explain`, `aggregate`) and `ask_queue`. No existing signature changed
  beyond the Ruling 9 entry above.
- 2026-10-06: Plan 6A merged onto Plan 3 (final review I2; an added enum value, allowed after the HTTP freeze):
  `DroppedOut.reason` is typed as `contracts.DropReason`, so it gains `"statement"`, and the evidence drawer's
  sentence table covers every `DropReason` (a test pins it). No path, field or status changed; no prompt changed.
- 2026-10-06: Plan 6B Task 1 (added paths, optional fields and one status, allowed after the freeze; lead's OK
  under rule 10 for the `csf` row): `GET /api/gap/{scope}`, `POST /api/gap/{scope}/run`, `GapOut`, `GapRow`,
  `PartOut`, `AnswerDetail.parts`, `SuggestionOut.part`; a gap-check run's export is 200 (was 409); migration
  `c4e8a2d6f1b3` (`run_items.parts`, `suggestions.part`). The `csf` row gains `current_mapping`, `check_part`,
  `part_result` and `CONTROLS_URL`. No prompt or label changes, so nothing is re-recorded.
- 2026-10-06: Plan 6B Task 1, preflight M5 and I3: a `runs` row records `STEP_PARTS`, `outcome_values` and
  `reopen_changed` for Tasks 3-4 (only these names of `app/runs.py` are contract); when `SuggestionOut.part` is
  above 0, its `question` is that part's wording (Task 4), not the outcome's.
- 2026-10-06: Plan 6B Task 1 fix round 1 (an added optional field and wording; lead's OK, Ruling 4, under rule 10
  for `retrieve`): `GapRow.not_applicable` (bool, default false; adversary-1 I1). `app.retrieve.retrieve` gains
  an optional `exclude_kinds=()` (Task 4; the default keeps today's candidates, so no prompt, label or replay
  changes and nothing is re-recorded). Recorded for the lane tasks (adversary-1 as ruled): a step checks its
  deadline before each unstored part and releases a cut-off outcome with its parts kept (Task 2); a failed
  outcome carries no gap label (Task 3) and is re-opened by Check again (Task 4); two first presses answer one run
  (Task 3); accepted per-part fills read Confirmed by you, evidence is compared as sets and per-part fills survive
  a re-open (Task 4). The 6A statements dropped by Task 1 (`source` `csf`, `ItemOut.csf_id`, the seam) are
  restored; "`GET /api/questionnaires` lists built-in questionnaires" stays out (it never did).
- 2026-10-06: Plan 6B Task 3 (an added sheet, no path, field or status changed): an xlsx questionnaire export
  carries the workspace's latest done gap check as a `Gap report` sheet (a free name when the file has one,
  compared case-insensitively), every cell inert; with no done gap check, or for a csv, the export is unchanged
  (Tarun, 2026-10-06).
  Bulk approve (`approve-verified`) skips a gap check's Not met outcomes (adversary-1 N3, Ruling 4; the lead).
- 2026-10-06: Plan 6B Task 4 (an added optional argument and wording; lead's OK, Rulings 4 and 6, under rule 10
  for `csf` and `retrieve`): `csf.explain` gains an optional `filled=()` (the part numbers filled from the
  visitor's answer, named first as "Confirmed by you: part n"); `retrieve(..., exclude_kinds=())` is in place and
  `csf.evidence` passes `("statement",)`, so a statement is no longer a `statement` drop but never a candidate
  (the questionnaire path is unchanged). The gap bullet's Confirmed-by-you sentence follows Ruling 6 (Task 1
  re-review R1). No prompt or label rule changes, so nothing is re-recorded.
- 2026-10-06: Plan 6B Task 4 fix round 1 (an added optional argument; lead's OK, Ruling 11, under rule 10 for
  `runs`): `reopen_changed` gains `models=None` (the deployed models a part's judge is compared with;
  `POST /api/gap/{scope}/run` passes the settings' models, the default is the run's own), so a model change
  re-opens an outcome once, not on every press. Check again and re-decide also take a Checked outcome that reads
  Confirmed by you through a part fill: its document-judged parts are checked and decided again, its filled parts
  kept. `retrieve`'s `exclude_kinds` also applies to the record hop. No prompt or label rule changes.
- 2026-10-06: Plan 6B adversary checkpoint 2 fix (lead's OK, Ruling 12, under rule 10 for `retrieve` and `csf`):
  `retrieve`'s `exclude_kinds` becomes `exclude_sources` and keys on `Document.source` (I1); its documents also
  count in neither the IDF (`ts_stat`) nor the chunk total, nor the hop's chunk count (I2). The default `()` is
  unchanged, so no questionnaire prompt, label or replay moves. `PATCH /api/documents/{id}` on a statement is a
  409 (I1, M7). `csf.explain` names a filled part "Confirmed by you" only when the part is Covered; any other
  filled part reads "<label words> in your answer" (M2). `PATCH /api/answers/{id}` and `POST
  /api/answers/{id}/approve` on a gap check's outcome are a 409, and `approve-verified` skips every gap check
  outcome (M5, M6). `GET /api/runs/{id}/export` on a gap run that is not done is a 409 (M3).
  `AnswerSummary.sources` for Confirmed by you counts the cited documents, at least 1 (M2). No prompt or label
  rule changes, so nothing is re-recorded.
- 2026-10-06: Plan 6B final review fix (Ruling 14; copy and mapping only, the label id `confirmed_by_you` and the OpenAPI schema are unchanged): an Ask-me outcome the visitor answered reads "Answered by you" (view chip, drawer, sheet via `csf.gap_word`) and stays in the review set; "Confirmed by you" is only for a Checked outcome made Covered by accepted fills (Ruling 6). The failed sheet word is "Failed" (stale "Not run yet" fixed). No prompt or label rule changes, so nothing is re-recorded.
- 2026-10-07: Plan 4 Task 2 (behaviour inside existing statuses; no path, field or status changed): a step answers
  its claimed items, or a gap check's parts, at the same time, each job on its own session, spender and cost meter;
  it spends before every model call and holds no transaction across one. Every claimed item is settled in
  questionnaire order: items that ran beside a refused, outage-hit or missing-recording item are written, not given
  back (they were paid), and an item whose write fails stays claimed while the others are still written. After the
  writes it raises ReplayMiss, then a refused budget, then an unexpected error, then the 503 when no model job
  answered (a row written with no model call, Failed at the attempt limit or an Ask-me outcome, does not count).
  When a model job answered, each item that met an outage keeps its attempt; when none did, only the first item
  that met it keeps its attempt and the others are refunded (Ruling 5), so a true outage costs at most one attempt
  a step and items the provider always fails still end Failed. A 429 is retried once after a short pause
  (Retry-After plus up to 0.5 s of jitter, at most 2 s; 1 s to 1.5 s without one). Whether the deadline cut a retry
  is decided when the retry is refused, not at settlement. A failed outcome now pays for each of its parts, since
  they run at once. A step answers by 270 s whatever the provider does; a job still running then goes back with its
  attempt counted, its cost is not added to the run (it may still spend, counted in every cap), and a part it
  stores later lands on no row (the write is guarded by the step's claim).
