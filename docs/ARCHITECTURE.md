# Architecture

How VART v2 is put together: the parts, what one fill run does, and where it runs. What is stored and sent where is
in [`SECURITY.md`](SECURITY.md); how to operate it is in [`RUNBOOK.md`](RUNBOOK.md); the exact function signatures are
in [`CONTRACTS.md`](CONTRACTS.md).

VART fills a vendor security questionnaire from a company's own documents. Each answer carries a label and a quote
from a document. The label is decided by code, never by the model; the model only reads passages and drafts words.

## The pieces

| Module (`app/`) | One job | Calls a model? |
|---|---|---|
| `settings.py`, `text.py` | settings; the frozen rules for matching a quote to a line and for writing a record line | no |
| `db/`, `services/` | tables; signed-cookie workspaces, budgets, per-network limits, audit log, 24-hour expiry, storage breaker, canary | no |
| `ingest/` (`parse`, `pdf`, `store`) | parse files into numbered lines; spreadsheet rows become dated records; store them in one transaction | no |
| `redact.py` | names, emails, phones, addresses and secrets replaced before storage and before any model call | no |
| `classify.py` | document metadata (kind, status, date, scope, usable as evidence): rules first, a model only when unsure | fallback only |
| `chunk.py` | heading-aware passages over line ranges, one passage per record row, chunk flags (negation, placeholder, injection) | no |
| `retrieve.py` | Postgres full-text search, rank fusion, a cap per document, a hop to related records | no (no vectors) |
| `stance.py` | one call per item: each passage says yes, no, partial or irrelevant, with an exact quote | yes |
| `decide.py` | pure rules that turn stances into label, value, citations, conflict and confidence | no |
| `draft.py`, `grounding.py` | one or two plain sentences from the surviving evidence; a code check of quotes, names and numbers | yes |
| `pipeline.py` | `answer_item`: retrieve, stance, decide, draft, check, for one item | orchestrates |
| `interview.py`, `redecide.py` | the "Questions for you" queue, follow-ups, re-checking related items against a visitor's answer | re-check only |
| `csf.py`, `api/gap.py` | the gap check: a company's controls against NIST CSF outcomes | yes |
| `questionnaires.py`, `export.py` | import with a column mapper; export written back into the visitor's own file | no |
| `runs.py` | resumable fill runs driven by a step endpoint | orchestrates |
| `llm/` | OpenRouter client with live, record and replay modes | -- |
| `observability.py` | Langfuse tracing, metadata only | -- |
| `api/` | FastAPI routes; the browser's types are generated from the OpenAPI file | -- |

`web/` is a React app (query-string routing; the console design). It builds into `public/`, which Vercel serves from
its CDN.

## The guided tour

Opening the precomputed sample run starts a ten-step tour in the browser: what VART does, documents, the
questionnaire, the run grid, the evidence drawer, Questions for you, export, the audit log, the gap check and a note
that this is not legal advice. It starts every time the sample run opens (there is no "seen" flag), never runs on a
visitor's own data, closes when another run opens or a live gap check runs, and `t`, the Tour button or `?` starts it
again. It is browser code over the sample run's stored answers, so it makes no request of its own and spends nothing.

## One fill run

```
 browser
   |  POST /api/questionnaires/{id}/runs        create the run (409 while one is live)
   |  POST /api/runs/{id}/step   (repeat)       one step per call
   v
 step endpoint
   | 1. claim: next 4 pending items, FOR UPDATE SKIP LOCKED, short transaction, then commit
   | 2. worker pool (bound 8, one session each, outside any transaction)
   |       per item: spend budget -> retrieve -> stance -> decide -> draft -> check
   |            |                          |
   |            v                          v
   |        Postgres (Neon)           OpenRouter (model)
   | 3. settle: write answers in questionnaire order (UNIQUE (run_id, item_id) makes a repeat a no-op)
   v
 answers to the browser, which calls the step again until nothing is pending
```

1. **Create.** A new run records the prompt versions and model ids it uses. One live run per questionnaire: a second
   start answers 409. A running run no step has touched for 10 minutes (abandoned) is closed as failed when a new run
   starts or a document is deleted, so it never blocks anything.
