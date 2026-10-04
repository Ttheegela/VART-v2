# VART v2 — Plan 1A: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build VART v2's production base from PriorPath's proven patterns — settings, a Postgres schema whose constraints enforce the honesty rules, cookie workspaces with budgets and per-IP limits, an OpenRouter client with record/replay, Langfuse tracing, a health check and daily model canary that keep the demo "alive, not awake", a monochrome React shell with generated API types, CI with checks that fail on broken rules — and ship a hello-world deploy.

**Architecture:** One FastAPI app (`app/`) serves the API and the built React UI (`web/` → `public/`) from one Vercel project, backed by a Neon Postgres project of its own. All model calls go through one `LLMClient` protocol with three interchangeable implementations: OpenRouter (live), a recorder (live + write JSONL), and a replayer (JSONL only, never the network). Rules that must never break are written in `CLAUDE.md` *and* enforced by a check that fails: database CHECK constraints, a sponsor-name scan, a colour scan, OpenAPI type drift, gitleaks.

**Tech Stack:** Python 3.12, FastAPI 0.142+, Pydantic 2 + pydantic-settings, SQLAlchemy 2 + Alembic, psycopg 3, Postgres 17 (pgvector image), openai SDK → OpenRouter, Langfuse SDK, itsdangerous, httpx; React 19 + Vite 8 + TypeScript 6 + Tailwind v4, oxlint, Vitest, Playwright, openapi-typescript; GitHub Actions; Vercel Hobby; Neon free; UptimeRobot.

**Spec:** `docs/superpowers/specs/2026-10-03-vart-v2-design.md` — §3 hard rules, §6.1–6.2, §6.11 (schema), §6.14 (LLM client), §9 (security, limits), §10 (operations, *alive not awake*), §11 (delivery, guardrails). Companion plan: `docs/superpowers/plans/2026-10-03-vart-v2-plan1b-dev-data.md`.

## Global Constraints

- Repo: `~/Desktop/portfolio/projects/VART`. Task 1 runs on `main`. Tasks 2–8 run on branch `plan1-foundation` in worktree `~/Desktop/portfolio/projects/VART-wt-foundation` (the lead creates it). Plan 1B runs in parallel on `plan1-data`. Task 9 merges both into `main`. Nothing is pushed before Task 9.
- Every commit message ends with exactly: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (even when the worker is a Sonnet model).
- Never open, list, copy or quote anything under `~/Desktop/portfolio/projects/ai-money-hackathon/` (sponsor-confidential). Never type the sponsor's company or people names into any file.
- Python `>=3.12,<3.13`. Runtime dependencies are exactly Task 1's list; adding one needs the lead's OK.
- Tests never call OpenRouter, Langfuse or any network service. Use `tests/fakes.py::FakeLLM` and `httpx.MockTransport`.
- Test database: Postgres from `docker compose up -d db` (image `pgvector/pgvector:pg17`, port **5434**). This lane uses database `vart_test_foundation`: `docker compose exec db createdb -U vart vart_test_foundation` once, then `export TEST_DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test_foundation`. `tests/conftest.py` refuses any database whose name lacks `test`.
- Backend chain (must pass before every commit from Task 2 on): `ruff check . && ruff format --check . && mypy app scripts && pytest -q && alembic check`. Frontend chain (Task 6 on): `cd web && npm run lint && npm test && npm run build`.
- UI is monochrome: `black`, `white`, `transparent`, `current` and Tailwind `neutral-*` only. State is shown in words.
- Secrets never in files, chat or commits. `.env*` is gitignored (except `.env.example`). Tarun enters secrets in his own terminal (`read -rs`).
- Each task owns the files it lists. Touching another file needs the lead's OK; the reviewer rejects unowned edits.
- Two-failure rule: the same failure twice → stop, report, wait for the adversary review. Never weaken, skip or delete a test to get green. Three attempts on a task → hand it back to the lead.
- Outward actions (repo rename/creation, push, Vercel, Neon, UptimeRobot, secrets) happen only in Task 9, after Tarun approves the numbered release plan.

## Review Focus

1. **Cookie for a workspace that no longer exists** (deleted by the 24 h cleanup or by reset, or a tampered cookie). Expect: a new workspace and cookie, never a 500. Pinned in Task 3 (`test_cookie_for_a_deleted_workspace_starts_fresh`, `test_tampered_cookie_starts_fresh`).
2. **Health under each canary state and a dead database.** Expect: no canary yet → 200 `"status":"ok"`; last canary failed or older than 36 h → 200 `"status":"degraded"`; database down → 503 `{"status":"degraded","db":"unavailable"}`; the healthy body contains the exact bytes `"status":"ok"` (UptimeRobot keyword). Pinned in Task 5.
3. **Bursts from one network** (parallel first requests, scripted workspace creation). Expect: every concurrent IP-limit upsert is counted, nothing 500s, the over-limit request gets 429 with `Retry-After`. Pinned in Task 3 (`test_concurrent_hits_count_every_event`, `test_new_workspaces_per_ip_are_limited`).
4. **Model failure modes** (non-JSON or wrong-shape reply, truncated reply, HTTP 402 out of credits, timeout). Expect: `LLMError`, never a raw SDK exception; the canary records the failure instead of crashing. Pinned in Task 4 and Task 5.
5. **Backend schema changed without regenerating frontend types.** Expect: CI fails on drift of `openapi.json` or `web/src/lib/api-types.ts`. Pinned in Task 6 (`tests/test_openapi.py`) and Task 8 (CI steps).

## Lane gates (run by the lead)

- **Adversary checkpoint 1** (Fable 5.1) after Task 1, before the lanes split: review `app/text.py` (the quote and record-line rules every citation depends on) and `CLAUDE.md`. Findings are fixed in Task 1 before Tasks 2+ and Plan 1B start.
- **Adversary checkpoint 2** whenever the two-failure rule fires.
- **Adversary checkpoint 3** (Fable 5.1) after Task 8, before Task 9: "what attack surface or edge case did everyone miss?" over the whole `plan1-foundation` diff.
- Final Opus review of the merged `main` before Task 9's push.

---

## File Structure

```
.gitignore .python-version .env.example LICENSE README.md CLAUDE.md          NEW (Task 1)
pyproject.toml requirements.txt requirements-dev.txt docker-compose.yml      NEW (Task 1)
app/__init__.py            NEW  version
app/settings.py            NEW  pydantic-settings Settings, model defaults
app/text.py                NEW  normalize/contains/record_line — the shared text rules
app/db/session.py          NEW  engine (NullPool), database_url()
app/db/models.py           NEW  all Plan 1 tables + CHECK constraints
alembic.ini, migrations/   NEW  Alembic env + initial migration
app/api/deps.py            NEW  cookie workspace, SessionDep, WorkspaceDep, LLMDep (Task 4 adds LLMDep)
app/api/workspace.py       NEW  GET /api/workspace, POST /api/workspace/reset
app/api/internal.py        NEW  cron-only /api/internal/cleanup (+ /canary in Task 5)
app/services/{ip_limits,llm_budget,capacity,audit_log,workspaces}.py   NEW
app/observability.py       NEW  Langfuse metadata-only tracing (from PriorPath)
app/llm/client.py          NEW  LLMRequest/LLMResult/LLMClient, OpenRouterClient, strict schemas
app/llm/recorder.py        NEW  RecordingClient, ReplayClient
app/services/canary.py     NEW  daily model + credit check
app/main.py                NEW  app, FlushTraces, /api/health, /api/version, UI mount
vercel.json, .vercelignore NEW
web/                       NEW  React shell, api client, generated api-types.ts, Playwright smoke
openapi.json               NEW  generated, committed
scripts/export_openapi.py  NEW
scripts/sponsor_check.sh   NEW
scripts/check_monochrome.py NEW
scripts/smoke.py           NEW
.github/workflows/ci.yml   NEW
docs/PROGRESS.md           NEW
tests/…                    NEW  conftest, factories, fakes, one test file per unit
```

---

### Task 1: Repo scaffold, settings, shared text rules, CLAUDE.md

Runs first, on `main`, alone. Plan 1B and Tasks 2+ start after it (and after adversary checkpoint 1).

**Files:**
- Create: `.gitignore`, `.python-version`, `.env.example`, `LICENSE`, `README.md`, `CLAUDE.md`, `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `docker-compose.yml`, `app/__init__.py`, `app/settings.py`, `app/text.py`
- Test: `tests/test_settings.py`, `tests/test_text.py`

**Interfaces:**
- Produces: `app.__version__ = "2.0.0.dev0"`; `app.settings.Settings`, `get_settings() -> Settings`, `DEFAULT_MODELS: dict[str, str]`, `Settings.models() -> dict[str, str]` (keys `stance`, `draft`, `classify`, `judge`); `app.text.normalize(text: str) -> str`, `contains(haystack: str, quote: str) -> bool`, `cell_text(value: object) -> str`, `record_line(headers: Sequence[str], values: Sequence[object]) -> str`.

- [ ] **Step 1: Write the repo files**

`.gitignore`:
```gitignore
.venv/
__pycache__/
*.pyc
.env
.env.*
!.env.example
.mypy_cache/
.ruff_cache/
.pytest_cache/
.hypothesis/
/public/
web/node_modules/
web/test-results/
web/playwright-report/
.vercel
.DS_Store
evals/recorded/candidates/
```

`.python-version`:
```
3.12
```

`.env.example`:
```bash
# Copy to .env for local development. Never commit real values. The app does not load this file itself.
DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test
SESSION_SECRET=dev-secret
CRON_SECRET=dev-cron-secret
# Optional: model calls (unset = AI steps unavailable)
OPENROUTER_API_KEY=
# Optional model overrides (defaults live in app/settings.py)
# STANCE_MODEL=google/gemini-2.5-flash-lite
# DRAFT_MODEL=deepseek/deepseek-v4-flash
# CLASSIFY_MODEL=google/gemini-2.5-flash-lite
# JUDGE_MODEL=google/gemini-2.5-flash
# CANARY_MIN_CREDITS_USD=2
# Optional: Langfuse tracing (on only when both keys are set)
# LANGFUSE_PUBLIC_KEY=
# LANGFUSE_SECRET_KEY=
# LANGFUSE_BASE_URL=
```

`LICENSE` (MIT):
```
MIT License

Copyright (c) 2026 Tarun Theegela

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

`README.md` (stub; rewritten in Plan 4):
```markdown
# VART

Fills a vendor security questionnaire from a company's own documents. Every answer cites the exact passage it came
from, contradictions between documents are flagged instead of guessed, and a person is asked only what the documents
do not cover.

Status: under construction (Plan 1: foundation and dev data). Design: `docs/superpowers/specs/2026-10-03-vart-v2-design.md`.

Code is MIT-licensed. Files under `data/` carry their own licenses; see `data/NOTICE.md`.
```

`CLAUDE.md`:
```markdown
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
```

`pyproject.toml`:
```toml
# Vercel's Python builder reads [project]; keep dependencies in sync with requirements.txt.
[project]
name = "vart"
version = "2.0.0.dev0"
requires-python = ">=3.12,<3.13"
dependencies = [
    "fastapi>=0.142,<1",
    "pydantic>=2.9,<3",
    "pydantic-settings>=2.6,<3",
    "sqlalchemy>=2.0.30,<2.1",
    "psycopg[binary]>=3.2,<4",
    "openai>=1.40,<4",
    "httpx>=0.27,<1",
    "itsdangerous>=2.2,<3",
    "langfuse>=3.10,<5",
]

[tool.ruff]
line-length = 110
target-version = "py312"
extend-exclude = ["migrations/versions", "docs", "data"]

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = ["openpyxl", "openpyxl.*", "docx", "docx.*", "pypdfium2", "pypdfium2.*", "fpdf", "fpdf.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
filterwarnings = [
    "ignore:Using `httpx` with `starlette.testclient` is deprecated",
]

# UI is served from Vercel's CDN (built into public/), not bundled into the function.
[tool.vercel.fastapi.static]
exclude = true
# The trace-flush ASGI middleware would otherwise keep the frontend inside the function,
# where `exclude` removes it; promote static files to the CDN regardless (PriorPath incident 2026-10-02).
cdn = true
```

`requirements.txt`:
```
fastapi>=0.142,<1
pydantic>=2.9,<3
pydantic-settings>=2.6,<3
sqlalchemy>=2.0.30,<2.1
psycopg[binary]>=3.2,<4
openai>=1.40,<4
httpx>=0.27,<1
itsdangerous>=2.2,<3
langfuse>=3.10,<5
```

