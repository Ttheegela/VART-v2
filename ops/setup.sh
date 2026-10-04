#!/usr/bin/env bash
# VART v2 infrastructure: Neon + Vercel + OpenRouter + UptimeRobot, one idempotent phase at a time.
# Run it in your own terminal (the hidden prompts need one). Re-running a phase never duplicates anything.
#
#   ops/setup.sh accounts [--langfuse] [--replace NAME[,NAME]]
#   ops/setup.sh release
#   ops/setup.sh uptime   [--domain HOST]
#   ops/setup.sh status   [--domain HOST]
#   ops/setup.sh --help
#
# Secrets never reach the screen, a file or a command line: they live in shell variables or pipes, and the EXIT trap
# unsets them. Flags and API fields were checked against: Vercel CLI 62.2.0 (npx --no-install vercel), neonctl 8.0.5
# (a shim for the `neon` CLI), UptimeRobot API v3 (https://uptimerobot.com/api/v3/), OpenRouter GET /api/v1/key.
set -euo pipefail
set +x # never trace: secrets pass through shell variables

# ---------------------------------------------------------------- project settings
GH_REPO=Ttheegela/VART-v2
PROD_BRANCH=main
VERCEL_SCOPE=theegelatarun-4606
VERCEL_PROJECT=vart
VERCEL_FRAMEWORK=fastapi
NEON_PROJECT=vart
NEON_REGION=aws-us-east-1
NEON_PG_VERSION=17
NEONCTL_VERSION=8.0.5
OPENROUTER_KEY_NAME=vart-prod
OPENROUTER_KEY_URL=https://openrouter.ai/api/v1/key
UPTIMEROBOT_API=https://api.uptimerobot.com/v3
UI_INTERVAL_S=300
HEALTH_INTERVAL_S=3600
HEALTH_KEYWORD='"status":"ok"'
ENV_TARGETS="production preview"
CRON_PATHS="/api/internal/cleanup /api/internal/canary"

PHASE=""
LANGFUSE=0
REPLACE=""
DOMAIN=""
ORG_FLAG=""
ROOT="" WORK=""
# secrets (unset on exit) and cached lookups
db_url="" direct_url="" session_secret="" cron_secret="" or_key="" lf_pk="" lf_sk="" lf_url="" ur_key="" UR_LIST=""
pj="" env_pairs="" neon_id="" neon_region="" domain=""

usage() {
  cat <<EOF
Usage: ops/setup.sh <phase> [options]

Phases (each is safe to re-run):
  accounts  Neon project, Vercel project + local link, Vercel env vars. Git is NOT connected and nothing is deployed.
            Checks: gh, node/npx, python3, Vercel CLI logged in as $VERCEL_SCOPE, Neon login (browser if needed), repo.
            Hidden prompts, in order: OpenRouter API key; with --langfuse also Langfuse public key, Langfuse secret
            key, then a visible optional Langfuse base URL. Create the OpenRouter key first: name $OPENROUTER_KEY_NAME,
            credit limit \$10, at https://openrouter.ai/settings/keys
  release   Run on $PROD_BRANCH after the app is merged and pushed (Plan 1A Task 9). Checks the branch is clean and
            equal to origin, then: alembic upgrade head (Neon direct URL), fresh CRON_SECRET, connect Git, deploy
            production, scripts/smoke.py, /api/internal/canary, /api/health. No prompts.
  uptime    UptimeRobot monitors on the production domain: HTTP on / every ${UI_INTERVAL_S}s, keyword on /api/health
            every ${HEALTH_INTERVAL_S}s that alerts when ${HEALTH_KEYWORD} is absent. Hidden prompt: UptimeRobot
            API key (just press Enter to get the manual steps instead).
  status    Names-only summary: Neon project, Vercel project, env var names, GitHub variable names, health.

Options:
  --langfuse        accounts: also store LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_BASE_URL
  --replace NAMES   accounts: overwrite these existing variables (comma separated), e.g. OPENROUTER_API_KEY
  --domain HOST     uptime, status: production host to use instead of asking Vercel
  -h, --help        this text

Environment: NEON_API_KEY skips the Neon browser login; NEON_ORG_ID selects an organization when your Neon
account has several.
EOF
}