2. **Claim.** A step claims the next pending items (4 for a questionnaire; for a gap check, outcomes until their
   parts add up to 8) with `FOR UPDATE SKIP LOCKED`, so a repeated or concurrent call never takes the same item. A
   claim older than 5 minutes (a crashed step) is reclaimed.
3. **Work at the same time.** Every claimed item (every not-yet-stored part of a claimed outcome) is one job, run by
   a pool of at most 8 workers. Each worker has its own database session and budget counter. A worker spends the
   budget before every model call and never holds a transaction open while a model runs. The budget counters are
   single atomic statements, so concurrent workers cannot spend past a cap. The speed-up is measured in Task 9:
   expected about 3 to 4 times faster than one item at a time (a 64-item run in about 3.5 minutes against about 11;
   to be measured in Task 9).
4. **Time limits.** `DEADLINE_S` (240 s) decides whether a job or a retry may start; `HARD_S` (270 s) bounds the whole
   step. A job still running at `HARD_S` is abandoned and its item goes back with its attempt counted, so a step always
   answers before Vercel's 300 s limit. An item that fails `MAX_ATTEMPTS` times is answered as failed.
5. **Settle.** Answers are written in questionnaire order, and the step returns what it finished. A provider outage
   that answered nothing is a 503 with `Retry-After`.

## The gap check

The visitor picks a NIST CSF function. Each outcome is cut into its parts (the separate things the outcome asks for);
each part is asked as a question of the company's documents through the same retrieve, stance and decide path; code
combines the parts into one label for the outcome (Covered, Partly covered, Gap, and so on). Outcomes are reviewed
through "Check again", not approved. Ask-me answers can fill open parts as suggestions.

## The precomputed sample run

"Try with a sample company" is instant and spends nothing. `scripts/sample_snapshot.py` drives the real endpoints
over the sample pack with the replay client on the eval recordings and writes a snapshot of the answers. A workspace
gets a copy when it holds exactly the sample documents with no override, upload or statement, the questionnaire is a
bundled one, and the snapshot's digest matches the deployed inputs (sample documents and questionnaires, prompt
versions, models and their reasoning settings, the CSF mapping). Otherwise the engine runs live, and "Re-run live"
always does. Two guards keep the snapshot honest: a CI test regenerates it and fails on any difference, and
`GET /api/version` reports `sample_precomputed`, which `scripts/smoke.py` checks after every deploy.

## The LLM client

One client, three modes. `live` calls OpenRouter with structured outputs (a JSON schema, strict) and
`provider.require_parameters`. `record` does the same and appends each request and reply to a JSONL file. `replay`
answers from that file and raises on a missing request, so tests and CI never touch the network. A recording's key is
the hash of the model, prompt version, messages, output schema and reasoning setting, so a changed prompt or model
fails loudly instead of reusing a stale reply. The evals, the sample snapshot and the end-to-end tests all replay the
same kind of recording.

## The database

Postgres 17 on Neon, with every table scoped to a workspace and deleted with it. Tables: `workspaces`, `documents`,
`document_lines` (the redacted text), `chunks` (with a generated full-text column), `questionnaires`, `items`, `runs`
(with the time of its last step), `run_items` (the step's work list), `answers`, `interview_questions`, `suggestions`,
`audit_events`, `llm_usage` and `ip_limits` (budget counters), `canary_runs`. Constraints carry the rules: a verified
or partial answer must have a citation; "Confirmed by you" must point at the visitor's statement; one answer per
item per run; labels come from a fixed list. Tests check that the migrated constraints match the models.

## Deployment

One Vercel project: the built UI is served from the CDN, FastAPI runs as a single function (Fluid compute, 300 s
maximum, region iad1 next to Neon in us-east-1). Neon holds the data. Two Vercel crons: cleanup (05:00 UTC) and a
canary (17:00 UTC) that makes one tiny call per configured model, reads the OpenRouter credit and sweeps expired
workspaces. UptimeRobot checks `/` every 5 minutes (CDN, no database) and `/api/health` every 60 minutes. Langfuse
traces metadata. GitHub Actions runs the gates, backend, frontend and end-to-end jobs; a release is a pull request
with green CI, then a fast-forward of `main`.
