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
| stance | `app/stance.py` (2A) | `PROMPT_VERSION = "stance@p1"`; `user_prompt(item, passages) -> str`; `stance(llm, item, passages, model, step="stance") -> tuple[Stance, ...]` | yes |
| decide | `app/decide.py` (2A) | `decide(passages, stances, dropped=()) -> Decision` | no |
| draft | `app/draft.py` (2A) | `PROMPT_VERSION = "draft@p1"`; `plain_name(filename: str) -> str`; `user_prompt(item: ItemInput, decision: Decision) -> str`; `check(text, decision, documents) -> list[str]`; `template_answer(decision) -> str`; `write_draft(llm, item, decision, model, spend, documents) -> Draft` | yes |
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

## Change log

- 2026-10-04: frozen (Plan 2A Task 2).