# ---------------------------------------------------------------- output helpers
ok() { printf 'OK    %s\n' "$*"; }
info() { printf '      %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*"; }
fail() {
  printf 'FAIL  %s\n' "$*" >&2
  exit 1
}
step() { printf '\n== %s\n' "$*"; }
has_line() { case $'\n'"$1"$'\n' in *$'\n'"$2"$'\n'*) return 0 ;; esac; return 1; }
trim() {
  local s=$1
  s=${s#"${s%%[![:space:]]*}"}
  s=${s%"${s##*[![:space:]]}"}
  printf '%s' "$s"
}
redact() { # stdin -> stdout, every argument replaced by [hidden]
  local s v
  s=$(cat)
  for v in "$@"; do
    if [ -n "$v" ]; then s=${s//"$v"/[hidden]}; fi
  done
  printf '%s\n' "$s"
}
read_secret() { # PROMPT VARNAME: hidden input into the named variable
  local _v
  [ -t 0 ] || fail "this step needs a terminal for a hidden prompt: run the script in your own terminal"
  stty -echo # before the prompt is printed, so nothing typed or pasted can be echoed
  printf '%s: ' "$1" >&2
  IFS= read -rs _v || true
  stty echo
  printf '\n' >&2
  eval "$2=\$(trim \"\$_v\")"
}
new_secret() { python3 -c 'import secrets; print(secrets.token_urlsafe(32))'; }

init() {
  ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
  cd "$ROOT"
  WORK=$(mktemp -d "${TMPDIR:-/tmp}/vart-setup.XXXXXX")
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
}
cleanup() {
  if [ -t 0 ]; then stty echo 2>/dev/null || true; fi
  unset db_url direct_url session_secret cron_secret or_key lf_pk lf_sk lf_url ur_key UR_LIST
  if [ -n "$WORK" ]; then rm -rf "$WORK"; fi
}

# ---------------------------------------------------------------- CLI wrappers
# Vercel: --scope pins the account; agent-detection variables are dropped so the output is the same everywhere.
# vc = quiet, no stdin (stderr kept for vc_err); vc_in = stdin comes from the caller; vc_live = stderr visible.
vc() { env -u AI_AGENT -u CLAUDECODE -u CLAUDE_CODE npx --no-install vercel "$@" --scope "$VERCEL_SCOPE" </dev/null 2>"$WORK/vc.err"; }
vc_in() { env -u AI_AGENT -u CLAUDECODE -u CLAUDE_CODE npx --no-install vercel "$@" --scope "$VERCEL_SCOPE" 2>"$WORK/vc.err"; }
vc_live() { env -u AI_AGENT -u CLAUDECODE -u CLAUDE_CODE npx --no-install vercel "$@" --scope "$VERCEL_SCOPE" </dev/null; }
vc_err() { sed -e '/^Vercel CLI [0-9.]*$/d' -e '/^$/d' "$WORK/vc.err" | head -15 | redact "$@" || true; }
# Neon: run from a scratch directory so the CLI can never drop a .neon file into the repo.
neonctl() { (cd "$WORK" && npx -y "neonctl@$NEONCTL_VERSION" "$@"); }

# ---------------------------------------------------------------- prerequisites
need() { command -v "$1" >/dev/null 2>&1 || fail "$1 not found. $2"; }

check_tools() {
  local ver maj min who
  need gh "Install: brew install gh, then: gh auth login"
  need node "Install Node 20.19 or newer: https://nodejs.org"
  need npx "Install Node 20.19 or newer: https://nodejs.org"
  need python3 "Install Python 3: brew install python"
  need curl "curl is missing"
  need git "git is missing"
  ver=$(node -p 'process.versions.node')
  IFS=. read -r maj min _ <<EOF2
$ver
EOF2
  if [ "$maj" -lt 20 ] || { [ "$maj" -eq 20 ] && [ "$min" -lt 19 ]; }; then
    fail "Node $ver is too old: the Vercel and Neon CLIs need 20.19 or newer"
  fi
  who=$(gh api user --jq .login 2>/dev/null) || fail "gh is not logged in. Run: gh auth login"
  ok "tools present (node $ver); gh logged in as $who"
}

check_vercel() {
  local who
  vc --version >/dev/null ||
    fail "the Vercel CLI is not installed. Run once: npx vercel --version (accept the install), then re-run"
  who=$(vc whoami) || {
    vc_err
    fail "the Vercel CLI is not logged in. Run: npx vercel login"
  }
  [ "$who" = "$VERCEL_SCOPE" ] ||
    fail "Vercel is logged in as '$who' but this project lives in '$VERCEL_SCOPE'. Run: npx vercel logout && npx vercel login"
  ok "Vercel CLI logged in as $who"
}

check_neon() {
  local login orgs n
  info "Neon CLI: neonctl@$NEONCTL_VERSION via npx (the first run downloads it)"
  login=$(neonctl me --output json | python3 -c 'import json, sys; print(json.load(sys.stdin).get("login", ""))' 2>/dev/null) || login=""
  if [ -z "$login" ]; then
    info "Neon: not signed in. A browser window opens (neonctl auth)."
    neonctl auth || fail "neonctl auth failed"
    login=$(neonctl me --output json | python3 -c 'import json, sys; print(json.load(sys.stdin).get("login", ""))' 2>/dev/null) ||
      fail "neonctl me still fails after signing in"
  fi
  ok "Neon logged in as $login"
  # Without --org-id the Neon CLI may ask which organization on stdout, which a script cannot show: always pass it.
  if [ -n "${NEON_ORG_ID:-}" ]; then
    ORG_FLAG="--org-id $NEON_ORG_ID"
    info "Neon organization: $NEON_ORG_ID"
    return 0
  fi
  orgs=$(neonctl orgs list --output json | python3 -c '
import json, sys
d = json.load(sys.stdin)
for o in (d if isinstance(d, list) else d.get("organizations", [])):
    print(o.get("id", ""), o.get("name", ""))') || orgs=""
  n=$(printf '%s\n' "$orgs" | awk 'NF' | wc -l | tr -d ' ')
  if [ "$n" -gt 1 ]; then
    printf '%s\n' "$orgs" | sed 's/^/      /'
    fail "your Neon account has $n organizations (ids above). Re-run with: NEON_ORG_ID=<id> ops/setup.sh $PHASE"
  elif [ "$n" -eq 1 ]; then
    ORG_FLAG="--org-id ${orgs%% *}"
    info "Neon organization: ${orgs%% *}"
  fi
}

# ---------------------------------------------------------------- Neon
neon_lookup() { # prints "ID REGION" for the project named $NEON_PROJECT, "AMBIGUOUS", or nothing
  # shellcheck disable=SC2086 # ORG_FLAG is "--org-id ID" or empty: it must split
  neonctl projects list --output json $ORG_FLAG | python3 -c '
import json, sys
d = json.load(sys.stdin)
ps = d["projects"] if isinstance(d, dict) else d
hits = [p for p in ps if isinstance(p, dict) and p.get("name") == sys.argv[1]]
if len(hits) > 1:
    print("AMBIGUOUS")
else:
    for p in hits:
        print(p["id"], p.get("region_id", ""))' "$NEON_PROJECT"
}

neon_find() { # sets neon_id and neon_region; empty neon_id when there is no such project
  local found
  found=$(neon_lookup) || fail "could not list Neon projects (message above)"
  [ "$found" != AMBIGUOUS ] || fail "more than one Neon project is named '$NEON_PROJECT'; rename or delete the extra one"
  neon_id=${found%% *}
  neon_region=${found#* }
}

neon_url() { # prints a connection string (a secret): call only inside $( ). Arguments: --pooled, or none for direct
  local i u
  for i in 1 2 3; do
    if u=$(neonctl connection-string --project-id "$neon_id" "$@"); then
      printf '%s' "$u"
      return 0
    fi
    sleep 4
  done
  return 1
}

neon_project() {
  step "Neon project '$NEON_PROJECT'"
  neon_find
  if [ -z "$neon_id" ]; then
    info "not found: creating it ($NEON_REGION, Postgres $NEON_PG_VERSION)"
    # --no-secrets keeps the credentials out of the output; it is discarded anyway
    # shellcheck disable=SC2086
    neonctl projects create --name "$NEON_PROJECT" --region-id "$NEON_REGION" --pg-version "$NEON_PG_VERSION" \
      --no-secrets --output json $ORG_FLAG >/dev/null || fail "neonctl projects create failed (message above)"
    neon_find
    [ -n "$neon_id" ] || fail "the new Neon project is not visible yet; re-run in a minute"
    ok "created Neon project $NEON_PROJECT (id $neon_id, $neon_region)"
  else
    ok "Neon project $NEON_PROJECT exists (id $neon_id, $neon_region)"
  fi
  if [ "$neon_region" != "$NEON_REGION" ]; then warn "region is $neon_region, expected $NEON_REGION"; fi
}

# ---------------------------------------------------------------- Vercel
vercel_has_project() {
  local js
  js=$(vc project ls --format json --filter "$VERCEL_PROJECT") || {
    vc_err
    fail "could not list Vercel projects"
  }
  printf '%s' "$js" | python3 -c '
import json, sys
sys.exit(0 if any(p.get("name") == sys.argv[1] for p in json.load(sys.stdin).get("projects", [])) else 1)' "$VERCEL_PROJECT"
}

load_project() { # pj = project JSON. It can hold env var records: only ever parse it, never print it.
  pj=$(vc api "/v9/projects/$VERCEL_PROJECT") || {
    vc_err
    fail "could not read the Vercel project '$VERCEL_PROJECT'"
  }
}
pjget() { printf '%s' "$pj" | python3 -c 'import json, sys
d = json.load(sys.stdin)
v = eval(sys.argv[1])
print("" if v is None else v)' "$1"; }
git_link() { # "TYPE ORG/REPO PRODUCTION_BRANCH", or nothing when no repository is connected
  printf '%s' "$pj" | python3 -c '
import json, sys
l = json.load(sys.stdin).get("link") or {}
if l.get("repo"):
    print(l.get("type", ""), "%s/%s" % (l.get("org", ""), l["repo"]), l.get("productionBranch", ""))'
}
prod_domain() { # the production host: <project>.vercel.app when present, else the first non-branch alias
  printf '%s' "$pj" | python3 -c '
import json, sys
al = ((json.load(sys.stdin).get("targets") or {}).get("production") or {}).get("alias") or []
pref = sys.argv[1] + ".vercel.app"
c = [a for a in al if a == pref] or [a for a in al if "-git-" not in a] or al
print(c[0] if c else "")' "$VERCEL_PROJECT"
}
cron_list() { printf '%s' "$pj" | python3 -c '
import json, sys
for x in (json.load(sys.stdin).get("crons") or {}).get("definitions") or []:
    print(x.get("path", ""), x.get("schedule", ""))'; }

refresh_env_pairs() { # env_pairs = lines "NAME target": names and targets only, by construction
  env_pairs=$(vc api "/v10/projects/$VERCEL_PROJECT/env" | python3 -c '
import json, sys
for e in json.load(sys.stdin).get("envs", []):
    t = e.get("target") or []
    for x in ([t] if isinstance(t, str) else t):
        print(e.get("key", ""), x)') || {
    vc_err
    fail "could not read the Vercel env var names"
  }
}
print_env_names() {
  printf '%s\n' "$env_pairs" | python3 -c '
import sys
m = {}
for line in sys.stdin:
    k, _, t = line.strip().partition(" ")
    if k:
        m.setdefault(k, []).append(t)
for k in sorted(m):
    print("      %-22s %s" % (k, ", ".join(sorted(m[k]))))'
}
should_set() { # NAME TARGET: true when the variable must be written (missing, or listed in --replace)
  if ! has_line "$env_pairs" "$1 $2"; then return 0; fi
  case ",$REPLACE," in *",$1,"*) return 0 ;; esac
  return 1
}
set_env() { # NAME TARGET VALUE: the value reaches Vercel through a pipe, never through a command line
  if printf %s "$3" | vc_in env add "$1" "$2" --force --sensitive --yes >/dev/null; then
    ok "$1 set for $2"
  else
    vc_err "$3"
    fail "could not set $1 for $2"
  fi
}

guard_gitignore() {
  local p
  for p in .vercel .env.local; do
    git check-ignore -q "$p" || fail "$p is not git-ignored here. Add .vercel and .env.* to .gitignore first, then re-run"
  done
}

ensure_link() { # link this directory to the project (idempotent). vercel link also drops a short-lived OIDC token
  local pid linked before had_env=0 # into .env.local; remove that file again when this run created it.
  pid=$(pjget 'd.get("id")')
  linked=$(python3 -c 'import json; print(json.load(open(".vercel/project.json")).get("projectId", ""))' 2>/dev/null || true)
  if [ "$linked" = "$pid" ]; then
    ok "directory linked to $VERCEL_PROJECT (.vercel/project.json)"
    return 0
  fi
  guard_gitignore
  if [ -e .env.local ]; then had_env=1; fi
  before=$(git status --porcelain)
  vc link --yes --project "$VERCEL_PROJECT" >/dev/null || {
    vc_err
    fail "vercel link failed"
  }
  if [ "$had_env" = 0 ]; then rm -f .env.local; fi
  [ "$(git status --porcelain)" = "$before" ] || fail "vercel link changed files in the repo (see git status); revert them, then re-run"
  linked=$(python3 -c 'import json; print(json.load(open(".vercel/project.json")).get("projectId", ""))' 2>/dev/null || true)
  [ "$linked" = "$pid" ] || fail "vercel link did not create .vercel/project.json for $VERCEL_PROJECT"
  ok "linked $ROOT to $VERCEL_PROJECT (.vercel is git-ignored)"
}

vercel_project() {
  local fw
  step "Vercel project '$VERCEL_PROJECT'"
  if vercel_has_project; then
    ok "project exists"
  else
    info "not found: creating it (no Git connection)"
    vc project add "$VERCEL_PROJECT" >/dev/null || {
      vc_err
      fail "vercel project add failed"
    }
    vercel_has_project || fail "the new Vercel project is not visible yet; re-run in a minute"
    ok "project created"
  fi
  load_project
  fw=$(pjget 'd.get("framework")')
  if [ -z "$fw" ]; then
    vc project update "$VERCEL_PROJECT" --framework "$VERCEL_FRAMEWORK" --yes >/dev/null || {
      vc_err
      fail "could not set the framework preset to $VERCEL_FRAMEWORK"
    }
    load_project
    fw=$(pjget 'd.get("framework")')
  fi
  if [ "$fw" = "$VERCEL_FRAMEWORK" ]; then ok "framework preset: $fw"; else warn "framework preset is '$fw', expected $VERCEL_FRAMEWORK"; fi
  if [ -n "$(git_link)" ]; then info "Git: already connected ($(git_link))"; else info "Git: not connected (the release phase does that)"; fi
  ensure_link
}

# ---------------------------------------------------------------- secrets: prompts and env vars
ask_openrouter() {
  local resp code limits
  printf '\nOpenRouter key (used for production and preview). Create it first:\n'
  printf '  1. open https://openrouter.ai/settings/keys\n  2. Create Key: name "%s", credit limit $10\n' "$OPENROUTER_KEY_NAME"
  printf '  3. paste it below (input is hidden)\n'
  read_secret "OpenRouter API key" or_key
  [ -n "$or_key" ] || fail "no key entered; nothing was stored. Re-run when you have the key"
  resp=$(printf 'Authorization: Bearer %s\n' "$or_key" | curl -sS -m 30 -H @- -w '\n%{http_code}' "$OPENROUTER_KEY_URL") ||
    fail "could not reach OpenRouter"
  code=${resp##*$'\n'}
  [ "$code" = 200 ] || fail "OpenRouter rejected the key (HTTP $code). Check you pasted the whole key, then re-run"
  limits=$(printf '%s' "${resp%$'\n'*}" | python3 -c '
import json, sys
d = (json.load(sys.stdin) or {}).get("data") or {}
print(d.get("limit"), d.get("limit_remaining"))') || fail "unexpected answer from OpenRouter"
  case $limits in
    None*) fail "this OpenRouter key has no credit limit. Set \$10 on the key at https://openrouter.ai/settings/keys, then re-run" ;;
  esac
  ok "OpenRouter key accepted (credit limit ${limits% *}, remaining ${limits#* })"
}

ask_langfuse() {
  printf '\nLangfuse keys (Langfuse project settings, API keys):\n'
  read_secret "Langfuse public key" lf_pk
  read_secret "Langfuse secret key" lf_sk
  IFS= read -rp "Langfuse base URL (Enter = SDK default, the EU cloud; US is https://us.cloud.langfuse.com): " lf_url || true
  lf_url=$(trim "$lf_url")
  [ -n "$lf_pk" ] && [ -n "$lf_sk" ] || fail "both Langfuse keys are required with --langfuse"
}

env_vars() {
  local t n need_db=0 need_sess=0 need_or=0 need_lf=0
  step "Vercel environment variables ($ENV_TARGETS)"
  for n in $(printf '%s' "$REPLACE" | tr ',' ' '); do
    case $n in
      DATABASE_URL | SESSION_SECRET | OPENROUTER_API_KEY | LANGFUSE_PUBLIC_KEY | LANGFUSE_SECRET_KEY | LANGFUSE_BASE_URL) ;;
      *) fail "--replace: unknown variable '$n'" ;;
    esac
  done
  refresh_env_pairs
  for t in $ENV_TARGETS; do
    if should_set DATABASE_URL "$t"; then need_db=1; fi
    if should_set SESSION_SECRET "$t"; then need_sess=1; fi
    if should_set OPENROUTER_API_KEY "$t"; then need_or=1; fi
    if [ "$LANGFUSE" = 1 ]; then
      if should_set LANGFUSE_PUBLIC_KEY "$t" || should_set LANGFUSE_SECRET_KEY "$t"; then need_lf=1; fi
    fi
  done
  if [ "$need_db" = 1 ]; then
    db_url=$(neon_url --pooled) || fail "could not get the pooled Neon connection string (message above)"
    case $db_url in postgres://* | postgresql://*) ;; *) fail "unexpected Neon connection string format" ;; esac
    case $db_url in *-pooler.*) ;; *) fail "Neon returned a non-pooled connection string" ;; esac
  fi
  if [ "$need_sess" = 1 ]; then session_secret=$(new_secret); fi
  if [ "$need_or" = 1 ]; then ask_openrouter; fi
  if [ "$need_lf" = 1 ]; then ask_langfuse; fi
  for t in $ENV_TARGETS; do
    if should_set DATABASE_URL "$t"; then set_env DATABASE_URL "$t" "$db_url"; else ok "DATABASE_URL already set for $t"; fi
    if should_set SESSION_SECRET "$t"; then set_env SESSION_SECRET "$t" "$session_secret"; else ok "SESSION_SECRET already set for $t"; fi
    if should_set OPENROUTER_API_KEY "$t"; then set_env OPENROUTER_API_KEY "$t" "$or_key"; else ok "OPENROUTER_API_KEY already set for $t"; fi
    if [ "$LANGFUSE" = 1 ]; then
      if should_set LANGFUSE_PUBLIC_KEY "$t"; then set_env LANGFUSE_PUBLIC_KEY "$t" "$lf_pk"; else ok "LANGFUSE_PUBLIC_KEY already set for $t"; fi
      if should_set LANGFUSE_SECRET_KEY "$t"; then set_env LANGFUSE_SECRET_KEY "$t" "$lf_sk"; else ok "LANGFUSE_SECRET_KEY already set for $t"; fi
      if [ -n "$lf_url" ]; then set_env LANGFUSE_BASE_URL "$t" "$lf_url"; fi
    fi
  done
  refresh_env_pairs
}

# ---------------------------------------------------------------- phase: accounts
repo_check() {
  local r
  r=$(gh repo view "$GH_REPO" --json visibility,defaultBranchRef --jq '.visibility + " " + .defaultBranchRef.name' 2>/dev/null) ||
    fail "GitHub repo $GH_REPO not found (or not visible to gh)"
  ok "GitHub repo $GH_REPO ($r)"
  case $r in *" $PROD_BRANCH") ;; *) warn "default branch is not $PROD_BRANCH; Vercel's production branch follows it" ;; esac
}