`requirements-dev.txt` (includes Plan 1B's data tools so the lanes never edit this file concurrently):
```
-r requirements.txt
pytest>=8.3
ruff>=0.6
mypy>=1.11
uvicorn>=0.30
alembic>=1.13,<2
openpyxl>=3.1,<4
python-docx>=1.1,<2
fpdf2>=2.8,<3
pypdfium2>=4.30,<6
pyyaml>=6,<7
types-PyYAML>=6
```

`docker-compose.yml`:
```yaml
services:
  db:
    image: pgvector/pgvector:pg17
    environment:
      POSTGRES_USER: vart
      POSTGRES_PASSWORD: vart
      POSTGRES_DB: vart_test
    ports:
      - "5434:5432"
```

`app/__init__.py`:
```python
__version__ = "2.0.0.dev0"
```

- [ ] **Step 2: Write the failing tests**

`tests/test_settings.py`:
```python
import pytest

from app.settings import DEFAULT_MODELS, get_settings


def test_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", "s3")
    monkeypatch.setenv("STANCE_MODEL", "acme/fast")
    monkeypatch.setenv("CANARY_MIN_CREDITS_USD", "5")
    s = get_settings()
    assert s.session_secret == "s3"
    assert s.models()["stance"] == "acme/fast"
    assert s.canary_min_credits_usd == 5.0


def test_model_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("STANCE_MODEL", "DRAFT_MODEL", "CLASSIFY_MODEL", "JUDGE_MODEL"):
        monkeypatch.delenv(name, raising=False)
    assert get_settings().models() == DEFAULT_MODELS


def test_secrets_have_no_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SESSION_SECRET", "CRON_SECRET", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    s = get_settings()
    assert (s.session_secret, s.cron_secret, s.openrouter_api_key) == ("", "", "")
```

`tests/test_text.py`:
```python
from datetime import date, datetime

from app.text import cell_text, contains, normalize, record_line


def test_normalize_straightens_quotes_dashes_and_spaces() -> None:
    assert normalize("  “Access” is reviewed — quarterly’s  ") == '"Access" is reviewed - quarterly\'s'


def test_normalize_folds_compatibility_characters() -> None:
    assert normalize("ﬁrewall") == "firewall"


def test_normalize_keeps_case() -> None:
    assert normalize("MFA") == "MFA"


def test_contains_ignores_layout_differences() -> None:
    text = "Access to production\nis reviewed   quarterly by the  Head of Security."
    assert contains(text, "is reviewed quarterly by the Head of Security")
    assert contains(text, "“Access to production is reviewed”".strip("“”"))


def test_contains_is_case_sensitive_and_rejects_empty_quotes() -> None:
    assert not contains("Access is reviewed quarterly.", "access is reviewed")
    assert not contains("Access is reviewed quarterly.", "   ")


def test_record_line_skips_empty_cells_and_formats_values() -> None:
    headers = ["System", "Owner", "Last review completed", "Users", "Notes"]
    values = ["Okta", None, datetime(2026, 1, 10), 42.0, ""]
    assert record_line(headers, values) == "System: Okta; Last review completed: 2026-01-10; Users: 42"


def test_record_line_names_missing_headers() -> None:
    assert record_line(["System"], ["AWS", "Overdue"]) == "System: AWS; Column 2: Overdue"


def test_cell_text_handles_dates_times_and_text() -> None:
    assert cell_text(date(2026, 9, 15)) == "2026-09-15"
    assert cell_text(datetime(2026, 9, 15, 13, 5)) == "2026-09-15 13:05"
    assert cell_text(3.5) == "3.5"
    assert cell_text("  On-premises file server ") == "On-premises file server"
```

- [ ] **Step 3: Run them to verify they fail**

```bash
cd ~/Desktop/portfolio/projects/VART
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/test_settings.py tests/test_text.py -q
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.settings'` / `'app.text'`.

- [ ] **Step 4: Implement**

`app/settings.py`:
```python
"""All configuration comes from environment variables. Nothing secret has a default."""

from pydantic_settings import BaseSettings, SettingsConfigDict

# Provisional defaults (PriorPath-proven model IDs); Plan 2's model bench replaces them with measured choices.
DEFAULT_MODELS = {
    "stance": "google/gemini-2.5-flash-lite",
    "draft": "deepseek/deepseek-v4-flash",
    "classify": "google/gemini-2.5-flash-lite",
    "judge": "google/gemini-2.5-flash",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str = ""
    session_secret: str = ""
    cron_secret: str = ""
    openrouter_api_key: str = ""
    stance_model: str = DEFAULT_MODELS["stance"]
    draft_model: str = DEFAULT_MODELS["draft"]
    classify_model: str = DEFAULT_MODELS["classify"]
    judge_model: str = DEFAULT_MODELS["judge"]
    canary_min_credits_usd: float = 2.0

    def models(self) -> dict[str, str]:
        return {
            "stance": self.stance_model,
            "draft": self.draft_model,
            "classify": self.classify_model,
            "judge": self.judge_model,
        }


def get_settings() -> Settings:
    # ponytail: re-reads the environment on every call (microseconds); keeps tests free to change env vars.
    # Cache it only if profiling ever shows it.
    return Settings()
```

`app/text.py`:
```python
"""Text rules shared by ingest, decide and the eval keys: how quotes are compared and how a table row becomes
one line. Every citation check depends on these, so changes here need the adversary review (Plan 1A lane gate)."""

import re
import unicodedata
from collections.abc import Sequence
from datetime import date, datetime

_TRANSLATE = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "‟": '"',
        "–": "-",
        "—": "-",
        "−": "-",
    }
)
_SPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """NFKC, straight quotes, plain hyphens, single spaces, trimmed. Case is kept."""
    return _SPACE.sub(" ", unicodedata.normalize("NFKC", text).translate(_TRANSLATE)).strip()


def contains(haystack: str, quote: str) -> bool:
    """True when the quote appears in the text after both are normalized. An empty quote never matches."""
    needle = normalize(quote)
    return bool(needle) and needle in normalize(haystack)


def cell_text(value: object) -> str:
    """How one spreadsheet or table cell reads inside a record line."""
    if value is None:
        return ""
    if isinstance(value, datetime):  # before date: datetime is a date subclass
        if value.time() == datetime.min.time():
            return value.date().isoformat()
        return value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return normalize(str(value))


def record_line(headers: Sequence[str], values: Sequence[object]) -> str:
    """One table row as one line: 'Header: value; Header: value'. Empty cells are skipped; a missing or blank
    header becomes 'Column N' (1-based)."""
    parts = []
    for i, value in enumerate(values):
        text = cell_text(value)
        if not text:
            continue
        header = normalize(headers[i]) if i < len(headers) else ""
        parts.append(f"{header or f'Column {i + 1}'}: {text}")
    return "; ".join(parts)
```

- [ ] **Step 5: Run the tests and the static checks**

```bash
pytest tests/test_settings.py tests/test_text.py -q
ruff check . && ruff format --check . && mypy app
```
Expected: all tests PASS; ruff and mypy clean.

- [ ] **Step 6: Commit**

```bash
git add .gitignore .python-version .env.example LICENSE README.md CLAUDE.md pyproject.toml requirements.txt \
  requirements-dev.txt docker-compose.yml app tests
git commit -m "chore: scaffold VART v2 with settings and shared text rules

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Database schema, first migration, test fixtures

**Files:**
- Create: `app/db/__init__.py` (empty), `app/db/session.py`, `app/db/models.py`, `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/<rev>_initial_schema.py` (generated)
- Test: `tests/conftest.py`, `tests/factories.py`, `tests/test_session.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: `app.settings.get_settings`.
- Produces: `app.db.session.database_url() -> str`, `get_engine() -> Engine`, `get_session() -> Iterator[Session]`; models `Workspace`, `Document`, `DocumentLine`, `Chunk`, `Questionnaire`, `Item`, `Run`, `RunItem`, `Answer`, `AuditEvent`, `LlmUsage`, `IpLimit`, `CanaryRun` with the columns below; constants `DOC_KINDS`, `LABELS`; test fixtures `migrated_db`, `db` (Engine; truncates after each test); `tests.factories` builders and `CITATION`.

- [ ] **Step 1: Write the session module and Alembic setup**

`app/db/session.py`:
```python
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.settings import get_settings


def database_url() -> str:
    url = get_settings().database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # Neon and Vercel hand out postgres:// URLs; SQLAlchemy needs the psycopg 3 driver name.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    # ponytail: NullPool — serverless instances don't keep pools warm; Neon's pooled URL does the pooling
    # (pgbouncer rejects server-side prepared statements, hence prepare_threshold=None).
    return create_engine(
        database_url(), poolclass=NullPool, connect_args={"prepare_threshold": None, "connect_timeout": 10}
    )


def get_session() -> Iterator[Session]:
    with sessionmaker(get_engine(), expire_on_commit=False)() as session:
        yield session
```

Create the Alembic skeleton, then replace `migrations/env.py`:
```bash
alembic init migrations
```
Edit `alembic.ini`: keep the generated file but set `sqlalchemy.url =` (blank) and `prepend_sys_path = .`.

`migrations/env.py`:
```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.db.models import Base
from app.db.session import database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(database_url(), poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 2: Write the test fixtures and failing tests**

`tests/conftest.py`:
```python
import os

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://vart:vart@localhost:5434/vart_test"
)

import pytest  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

if "test" not in (make_url(TEST_DATABASE_URL).database or ""):
    pytest.exit("TEST_DATABASE_URL must point at a test database", returncode=2)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SESSION_SECRET", "test-session-secret")
os.environ.setdefault("CRON_SECRET", "test-cron-secret")
for _name in ("OPENROUTER_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "VERCEL"):
    os.environ.pop(_name, None)

from collections.abc import Iterator  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import Engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from app.db.session import get_engine  # noqa: E402

TABLES = (
    "workspaces, documents, document_lines, chunks, questionnaires, items, runs, run_items, answers, "
    "audit_events, llm_usage, ip_limits, canary_runs"
)


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[Engine]:
    engine = get_engine()
    try:
        with engine.connect():
            pass
    except OperationalError:
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail("Postgres is required but not reachable at TEST_DATABASE_URL")
        pytest.skip("Postgres not running: docker compose up -d db")
    command.upgrade(Config("alembic.ini"), "head")
    yield engine


@pytest.fixture
def db(migrated_db: Engine) -> Iterator[Engine]:
    yield migrated_db
    with migrated_db.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
```

`tests/factories.py`:
```python
"""Tiny row builders for tests. Each one flushes so ids are set; callers commit when they need to."""

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Answer, Chunk, Document, Item, Questionnaire, Run, Workspace

CITATION: dict[str, Any] = {
    "chunk_id": "c1",
    "document_id": "d1",
    "line_start": 1,
    "line_end": 1,
    "quote": "Access is reviewed quarterly.",
    "stance": "yes",
}


def workspace(s: Session, **kw: Any) -> Workspace:
    ws = Workspace(**kw)
    s.add(ws)
    s.flush()
    return ws


def document(s: Session, ws: Workspace, **kw: Any) -> Document:
    values: dict[str, Any] = {
        "filename": "policy.docx",
        "source": "upload",
        "sha256": uuid.uuid4().hex * 2,
        "kind": "policy",
    }
    d = Document(workspace_id=ws.id, **(values | kw))
    s.add(d)
    s.flush()
    return d


def chunk(s: Session, doc: Document, **kw: Any) -> Chunk:
    values: dict[str, Any] = {"line_start": 1, "line_end": 1, "text": "Access is reviewed quarterly."}
    c = Chunk(workspace_id=doc.workspace_id, document_id=doc.id, **(values | kw))
    s.add(c)
    s.flush()
    return c


def questionnaire(s: Session, ws: Workspace, **kw: Any) -> Questionnaire:
    q = Questionnaire(workspace_id=ws.id, **({"filename": "q.xlsx", "source": "upload"} | kw))
    s.add(q)
    s.flush()
    return q


def item(s: Session, q: Questionnaire, **kw: Any) -> Item:
    values: dict[str, Any] = {"position": 1, "row_ref": "Questionnaire!C6", "question": "Do you review access?"}
    it = Item(workspace_id=q.workspace_id, questionnaire_id=q.id, **(values | kw))
    s.add(it)
    s.flush()
    return it


def run(s: Session, q: Questionnaire, **kw: Any) -> Run:
    r = Run(workspace_id=q.workspace_id, questionnaire_id=q.id, **kw)
    s.add(r)
    s.flush()
    return r


def answer(s: Session, r: Run, it: Item, **kw: Any) -> Answer:
    a = Answer(workspace_id=r.workspace_id, run_id=r.id, item_id=it.id, **({"label": "unknown"} | kw))
    s.add(a)
    s.flush()
    return a
```

`tests/test_session.py`:
```python
import pytest

from app.db.session import database_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
        ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ],
)
def test_database_url_uses_the_psycopg_driver(monkeypatch: pytest.MonkeyPatch, raw: str, expected: str) -> None:
    monkeypatch.setenv("DATABASE_URL", raw)
    assert database_url() == expected


def test_database_url_must_be_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        database_url()
```

`tests/test_models.py`:
```python
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Chunk, Document, DocumentLine, Workspace
from tests import factories as f


@pytest.fixture
def s(db: Engine) -> Iterator[Session]:
    with Session(db) as session:
        yield session


def _run(s: Session):  # type: ignore[no-untyped-def]
    ws = f.workspace(s)
    q = f.questionnaire(s, ws)
    return ws, q, f.item(s, q), f.run(s, q)


def test_verified_answer_with_a_citation_is_accepted(s: Session) -> None:
    _, _, it, r = _run(s)
    f.answer(s, r, it, label="verified", value="Yes", citations=[f.CITATION], confidence=0.9)
    s.commit()


@pytest.mark.parametrize("label", ["verified", "partial"])
def test_verified_or_partial_answer_needs_a_citation(s: Session, label: str) -> None:
    _, _, it, r = _run(s)
    with pytest.raises(IntegrityError, match="ck_answers_cited"):
        f.answer(s, r, it, label=label, value="Yes", citations=[])


def test_unknown_answer_needs_no_citation(s: Session) -> None:
    _, _, it, r = _run(s)
    f.answer(s, r, it, label="unknown")
    s.commit()


def test_user_confirmed_answer_needs_its_statement(s: Session) -> None:
    ws, _, it, r = _run(s)
    with pytest.raises(IntegrityError, match="ck_answers_statement"):
        f.answer(s, r, it, label="user_confirmed")
    s.rollback()
    ws, _, it, r = _run(s)
    stmt = f.document(s, ws, kind="statement", source="statement", filename="answer.txt")
    f.answer(s, r, it, label="user_confirmed", statement_id=stmt.id)
    s.commit()


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"label": "maybe"}, "ck_answers_label"),
        ({"label": "unknown", "value": "Maybe"}, "ck_answers_value"),
        ({"label": "unknown", "confidence": 1.5}, "ck_answers_confidence"),
    ],
)
def test_answer_fields_are_constrained(s: Session, fields: dict[str, object], constraint: str) -> None:
    _, _, it, r = _run(s)
    with pytest.raises(IntegrityError, match=constraint):
        f.answer(s, r, it, **fields)


def test_one_answer_per_item_per_run(s: Session) -> None:
    _, _, it, r = _run(s)
    f.answer(s, r, it)
    with pytest.raises(IntegrityError, match="uq_answers_run_item"):
        f.answer(s, r, it)


@pytest.mark.parametrize(
    ("fields", "constraint"),
    [
        ({"flags": ["shouting"]}, "ck_chunks_flags"),
        ({"line_start": 3, "line_end": 2}, "ck_chunks_lines"),
        ({"line_start": 0, "line_end": 0}, "ck_chunks_lines"),
    ],
)
def test_chunk_fields_are_constrained(s: Session, fields: dict[str, object], constraint: str) -> None:
    doc = f.document(s, f.workspace(s))
    with pytest.raises(IntegrityError, match=constraint):
        f.chunk(s, doc, **fields)


def test_document_kind_is_constrained(s: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_documents_kind"):
        f.document(s, f.workspace(s), kind="memo")


def test_chunks_are_full_text_searchable(s: Session) -> None:
    doc = f.document(s, f.workspace(s))
    f.chunk(s, doc, heading="Access reviews", text="User access is reviewed quarterly.", flags=["negation"])
    s.commit()
    hits = s.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.tsv.op("@@")(func.websearch_to_tsquery("english", "quarterly access review")))
    )
    assert hits == 1


def test_deleting_a_workspace_deletes_everything_in_it(s: Session) -> None:
    ws, _, it, r = _run(s)
    doc = f.document(s, ws)
    s.add(DocumentLine(document_id=doc.id, n=1, text="Access is reviewed quarterly."))
    f.chunk(s, doc)
    stmt = f.document(s, ws, kind="statement", source="statement", filename="answer.txt")
    f.answer(s, r, it, label="user_confirmed", statement_id=stmt.id)
    s.add(AuditEvent(workspace_id=ws.id, actor="visitor", action="upload"))
    s.commit()
    s.execute(delete(Workspace).where(Workspace.id == ws.id))
    s.commit()
    for table in ("documents", "document_lines", "chunks", "questionnaires", "items", "runs", "answers",
                  "audit_events"):
        assert s.scalar(text(f"select count(*) from {table}")) == 0, table
    assert s.scalar(select(func.count()).select_from(Document)) == 0
```

- [ ] **Step 3: Run them to verify they fail**

```bash
docker compose up -d db
docker compose exec db createdb -U vart vart_test_foundation || true
export TEST_DATABASE_URL=postgresql+psycopg://vart:vart@localhost:5434/vart_test_foundation
pytest tests/test_session.py tests/test_models.py -q
```
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db.models'` (the session tests fail on the missing module import chain or pass once session.py exists; the model tests must fail).

- [ ] **Step 4: Write the models**

