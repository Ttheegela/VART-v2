# Runbook

How to release, roll back, read an alert, re-record the evals and keep costs down for https://vart-v2.vercel.app.
Parts: [`ARCHITECTURE.md`](ARCHITECTURE.md). What is stored and sent where: [`SECURITY.md`](SECURITY.md).

Conventions: run commands from the repository root with the virtual environment active. Production secrets live in
Vercel; steps that need one run in Tarun's own terminal through the script's hidden prompts, and a value is never
pasted into a file, a commit, an issue or a chat.

## Release
1. Open a pull request from the work branch to `main`; wait for green CI (gates, backend, frontend, end-to-end).
2. Check the function size on a CLI preview (below).
3. Tarun runs `ops/setup.sh migrate` (migrations never run in the build).
4. Fast-forward `main` to the pull request's head. Vercel deploys `main`. Migrate and deploy while no run is mid-step
   (a quiet moment on the demo): a step that straddles the switch can meet the old code or schema halfway.
5. `python scripts/smoke.py https://vart-v2.vercel.app` prints one `ok:` line, or one `FAIL: <check>: <reason>` line.
6. Check `/api/health` (`"status":"ok"`) and, after the next 17:00 UTC run, the canary.
7. Safari check on the Mac and on an iPhone (below).

## Migrations
Additive first (a new column or table), from Tarun's terminal against a Neon branch before production, never in the
build. A risky one runs back to back with the deploy. Run `ops/setup.sh migrate` before `main` moves, so the code
that needs the change never meets a database without it.

## Rollback
Promote the previous deployment in Vercel (Deployments, the earlier one, Promote to Production). Never downgrade an
additive migration (the old code ignores the column); roll a risky one back together with the deploy.

## Alerts and what to do
| Signal | Meaning | Do |
|---|---|---|
| `/api/health` `degraded`, canary failed | a model id is retired or a provider fails | read `/api/health` for the failing model; change the model variable in Vercel, re-record the evals, regenerate the sample snapshot, release |
| `/api/health` `degraded`, low credit | OpenRouter balance under $2 | top up the production key (Tarun) |
| `/api/health` `degraded`, canary old | the 17:00 UTC cron stopped | check Vercel Crons; run `/api/internal/canary` once with the cron secret |
| `/api/health` 503 | the database is unreachable | check Neon; it wakes on the next request |
| 503 "the demo is full" | the storage breaker: the database is near its size limit | wait for the sweeps, or run the cleanup once; look at Neon storage |
| smoke `FAIL: sample` | the deployed models or data differ from the sample snapshot | a model variable changed without a re-recording: restore it, or re-record, regenerate and release |
| a run that never finishes | its steps stopped | after 10 minutes the run counts as abandoned; the visitor presses `r`: a questionnaire gets a new run, a gap check resumes |
| 429 on every step after a long provider outage | each step's retries spent the workspace's stance calls: a long outage exhausts the 150-an-hour stance cap in about 20 to 25 minutes | nothing to fix: steps answer 429 until the hour turns, then the run goes on |

## Known limits
- `create_run` and `copy_questionnaire_run` (`app/runs.py`, `app/sample_run.py`) lock the questionnaire row and then
  want the workspace row, while a workspace reset locks the workspace and its cascade wants the questionnaire: a
  start and a reset at the same instant can deadlock. Postgres aborts one of them, the visitor sees an error and
  repeats the action. Accepted for a demo (adversary-1 M12, adversary-2 M1).
- A database error (`SQLAlchemyError`, such as a dropped Neon connection) inside a step's worker marks that answer
  FAILED ("the model call failed twice") with no model call made and no attempt left. A step opens up to nine
  NullPool connections, so it is likelier than before concurrent steps (adversary-2 M10). Not fixed: the fix is to
  treat it like a provider outage (give the item back, attempt kept).

## The sample snapshot
`python scripts/sample_snapshot.py` rebuilds it from the eval recordings; no key is needed. A CI test fails when the
committed file differs, so regenerate and commit it after any change to a recording, prompt, model, engine or sample
data.

## Re-recording the evals and the end-to-end tests
The commands are in `CLAUDE.md`; they use the eval key from `~/.config/vart/eval.env` (mode 600, $5 credit limit),
never the production key, and never print it. After a re-recording, regenerate the sample snapshot and run
`python -m evals.run --pack dev` (and `--pack gap-dev` and `--pack holdout`) with no network to confirm the results file does not drift.

## Rotating a secret
`ops/setup.sh accounts --replace NAME` (for example `OPENROUTER_API_KEY`), in Tarun's terminal, then redeploy so the
function sees it.

## Size check on a CLI preview
`npx vercel deploy` (without `--prod`) makes a preview; the build output shows the Python function's size (it was
about 72 MB at the last check). The preview sits behind Vercel Authentication, which is fine
for reading the build output. CLI previews have no database (Decision 14), so only `/` and the size are checked there.

## Costs to watch
Neon compute hours (the monitors wake it about 24 times a day, estimated at about 15 hours a month of the 100 free; confirm on Neon's usage page after launch), Neon storage,
Vercel function usage and the OpenRouter balance. The default sample path spends no model credit.

## Which browsers are tested
Chromium-based browsers (Chrome, Brave, Comet, Edge) are covered by the Chromium tests. Safari is covered by the
WebKit tests (the smoke test and the sample flow) and by Tarun's manual check at each release, on the Mac and on an
iPhone: the sample flow, Enter on the Workspace dropdowns, and the drawer full screen under 900 px. Firefox is
untested. To run the WebKit project locally: `npx playwright install webkit` once (about 80 MB), then run the
Playwright suite with the WebKit project.