phase_accounts() {
  echo "Creates the Neon and Vercel projects and stores the env vars. Git stays disconnected, nothing is deployed."
  check_tools
  check_vercel
  check_neon
  repo_check
  neon_project
  vercel_project
  env_vars
  step "Summary (names only)"
  info "Neon:   project $NEON_PROJECT, id $neon_id, $neon_region"
  info "Vercel: project $VERCEL_PROJECT, linked from $ROOT, Git not connected"
  info "Vercel environment variables:"
  print_env_names
  echo
  ok "accounts done. Next, once Plan 1A Task 9 has the app on $PROD_BRANCH and pushed: ops/setup.sh release"
}

# ---------------------------------------------------------------- phase: release
release_checks() {
  local f ci
  step "Release checks"
  for f in alembic.ini vercel.json scripts/smoke.py app/main.py; do
    [ -f "$f" ] || fail "$f not found: the app code must be on $PROD_BRANCH (Plan 1A Task 9, steps 1-2) before releasing"
  done
  [ "$(git rev-parse --abbrev-ref HEAD)" = "$PROD_BRANCH" ] || fail "not on $PROD_BRANCH: run: git switch $PROD_BRANCH"
  [ -z "$(git status --porcelain)" ] || fail "the working tree has uncommitted changes; commit or stash them first"
  git fetch -q origin "$PROD_BRANCH" || fail "could not fetch origin/$PROD_BRANCH"
  [ "$(git rev-parse HEAD)" = "$(git rev-parse "origin/$PROD_BRANCH")" ] ||
    fail "local $PROD_BRANCH differs from origin/$PROD_BRANCH: push it first (git push origin $PROD_BRANCH)"
  ok "on $PROD_BRANCH, clean, equal to origin/$PROD_BRANCH ($(git rev-parse --short HEAD))"
  ci=$(gh run list -R "$GH_REPO" --commit "$(git rev-parse HEAD)" --json status,conclusion 2>/dev/null | python3 -c '
import json, sys
print(",".join(sorted({r.get("conclusion") or r.get("status") or "?" for r in json.load(sys.stdin)})))' 2>/dev/null) || ci=""
  case $ci in
    success) ok "CI is green for this commit" ;;
    "") warn "no CI run found for this commit (Plan 1A Task 9 wants green CI before releasing)" ;;
    *failure* | *cancelled* | *timed_out*) fail "CI is not green for this commit ($ci). Fix it first (Plan 1A Task 9, step 2)" ;;
    *) warn "CI status for this commit: $ci. Wait for success before releasing" ;;
  esac
}