`app/db/models.py`:
```python
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DOC_KINDS = ("policy", "report", "record", "contract", "plan", "questionnaire", "statement", "other")
LABELS = ("verified", "partial", "conflict", "unknown", "user_confirmed", "na")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _workspace_fk() -> Mapped[uuid.UUID]:
    return mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = _uuid_pk()
    created_at: Mapped[datetime] = _created_at()
    ip_hash: Mapped[str | None] = mapped_column(String(32), default=None)
    __table_args__ = (Index("ix_workspaces_created_at", "created_at"),)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    filename: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(16))
    sha256: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(8), default="final", server_default="final")
    effective_date: Mapped[date | None] = mapped_column(Date, default=None)
    scope: Mapped[str | None] = mapped_column(Text, default=None)
    evidence_allowed: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    metadata_source: Mapped[str] = mapped_column(String(8), default="rule", server_default="rule")
    line_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = _created_at()
    __table_args__ = (
        CheckConstraint(_in("source", ("sample", "upload", "drive", "statement")), name="ck_documents_source"),
        CheckConstraint(_in("kind", DOC_KINDS), name="ck_documents_kind"),
        CheckConstraint(_in("status", ("final", "draft")), name="ck_documents_status"),
        CheckConstraint(_in("metadata_source", ("rule", "model", "user")), name="ck_documents_metadata_source"),
    )


class DocumentLine(Base):
    __tablename__ = "document_lines"
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    n: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    __table_args__ = (CheckConstraint("n >= 1", name="ck_document_lines_n"),)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    heading: Mapped[str | None] = mapped_column(Text, default=None)
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    as_of: Mapped[date | None] = mapped_column(Date, default=None)
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(heading, '') || ' ' || text)", persisted=True),
    )
    __table_args__ = (
        CheckConstraint("line_start >= 1 AND line_end >= line_start", name="ck_chunks_lines"),
        CheckConstraint("flags <@ ARRAY['negation', 'placeholder', 'injection']::text[]", name="ck_chunks_flags"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )


class Questionnaire(Base):
    __tablename__ = "questionnaires"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    filename: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(16))
    original_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True, default=None)
    sheet: Mapped[str | None] = mapped_column(String(255), default=None)
    mapping: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = _created_at()
    __table_args__ = (
        CheckConstraint(_in("source", ("sample", "upload", "drive")), name="ck_questionnaires_source"),
    )


class Item(Base):
    __tablename__ = "items"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    questionnaire_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questionnaires.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    row_ref: Mapped[str] = mapped_column(String(64))
    code: Mapped[str | None] = mapped_column(String(64), default=None)
    topic: Mapped[str | None] = mapped_column(Text, default=None)
    question: Mapped[str] = mapped_column(Text)
    csf_id: Mapped[str | None] = mapped_column(String(16), default=None)
    __table_args__ = (UniqueConstraint("questionnaire_id", "position", name="uq_items_position"),)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    questionnaire_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("questionnaires.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="running", server_default="running")
    prompt_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    models: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"), server_default="0")
    started_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    __table_args__ = (CheckConstraint(_in("status", ("running", "done", "failed")), name="ck_runs_status"),)


class RunItem(Base):
    __tablename__ = "run_items"
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[str] = mapped_column(String(8), default="pending", server_default="pending")
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    __table_args__ = (
        CheckConstraint(_in("state", ("pending", "claimed", "done")), name="ck_run_items_state"),
        Index("ix_run_items_state", "run_id", "state"),
    )


class Answer(Base):
    __tablename__ = "answers"
    id: Mapped[uuid.UUID] = _uuid_pk()
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(16))
    value: Mapped[str | None] = mapped_column(String(8), default=None)
    text: Mapped[str] = mapped_column(Text, default="", server_default="")
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    dropped: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    conflict: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    scope_note: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    # NO ACTION (not RESTRICT): a workspace delete removes answers and statements in one statement.
    statement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id"), default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    edited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = _created_at()
    __table_args__ = (
        UniqueConstraint("run_id", "item_id", name="uq_answers_run_item"),
        CheckConstraint(_in("label", LABELS), name="ck_answers_label"),
        CheckConstraint("value IS NULL OR value IN ('Yes', 'No', 'Partial')", name="ck_answers_value"),
        CheckConstraint(
            "jsonb_typeof(citations) = 'array' AND jsonb_typeof(dropped) = 'array'", name="ck_answers_json_arrays"
        ),
        CheckConstraint(
            "label NOT IN ('verified', 'partial') OR jsonb_array_length(citations) > 0", name="ck_answers_cited"
        ),
        CheckConstraint("label <> 'user_confirmed' OR statement_id IS NOT NULL", name="ck_answers_statement"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_answers_confidence"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    ref: Mapped[str | None] = mapped_column(String(64), default=None)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    at: Mapped[datetime] = _created_at()


class LlmUsage(Base):
    __tablename__ = "llm_usage"
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    hour_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)


class IpLimit(Base):
    __tablename__ = "ip_limits"
    ip_hash: Mapped[str] = mapped_column(String(32), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    hits: Mapped[int] = mapped_column(Integer, default=0)


class CanaryRun(Base):
    __tablename__ = "canary_runs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    ok: Mapped[bool] = mapped_column(Boolean)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
```

- [ ] **Step 5: Generate and inspect the migration**

```bash
export DATABASE_URL=$TEST_DATABASE_URL
alembic revision --autogenerate -m "initial schema"
```
Open the generated `migrations/versions/*_initial_schema.py` and confirm it contains: 13 `op.create_table` calls; `sa.Computed("to_tsvector('english', coalesce(heading, '') || ' ' || text)", persisted=True)` on `chunks.tsv`; `op.create_index('ix_chunks_tsv', ..., postgresql_using='gin')`; every `CheckConstraint` and `UniqueConstraint` by the names above. If a constraint is missing, add it to the migration by hand (same SQL as the model). Then:
```bash
alembic upgrade head && alembic check
```
Expected: `No new upgrade operations detected.`

- [ ] **Step 6: Run the tests**

```bash
pytest tests/test_session.py tests/test_models.py -q
```
Expected: PASS.

- [ ] **Step 7: Backend chain and commit**

```bash
ruff check . && ruff format --check . && mypy app scripts && pytest -q && alembic check
git add app/db alembic.ini migrations tests/conftest.py tests/factories.py tests/test_session.py tests/test_models.py
git commit -m "feat(db): initial schema with constraints that enforce cited answers

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
(`mypy ... scripts` warns "no files" until Task 5 creates scripts/; if mypy errors on the missing directory, run `mypy app` for this commit only.)

---

### Task 3: Cookie workspaces, per-IP limits, budgets, audit log, cleanup

**Files:**
- Create: `app/api/__init__.py` (empty), `app/api/deps.py`, `app/api/workspace.py`, `app/api/internal.py`, `app/services/__init__.py` (empty), `app/services/ip_limits.py`, `app/services/llm_budget.py`, `app/services/capacity.py`, `app/services/audit_log.py`, `app/services/workspaces.py`, `app/main.py` (minimal; Task 5 rewrites it)
- Test: `tests/test_workspace.py`, `tests/test_ip_limits.py`, `tests/test_llm_budget.py`, `tests/test_cleanup.py`, `tests/test_audit_log.py`

**Interfaces:**
- Consumes: models from Task 2; `get_settings`.
- Produces: `deps.COOKIE_NAME = "vart_ws"`, `SessionDep`, `WorkspaceDep`, `current_workspace(request, response, session) -> Workspace`; `ip_limits.LIMITS: dict[str, tuple[int, timedelta]]`, `client_ip(request) -> str`, `ip_hash(ip: str, secret: str) -> str`, `hit(session, ip_digest: str, kind: str, now: datetime | None = None) -> bool`, `purge(session, now=None) -> int`; `llm_budget.CAPS: dict[str, int]`, `GLOBAL_PER_HOUR: int`, `remaining(session, workspace_id, kind, now=None) -> int`, `try_consume(session, workspace_id, kind, now=None) -> bool`; `capacity.ensure_capacity(session) -> None`; `audit_log.record(session, workspace_id, action, *, actor="visitor", ref=None, detail=None) -> AuditEvent`; `workspaces.WORKSPACE_TTL`, `cleanup_expired(session, now=None) -> dict[str, int]`; `internal.require_cron`, `internal.CronDep`, `internal.router`; `workspace.router` with `WorkspaceOut`.

- [ ] **Step 1: Write the failing tests**

`tests/test_workspace.py`:
```python
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from app.db.models import Workspace
from app.main import app
from app.services import ip_limits


@pytest.fixture
def client(db: Engine) -> TestClient:
    return TestClient(app)


def _count(db: Engine) -> int:
    with Session(db) as s:
        return int(s.scalar(select(func.count()).select_from(Workspace)) or 0)


def test_first_visit_creates_a_workspace_and_sets_a_cookie(client: TestClient, db: Engine) -> None:
    r = client.get("/api/workspace")
    assert r.status_code == 200
    assert "created_at" in r.json()
    cookie = r.headers["set-cookie"].lower()
    assert "vart_ws=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert _count(db) == 1


def test_the_cookie_reuses_the_workspace(client: TestClient, db: Engine) -> None:
    client.get("/api/workspace")
    client.get("/api/workspace")
    assert _count(db) == 1


def test_cookie_for_a_deleted_workspace_starts_fresh(client: TestClient, db: Engine) -> None:
    client.get("/api/workspace")
    with db.begin() as conn:
        conn.execute(text("delete from workspaces"))
    r = client.get("/api/workspace")
    assert r.status_code == 200
    assert _count(db) == 1


def test_tampered_cookie_starts_fresh(client: TestClient, db: Engine) -> None:
    client.cookies.set("vart_ws", "not-a-signed-value")
    assert client.get("/api/workspace").status_code == 200
    assert _count(db) == 1


def test_reset_deletes_the_workspace_and_clears_the_cookie(client: TestClient, db: Engine) -> None:
    client.get("/api/workspace")
    r = client.post("/api/workspace/reset")
    assert r.status_code == 204
    assert 'vart_ws=""' in r.headers["set-cookie"] or "max-age=0" in r.headers["set-cookie"].lower()
    assert _count(db) == 0


