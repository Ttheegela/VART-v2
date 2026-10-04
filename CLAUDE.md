# VART v2 — map for agents

Fills vendor security questionnaires from a company's own documents with cited answers whose labels are decided by
code, not by the model. Spec: `docs/superpowers/specs/2026-10-03-vart-v2-design.md`. Plans: `docs/superpowers/plans/`.
Progress and decisions: `docs/PROGRESS.md`.

## Hard rules (each one has a check that fails)
1. Never open, copy or quote anything under `~/Desktop/portfolio/projects/ai-money-hackathon/` (sponsor-confidential).
   Check: `scripts/sponsor_check.sh` in CI.
2. No verified or partial answer without a citation. Check: database constraint `ck_answers_cited`.
3. Tests never touch the network or real keys. Check: CI has no keys; use `tests/fakes.py` and `httpx.MockTransport`.
4. Monochrome UI: black, white, `neutral-*` only. Check: `scripts/check_monochrome.py`.
5. No secrets in files or commits. Check: gitleaks in CI.
6. Frontend API types are generated from the backend. Check: drift of `openapi.json` and `web/src/lib/api-types.ts`.
7. Edit only the files your task owns. The same failure twice: stop and report. Never weaken a test.
8. Commit trailer, exactly: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## Map
- `app/` FastAPI: `settings.py`, `text.py` (quote + record-line rules), `db/`, `api/`, `services/`, `llm/`, `observability.py`, `main.py`
- `migrations/` Alembic. Production migrations run from Tarun's terminal, never in the build.
- `web/` React + Vite + TypeScript + Tailwind v4; builds into `../public`, which FastAPI serves.
- `datakit/` dev-data tools (schemas, renderers, key derivation, validators). `data/` questionnaires, company packs, keys.
- `scripts/` sponsor_check, check_monochrome, export_openapi, smoke. `tests/` pytest (needs Postgres).

## Commands
- `docker compose up -d db` — Postgres 17 + pgvector on port 5434 (user/password `vart`).
- `export TEST_DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test` (lanes use `vart_test_<lane>`).
- Backend: `ruff check . && ruff format --check . && mypy app scripts && pytest -q && alembic check`
- Frontend: `cd web && npm run lint && npm test && npm run build`