migrate() {
  local alembic out rc pw
  step "Database migration (Neon direct connection)"
  neon_find
  [ -n "$neon_id" ] || fail "Neon project '$NEON_PROJECT' not found. Run: ops/setup.sh accounts"
  direct_url=$(neon_url) || fail "could not get the direct Neon connection string (message above)"
  case $direct_url in *-pooler.*) fail "got a pooled connection string; migrations need the direct one" ;; esac
  if [ -x .venv/bin/alembic ]; then alembic=.venv/bin/alembic; elif command -v alembic >/dev/null 2>&1; then alembic=alembic; else
    fail "alembic not found. Create the venv: python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt"
  fi
  pw=$(printf '%s' "$direct_url" | python3 -c 'import sys, urllib.parse as u; print(u.urlsplit(sys.stdin.read().strip()).password or "")')
  rc=0
  out=$(DATABASE_URL="$direct_url" "$alembic" upgrade head 2>&1) || rc=$?
  printf '%s\n' "$out" | redact "$direct_url" "$pw" | sed 's/^/      /'
  [ "$rc" = 0 ] || fail "alembic upgrade head failed (exit $rc)"
  out=$(DATABASE_URL="$direct_url" "$alembic" current 2>&1) || out=""
  case $out in *"(head)"*) ;; *) fail "the database is not at alembic head after the upgrade" ;; esac
  ok "alembic upgrade head: database is at head"
  unset direct_url pw out
}