def test_new_workspaces_per_ip_are_limited(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(ip_limits.LIMITS, "workspace", (2, timedelta(hours=1)))
    statuses = []
    for _ in range(3):
        fresh = TestClient(app)  # no cookie: a new visitor each time
        statuses.append(fresh.get("/api/workspace", headers={"x-real-ip": "203.0.113.7"}))
    assert [r.status_code for r in statuses] == [200, 200, 429]
    assert statuses[2].headers["retry-after"] == "3600"
    other = TestClient(app).get("/api/workspace", headers={"x-real-ip": "198.51.100.1"})
    assert other.status_code == 200
    assert _count(db) == 3


def test_cookie_is_secure_on_vercel(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERCEL", "1")
    assert "secure" in client.get("/api/workspace").headers["set-cookie"].lower()
```

`tests/test_ip_limits.py`:
```python
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.db.models import IpLimit
from app.services import ip_limits
from app.services.ip_limits import client_ip, hit, ip_hash, purge


def _request(headers: dict[str, str], client: tuple[str, int] | None = ("10.0.0.1", 1234)) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": client})


def test_client_ip_prefers_x_real_ip_then_forwarded_for_then_the_socket() -> None:
    assert client_ip(_request({"x-real-ip": "1.1.1.1", "x-forwarded-for": "2.2.2.2"})) == "1.1.1.1"
    assert client_ip(_request({"x-forwarded-for": "2.2.2.2, 3.3.3.3"})) == "2.2.2.2"
    assert client_ip(_request({})) == "10.0.0.1"
    assert client_ip(_request({}, client=None)) == "unknown"


def test_ip_hash_is_keyed_and_short() -> None:
    assert ip_hash("1.1.1.1", "a") != ip_hash("1.1.1.1", "b")
    assert len(ip_hash("1.1.1.1", "a")) == 32


def test_hits_over_the_limit_are_refused(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(ip_limits.LIMITS, "upload", (2, timedelta(hours=1)))
    now = datetime(2026, 10, 3, 12, 30, tzinfo=UTC)
    with Session(db) as s:
        assert [hit(s, "ipA", "upload", now) for _ in range(3)] == [True, True, False]
        assert hit(s, "ipA", "upload", now + timedelta(hours=1)) is True  # next window
        assert hit(s, "ipB", "upload", now) is True


def test_concurrent_hits_count_every_event(db: Engine) -> None:
    def one(_: int) -> None:
        with Session(db) as s:
            hit(s, "ipC", "upload")
            s.commit()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(one, range(16)))
    with Session(db) as s:
        assert s.scalar(select(IpLimit.hits).where(IpLimit.ip_hash == "ipC")) == 16


def test_purge_drops_windows_older_than_two_days(db: Engine) -> None:
    now = datetime(2026, 10, 3, tzinfo=UTC)
    with Session(db) as s:
        hit(s, "old", "upload", now - timedelta(days=3))
        hit(s, "new", "upload", now)
        assert purge(s, now) == 1
        s.commit()
        assert [r for (r,) in s.execute(select(IpLimit.ip_hash))] == ["new"]
```

`tests/test_llm_budget.py`:
```python
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.services import llm_budget
from app.services.llm_budget import remaining, try_consume
from tests import factories as f

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)


def test_each_step_has_its_own_hourly_cap(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 2)
    with Session(db) as s:
        ws = f.workspace(s)
        assert [try_consume(s, ws.id, "stance", NOW) for _ in range(3)] == [True, True, False]
        assert try_consume(s, ws.id, "draft", NOW) is True
        assert remaining(s, ws.id, "stance", NOW) == 0


def test_the_global_cap_is_shared(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 5)
    monkeypatch.setattr(llm_budget, "GLOBAL_PER_HOUR", 3)
    with Session(db) as s:
        a, b = f.workspace(s), f.workspace(s)
        assert [try_consume(s, a.id, "stance", NOW) for _ in range(2)] == [True, True]
        assert try_consume(s, b.id, "stance", NOW) is True
        assert try_consume(s, b.id, "stance", NOW) is False


def test_refused_retries_do_not_drain_the_global_cap(db: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(llm_budget.CAPS, "stance", 1)
    monkeypatch.setattr(llm_budget, "GLOBAL_PER_HOUR", 2)
    with Session(db) as s:
        a, b = f.workspace(s), f.workspace(s)
        for _ in range(5):
            try_consume(s, a.id, "stance", NOW)  # 1 allowed, 4 refused
        assert try_consume(s, b.id, "stance", NOW) is True


def test_unknown_step_is_a_programming_error(db: Engine) -> None:
    with Session(db) as s, pytest.raises(KeyError):
        try_consume(s, uuid.uuid4(), "poetry", NOW)
```

`tests/test_cleanup.py`:
```python
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.db.models import CanaryRun, Workspace
from app.main import app
from app.services.ip_limits import hit
from app.services.workspaces import cleanup_expired


def test_cleanup_removes_expired_rows(db: Engine) -> None:
    now = datetime.now(UTC)
    with Session(db) as s:
        s.add(Workspace(created_at=now - timedelta(hours=25)))
        s.add(Workspace(created_at=now - timedelta(hours=1)))
        s.add(CanaryRun(ok=True, at=now - timedelta(days=31)))
        s.add(CanaryRun(ok=True, at=now - timedelta(days=1)))
        hit(s, "old-ip", "upload", now - timedelta(days=3))
        s.commit()
        assert cleanup_expired(s, now) == {"workspaces": 1, "ip_limits": 1, "canary_runs": 1}
        assert s.scalar(select(func.count()).select_from(Workspace)) == 1


def test_cleanup_endpoint_needs_the_cron_secret(db: Engine) -> None:
    c = TestClient(app)
    assert c.get("/api/internal/cleanup").status_code == 401
    assert c.get("/api/internal/cleanup", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = c.get("/api/internal/cleanup", headers={"Authorization": "Bearer test-cron-secret"})
    assert ok.status_code == 200
    assert set(ok.json()) == {"workspaces", "ip_limits", "canary_runs"}


def test_cleanup_is_closed_when_no_secret_is_configured(db: Engine, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("CRON_SECRET", "")
    r = TestClient(app).get("/api/internal/cleanup", headers={"Authorization": "Bearer "})
    assert r.status_code == 401


def test_internal_routes_are_not_in_the_public_schema() -> None:
    assert not [p for p in app.openapi()["paths"] if p.startswith("/api/internal")]
```

`tests/test_audit_log.py`:
```python
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent
from app.services.audit_log import record
from tests import factories as f


def test_record_adds_an_event(db: Engine) -> None:
    with Session(db) as s:
        ws = f.workspace(s)
        record(s, ws.id, "approve", ref="a1", detail={"label": "verified"})
        s.commit()
        event = s.scalars(select(AuditEvent)).one()
        assert (event.actor, event.action, event.ref, event.detail) == ("visitor", "approve", "a1", {"label": "verified"})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_workspace.py tests/test_ip_limits.py tests/test_llm_budget.py tests/test_cleanup.py tests/test_audit_log.py -q`
Expected: FAIL with `ModuleNotFoundError` for `app.main` / `app.services.*`.

- [ ] **Step 3: Implement the services**

`app/services/ip_limits.py`:
```python
"""Per-network limits for actions that create rows or spend money. Counts live in Postgres (no Redis)."""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.db.models import IpLimit

# (events allowed, window) per kind; generous for people, tight for scripts.
LIMITS: dict[str, tuple[int, timedelta]] = {
    "workspace": (20, timedelta(hours=1)),
    "upload": (60, timedelta(hours=1)),
    "run": (20, timedelta(hours=1)),
}
KEEP = timedelta(days=2)


def client_ip(request: Request) -> str:
    # Vercel sets x-real-ip and overwrites x-forwarded-for, so clients cannot spoof either there.
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def ip_hash(ip: str, secret: str) -> str:
    return hmac.new(secret.encode(), ip.encode(), hashlib.sha256).hexdigest()[:32]


def _window_start(now: datetime, window: timedelta) -> datetime:
    seconds = int(window.total_seconds())
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, UTC)


def hit(session: Session, ip_digest: str, kind: str, now: datetime | None = None) -> bool:
    """Count one event; False when this network is over its limit in the current window."""
    limit, window = LIMITS[kind]
    start = _window_start(now or datetime.now(UTC), window)
    stmt = (
        insert(IpLimit)
        .values(ip_hash=ip_digest, window_start=start, kind=kind, hits=1)
        .on_conflict_do_update(
            index_elements=[IpLimit.ip_hash, IpLimit.window_start, IpLimit.kind],
            set_={"hits": IpLimit.hits + 1},
        )
        .returning(IpLimit.hits)
    )
    return int(session.execute(stmt).scalar_one()) <= limit


def purge(session: Session, now: datetime | None = None) -> int:
    cutoff = (now or datetime.now(UTC)) - KEEP
    result = session.execute(delete(IpLimit).where(IpLimit.window_start < cutoff))
    return int(result.rowcount or 0)  # type: ignore[attr-defined]
```

`app/services/llm_budget.py`:
```python
"""Hourly model-call budgets per workspace and step, plus one global cap (PriorPath pattern, generalized)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import LlmUsage

# Calls per workspace per hour. A 60-item questionnaire needs about 60 stance + 50 draft calls.
CAPS: dict[str, int] = {"stance": 150, "draft": 120, "classify": 40, "recheck": 60}
GLOBAL_PER_HOUR = 1500  # all workspaces, all steps


def _hour(now: datetime | None) -> datetime:
    return (now or datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)


def _global_used(session: Session, hour: datetime) -> int:
    # Count each workspace/step at most up to its own cap, so refused retries from one workspace
    # can't use up the global budget for everyone else.
    per_workspace = case(
        *[(LlmUsage.kind == kind, func.least(LlmUsage.calls, cap)) for kind, cap in CAPS.items()],
        else_=LlmUsage.calls,
    )
    total = session.scalar(
        select(func.coalesce(func.sum(per_workspace), 0)).where(LlmUsage.hour_start == hour)
    )
    return int(total or 0)


def remaining(session: Session, workspace_id: uuid.UUID, kind: str, now: datetime | None = None) -> int:
    hour = _hour(now)
    used = session.scalar(
        select(LlmUsage.calls).where(
            LlmUsage.workspace_id == workspace_id, LlmUsage.hour_start == hour, LlmUsage.kind == kind
        )
    )
    own = CAPS[kind] - (used or 0)
    return max(0, min(own, GLOBAL_PER_HOUR - _global_used(session, hour)))


def try_consume(session: Session, workspace_id: uuid.UUID, kind: str, now: datetime | None = None) -> bool:
    cap = CAPS[kind]  # KeyError for an unknown step: a programming error, not a visitor error
    hour = _hour(now)
    stmt = (
        insert(LlmUsage)
        .values(workspace_id=workspace_id, hour_start=hour, kind=kind, calls=1)
        .on_conflict_do_update(
            index_elements=[LlmUsage.workspace_id, LlmUsage.hour_start, LlmUsage.kind],
            set_={"calls": LlmUsage.calls + 1},
        )
        .returning(LlmUsage.calls)
    )
    if int(session.execute(stmt).scalar_one()) > cap:
        return False
    return _global_used(session, hour) <= GLOBAL_PER_HOUR
```

`app/services/capacity.py`:
```python
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

MAX_DB_BYTES = 400 * 1024 * 1024  # Neon free gives 1 GB per project; stay well under it


def demo_is_full(session: Session) -> bool:
    return bool(session.scalar(text("select pg_database_size(current_database())")) > MAX_DB_BYTES)


def ensure_capacity(session: Session) -> None:
    if demo_is_full(session):
        raise HTTPException(status_code=503, detail="the demo is full right now; please try again later")
```

`app/services/audit_log.py`:
```python
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditEvent


def record(
    session: Session,
    workspace_id: uuid.UUID,
    action: str,
    *,
    actor: str = "visitor",
    ref: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(workspace_id=workspace_id, actor=actor, action=action, ref=ref, detail=detail or {})
    session.add(event)
    return event
```

`app/services/workspaces.py`:
```python
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import CanaryRun, Workspace
from app.services.ip_limits import purge

WORKSPACE_TTL = timedelta(hours=24)
CANARY_KEEP = timedelta(days=30)


def cleanup_expired(session: Session, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    workspaces = session.execute(delete(Workspace).where(Workspace.created_at < now - WORKSPACE_TTL))
    limits = purge(session, now)
    canaries = session.execute(delete(CanaryRun).where(CanaryRun.at < now - CANARY_KEEP))
    session.commit()
    return {
        "workspaces": int(workspaces.rowcount or 0),  # type: ignore[attr-defined]
        "ip_limits": limits,
        "canary_runs": int(canaries.rowcount or 0),  # type: ignore[attr-defined]
    }
```

- [ ] **Step 4: Implement the API pieces**

`app/api/deps.py`:
```python
import os
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.orm import Session

from app.db.models import Workspace
from app.db.session import get_session
from app.services.capacity import ensure_capacity
from app.services.ip_limits import client_ip, hit, ip_hash
from app.settings import get_settings

COOKIE_NAME = "vart_ws"
COOKIE_MAX_AGE = 24 * 3600

SessionDep = Annotated[Session, Depends(get_session)]


def _serializer() -> URLSafeSerializer:
    secret = get_settings().session_secret
    if not secret:
        raise RuntimeError("SESSION_SECRET is not set")
    return URLSafeSerializer(secret, salt="workspace")


def _load(session: Session, raw: str) -> Workspace | None:
    try:
        ws_id = uuid.UUID(str(_serializer().loads(raw)))
    except (BadSignature, ValueError):
        return None
    return session.get(Workspace, ws_id)


def current_workspace(request: Request, response: Response, session: SessionDep) -> Workspace:
    raw = request.cookies.get(COOKIE_NAME)
    ws = _load(session, raw) if raw else None
    if ws is not None:
        return ws
    ensure_capacity(session)
    digest = ip_hash(client_ip(request), get_settings().session_secret)
    allowed = hit(session, digest, "workspace")
    session.commit()  # count the attempt even when it is refused
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="too many new sessions from this network; try again in an hour",
            headers={"Retry-After": "3600"},
        )
    ws = Workspace(ip_hash=digest)
    session.add(ws)
    session.commit()
    response.set_cookie(
        COOKIE_NAME,
        _serializer().dumps(str(ws.id)),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.environ.get("VERCEL") == "1",
    )
    return ws


WorkspaceDep = Annotated[Workspace, Depends(current_workspace)]
```

`app/api/workspace.py`:
```python
from datetime import datetime

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import delete

from app.api.deps import COOKIE_NAME, SessionDep, WorkspaceDep
from app.db.models import Workspace

router = APIRouter()


class WorkspaceOut(BaseModel):
    created_at: datetime


@router.get("/api/workspace")
def read_workspace(ws: WorkspaceDep) -> WorkspaceOut:
    return WorkspaceOut(created_at=ws.created_at)


@router.post("/api/workspace/reset", status_code=204)
def reset_workspace(ws: WorkspaceDep, session: SessionDep, response: Response) -> None:
    session.execute(delete(Workspace).where(Workspace.id == ws.id))
    session.commit()
    response.delete_cookie(COOKIE_NAME)
```

`app/api/internal.py`:
```python
import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from app.api.deps import SessionDep
from app.services.workspaces import cleanup_expired
from app.settings import get_settings

router = APIRouter(include_in_schema=False)


def require_cron(authorization: Annotated[str | None, Header()] = None) -> None:
    # Vercel cron sends "Authorization: Bearer $CRON_SECRET"; no secret configured = closed.
    secret = get_settings().cron_secret
    if not secret or not hmac.compare_digest((authorization or "").encode(), f"Bearer {secret}".encode()):
        raise HTTPException(status_code=401, detail="unauthorized")


CronDep = Annotated[None, Depends(require_cron)]


@router.get("/api/internal/cleanup")
def cleanup(_: CronDep, session: SessionDep) -> dict[str, int]:
    return cleanup_expired(session)
```

`app/main.py` (minimal; Task 5 replaces it):
```python
from fastapi import FastAPI

from app import __version__
from app.api import internal, workspace

app = FastAPI(
    title="VART", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None
)
app.include_router(workspace.router)
app.include_router(internal.router)
```

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_workspace.py tests/test_ip_limits.py tests/test_llm_budget.py tests/test_cleanup.py tests/test_audit_log.py -q`
Expected: PASS.

- [ ] **Step 6: Backend chain and commit**

```bash
ruff check . && ruff format --check . && mypy app && pytest -q && alembic check
git add app/api app/services app/main.py tests/test_workspace.py tests/test_ip_limits.py tests/test_llm_budget.py \
  tests/test_cleanup.py tests/test_audit_log.py
git commit -m "feat: cookie workspaces with per-IP limits, model budgets, audit log and cleanup

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: LLM client with strict JSON outputs, record/replay, tracing

**Files:**
- Create: `app/observability.py`, `app/llm/__init__.py` (empty), `app/llm/client.py`, `app/llm/recorder.py`, `tests/fakes.py`
- Modify: `app/api/deps.py` (append `get_llm`, `LLMDep`)
- Test: `tests/test_llm_client.py`, `tests/test_recorder.py`, `tests/test_observability.py`

**Interfaces:**
- Consumes: `get_settings`.
- Produces: `observability.Step = Literal["stance","draft","classify","recheck","judge","canary"]`, `trace_llm(name, *, model, kind: Step, metadata) -> ContextManager[Span]`, `has_pending()`, `flush()`; `client.OPENROUTER_BASE_URL`, `LLMError(Exception)`, `LLMRequest` (frozen dataclass: `step, model, prompt_version, system, user, schema_name, schema, max_tokens=1200`; `.key() -> str`), `LLMResult` (`text, input_tokens=0, output_tokens=0, cost_usd: float | None = None`), `LLMClient` Protocol (`complete(req) -> LLMResult`), `build_request(step, model, prompt_version, system, user, out: type[BaseModel], max_tokens=1200) -> LLMRequest` (raises `ValueError` for a non-strict schema), `complete_model(client, req, out: type[M]) -> M`, `OpenRouterClient(api_key, *, timeout=60.0, http_client=None)`, `default_client() -> LLMClient | None`; `recorder.ReplayMiss(LLMError)`, `RecordingClient(inner, path)`, `ReplayClient(path)`; `tests.fakes.FakeLLM(replies)` with `.requests: list[LLMRequest]`; `deps.get_llm() -> LLMClient | None`, `deps.LLMDep`.
- Rule for every later model-output schema: `model_config = ConfigDict(extra="forbid")` and no field defaults (nullable fields are `X | None` without a default). `build_request` enforces it.

- [ ] **Step 1: Write the failing tests and the fake**

`tests/fakes.py`:
```python
from app.llm.client import LLMRequest, LLMResult


class FakeLLM:
    """Scripted replies, used in order. An Exception item is raised instead. Every request is kept."""

    def __init__(self, replies: list[str | Exception] | None = None) -> None:
        self.replies = list(replies or [])
        self.requests: list[LLMRequest] = []

    def complete(self, req: LLMRequest) -> LLMResult:
        self.requests.append(req)
        if not self.replies:
            raise AssertionError(f"FakeLLM ran out of replies at step {req.step}")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(text=reply, input_tokens=10, output_tokens=5, cost_usd=0.0)
```

`tests/test_llm_client.py`:
```python
import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from app.llm.client import LLMError, OpenRouterClient, build_request, complete_model
from tests.fakes import FakeLLM


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    note: str | None


def _reply(content: str, finish: str = "stop", cost: float | None = 0.0001) -> dict[str, Any]:
    usage: dict[str, Any] = {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "gen-1",
        "object": "chat.completion",
        "created": 0,
        "model": "acme/fast",
        "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", "content": content}}],
        "usage": usage,
    }


def _client(handler: Any) -> OpenRouterClient:
    return OpenRouterClient("test-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def _req() -> Any:
    return build_request("stance", "acme/fast", "stance@p1", "system text", "user text", Out)


def test_sends_a_strict_json_schema_request() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=_reply('{"ok": true, "note": null}'))

    result = _client(handler).complete(_req())
    assert seen["model"] == "acme/fast" and seen["temperature"] == 0
    fmt = seen["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["name"] == "Out"
    assert seen["usage"] == {"include": True}
    assert result.text == '{"ok": true, "note": null}'
    assert (result.input_tokens, result.output_tokens, result.cost_usd) == (12, 3, 0.0001)


def test_truncated_reply_is_an_error() -> None:
    client = _client(lambda r: httpx.Response(200, json=_reply('{"ok": tr', finish="length")))
    with pytest.raises(LLMError, match="finish_reason"):
        client.complete(_req())


def test_http_errors_are_llm_errors_and_never_retried() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(402, json={"error": {"message": "Insufficient credits"}})

    with pytest.raises(LLMError):
        _client(handler).complete(_req())
    assert len(calls) == 1


def test_timeouts_are_llm_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(LLMError):
        _client(handler).complete(_req())


def test_complete_model_parses_and_rejects_wrong_shapes() -> None:
    assert complete_model(FakeLLM(['{"ok": true, "note": "x"}']), _req(), Out) == Out(ok=True, note="x")
    with pytest.raises(LLMError, match="Out"):
        complete_model(FakeLLM(['{"ok": "maybe"}']), _req(), Out)
    with pytest.raises(LLMError):
        complete_model(FakeLLM(["not json"]), _req(), Out)


def test_build_request_rejects_loose_schemas() -> None:
    class WithDefault(BaseModel):
        model_config = ConfigDict(extra="forbid")
        ok: bool = True

    class Open(BaseModel):
        ok: bool

    for loose in (WithDefault, Open):
        with pytest.raises(ValueError):
            build_request("stance", "m", "p", "s", "u", loose)


def test_nested_models_must_be_strict_too() -> None:
    class Inner(BaseModel):
        ok: bool

    class Outer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        items: list[Inner]

    with pytest.raises(ValueError):
        build_request("stance", "m", "p", "s", "u", Outer)


def test_request_key_is_stable_and_changes_with_the_prompt_version() -> None:
    a = build_request("stance", "m", "p1", "s", "u", Out)
    b = build_request("stance", "m", "p1", "s", "u", Out)
    c = build_request("stance", "m", "p2", "s", "u", Out)
    assert a.key() == b.key() != c.key()
```

`tests/test_recorder.py`:
```python
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict

from app.llm.client import LLMError, build_request
from app.llm.recorder import RecordingClient, ReplayClient, ReplayMiss
from tests.fakes import FakeLLM


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


REQ = build_request("draft", "acme/fast", "draft@p1", "s", "u", Out)
OTHER = build_request("draft", "acme/fast", "draft@p1", "s", "different user text", Out)


def test_recording_calls_the_model_once_per_request(tmp_path: Path) -> None:
    inner = FakeLLM(['{"ok": true}'])
    rec = RecordingClient(inner, tmp_path / "r.jsonl")
    assert rec.complete(REQ).text == rec.complete(REQ).text == '{"ok": true}'
    assert len(inner.requests) == 1
    assert len((tmp_path / "r.jsonl").read_text().splitlines()) == 1


def test_recording_resumes_from_an_existing_file(tmp_path: Path) -> None:
    RecordingClient(FakeLLM(['{"ok": true}']), tmp_path / "r.jsonl").complete(REQ)
    again = RecordingClient(FakeLLM([]), tmp_path / "r.jsonl")  # would raise if it called the model
    assert again.complete(REQ).text == '{"ok": true}'


def test_replay_returns_recordings_and_fails_loudly_on_a_miss(tmp_path: Path) -> None:
    RecordingClient(FakeLLM(['{"ok": false}']), tmp_path / "r.jsonl").complete(REQ)
    replay = ReplayClient(tmp_path / "r.jsonl")
    assert replay.complete(REQ).text == '{"ok": false}'
    with pytest.raises(ReplayMiss, match="draft"):
        replay.complete(OTHER)


def test_a_replay_miss_is_an_llm_error() -> None:
    assert issubclass(ReplayMiss, LLMError)
```

`tests/test_observability.py`:
```python
from typing import Any

import pytest

from app import observability
from app.observability import flush, has_pending, trace_llm


class FakeObs:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []
        self.ended = False

    def update(self, **kw: Any) -> None:
        self.updates.append(kw)

    def end(self) -> None:
        self.ended = True


class FakeLangfuse:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.obs = FakeObs()
        self.flushed = 0

    def start_observation(self, **kw: Any) -> FakeObs:
        self.started.append(kw)
        return self.obs

    def flush(self) -> None:
        self.flushed += 1


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeLangfuse:
    fl = FakeLangfuse()
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setattr(observability, "_factory", lambda: fl)
    monkeypatch.setattr(observability, "_client", None)
    monkeypatch.setattr(observability, "_pending", 0)
    return fl


def test_without_keys_tracing_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)

    def boom() -> None:
        raise AssertionError("must not build a client")

    monkeypatch.setattr(observability, "_factory", boom)
    with trace_llm("stance", model="m", kind="stance", metadata={}) as span:
        span.end({"ok": True})


def test_only_allow_listed_metadata_leaves_the_app(fake: FakeLangfuse) -> None:
    meta = {"prompt_version": "stance@p1", "item_id": "i-1", "question": "SECRET QUESTION"}
    with trace_llm("stance", model="m", kind="stance", metadata=meta) as span:
        span.end({"ok": True, "answer": "SECRET ANSWER"}, {"input": 1, "output": 2})
    sent = fake.started[0]["metadata"]
    assert sent == {"prompt_version": "stance@p1", "item_id": "i-1", "kind": "stance"}
    out = fake.obs.updates[0]["output"]
    assert "answer" not in out and out["ok"] is True and "latency_ms" in out


def test_sdk_failures_never_reach_the_caller(fake: FakeLangfuse, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(**kw: Any) -> None:
        raise RuntimeError("langfuse down")

    monkeypatch.setattr(fake, "start_observation", broken)
    with trace_llm("draft", model="m", kind="draft", metadata={}) as span:
        span.end({"ok": True})


def test_flush_delivers_pending_spans(fake: FakeLangfuse) -> None:
    with trace_llm("draft", model="m", kind="draft", metadata={}) as span:
        span.end({"ok": True})
    assert has_pending()
    flush()
    assert fake.flushed == 1 and not has_pending()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_llm_client.py tests/test_recorder.py tests/test_observability.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm'` / `'app.observability'`.

- [ ] **Step 3: Implement observability**

`app/observability.py` (PriorPath's module; kinds and allow-list changed):
```python
"""Best-effort Langfuse tracing. Never sends prompts, completions, document text or answers: only the
allow-listed metadata below, model id, latency and token usage. Any SDK failure is swallowed (logged once)."""

import logging
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, Literal

log = logging.getLogger(__name__)
Scalar = str | int | float | bool
Step = Literal["stance", "draft", "classify", "recheck", "judge", "canary"]
ALLOWED = {"prompt_version", "finish_reason", "ok", "error_type", "kind", "latency_ms", "step", "item_id"}
_TIMEOUT_SECONDS = 3  # SDK HTTP timeout

_client: Any = None
_pending = 0  # spans ended since the last flush (guarded by _lock)
_lock = threading.Lock()
_FLUSH_BUDGET_SECONDS = 2.0  # langfuse's flush() is unbounded
_warned = False
_flusher: threading.Thread | None = None


def _build() -> Any:
    from langfuse import Langfuse

    # LANGFUSE_HOST is deprecated in the SDK in favour of LANGFUSE_BASE_URL; honour both.
    host = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST")
    return Langfuse(base_url=host, timeout=_TIMEOUT_SECONDS)


_factory: Callable[[], Any] = _build


def observability_enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def _warn(exc: Exception) -> None:
    global _warned
    if not _warned:
        _warned = True
        log.warning("langfuse tracing failed (further failures suppressed): %s", type(exc).__name__)


def _get() -> Any:
    global _client
    with _lock:
        if _client is None:
            _client = _factory()
        return _client


def _clean(d: dict[str, Scalar]) -> dict[str, Scalar]:
    return {k: v for k, v in d.items() if k in ALLOWED}


class Span:
    def __init__(self, obs: Any, started: float) -> None:
        self._obs = obs
        self._started = started
        self.ended = False

    def end(self, output_summary: dict[str, Scalar], usage: dict[str, int] | None = None) -> None:
        if self.ended:
            return
        self.ended = True
        if self._obs is None:
            return
        out = _clean(output_summary) | {"latency_ms": int((time.monotonic() - self._started) * 1000)}
        try:
            self._obs.update(output=out, usage_details=usage)
            self._obs.end()
        except Exception as exc:
            _warn(exc)
        global _pending
        with _lock:
            _pending += 1


@contextmanager
def trace_llm(name: str, *, model: str, kind: Step, metadata: dict[str, Scalar]) -> Iterator[Span]:
    started = time.monotonic()
    obs: Any = None
    if observability_enabled():
        try:
            obs = _get().start_observation(
                name=name, as_type="generation", model=model, metadata=_clean({**metadata, "kind": kind})
            )
        except Exception as exc:
            _warn(exc)
    span = Span(obs, started)
    try:
        yield span
    except Exception as exc:
        span.end({"ok": False, "error_type": type(exc).__name__})
        raise
    span.end({"ok": True})


def has_pending() -> bool:
    return _pending > 0


def flush() -> None:
    """Deliver pending spans; waits at most the budget. Single-flight: while a previous flush is running,
    spans stay pending for the next request."""
    global _pending, _flusher
    client = _client

    def run() -> None:
        try:
            client.flush()
        except Exception as exc:
            _warn(exc)

    with _lock:
        if _flusher is not None and _flusher.is_alive():
            return
        n, _pending = _pending, 0
        if n == 0 or client is None:
            return
        _flusher = worker = threading.Thread(target=run, daemon=True)
        worker.start()
    worker.join(_FLUSH_BUDGET_SECONDS)
    if worker.is_alive():
        _warn(TimeoutError("flush exceeded budget"))
```

- [ ] **Step 4: Implement the client and the recorder**

`app/llm/client.py`:
```python
"""OpenRouter chat completions with strict JSON-schema outputs. Recording and replay live in recorder.py."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

import httpx
from openai import APIError, OpenAI
from pydantic import BaseModel, ValidationError

from app.observability import Step, trace_llm
from app.settings import get_settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
M = TypeVar("M", bound=BaseModel)


class LLMError(Exception):
    """The model call failed or returned something unusable. Callers degrade; a request never crashes."""


@dataclass(frozen=True)
class LLMRequest:
    step: Step
    model: str
    prompt_version: str
    system: str
    user: str
    schema_name: str
    schema: dict[str, Any]
    max_tokens: int = 1200

    def key(self) -> str:
        payload = json.dumps(
            [self.model, self.prompt_version, self.system, self.user, self.schema_name, self.schema],
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(frozen=True)
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


class LLMClient(Protocol):
    def complete(self, req: LLMRequest) -> LLMResult: ...


def _assert_strict(schema: dict[str, Any], where: str = "$") -> None:
    """Strict structured outputs need every object closed and every property required."""
    if schema.get("type") == "object":
        if schema.get("additionalProperties") is not False:
            raise ValueError(f"{where}: set model_config = ConfigDict(extra='forbid')")
        missing = set(schema.get("properties", {})) - set(schema.get("required", []))
        if missing:
            raise ValueError(f"{where}: fields need no default for strict outputs: {sorted(missing)}")
    for key in ("properties", "$defs"):
        for name, sub in schema.get(key, {}).items():
            _assert_strict(sub, f"{where}.{name}")
    if isinstance(schema.get("items"), dict):
        _assert_strict(schema["items"], f"{where}[]")
    for sub in schema.get("anyOf", []):
        _assert_strict(sub, where)


def build_request(
    step: Step,
    model: str,
    prompt_version: str,
    system: str,
    user: str,
    out: type[BaseModel],
    max_tokens: int = 1200,
) -> LLMRequest:
    schema = out.model_json_schema()
    _assert_strict(schema)
    return LLMRequest(step, model, prompt_version, system, user, out.__name__, schema, max_tokens)


def complete_model(client: LLMClient, req: LLMRequest, out: type[M]) -> M:
    result = client.complete(req)
    try:
        return out.model_validate_json(result.text)
    except ValidationError as exc:
        raise LLMError(f"{req.step}: output did not match {req.schema_name}") from exc


def _usage(response: Any) -> tuple[int, int, float | None]:
    u = getattr(response, "usage", None)
    if u is None:
        return 0, 0, None
    cost = getattr(u, "cost", None)
    return int(u.prompt_tokens or 0), int(u.completion_tokens or 0), float(cost) if cost is not None else None


class OpenRouterClient:
    def __init__(self, api_key: str, *, timeout: float = 60.0, http_client: httpx.Client | None = None) -> None:
        self._client = OpenAI(
            api_key=api_key, base_url=OPENROUTER_BASE_URL, timeout=timeout, max_retries=0, http_client=http_client
        )

    def complete(self, req: LLMRequest) -> LLMResult:
        meta: dict[str, str | int | float | bool] = {"prompt_version": req.prompt_version, "step": req.step}
        with trace_llm(req.step, model=req.model, kind=req.step, metadata=meta) as span:
            try:
                response = self._client.chat.completions.create(
                    model=req.model,
                    messages=[{"role": "system", "content": req.system}, {"role": "user", "content": req.user}],
                    max_tokens=req.max_tokens,
                    temperature=0,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": req.schema_name, "strict": True, "schema": req.schema},
                    },
                    extra_body={"usage": {"include": True}},
                )
            except APIError as exc:  # connection errors, timeouts and HTTP status errors
                raise LLMError(f"{req.step}: {type(exc).__name__}") from exc
            choice = response.choices[0]
            tokens_in, tokens_out, cost = _usage(response)
            span.end(
                {"ok": choice.finish_reason == "stop", "finish_reason": str(choice.finish_reason)},
                {"input": tokens_in, "output": tokens_out},
            )
            if choice.finish_reason != "stop":  # truncated or filtered
                raise LLMError(f"{req.step}: finish_reason={choice.finish_reason}")
            return LLMResult(choice.message.content or "", tokens_in, tokens_out, cost)


def default_client() -> LLMClient | None:
    key = get_settings().openrouter_api_key
    return OpenRouterClient(key) if key else None
```

`app/llm/recorder.py`:
```python
"""Record and replay model outputs so tests, evals and CI run without keys or network.

A recording is JSONL: one line per model call, keyed by LLMRequest.key(). Replay never calls a model; a missing
key raises ReplayMiss, so a changed prompt fails loudly instead of silently going live."""

import json
import threading
from pathlib import Path
from typing import Any

from app.llm.client import LLMClient, LLMError, LLMRequest, LLMResult


class ReplayMiss(LLMError):
    pass


def _load(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row["key"]] = row
    return rows


def _result(row: dict[str, Any]) -> LLMResult:
    return LLMResult(row["text"], row["input_tokens"], row["output_tokens"], row["cost_usd"])


class ReplayClient:
    def __init__(self, path: Path) -> None:
        self._rows = _load(path)

    def complete(self, req: LLMRequest) -> LLMResult:
        row = self._rows.get(req.key())
        if row is None:
            raise ReplayMiss(f"{req.step}: no recording for key {req.key()[:12]} ({req.prompt_version})")
        return _result(row)


class RecordingClient:
    def __init__(self, inner: LLMClient, path: Path) -> None:
        self._inner = inner
        self._path = path
        self._rows = _load(path)
        self._lock = threading.Lock()  # stance calls run in parallel threads

    def complete(self, req: LLMRequest) -> LLMResult:
        key = req.key()
        with self._lock:
            if key in self._rows:
                return _result(self._rows[key])
        result = self._inner.complete(req)
        row = {
            "key": key,
            "step": req.step,
            "model": req.model,
            "prompt_version": req.prompt_version,
            "text": result.text,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cost_usd": result.cost_usd,
        }
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            self._rows[key] = row
        return result
```

Append to `app/api/deps.py`:
```python
from app.llm.client import LLMClient, default_client  # noqa: E402  (keep with the other imports at the top)


def get_llm() -> LLMClient | None:
    return default_client()


LLMDep = Annotated[LLMClient | None, Depends(get_llm)]
```
(Put the import with the other imports at the top of the file; the comment above only marks what is new.)

- [ ] **Step 5: Run the tests**

Run: `pytest tests/test_llm_client.py tests/test_recorder.py tests/test_observability.py -q`
Expected: PASS.

- [ ] **Step 6: Backend chain and commit**

```bash
ruff check . && ruff format --check . && mypy app && pytest -q && alembic check
git add app/observability.py app/llm app/api/deps.py tests/fakes.py tests/test_llm_client.py tests/test_recorder.py \
  tests/test_observability.py
git commit -m "feat(llm): OpenRouter client with strict JSON outputs, record/replay and metadata-only tracing

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Health, version, daily canary, app wiring, Vercel config

**Files:**
- Create: `app/services/canary.py`, `vercel.json`, `.vercelignore`
- Modify: `app/main.py` (full rewrite below), `app/api/internal.py` (add the canary route)
- Test: `tests/test_main.py`, `tests/test_canary.py`

**Interfaces:**
- Consumes: Task 3 `require_cron`/`CronDep`/`SessionDep`, Task 4 `LLMDep`, `build_request`, `complete_model`, `LLMError`, `OPENROUTER_BASE_URL`.
- Produces: `GET /api/health` → `HealthOut {status: "ok"|"degraded", db: "ok"|"unavailable", canary: CanaryStatus|null}` (`CanaryStatus {ok, at, credits_usd}`), 503 when the database is down; `GET /api/version` → `VersionOut {version, models}`; `canary.PROMPT_VERSION = "canary@1"`, `CanaryOut`, `run_canary(session, client, http, settings) -> CanaryRun`, `remaining_credits(http, api_key) -> float | None`; `main.CANARY_STALE = timedelta(hours=36)`, `main.mount_frontend(target, directory)`.

- [ ] **Step 1: Write the failing tests**

`tests/test_main.py`:
```python
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

import app.main as main
from app.db.models import CanaryRun
from app.main import app, mount_frontend


@pytest.fixture
def client(db: Engine) -> TestClient:
    return TestClient(app)


def _canary(db: Engine, ok: bool, age: timedelta, credits: float | None = 7.5) -> None:
    with Session(db) as s:
        s.add(CanaryRun(ok=ok, at=datetime.now(UTC) - age, detail={"credits_usd": credits}))
        s.commit()


def test_healthy_with_no_canary_yet(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert '"status":"ok"' in r.text  # the exact bytes UptimeRobot's keyword monitor looks for
    assert r.json() == {"status": "ok", "db": "ok", "canary": None}


def test_healthy_with_a_fresh_passing_canary(client: TestClient, db: Engine) -> None:
    _canary(db, ok=True, age=timedelta(hours=2))
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["canary"]["ok"] is True and body["canary"]["credits_usd"] == 7.5


def test_degraded_when_the_last_canary_failed(client: TestClient, db: Engine) -> None:
    _canary(db, ok=True, age=timedelta(hours=30))
    _canary(db, ok=False, age=timedelta(hours=1))
    r = client.get("/api/health")
    assert r.status_code == 200 and '"status":"degraded"' in r.text


def test_degraded_when_the_canary_is_stale(client: TestClient, db: Engine) -> None:
    _canary(db, ok=True, age=timedelta(hours=40))
    assert client.get("/api/health").json()["status"] == "degraded"


def test_503_when_the_database_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    dead = create_engine("postgresql+psycopg://x:y@127.0.0.1:1/nothing_test", connect_args={"connect_timeout": 1})
    monkeypatch.setattr(main, "get_engine", lambda: dead)
    r = TestClient(app).get("/api/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "db": "unavailable"}
    assert "x:y" not in r.text


def test_version_lists_the_models(client: TestClient) -> None:
    body = client.get("/api/version").json()
    assert body["version"] == "2.0.0.dev0"
    assert set(body["models"]) == {"stance", "draft", "classify", "judge"}


def test_ui_is_served_when_built(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<div id=root></div>")
    target = FastAPI()
    mount_frontend(target, tmp_path)
    assert TestClient(target).get("/").text == "<div id=root></div>"


def test_no_ui_mount_without_a_build(tmp_path: Path) -> None:
    target = FastAPI()
    mount_frontend(target, tmp_path / "missing")
    assert TestClient(target).get("/").status_code == 404


def test_pending_traces_are_flushed_after_the_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    flushed = []
    monkeypatch.setattr(main, "has_pending", lambda: True)
    monkeypatch.setattr(main, "flush_traces", lambda: flushed.append(1))
    client.get("/api/version")
    assert flushed == [1]
```

`tests/test_canary.py`:
```python
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.api.deps import get_llm
from app.db.models import CanaryRun
from app.llm.client import LLMError
from app.main import app
from app.services import canary
from app.services.canary import remaining_credits, run_canary
from app.settings import get_settings
from tests.fakes import FakeLLM

OK = '{"ok": true}'


@pytest.fixture(autouse=True)
def four_models(monkeypatch: pytest.MonkeyPatch) -> None:
    for step, model in (("STANCE", "m/a"), ("DRAFT", "m/b"), ("CLASSIFY", "m/c"), ("JUDGE", "m/d")):
        monkeypatch.setenv(f"{step}_MODEL", model)


def _http(payload: object, status: int = 200) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, json=payload)))


def test_every_model_answers_and_credits_are_fine(db: Engine) -> None:
    with Session(db) as s:
        row = run_canary(s, FakeLLM([OK] * 4), _http({"data": {"limit_remaining": 5.0}}), get_settings())
    assert row.ok is True
    assert row.detail == {"models": {"m/a": "ok", "m/b": "ok", "m/c": "ok", "m/d": "ok"}, "credits_usd": 5.0}


def test_a_failing_model_fails_the_canary(db: Engine) -> None:
    with Session(db) as s:
        row = run_canary(s, FakeLLM([OK, LLMError("draft: NotFoundError"), OK, OK]), _http({}), get_settings())
    assert row.ok is False
    assert row.detail["models"]["m/b"].startswith("draft: NotFoundError")


def test_low_credits_fail_the_canary(db: Engine) -> None:
    with Session(db) as s:
        row = run_canary(s, FakeLLM([OK] * 4), _http({"data": {"limit_remaining": 0.4}}), get_settings())
    assert row.ok is False and row.detail["credits_usd"] == 0.4


def test_no_key_fails_the_canary(db: Engine) -> None:
    with Session(db) as s:
        row = run_canary(s, None, _http({}), get_settings())
    assert row.ok is False and "OPENROUTER_API_KEY" in row.detail["error"]


@pytest.mark.parametrize(
    ("payload", "status", "expected"),
    [
        ({"data": {"limit_remaining": 3.5}}, 200, 3.5),
        ({"data": {"limit_remaining": None}}, 200, None),
        ({"error": "nope"}, 500, None),
        ("not an object", 200, None),
    ],
)
def test_remaining_credits(payload: object, status: int, expected: float | None) -> None:
    assert remaining_credits(_http(payload, status), "k") == expected


def test_remaining_credits_survives_network_errors() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    assert remaining_credits(httpx.Client(transport=httpx.MockTransport(boom)), "k") is None


def test_canary_endpoint_needs_the_cron_secret_and_feeds_health(
    db: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(canary, "remaining_credits", lambda http, key: 9.0)
    app.dependency_overrides[get_llm] = lambda: FakeLLM([OK] * 4)
    try:
        c = TestClient(app)
        assert c.get("/api/internal/canary").status_code == 401
        r = c.get("/api/internal/canary", headers={"Authorization": "Bearer test-cron-secret"})
        assert r.status_code == 200 and r.json()["ok"] is True
        assert c.get("/api/health").json()["canary"]["credits_usd"] == 9.0
    finally:
        app.dependency_overrides.clear()
    with Session(db) as s:
        assert len(s.scalars(select(CanaryRun)).all()) == 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest tests/test_main.py tests/test_canary.py -q`
Expected: FAIL (`ImportError: cannot import name 'mount_frontend'`, `No module named 'app.services.canary'`).

- [ ] **Step 3: Implement the canary**

`app/services/canary.py`:
```python
"""Daily check that each configured model still answers and the OpenRouter key still has credit, so a retired
model ID or an empty balance shows up in /api/health (and UptimeRobot's email) before a visitor finds it."""

from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.models import CanaryRun
from app.llm.client import OPENROUTER_BASE_URL, LLMClient, LLMError, build_request, complete_model
from app.settings import Settings

PROMPT_VERSION = "canary@1"


class CanaryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


def remaining_credits(http: httpx.Client, api_key: str) -> float | None:
    """This key's remaining credit when the key has a limit (set one in OpenRouter); otherwise None."""
    try:
        r = http.get(f"{OPENROUTER_BASE_URL}/key", headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        r.raise_for_status()
        body = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    value = body.get("data", {}).get("limit_remaining") if isinstance(body, dict) else None
    return float(value) if isinstance(value, int | float) else None


def run_canary(session: Session, client: LLMClient | None, http: httpx.Client, settings: Settings) -> CanaryRun:
    detail: dict[str, Any] = {"models": {}, "credits_usd": None}
    ok = True
    if client is None:
        detail["error"] = "OPENROUTER_API_KEY is not set"
        ok = False
    else:
        for model in sorted(set(settings.models().values())):
            req = build_request(
                "canary", model, PROMPT_VERSION, "Reply with JSON only.", 'Return {"ok": true}.', CanaryOut, 200
            )
            try:
                complete_model(client, req, CanaryOut)
                detail["models"][model] = "ok"
            except LLMError as exc:
                detail["models"][model] = str(exc)[:200]
                ok = False
        credits = remaining_credits(http, settings.openrouter_api_key)
        detail["credits_usd"] = credits
        if credits is not None and credits < settings.canary_min_credits_usd:
            ok = False
    row = CanaryRun(ok=ok, detail=detail)
    session.add(row)
    session.commit()
    return row
```

Append to `app/api/internal.py` (imports at the top of the file):
```python
import httpx

from app.api.deps import LLMDep
from app.services.canary import run_canary


@router.get("/api/internal/canary")
def run_daily_canary(_: CronDep, session: SessionDep, llm: LLMDep) -> dict[str, object]:
    with httpx.Client() as http:
        row = run_canary(session, llm, http, get_settings())
    return {"ok": row.ok, "detail": row.detail}
```

- [ ] **Step 4: Rewrite `app/main.py`**

```python
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from app import __version__
from app.api import internal, workspace
from app.db.session import get_engine
from app.observability import flush as flush_traces
from app.observability import has_pending
from app.settings import get_settings

log = logging.getLogger(__name__)
CANARY_STALE = timedelta(hours=36)  # daily cron + slack; older means the cron stopped

app = FastAPI(
    title="VART", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None
)


class FlushTraces:
    """Pure ASGI: after the response is fully sent, deliver pending traces."""

    def __init__(self, inner: ASGIApp) -> None:
        self.inner = inner

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await self.inner(scope, receive, send)
        finally:
            if scope["type"] == "http" and has_pending():
                await run_in_threadpool(flush_traces)


app.add_middleware(FlushTraces)
app.include_router(workspace.router)
app.include_router(internal.router)


class CanaryStatus(BaseModel):
    ok: bool
    at: datetime
    credits_usd: float | None


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    db: Literal["ok", "unavailable"]
    canary: CanaryStatus | None = None


class VersionOut(BaseModel):
    version: str
    models: dict[str, str]


@app.get("/api/health", response_model=HealthOut, responses={503: {"model": HealthOut}})
def health() -> JSONResponse:
    try:
        with get_engine().connect() as conn, conn.begin():
            conn.execute(text("SET LOCAL statement_timeout = '2s'"))
            row = conn.execute(
                text("SELECT ok, at, detail -> 'credits_usd' FROM canary_runs ORDER BY at DESC LIMIT 1")
            ).first()
    except (SQLAlchemyError, RuntimeError):  # RuntimeError: DATABASE_URL unset
        log.exception("health check: database unavailable")
        return JSONResponse({"status": "degraded", "db": "unavailable"}, status_code=503)
    body: dict[str, object] = {"status": "ok", "db": "ok", "canary": None}
    if row is not None:
        ok, at, credits = row
        body["canary"] = {"ok": bool(ok), "at": at.isoformat(), "credits_usd": credits}
        if not ok or at < datetime.now(UTC) - CANARY_STALE:
            body["status"] = "degraded"
    return JSONResponse(body)


@app.get("/api/version")
def version() -> VersionOut:
    return VersionOut(version=__version__, models=get_settings().models())


def mount_frontend(target: FastAPI, directory: Path) -> None:
    """Serve the built UI as low-priority routes; skipped when there is no build (tests, API-only dev)."""
    if directory.is_dir():
        target.frontend("/", directory=directory, fallback="index.html")


mount_frontend(app, Path(__file__).resolve().parent.parent / "public")
```

- [ ] **Step 5: Vercel configuration**

`vercel.json`:
```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "buildCommand": "cd web && npm ci && npm run build",
  "functions": {
    "app/main.py": { "excludeFiles": "web/**" }
  },
  "crons": [
    { "path": "/api/internal/cleanup", "schedule": "0 5 * * *" },
    { "path": "/api/internal/canary", "schedule": "0 6 * * *" }
  ]
}
```

`.vercelignore`:
```
# Keep the deployed function small: the runtime needs only app/. Plan 4 un-ignores data/ for the sample pack.
.venv
.env*
docs
tests
evals
scripts
datakit
data
.github
.mypy_cache
.ruff_cache
.pytest_cache
.hypothesis
.claude
migrations
alembic.ini
docker-compose.yml
openapi.json
/public
web/node_modules
web/test-results
web/playwright-report
```

- [ ] **Step 6: Run the tests, backend chain, commit**

```bash
pytest tests/test_main.py tests/test_canary.py -q
ruff check . && ruff format --check . && mypy app && pytest -q && alembic check
git add app/main.py app/api/internal.py app/services/canary.py vercel.json .vercelignore tests/test_main.py \
  tests/test_canary.py
git commit -m "feat: health with database and canary status, daily model canary, Vercel config

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
Expected: all PASS.

---

### Task 6: Monochrome React shell with generated API types (Opus)

**Files:**
- Create: `web/package.json`, `web/package-lock.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/tsconfig.app.json`, `web/tsconfig.node.json`, `web/.oxlintrc.json`, `web/playwright.config.ts`, `web/index.html`, `web/public/favicon.svg`, `web/src/main.tsx`, `web/src/index.css`, `web/src/App.tsx`, `web/src/App.test.tsx`, `web/src/lib/api.ts`, `web/src/lib/api.test.ts`, `web/src/lib/api-types.ts` (generated), `web/src/components/ErrorBoundary.tsx`, `web/src/components/StatusPanel.tsx`, `web/src/components/StatusPanel.test.tsx`, `web/src/test/setup.ts`, `web/e2e/smoke.spec.ts`, `scripts/export_openapi.py`, `openapi.json` (generated)
- Test: `tests/test_openapi.py`

**Interfaces:**
- Consumes: `GET /api/workspace`, `GET /api/health` (`HealthOut`), `app.openapi()`.
- Produces: `npm run gen:api` (writes `src/lib/api-types.ts` from `../openapi.json`); `src/lib/api.ts` exports `ApiError`, `errorMessage(res)`, `messageOf(e)`, `request<T>(path, init)`, `ensureWorkspace()`, `resetWorkspaceForTests()`, `getHealth(): Promise<Health>`, `type Health = components["schemas"]["HealthOut"]`; `scripts/export_openapi.py` writes `openapi.json`.

- [ ] **Step 1: Export the schema and test that it is current**

`scripts/export_openapi.py`:
```python
"""Write the API's OpenAPI schema to openapi.json (committed). The frontend generates its types from it, and CI
fails when either file is stale."""

import json
from pathlib import Path

from app.main import app

OUT = Path(__file__).resolve().parent.parent / "openapi.json"


def render() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    OUT.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    main()
```

`tests/test_openapi.py`:
```python
import json

from scripts.export_openapi import OUT, render


def test_committed_openapi_is_current() -> None:
    assert OUT.read_text(encoding="utf-8") == render(), "run: python scripts/export_openapi.py && cd web && npm run gen:api"


def test_health_and_workspace_are_public_and_internal_routes_are_not() -> None:
    paths = set(json.loads(render())["paths"])
    assert {"/api/health", "/api/version", "/api/workspace", "/api/workspace/reset"} <= paths
    assert not [p for p in paths if p.startswith("/api/internal")]
```

Run: `pytest tests/test_openapi.py -q` → Expected: FAIL (`FileNotFoundError: openapi.json`). Then `python scripts/export_openapi.py` and re-run → PASS.

- [ ] **Step 2: Scaffold `web/` from PriorPath's configuration**

`web/package.json`:
```json
{
  "name": "web",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "oxlint",
    "preview": "vite preview",
    "test": "vitest run",
    "e2e": "playwright test",
    "gen:api": "openapi-typescript ../openapi.json -o src/lib/api-types.ts"
  },
  "dependencies": {
    "@tailwindcss/vite": "^4.3.3",
    "react": "^19.2.8",
    "react-dom": "^19.2.8",
    "tailwindcss": "^4.3.3"
  },
  "devDependencies": {
    "@playwright/test": "^1.63.0",
    "@testing-library/jest-dom": "^7.0.1",
    "@testing-library/react": "^16.3.3",
    "@testing-library/user-event": "^14.6.7",
    "@types/node": "^24.13.3",
    "@types/react": "^19.2.18",
    "@types/react-dom": "^19.2.7",
    "@vitejs/plugin-react": "^6.1.1",
    "jsdom": "^30.1.1",
    "oxlint": "^1.81.0",
    "typescript": "~6.0.2",
    "vite": "^8.3.0",
    "vitest": "^5.0.3"
  },
  "engines": {
    "node": ">=22"
  }
}
```
Then:
```bash
cd web && npm install && npm install -D openapi-typescript@latest
```
If npm reports a TypeScript peer-dependency conflict for openapi-typescript, install the newest openapi-typescript whose peer range accepts the installed TypeScript (`npm view openapi-typescript peerDependencies` per version); do not downgrade TypeScript and do not use `--force`.

Copy these files verbatim from PriorPath (`~/Desktop/portfolio/projects/PriorPath/web/`): `vite.config.ts`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`, `.oxlintrc.json`, `playwright.config.ts`, `src/test/setup.ts`. They contain no PriorPath-specific text. `src/index.css` is the single line `@import "tailwindcss";`.

`web/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>VART — security questionnaire answering</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`web/public/favicon.svg`:
```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" fill="#000"/><path d="M8 8l8 16 8-16" fill="none" stroke="#fff" stroke-width="3"/></svg>
```

`web/src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

Generate the types: `npm run gen:api` → creates `src/lib/api-types.ts`.

- [ ] **Step 3: Write the failing frontend tests**

`web/src/lib/api.test.ts`:
```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, ensureWorkspace, getHealth, resetWorkspaceForTests } from "./api";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("api", () => {
  beforeEach(() => resetWorkspaceForTests());

  it("creates the workspace once", async () => {
    const fetchMock = vi.fn(async () => json(200, { created_at: "2026-10-03T12:00:00Z" }));
    vi.stubGlobal("fetch", fetchMock);
    await ensureWorkspace();
    await ensureWorkspace();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reads a degraded health body from a 503", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(503, { status: "degraded", db: "unavailable" })));
    await expect(getHealth()).resolves.toEqual({ status: "degraded", db: "unavailable" });
  });

  it("turns other failures into ApiError with the server's detail", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(429, { detail: "too many new sessions" })));
    await expect(ensureWorkspace()).rejects.toEqual(new ApiError(429, "too many new sessions"));
  });
});
```

`web/src/components/StatusPanel.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StatusPanel from "./StatusPanel";

const respond = (status: number, body: unknown) =>
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));

describe("StatusPanel", () => {
  it("shows a healthy system in words", async () => {
    respond(200, { status: "ok", db: "ok", canary: { ok: true, at: "2026-10-03T06:00:00Z", credits_usd: 8 } });
    render(<StatusPanel />);
    expect(await screen.findByText("Database")).toBeInTheDocument();
    expect(screen.getAllByText("OK").length).toBeGreaterThanOrEqual(2);
  });

  it("says when the model check has not run", async () => {
    respond(200, { status: "ok", db: "ok", canary: null });
    render(<StatusPanel />);
    expect(await screen.findByText("Not run yet")).toBeInTheDocument();
  });

  it("shows an unavailable database", async () => {
    respond(503, { status: "degraded", db: "unavailable" });
    render(<StatusPanel />);
    expect(await screen.findByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("Degraded")).toBeInTheDocument();
  });
});
```

`web/src/App.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { resetWorkspaceForTests } from "./lib/api";

describe("App", () => {
  beforeEach(() => resetWorkspaceForTests());

  it("shows the product name and the system status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        new Response(
          JSON.stringify(url.endsWith("/api/workspace") ? { created_at: "2026-10-03T12:00:00Z" } : { status: "ok", db: "ok", canary: null }),
          { status: 200 },
        ),
      ),
    );
    render(<App />);
    expect(screen.getByRole("heading", { name: "VART" })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "System status" })).toBeInTheDocument();
  });

  it("explains when the demo cannot start", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "the demo is full right now" }), { status: 503 })));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("the demo is full right now");
  });
});
```

Run: `npm test` → Expected: FAIL (modules `./api`, `./StatusPanel`, `./App` not found).

- [ ] **Step 4: Implement the shell**

`web/src/lib/api.ts`:
```ts
import type { components } from "./api-types";

export type Health = components["schemas"]["HealthOut"];

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join("; ");
  } catch {
    // not JSON
  }
  return `Request failed (${res.status})`;
}

export function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin", ...init });
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res));
  return (await res.json()) as T;
}

let workspace: Promise<void> | undefined;

/** Test-only: forget the memoized workspace. */
export function resetWorkspaceForTests() {
  workspace = undefined;
}

/** Creates (or loads) this browser's workspace. Must resolve before any workspace call. */
export function ensureWorkspace(): Promise<void> {
  workspace ??= request<{ created_at: string }>("/api/workspace").then(
    () => undefined,
    (e) => {
      workspace = undefined;
      throw e;
    },
  );
  return workspace;
}

/** Health answers 503 with a body when the database is down; both are readable states, not errors. */
export async function getHealth(): Promise<Health> {
  const res = await fetch("/api/health", { credentials: "same-origin" });
  if (res.status === 200 || res.status === 503) return (await res.json()) as Health;
  throw new ApiError(res.status, await errorMessage(res));
}
```

`web/src/components/StatusPanel.tsx`:
```tsx
import { useEffect, useState } from "react";
import { getHealth, messageOf, type Health } from "../lib/api";

export default function StatusPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealth().then(setHealth, (e) => setError(messageOf(e)));
  }, []);

  if (error) return <p role="alert" className="border border-black p-3">Status check failed: {error}</p>;
  if (!health) return <p>Checking status…</p>;
  const canary = health.canary;
  return (
    <section aria-label="System status" className="border border-black bg-white p-4">
      <h2 className="font-semibold">System status</h2>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
        <dt>Overall</dt>
        <dd>{health.status === "ok" ? "OK" : "Degraded"}</dd>
        <dt>Database</dt>
        <dd>{health.db === "ok" ? "OK" : "Unavailable"}</dd>
        <dt>Model check</dt>
        <dd>{!canary ? "Not run yet" : canary.ok ? `OK (${new Date(canary.at).toLocaleDateString()})` : "Failing"}</dd>
      </dl>
    </section>
  );
}
```

`web/src/components/ErrorBoundary.tsx`:
```tsx
import { Component, type ReactNode } from "react";

export default class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    console.error("Screen render failed", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="space-y-3 border border-black bg-white p-4">
        <p className="font-medium">Something went wrong on this screen.</p>
        <button type="button" onClick={() => window.location.reload()} className="rounded bg-black px-3 py-1.5 text-white">
          Reload
        </button>
      </div>
    );
  }
}
```

`web/src/App.tsx`:
```tsx
import { useEffect, useState } from "react";
import ErrorBoundary from "./components/ErrorBoundary";
import StatusPanel from "./components/StatusPanel";
import { ensureWorkspace, messageOf } from "./lib/api";

export default function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ensureWorkspace().then(
      () => setReady(true),
      (e) => setError(messageOf(e)),
    );
  }, []);

  return (
    <div className="min-h-screen bg-neutral-100 text-black">
      <header className="border-b border-black bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-baseline gap-x-6 gap-y-1 px-4 py-3">
          <h1 className="text-xl font-semibold">VART</h1>
          <span className="text-sm text-neutral-600">
            Security questionnaire answering · synthetic demo data · every answer cites its source
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        {error ? (
          <p role="alert" className="border border-black p-3 font-medium">Couldn't start the demo: {error}</p>
        ) : !ready ? (
          <p>Loading…</p>
        ) : (
          <ErrorBoundary>
            <StatusPanel />
            <p className="text-sm text-neutral-700">
              The questionnaire workspace arrives in the next build. This page checks that the app, its database and
              its model connection are alive.
            </p>
          </ErrorBoundary>
        )}
      </main>
    </div>
  );
}
```

`web/e2e/smoke.spec.ts`:
```ts
import { expect, test } from "@playwright/test";

test("home page loads and reports a healthy system", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "VART" })).toBeVisible();
  const status = page.getByRole("region", { name: "System status" });
  await expect(status).toBeVisible();
  await expect(status.getByText("Database")).toBeVisible();
  const cookies = await page.context().cookies();
  expect(cookies.some((c) => c.name === "vart_ws" && c.httpOnly)).toBe(true);
});
```

- [ ] **Step 5: Run everything**

```bash
cd web && npm run lint && npm test && npm run build && npm run e2e && cd ..
python scripts/export_openapi.py && (cd web && npm run gen:api) && git diff --exit-code openapi.json web/src/lib/api-types.ts
pytest tests/test_openapi.py -q
```
Expected: lint clean, Vitest PASS, build writes `public/`, Playwright PASS (it builds, starts uvicorn against `DATABASE_URL`; export `DATABASE_URL=$TEST_DATABASE_URL`, `SESSION_SECRET=dev`, and run `alembic upgrade head` first), no drift.

- [ ] **Step 6: Commit**

```bash
git add web scripts/export_openapi.py openapi.json tests/test_openapi.py
git commit -m "feat(web): monochrome shell with system status and API types generated from OpenAPI

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Mechanical gates — sponsor-name check, colour scan

**Files:**
- Create: `scripts/sponsor_check.sh`, `scripts/check_monochrome.py`
- Test: `tests/test_sponsor_check.py`, `tests/test_check_monochrome.py`

**Interfaces:**
- Produces: `bash scripts/sponsor_check.sh` (reads `SPONSOR_NAME` from the environment; exit 0 clean, 1 found, non-zero when unset); `check_monochrome.violations(path) -> list[str]`, CLI `python scripts/check_monochrome.py`.
- The sponsor's name is never written into any file. In CI it comes from the GitHub repository variable `SPONSOR_NAME` (set in Task 9); locally the lead passes it on the command line.

- [ ] **Step 1: Write the failing tests**

`tests/test_sponsor_check.py`:
```python
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "sponsor_check.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
                   check=True, capture_output=True)


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def _run(repo: Path, name: str | None = "Acmecorp") -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "SPONSOR_NAME"}
    if name:
        env["SPONSOR_NAME"] = name
    return subprocess.run(["bash", str(SCRIPT)], cwd=repo, env=env, capture_output=True, text=True)


