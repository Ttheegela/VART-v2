# VART v2 — map for agents

Fills vendor security questionnaires from a company's own documents with cited answers whose labels are decided by
code, not by the model. Spec: `docs/superpowers/specs/2026-10-03-vart-v2-design.md`. Plans: `docs/superpowers/plans/`.
Progress and decisions: `docs/PROGRESS.md`.

## Hard rules (each gets a check that fails; the checks land with Plan 1A Tasks 2, 6, 7 and 8)
1. Never open, copy or quote anything under `~/Desktop/portfolio/projects/ai-money-hackathon/` (sponsor-confidential).
   Check (CI only, a name scan; the rule is wider than the check): `scripts/sponsor_check.sh` (Task 7).
2. No verified or partial answer without a citation. Check: database constraint `ck_answers_cited` (Task 2); the
   real guarantee for what a quote says is decide's containment check.
3. Tests never touch the network or real keys. Check: pytest-socket blocks every non-localhost connection; use
   `tests/fakes.py` (Task 4) and `httpx.MockTransport`.
4. Monochrome UI: black, white, `neutral-*` only. Check: `scripts/check_monochrome.py` (Task 7).
5. No secrets in files or commits. Check: gitleaks in CI (Task 8).
6. Frontend API types are generated from the backend. Check: drift of `openapi.json` and `web/src/lib/api-types.ts` (Tasks 6 and 8).
7. Edit only the files your task owns. The same failure twice: stop and report. Never weaken a test. (review; no automated check)
8. Commit trailer, exactly, regardless of which model commits: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
   (review; no automated check)
9. `app/text.py` is frozen after adversary checkpoint 1. Changing it means recomputing the pinned digest in
   `tests/test_text.py`, re-deriving the eval keys and re-recording evals. Check: `test_normalize_is_pinned`.

## Map
- `app/` FastAPI: `settings.py`, `text.py` (quote + record-line rules), `db/`, `api/`, `services/`, `llm/`, `observability.py`, `main.py`
- `migrations/` Alembic. Production migrations run from Tarun's terminal, never in the build.
- `web/` React + Vite + TypeScript + Tailwind v4; builds into `../public`, which FastAPI serves.
- `datakit/` dev-data tools (schemas, renderers, key derivation, validators). `data/` questionnaires, company packs, keys.
- `scripts/` sponsor_check, check_monochrome, export_openapi, smoke. `tests/` pytest (needs Postgres).

## Commands
- `docker compose up -d db` — Postgres 17 + pgvector on port 5434 (user/password `vart`).
- `export TEST_DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test && export DATABASE_URL=$TEST_DATABASE_URL`
  (lanes use `vart_test_<lane>`). pytest reads `TEST_DATABASE_URL`; `alembic check` and the app read `DATABASE_URL`.
- Backend: `ruff check . && ruff format --check . && mypy app scripts && pytest -q && alembic check`
  (until `scripts/` and `migrations/` exist: `mypy app`, and skip `alembic check`)
- Frontend: `cd web && npm run lint && npm test && npm run build`