connect_git() {
  local g gtype grepo gbranch
  step "Git connection"
  load_project
  g=$(git_link)
  if [ -z "$g" ]; then
    # `vercel git connect` exits 1 when the repo is already connected, so it only runs when nothing is connected
    vc git connect "https://github.com/$GH_REPO" --yes >/dev/null || {
      vc_err
      fail "could not connect $GH_REPO. Make sure the Vercel GitHub app can see it: https://github.com/settings/installations -> Vercel -> Configure -> add $GH_REPO"
    }
    load_project
    g=$(git_link)
  fi
  [ -n "$g" ] || fail "Git connection did not stick; check the project's Git settings in Vercel"
  # shellcheck disable=SC2086
  set -- $g
  gtype=$1 grepo=$2 gbranch=${3:-}
  [ "$gtype" = github ] && [ "$grepo" = "$GH_REPO" ] ||
    fail "the project is connected to $grepo ($gtype), not $GH_REPO: run npx vercel git disconnect, then re-run"
  ok "Git connected: $grepo"
  if [ "$gbranch" = "$PROD_BRANCH" ]; then ok "production branch: $gbranch"; else warn "production branch is '$gbranch', expected $PROD_BRANCH (Project Settings -> Environments -> Production)"; fi
}

deploy_prod() {
  local dep d p
  step "Production deploy"
  info "building on Vercel (a few minutes)"
  dep=$(vc_live deploy --prod --yes) || fail "deploy failed (output above). Logs: npx vercel inspect <deployment-url> --logs"
  ok "deployed: $dep"
  load_project
  domain=$(prod_domain)
  [ -n "$domain" ] || fail "no production domain found after the deploy"
  ok "production domain: https://$domain"
  d=$(cron_list)
  for p in $CRON_PATHS; do
    if has_line "$(printf '%s\n' "$d" | sed 's/ .*//')" "$p"; then ok "cron registered: $p"; else warn "cron not registered: $p"; fi
  done
}