def test_a_clean_repo_passes(tmp_path: Path) -> None:
    assert _run(_repo(tmp_path, {"a.md": "hello"})).returncode == 0


def test_the_name_in_a_file_fails_in_any_case(tmp_path: Path) -> None:
    assert _run(_repo(tmp_path, {"a.md": "built for ACMECORP"})).returncode == 1


def test_the_name_in_a_file_name_fails(tmp_path: Path) -> None:
    assert _run(_repo(tmp_path, {"acmecorp_policy.txt": "x"})).returncode == 1


def test_the_name_only_in_history_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"a.md": "copied from Acmecorp"})
    (repo / "a.md").write_text("clean now")
    _git(repo, "commit", "-qam", "scrub")
    assert _run(repo).returncode == 1


def test_an_unset_name_is_an_error_not_a_pass(tmp_path: Path) -> None:
    assert _run(_repo(tmp_path, {"a.md": "hello"}), name=None).returncode != 0
```

`tests/test_check_monochrome.py`:
```python
from pathlib import Path

from scripts.check_monochrome import violations


def _file(tmp_path: Path, text: str, name: str = "a.tsx") -> Path:
    p = tmp_path / name
    p.write_text(text)
    return p


def test_colour_utilities_are_flagged(tmp_path: Path) -> None:
    found = violations(_file(tmp_path, '<div className="bg-blue-500 text-red-600 hover:border-emerald-300">'))
    assert len(found) == 3


