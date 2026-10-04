# VART v2 — Progress Log

_Last updated: 2026-10-03 · Branch: `main` (local; no remote yet) · Live: not yet deployed_

## At a glance
| Plan | Status | Notes |
|---|---|---|
| 1A Foundation | in progress | schema, workspaces, LLM client, health + canary, React shell, CI, gates |
| 1B Dev data | in progress | fact sheet, questionnaires, documents, keys |
| 2 Engine and evals | not started | |
| 3 API and UI | not started | |
| 4 Hardening and launch | not started | |
| 5 Google Drive | not started | |

## Decisions
| Date | Decision |
|---|---|
| 2026-10-03 | Stack copied from PriorPath v2; VART gets its own Vercel project and Neon project |
| 2026-10-03 | Unit contracts are frozen at the start of Plan 2, the HTTP contract at the start of Plan 3 (each with an adversary review); Plan 1 freezes only the shared text rules and data schemas |

## How to run
See `CLAUDE.md` (commands) and `README.md`.