run_smoke() {
  local py i out
  step "Smoke test"
  py=python3
  if [ -x .venv/bin/python ]; then py=.venv/bin/python; fi
  for i in 1 2 3; do
    if out=$("$py" scripts/smoke.py "https://$domain" 2>&1); then
      ok "$out"
      return 0
    fi
    info "attempt $i failed: $(printf '%s' "$out" | tail -n 3 | head -c 500)"
    sleep 10
  done
  fail "smoke test failed three times. If the page is a Vercel login, turn off Vercel Authentication for production (Project Settings -> Deployment Protection)"
}

run_canary() { # returns 0 when /api/internal/canary answers {"ok": true}
  local resp code body
  step "Canary and health"
  resp=$(printf 'Authorization: Bearer %s\n' "$cron_secret" | curl -sS -m 180 -H @- -w '\n%{http_code}' "https://$domain/api/internal/canary") || {
    warn "canary request failed"
    return 1
  }
  code=${resp##*$'\n'}
  body=${resp%$'\n'*}
  if [ "$code" = 200 ] && printf '%s' "$body" | python3 -c 'import json, sys; sys.exit(0 if json.load(sys.stdin).get("ok") is True else 1)' 2>/dev/null; then
    ok "canary ok: $(printf '%s' "$body" | head -c 500)"
    return 0
  fi
  warn "canary not ok (HTTP $code): $(printf '%s' "$body" | head -c 700)"
  return 1
}

print_health() {
  local body
  body=$(curl -sS -m 60 "https://$domain/api/health") || {
    warn "health request failed"
    return 0
  }
  info "GET /api/health -> $(printf '%s' "$body" | head -c 500)"
}

phase_release() {
  local canary_ok=1 n
  echo "Migrates Neon, sets a fresh CRON_SECRET, connects Git, deploys production, then checks it."
  check_tools
  check_vercel
  check_neon
  release_checks
  step "Vercel project"
  vercel_has_project || fail "Vercel project '$VERCEL_PROJECT' not found. Run: ops/setup.sh accounts"
  load_project
  ensure_link
  migrate
  step "Cron secret and env check"
  cron_secret=$(new_secret)
  set_env CRON_SECRET production "$cron_secret"
  refresh_env_pairs
  for n in DATABASE_URL SESSION_SECRET OPENROUTER_API_KEY CRON_SECRET; do
    has_line "$env_pairs" "$n production" || fail "$n is missing for production. Run: ops/setup.sh accounts"
  done
  ok "production env vars present: DATABASE_URL SESSION_SECRET OPENROUTER_API_KEY CRON_SECRET"
  connect_git
  deploy_prod
  run_smoke
  run_canary || canary_ok=0
  print_health
  echo
  if [ "$canary_ok" = 1 ]; then
    ok "release done: https://$domain. Next: ops/setup.sh uptime; open the site in a real browser and check the status panel"
  else
    fail "released at https://$domain but the canary is not ok (see above). Fix the cause and re-run: ops/setup.sh release"
  fi
}

# ---------------------------------------------------------------- phase: uptime
UR_CODE="" UR_BODY=""
ur() { # METHOD PATH [JSON]: sets UR_CODE and UR_BODY. Bodies can carry per-monitor API keys: parse them, never print them.
  local resp n=0
  while :; do
    if [ -n "${3:-}" ]; then
      resp=$(printf 'Authorization: Bearer %s\n' "$ur_key" | curl -sS -m 60 -X "$1" -H @- -H 'Content-Type: application/json' \
        --data-binary "$3" -w '\n%{http_code}' "$UPTIMEROBOT_API$2") || fail "could not reach UptimeRobot"
    else
      resp=$(printf 'Authorization: Bearer %s\n' "$ur_key" | curl -sS -m 60 -X "$1" -H @- \
        -w '\n%{http_code}' "$UPTIMEROBOT_API$2") || fail "could not reach UptimeRobot"
    fi
    UR_CODE=${resp##*$'\n'}
    UR_BODY=${resp%$'\n'*}
    if [ "$UR_CODE" = 429 ] && [ "$n" -lt 3 ]; then
      n=$((n + 1))
      info "UptimeRobot free plan allows 10 requests a minute; waiting 20 s"
      sleep 20
      continue
    fi
    return 0
  done
}
ur_error() { printf '%s' "$UR_BODY" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("code", ""), d.get("message", ""))
except Exception:
    print("(no details)")'; }

ur_find() { # URL KEYWORD(or empty for a plain HTTP monitor): prints the id of the matching monitor in UR_LIST, if any
  printf '%s' "$UR_LIST" | python3 -c '
import json, sys
norm = lambda u: (u or "").strip().rstrip("/").lower()
for m in json.load(sys.stdin).get("data", []):
    if norm(m.get("url")) == norm(sys.argv[1]) and (m.get("keywordValue") or "").strip() == sys.argv[2]:
        print(m["id"])
        break' "$1" "$2"
}
ur_body() { # KIND NAME URL INTERVAL CONTACT_IDS [KEYWORD]
  python3 -c '
import json, sys
kind, name, url, interval, contacts = sys.argv[1:6]
b = {"friendlyName": name, "url": url, "interval": int(interval), "timeout": 30, "httpMethodType": "GET"}
if kind == "keyword":
    b.update(type="KEYWORD", keywordType="ALERT_NOT_EXISTS", keywordCaseType="CaseSensitive", keywordValue=sys.argv[6])
else:
    b["type"] = "HTTP"
ids = [int(x) for x in contacts.split(",") if x]
if ids:
    b["assignedAlertContacts"] = [{"alertContactId": i, "threshold": 0, "recurrence": 0} for i in ids]
print(json.dumps(b))' "$@"
}

ur_ensure() { # KIND NAME URL INTERVAL CONTACT_IDS [KEYWORD]
  local id kw=${6:-}
  id=$(ur_find "$3" "$kw")
  if [ -n "$id" ]; then
    ok "monitor already exists: $2 (id $id)"
    return 0
  fi
  ur POST /monitors "$(ur_body "$@")"
  case $UR_CODE in
    200 | 201) ok "created monitor: $2 (id $(printf '%s' "$UR_BODY" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("id", "?"))'))" ;;
    *) fail "UptimeRobot refused the monitor '$2' (HTTP $UR_CODE: $(ur_error))" ;;
  esac
}