def test_neutral_black_and_white_are_allowed(tmp_path: Path) -> None:
    assert violations(_file(tmp_path, '<p className="bg-neutral-100 text-black border-white">')) == []


def test_tinted_greys_are_flagged_to_keep_one_grey_family(tmp_path: Path) -> None:
    assert violations(_file(tmp_path, '<p className="text-slate-700 bg-zinc-50">'))


def test_hex_colours_must_be_grey(tmp_path: Path) -> None:
    assert violations(_file(tmp_path, ".a { color: #ff0000 }", "a.css"))
    assert violations(_file(tmp_path, ".a { color: #333; background: #f5f5f5 }", "a.css")) == []


def test_colour_functions_are_flagged(tmp_path: Path) -> None:
    assert violations(_file(tmp_path, ".a { color: rgb(10 20 30) }", "a.css"))
```

Run: `pytest tests/test_sponsor_check.py tests/test_check_monochrome.py -q` → Expected: FAIL (script missing; `ModuleNotFoundError: scripts.check_monochrome`).

- [ ] **Step 2: Implement the sponsor-name check**

`scripts/sponsor_check.sh`:
```bash
#!/usr/bin/env bash
# Fail when the hackathon sponsor's name appears in any tracked file, file name or commit (spec section 3, rule 1).
# The name comes from $SPONSOR_NAME (a GitHub repository variable in CI), so no file in the repo holds it.
# Anything copied from the hackathon version of VART carries the name, so this catches copies of its code and data.
set -euo pipefail
name="${SPONSOR_NAME:?SPONSOR_NAME is not set}"
found=0
if git grep -l -I -i -F -e "$name" -- . ; then
  echo "sponsor-check: the name appears in the files above" >&2
  found=1
