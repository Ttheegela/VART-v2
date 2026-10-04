# VART v2 — Progress Log

_Last updated: 2026-10-04 · Branch: `main` (origin: https://github.com/Ttheegela/VART-v2, public) · Live: https://vart-v2.vercel.app_

## At a glance
| Plan | Status | Notes |
|---|---|---|
| 1A Foundation | done, live 2026-10-04 | schema, workspaces, LLM client, health + canary, React shell, CI, gates |
| 1B Dev data | done | fact sheet, questionnaires, documents, keys |
| 2 Engine and evals | not started | |
| 3 API and UI | not started | |
| 4 Hardening and launch | not started | |
| 5 Google Drive | not started | |

## Releases
### Plan 1 — 2026-10-04
- `main` = `f26ae27`, merged by PR #1 after green CI: backend 522 tests, frontend 18 tests, 1 e2e test, gates (gitleaks over
  the full history, sponsor check, monochrome).
- `ops/setup.sh release`: Neon migrated to `186f3400ded0`, fresh `CRON_SECRET`, Git connected (production branch `main`),
  production deployed; the smoke test, the canary (all three models ok) and `/api/health` (`"status":"ok"`) passed.
- Live: https://vart-v2.vercel.app (Vercel also assigned https://vart-orpin.vercel.app). The page shows the status panel;
  the questionnaire workspace arrives with Plans 2 and 3.
- Monitors (UptimeRobot, email alerts): HTTP on `/` every 5 min (served by the CDN, so the database stays asleep) and a
  keyword check for `"status":"ok"` on `/api/health` every 60 min.

| Release check | Result |
|---|---|
| Fluid compute | on (region iad1, next to Neon in us-east-1; default timeout 300 s) |
| Live canary | ok for all three models within the release script's 180 s limit; no `length` finish |
| Daily crons (cleanup 05:00 UTC, canary 17:00 UTC) | pending: the canary time in `/api/health` after 17:00 UTC on 2026-10-05 |
| Vercel builds only `main` | ok: the push of this record's PR branch made no deployment (2026-10-04) |

## Decisions
This table is the decisions log kept in the repo. The detailed per-task review rulings are in the lead's local ledgers,
which are not in the repo; the ones that changed the spec or a plan are written into that document (the spec, and each
plan's "Execution notes").

| Date | Decision |
|---|---|
| 2026-10-03 | Stack copied from PriorPath v2; VART gets its own Vercel project and Neon project |
| 2026-10-03 | Unit contracts are frozen at the start of Plan 2, the HTTP contract at the start of Plan 3 (each with an adversary review); Plan 1 freezes only the shared text rules and data schemas |
| 2026-10-04 | Production domain `vart-v2.vercel.app` (`vart.vercel.app` was taken); a release goes through a PR with green CI, then `main` is fast-forwarded to it |
| 2026-10-04 | Monitors keep the demo alive without keeping Neon awake: `/` every 5 min, `/api/health` every 60 min |

## How to run
See `CLAUDE.md` (commands) and `README.md`.