uptime_manual() {
  cat <<EOF

Manual steps (https://dashboard.uptimerobot.com, "+ New monitor"):
  1. Monitor type "HTTP(s)", URL https://$domain/ , interval 5 minutes. Pick your email as the alert contact.
  2. Monitor type "Keyword", URL https://$domain/api/health , keyword ${HEALTH_KEYWORD} , alert when the keyword
     does NOT exist (case sensitive), interval 60 minutes. Same alert contact.
EOF
}

phase_uptime() {
  local contacts
  echo "Creates two UptimeRobot monitors on the production domain (the database stays asleep except for the hourly check)."
  check_tools
  domain=$DOMAIN
  if [ -z "$domain" ]; then
    check_vercel
    vercel_has_project || fail "Vercel project '$VERCEL_PROJECT' not found. Run: ops/setup.sh accounts"
    load_project
    domain=$(prod_domain)
  fi
  [ -n "$domain" ] || fail "no production domain yet: run ops/setup.sh release first, or pass --domain HOST"
  ok "production domain: https://$domain"
  step "UptimeRobot"
  printf 'Get the key at dashboard.uptimerobot.com -> Integrations -> API (the account key).\n'
  read_secret "UptimeRobot API key (Enter to skip)" ur_key
  if [ -z "$ur_key" ]; then
    warn "no key entered: nothing created"
    uptime_manual
    return 0
  fi
  ur GET /user/me
  if [ "$UR_CODE" != 200 ]; then
    uptime_manual
    fail "UptimeRobot rejected the key (HTTP $UR_CODE: $(ur_error)). Use the account API key from Integrations -> API, or follow the manual steps above"
  fi
  ok "UptimeRobot key accepted"
  ur GET /user/alert-contacts
  [ "$UR_CODE" = 200 ] || fail "could not read alert contacts (HTTP $UR_CODE: $(ur_error))"
  contacts=$(printf '%s' "$UR_BODY" | python3 -c '
import json, sys
print(",".join(str(c["id"]) for c in json.load(sys.stdin) if isinstance(c, dict) and "id" in c))')
  if [ -z "$contacts" ]; then warn "the account has no alert contacts: add your email in the dashboard, or the monitors alert nobody"; fi
  ur GET "/monitors?limit=200"
  [ "$UR_CODE" = 200 ] || fail "could not list monitors (HTTP $UR_CODE: $(ur_error))"
  UR_LIST=$UR_BODY
  ur_ensure http "VART UI" "https://$domain/" "$UI_INTERVAL_S" "$contacts"
  ur_ensure keyword "VART health" "https://$domain/api/health" "$HEALTH_INTERVAL_S" "$contacts" "$HEALTH_KEYWORD"
  echo
  ok "uptime done: UI every ${UI_INTERVAL_S}s (CDN, no database), health every ${HEALTH_INTERVAL_S}s (keyword ${HEALTH_KEYWORD})"
}

# ---------------------------------------------------------------- phase: status
phase_status() {
  local g d
  echo "Names only: no secret is read or printed."
  check_tools
  check_vercel
  step "Neon"
  (
    check_neon
    neon_find
    if [ -n "$neon_id" ]; then info "project $NEON_PROJECT, id $neon_id, region $neon_region"; else warn "no Neon project named $NEON_PROJECT"; fi
  ) || warn "Neon could not be read (message above); the rest of the summary continues"
  step "Vercel"
  if vercel_has_project; then
    load_project
    info "project $VERCEL_PROJECT, id $(pjget 'd.get("id")'), framework $(pjget 'd.get("framework")')"
    g=$(git_link)
    if [ -n "$g" ]; then info "Git: $g"; else info "Git: not connected"; fi
    refresh_env_pairs
    info "environment variables:"
    print_env_names
    d=$(cron_list)
    if [ -n "$d" ]; then printf '%s\n' "$d" | sed 's/^/      cron: /'; else info "no crons registered yet"; fi
    domain=${DOMAIN:-$(prod_domain)}
    if [ -n "$domain" ]; then info "production URL: https://$domain"; fi
    d=$(printf '%s' "$pj" | python3 -c '
import json, sys
t = (json.load(sys.stdin).get("targets") or {}).get("production") or {}
if t:
    print(t.get("readyState", ""), t.get("url", ""))')
    if [ -n "$d" ]; then info "latest production deployment: $d"; else info "no production deployment yet"; fi
  else
    warn "no Vercel project named $VERCEL_PROJECT"
  fi
  step "GitHub"
  info "repo $GH_REPO"
  d=$(gh variable list -R "$GH_REPO" --json name --jq '.[].name' 2>/dev/null | tr '\n' ' ') || d=""
  info "variable names: ${d:-(none)}"
  step "Health"
  domain=${domain:-$DOMAIN}
  if [ -n "$domain" ]; then
    info "https://$domain/api/health -> $(curl -sS -m 60 "https://$domain/api/health" 2>&1 | head -c 500)"
  else
    info "no production domain yet"
  fi
}

# ---------------------------------------------------------------- main
main() {
  local phase=${1:-}
  case $phase in '' | -h | --help | help)
    usage
    exit 0
    ;;
  esac
  shift
  while [ $# -gt 0 ]; do
    case $1 in
      --langfuse) LANGFUSE=1 ;;
      --replace)
        [ $# -ge 2 ] || fail "--replace needs a value"
        REPLACE=$2
        shift
        ;;
      --domain)
        [ $# -ge 2 ] || fail "--domain needs a value"
        DOMAIN=$2
        shift
        ;;
      -h | --help)
        usage
        exit 0
        ;;
      *) fail "unknown option: $1 (see --help)" ;;
    esac
    shift
  done
  PHASE=$phase
  init
  case $phase in
    accounts) phase_accounts ;;
    release) phase_release ;;
    uptime) phase_uptime ;;
    status) phase_status ;;
    *) fail "unknown phase '$phase' (accounts, release, uptime, status)" ;;
  esac
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then main "$@"; fi