fi
if git ls-files | grep -i -F -e "$name" ; then
  echo "sponsor-check: the name appears in the file names above" >&2
  found=1
fi
# No grep -q: an early exit would SIGPIPE git log, and pipefail would turn a match into a miss.
if git log --all -p | grep -i -F -e "$name" > /dev/null ; then
  echo "sponsor-check: the name appears in git history" >&2
  found=1
fi
[ "$found" -eq 0 ] && echo "sponsor-check: clean"
exit "$found"
```
`chmod +x scripts/sponsor_check.sh`.

- [ ] **Step 3: Implement the colour scan**

`scripts/check_monochrome.py`:
```python
"""Fail on colour in the UI. Allowed: black, white, transparent, current, Tailwind neutral-* and grey hex values."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PALETTES = (
    "red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose"
    "|slate|gray|zinc|stone|taupe|mauve|mist|olive"
)
UTILITY = re.compile(rf"\b[a-z]+(?:-[a-z]+)*-(?:{PALETTES})-(?:50|[1-9]00|950)\b")
HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
FUNCTION = re.compile(r"\b(?:rgba?|hsla?|oklch|oklab|lab|lch)\(")


def _grey(hex_colour: str) -> bool:
    h = hex_colour[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return h[0:2].lower() == h[2:4].lower() == h[4:6].lower()


def violations(path: Path) -> list[str]:
    found = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        found += [f"{path}:{n}: colour utility {m.group(0)}" for m in UTILITY.finditer(line)]
        found += [f"{path}:{n}: non-grey colour {m.group(0)}" for m in HEX.finditer(line) if not _grey(m.group(0))]
        found += [f"{path}:{n}: colour function {m.group(0)}" for m in FUNCTION.finditer(line)]
    return found


def main() -> int:
    files = [p for p in (ROOT / "web" / "src").rglob("*") if p.suffix in {".ts", ".tsx", ".css"}]
    files += [ROOT / "web" / "index.html", ROOT / "web" / "public" / "favicon.svg"]
    problems = [v for f in files if f.exists() and f.name != "api-types.ts" for v in violations(f)]
    for p in problems:
        print(p, file=sys.stderr)
    print(f"monochrome: {len(files)} files checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and the scripts**

```bash
pytest tests/test_sponsor_check.py tests/test_check_monochrome.py -q
python scripts/check_monochrome.py
```
Expected: tests PASS; `monochrome: … 0 problems`. (The lead runs the sponsor check on this repo with the real name in Task 9.)

- [ ] **Step 5: Backend chain and commit**

```bash
ruff check . && ruff format --check . && mypy app scripts && pytest -q && alembic check
git add scripts/sponsor_check.sh scripts/check_monochrome.py tests/test_sponsor_check.py tests/test_check_monochrome.py
git commit -m "feat: sponsor-name and monochrome checks that fail the build

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: CI workflow, deploy smoke script, progress log

**Files:**
- Create: `.github/workflows/ci.yml`, `scripts/smoke.py`, `docs/PROGRESS.md`
- Test: `tests/test_smoke.py`

**Interfaces:**
- Consumes: every command above; Plan 1B's `python -m datakit.validate all` (present once the data lane merges).
- Produces: CI jobs `backend`, `frontend`, `gates`, `e2e`; `scripts/smoke.py BASE_URL` (exit 0 when the deploy is alive).

- [ ] **Step 1: Write the failing smoke-script test**

`tests/test_smoke.py`:
```python
import httpx
import pytest

from scripts.smoke import check


def _transport(health: dict[str, object], root: str = '<div id="root"></div>') -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(200, text=root)
        if request.url.path == "/api/health":
            return httpx.Response(200, json=health)
        if request.url.path == "/api/workspace":
            return httpx.Response(200, json={"created_at": "2026-10-03T00:00:00Z"},
                                  headers={"set-cookie": "vart_ws=abc; HttpOnly; Path=/"})
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "2.0.0.dev0", "models": {}})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_a_healthy_deploy_passes() -> None:
    with httpx.Client(base_url="https://x", transport=_transport({"status": "ok", "db": "ok", "canary": None})) as c:
        assert check(c).startswith("ok")


def test_a_missing_ui_fails() -> None:
    with httpx.Client(base_url="https://x", transport=_transport({"status": "ok"}, root="Not Found")) as c, \
            pytest.raises(SystemExit, match="UI"):
        check(c)


def test_a_degraded_deploy_fails() -> None:
    with httpx.Client(base_url="https://x", transport=_transport({"status": "degraded"})) as c, \
            pytest.raises(SystemExit, match="health"):
        check(c)
```

Run: `pytest tests/test_smoke.py -q` → Expected: FAIL (`No module named 'scripts.smoke'`).

- [ ] **Step 2: Implement the smoke script**

`scripts/smoke.py`:
```python
"""Check a deployed VART: UI served from the CDN, health ok, workspace cookie, version.

  python scripts/smoke.py https://vart.vercel.app
