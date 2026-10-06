# VART v2 — map for agents

Fills vendor security questionnaires from a company's own documents with cited answers whose labels are decided by
code, not by the model. Spec: `docs/superpowers/specs/2026-10-03-vart-v2-design.md`. Plans: `docs/superpowers/plans/`.
Progress and the decisions table: `docs/PROGRESS.md`. The detailed per-task ledgers are local (git-ignored
`.superpowers/`), not in the repo; what they changed is in the spec and each plan's "Execution notes".

## Hard rules (each gets a check that fails; the checks land with Plan 1A Tasks 2, 6, 7 and 8)
1. Never open, copy or quote anything under `~/Desktop/portfolio/projects/ai-money-hackathon/` (sponsor-confidential).
   Check (CI only, a name scan; the rule is wider than the check): `scripts/sponsor_check.sh` (Task 7).
2. No verified or partial answer without a citation. Check: database constraint `ck_answers_cited` in the migration,
   pinned to `models.py` by `test_migrated_check_constraints_match_the_models` (Task 2); the real guarantee for what
   a quote says is decide's containment check.
3. Tests never touch the network or real keys. Check: pytest-socket blocks non-localhost Python-socket
   connections (httpx, openai clients); use `tests/fakes.py` (Task 4) and `httpx.MockTransport`.
4. Monochrome UI: black, white, `neutral-*` only. Check: `scripts/check_monochrome.py` (Task 7).
5. No secrets in files or commits. Check: gitleaks in CI (Task 8).
6. Frontend API types are generated from the backend. Check: drift of `openapi.json` and `web/src/lib/api-types.ts` (Tasks 6 and 8).
7. Edit only the files your task owns. The same failure twice: stop and report. Never weaken a test. (review; no automated check)
8. Commit trailer, exactly, regardless of which model commits: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
   (review; no automated check)
9. `app/text.py` is frozen after adversary checkpoint 1. Changing it means recomputing the pinned digest in
   `tests/test_text.py`, re-deriving the eval keys and re-recording evals. Check: `test_normalize_is_pinned`.
10. `app/contracts.py`, `app/patterns.py` and the signatures in `docs/CONTRACTS.md` are frozen after Plan 2's
    adversary checkpoint 1: a change needs the lead's OK, a change-log line in `docs/CONTRACTS.md`, and a
    re-recording when a prompt or a label can change. (review; no automated check)
11. Engine code spends the budget before every model call (`app.services.llm_budget.spender`) and never holds a
    database transaction across one. Check: `tests/test_pipeline.py::test_no_transaction_is_open_while_a_model_runs`
    (Plan 2A Task 8).

## Map
- `app/` FastAPI: `settings.py`, `text.py` (quote + record-line rules), `db/`, `api/`, `services/`, `llm/`, `observability.py`, `main.py`
- `migrations/` Alembic. Production migrations run from Tarun's terminal, never in the build.
- `web/` React + Vite + TypeScript + Tailwind v4; builds into `../public`, which FastAPI serves. Only `/` and
  `/api/*` exist in production (Vercel serves `public/` from the CDN; other paths are FastAPI's JSON 404), so the UI
  routes by query string.
- `datakit/` dev-data tools (schemas, renderers, key derivation, validators). `data/` questionnaires, company packs, keys.
- `scripts/` sponsor_check, check_monochrome, export_openapi, smoke. `tests/` pytest (needs Postgres).
- `ops/` `setup.sh` runs the infrastructure phases (accounts, release, migrate, uptime, status). Tarun runs it in his
  terminal; secrets go only through its hidden prompts.
- Engine (Plan 2): `app/contracts.py` (frozen unit types; signatures in `docs/CONTRACTS.md`), `app/patterns.py`,
  `app/ingest/` (parse, pdf, store), `app/redact.py`, `app/classify.py`, `app/chunk.py`, `app/retrieve.py`,
  `app/stance.py`, `app/decide.py`, `app/draft.py`, `app/grounding.py`, `app/pipeline.py` (`answer_item`),
  `app/interview.py`, `app/csf.py` (CSF 2.0 gap check: framework, built-in questionnaire, per-part checks,
  gap labels).
- `data/csf/` NIST CSF 2.0 extract, `tiers.yaml`, built `csf-2.0.json` (`python -m datakit.csf build`);
  `data/dev/gap/` the gap check's fact-sheet extension (`python -m datakit.gap dev`).
- `evals/`: `run.py` (harness), `gap.py` (the `gap-dev` pack), `score.py` (metrics, gates), `bench.py` (model bench), `recorded/` (replayed model
  outputs), `results/` (committed results; CI fails on drift).

## Commands
- `docker compose up -d db` — Postgres 17 + pgvector on port 5434 (user/password `vart`).
- `export TEST_DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test && export DATABASE_URL=$TEST_DATABASE_URL`
  (lanes use `vart_test_<lane>`). pytest reads `TEST_DATABASE_URL`; `alembic check` and the app read `DATABASE_URL`.
- Backend: `ruff check . && ruff format --check . && mypy app scripts datakit evals && pytest -q && alembic check`
- Frontend: `cd web && npm run lint && npm test && npm run build`
- Gates: `python scripts/check_monochrome.py` (the sponsor check is CI-only: it needs the secret)
- Dev data: `python -m datakit.validate all` (stages: facts, docs, questionnaires, keys, mapper)
- Evals, no network: `python -m evals.run --pack dev` and `python -m evals.run --pack gap-dev` (label_accuracy is
  reported there, not gating). Recording (`--mode record|live`) and `python -m evals.bench`
  use the eval key, never the production key. The lead, or an agent it names, runs them without asking Tarun, never
  prints the key, and asks before spending past its $5 cap:
  `(set -a; . ~/.config/vart/eval.env; set +a; OPENROUTER_API_KEY="$VART_EVAL_OPENROUTER_API_KEY" python -m evals.run --pack dev --mode record)`
