# VART v2 — Progress Log

_Last updated: 2026-10-05 · Branch: `main` (origin: https://github.com/Ttheegela/VART-v2, public) · Live: https://vart-v2.vercel.app_

## At a glance
| Plan | Status | Notes |
|---|---|---|
| 1A Foundation | done, live 2026-10-04 | schema, workspaces, LLM client, health + canary, React shell, CI, gates |
| 1B Dev data | done | fact sheet, questionnaires, documents, keys |
| 2 Engine and evals | done (branch `plan2`; release waits for Tarun's OK) | engine, ingest, evals; baseline label accuracy 0.9213, recall@8 0.9738, cost $0.0361 per 60 items |
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
| Daily crons (cleanup 05:00 UTC, canary 17:00 UTC) | ok: `/api/health` at 19:58 UTC on 2026-10-05 showed `"status":"ok"` and the canary ok at 17:59 UTC that day (the canary cron ran; Hobby crons fire within their hour). The cleanup cron leaves no mark in `/api/health` |
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
| 2026-10-04 | Plan 2 models: every default comes from the model pool (cheap Chinese or open-weight OpenRouter models with structured outputs); Claude Sonnet 5.5 is only the bench's quality reference. A pick is the cheapest pool model that passes every gate and is within 0.02 of Sonnet 5.5, approved by Tarun; the starting defaults are Qwen and DeepSeek models (spec 6.14, 8) |
| 2026-10-04 | Plan 2 gates tighten after the baseline to max(spec value, baseline - 0.02) (spec 8) |
| 2026-10-04 | Redaction covers visitors' own interview answers too (names and emails become tokens), the same way as uploads (spec 9) |
| 2026-10-04 | Place names and cloud regions stay unredacted, because data-residency answers need them (spec 9) |
| 2026-10-04 | Presidio and spaCy `en_core_web_sm` ship in the Vercel function bundle; before the release the lead checks the function size on a `vercel deploy` preview, because Git previews are off for every branch except `main` (spec 10) |
| 2026-10-04 | Vectors are tried only if the real baseline's recall@8 is below 0.95, and kept only if they raise it by at least 0.05 (spec 6.5) |
| 2026-10-04 | Plan 2 runs three lanes in parallel, each in its own worktree: engine (Opus 5.5), ingest (Sonnet 5.5), evals (Sonnet 5.5) |
| 2026-10-04 | Eval key `VART_EVAL_OPENROUTER_API_KEY` lives in `~/.config/vart/eval.env` (mode 600, outside every repo, $5 credit limit); the lead, or an agent it names, runs recordings and the bench with it without asking Tarun, spending past the cap needs him, and the production key stays in Vercel only (spec 8) |
| 2026-10-04 | Plan 2 integrates on branch `plan2` (worktree `VART-wt-plan2`), so `main` stays production: the lead merges lanes into it locally; pushing and the release (PR to `main`, fast-forward after green CI, deploy) need Tarun's OK (spec 11.3-11.5) |
| 2026-10-05 | Tarun: the conflict gate counts planted conflict traps, as spec 8 says (5 in the dev pack), not keyed items; a trap is caught when at least one of its items is labelled conflict, and the date rule is gated per planted date trap the same way. The per-item numbers stay in the report, ungated (spec 8) |
| 2026-10-05 | Tarun: no faster mode; every Plan 2 task keeps the full process (implementer, review, fix rounds) |
| 2026-10-05 | Tarun: design direction C (console) for the UI; it is locked on branch `design` and waits for Plan 3 |
| 2026-10-05 | Tarun accepted the Plan 2 baseline (15/15 gates). Known issues, reported and not gated: false verified No answers and false conflicts (conflict precision 0.8571), scope notes on 1 of 3 scope traps, per-item conflict recall 0.8571 and date-rule items 0.75 |
| 2026-10-05 | Models per step from the bench, approved by Tarun: stance deepseek/deepseek-v4-pro, draft z-ai/glm-5.3-flash (reasoning at its lowest effort), judge qwen/qwen3.7-plus; classify stays deepseek/deepseek-v4-flash and recheck uses the stance model (spec 6.14) |
| 2026-10-05 | Retrieval is full-text only: recall@8 0.9738; vectors are tried only below 0.95 and kept only if they add 0.05 (not tried) (spec 6.5) |
| 2026-10-05 | Gates set from the baseline (`evals/score.py`): label accuracy 0.90, recall@8 0.95, judge faithfulness 0.95; every other gate stays at its spec value. CI replays the dev pack, fails on a missed gate or on drift in `evals/results`, and holds decide at 100% branch coverage |
| 2026-10-05 | Sample packs are not redacted; uploads and visitor answers are; citations quote the stored line (Plan 1A Ruling 10) - SECURITY.md (Plan 4) must say so |
| 2026-10-05 | `ops/setup.sh migrate` brings production to alembic head before `main` moves, because Vercel's Git integration deploys `main` at once (spec 10) |
| 2026-10-05 | Tarun: a Jev (TypeSafe) spike runs after the Plan 2 baseline: a throwaway sentence-selection stance measured against the current one, with no contract change and no merge; its output is a recommendation |
| 2026-10-05 | Tarun approved the CSF 2.0 gap check design and Plan 6A (backend and evals), on branch `spec-csf-gap` |

## How to run
See `CLAUDE.md` (commands) and `README.md`.