"""

import argparse

import httpx


def fail(what: str, got: object) -> SystemExit:
    return SystemExit(f"FAIL: {what} — got {str(got)[:300]}")


def check(c: httpx.Client) -> str:
    root = c.get("/")
    if root.status_code != 200 or 'id="root"' not in root.text:
        raise fail("UI at / (the PriorPath cdn=true incident looked like this)", root.text)
    health = c.get("/api/health")
    if health.status_code != 200 or '"status":"ok"' not in health.text.replace(" ", ""):
        raise fail("health", health.text)
    ws = c.get("/api/workspace")
    if ws.status_code != 200 or "vart_ws=" not in ws.headers.get("set-cookie", ""):
        raise fail("workspace cookie", ws.headers)
    version = c.get("/api/version").json()
    return f"ok: version {version['version']}, canary {health.json().get('canary')}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_url")
    args = ap.parse_args()
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=60) as c:
        print(check(c))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run: `pytest tests/test_smoke.py -q` → Expected: PASS.

- [ ] **Step 3: Write the CI workflow**

`.github/workflows/ci.yml`:
```yaml
name: ci
on:
  push:
  pull_request:
jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg17
        env:
          POSTGRES_USER: vart
          POSTGRES_PASSWORD: vart
          POSTGRES_DB: vart_test
        ports:
          - 5434:5432
        options: >-
          --health-cmd "pg_isready -U vart"
          --health-interval 5s --health-timeout 5s --health-retries 10
    env:
      TEST_DATABASE_URL: postgresql+psycopg://vart:vart@localhost:5434/vart_test
      DATABASE_URL: postgresql+psycopg://vart:vart@localhost:5434/vart_test
      REQUIRE_DB: "1"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version-file: .python-version
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - run: pip install -r requirements-dev.txt
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy app scripts datakit
      - run: pytest -q
      - run: alembic check
      - run: python scripts/export_openapi.py && git diff --exit-code openapi.json
      - run: python -m datakit.validate all
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm test
      - run: npm run build
      - run: npm run gen:api && git diff --exit-code src/lib/api-types.ts
  gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version-file: .python-version
      - run: bash scripts/sponsor_check.sh
        env:
          SPONSOR_NAME: ${{ vars.SPONSOR_NAME }}
      - run: python scripts/check_monochrome.py
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  e2e:
    runs-on: ubuntu-latest
    needs: [backend, frontend]
    services:
      postgres:
        image: pgvector/pgvector:pg17
        env:
          POSTGRES_USER: vart
          POSTGRES_PASSWORD: vart
          POSTGRES_DB: vart_test
        ports:
          - 5434:5432
        options: >-
          --health-cmd "pg_isready -U vart"
          --health-interval 5s --health-timeout 5s --health-retries 10
    env:
      DATABASE_URL: postgresql+psycopg://vart:vart@localhost:5434/vart_test
      SESSION_SECRET: ci-session-secret
      CRON_SECRET: ci-cron-secret
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version-file: .python-version
          cache: pip
          cache-dependency-path: requirements-dev.txt
      - run: pip install -r requirements-dev.txt
      - run: alembic upgrade head
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm ci
        working-directory: web
      - run: npx playwright install --with-deps chromium
        working-directory: web
      - run: npm run e2e
        working-directory: web
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: web/test-results
```
Locally, verify every command in the `backend`, `frontend` and `gates` jobs except `mypy … datakit`, `python -m datakit.validate all` (Plan 1B), gitleaks (GitHub only) and the sponsor check (the lead runs it in Task 9; an unset `SPONSOR_NAME` fails it by design).

- [ ] **Step 4: Write the progress log**

`docs/PROGRESS.md`:
```markdown
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
```

- [ ] **Step 5: Backend chain and commit**

```bash
ruff check . && ruff format --check . && mypy app scripts && pytest -q && alembic check
git add .github/workflows/ci.yml scripts/smoke.py tests/test_smoke.py docs/PROGRESS.md
git commit -m "ci: backend, frontend, gates and e2e jobs; deploy smoke script; progress log

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Release — merge lanes, publish, hello-world deploy (Tarun approves first)

This task is run by the lead with Tarun. Present the numbered list below as one release plan; start only after Tarun's explicit OK. Steps marked **(Tarun's terminal)** need a secret or his accounts; ping him with the exact command.

**Files:**
- Modify: `docs/PROGRESS.md` (live URL, release notes)

- [ ] **Step 1: Merge the lanes and run everything on `main`**

```bash
cd ~/Desktop/portfolio/projects/VART
git merge --no-ff plan1-foundation -m "merge: Plan 1A foundation"
git merge --no-ff plan1-data -m "merge: Plan 1B dev data"
ruff check . && ruff format --check . && mypy app scripts datakit && pytest -q && alembic check
python -m datakit.validate all && python scripts/check_monochrome.py
(cd web && npm ci && npm run lint && npm test && npm run build && npm run e2e)
python scripts/export_openapi.py && (cd web && npm run gen:api) && git diff --exit-code openapi.json web/src/lib/api-types.ts
SPONSOR_NAME='<the sponsor company name>' bash scripts/sponsor_check.sh
```
Expected: all green, including `sponsor-check: clean`. Then the final Opus review of `main`.

- [ ] **Step 2: Point the old hackathon clones at the renamed repo (lead, before any rename)**

Only the git configuration is touched; no file in those folders is opened.
```bash
for d in VART VART-adapter VART-merge VART-ui VART-ui-real; do
  git -C ~/Desktop/portfolio/projects/ai-money-hackathon/$d remote set-url origin https://github.com/Ttheegela/VART-hackathon.git
done
for d in VART VART-adapter VART-merge VART-ui VART-ui-real; do
  git -C ~/Desktop/portfolio/projects/ai-money-hackathon/$d remote get-url origin
done
```
Expected: five lines ending `VART-hackathon.git`.

- [ ] **Step 3: Rename the old repo (outward)**

```bash
gh repo rename VART-hackathon -R Ttheegela/VART --yes
gh repo view Ttheegela/VART-hackathon --json name,visibility
```
Expected: `{"name":"VART-hackathon","visibility":"PRIVATE"}`.

- [ ] **Step 4: Create the public repo, set the check's variable, push (outward)**

The variable must exist before the first push, because the first push starts CI.
```bash
gh repo create Ttheegela/VART --public \
  --description "Fills vendor security questionnaires from a company's own documents, with cited, code-decided answers" \
  --source . --remote origin
gh variable set SPONSOR_NAME -R Ttheegela/VART --body '<the sponsor company name>'
git push -u origin main
gh repo edit Ttheegela/VART --add-topic fastapi --add-topic llm --add-topic rag --add-topic security-questionnaire
```
Then check the first CI run once (`gh run list -R Ttheegela/VART --limit 1`); fix any red job before Step 5.

- [ ] **Step 5: Neon project and migration (Tarun's console + terminal)**

In the Neon console: create project `vart`, Postgres 17, region AWS us-east-1. Copy the **direct** connection string (for migrations) and the **pooled** one (for Vercel). Then:
```bash
read -rs DATABASE_URL && export DATABASE_URL   # paste the DIRECT URL
alembic upgrade head && alembic current
unset DATABASE_URL
```

- [ ] **Step 6: Vercel project, secrets, Git connection (Tarun's terminal)**

```bash
cd ~/Desktop/portfolio/projects/VART
npx vercel link --yes --project vart        # creates the project if missing; note the assigned *.vercel.app domain
read -rs DB && printf %s "$DB" | npx vercel env add DATABASE_URL production && unset DB    # paste the POOLED URL
python -c "import secrets; print(secrets.token_urlsafe(32))" | npx vercel env add SESSION_SECRET production
CRON_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
printf %s "$CRON_SECRET" | npx vercel env add CRON_SECRET production
# In OpenRouter: create key "vart-prod" with a credit limit (e.g. $10) so the canary can read limit_remaining.
read -rs KEY && printf %s "$KEY" | npx vercel env add OPENROUTER_API_KEY production && unset KEY
npx vercel git connect                      # production branch: main
```
Optional Langfuse (new project "vart"): add `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` the same way.

- [ ] **Step 7: Deploy and verify**

```bash
npx vercel deploy --prod                    # or push to main now that Git is connected
python scripts/smoke.py https://<assigned-domain>
curl -s -H "Authorization: Bearer $CRON_SECRET" https://<assigned-domain>/api/internal/canary   # Tarun's terminal
unset CRON_SECRET
curl -s https://<assigned-domain>/api/health
```
Expected: smoke `ok: …`; canary `{"ok":true,…}`; health shows `"status":"ok"` with the canary's credits. Open `/` in a real browser (Tarun uses Comet) and confirm the status panel.

- [ ] **Step 8: Uptime monitors (Tarun, UptimeRobot dashboard)**

1. HTTP(s) monitor `https://<assigned-domain>/`, every 5 minutes.
2. Keyword monitor `https://<assigned-domain>/api/health`, keyword `"status":"ok"` (alert when **not** present), every 60 minutes.

- [ ] **Step 9: Record the release**

Update `docs/PROGRESS.md` (live URL, Plan 1A/1B done, what each check showed), commit and push. Update `~/Desktop/portfolio/PROJECT_PLAN.md`'s tracker row for VART (E3).
