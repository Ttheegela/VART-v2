# Design — VART v2

Locked design system, direction C ("console"). Future Hallmark runs read this file first; every view defers to it.
Amend intentionally, with a line in the change log at the bottom. Tokens live in `web/src/index.css` (`@theme`);
that file is the source of truth and this one explains it. Reference mockups: `design/mockups/run-grid-c.html`
(Run grid, Evidence drawer) and `design/mockups/home.html` (Home). The A and B mockups (`run-grid.html`,
`run-grid-b.html`) are kept as history only; do not build from them.

## System
- Genre · modern-minimal (B2B security tool), pushed toward an instrument: dense, ruled, driven from the keyboard
- Macrostructure · App views: Workbench (inverted top bar, a command line, a filter line, one dense list, an
  inspector drawer on the right, an inverted status line). Home: Index-First (a short paragraph, then the two ways
  in as rows), in the same chrome
- Theme · custom (vibe: "an instrument you drive from the keyboard")
- Axes · light body with dark chrome / mono / neutral (no accent hue; ink is the accent)
- Nav · N8 terminal bar: numbered views, inverted. Footer · the status line (mode, cursor, keys, credit)
- Hard rule · black, white and `neutral-*` only (`scripts/check_monochrome.py`). No hex, rgb(), oklch() under
  `web/src`. Distinctness from PriorPath comes from the single mono face, the inverted chrome, key hints on every
  action and the line-numbered citation listing.

## Tokens (`web/src/index.css`, Tailwind v4 `@theme`, aliases of neutral, black and white)
| Token | Alias | Use |
|---|---|---|
| `paper` | white | page, list, drawer body, inputs |
| `sunken` | neutral-100 | row hover, selected row, filter line, cited lines |
| `mark` | neutral-200 | the quoted span inside a cited line |
| `rule` | neutral-200 | hairline between rows |
| `rule-strong` | neutral-300 | panel edges, input borders, kbd border on paper |
| `ink` | neutral-950 | text, the list header rule, drawer edge, focus ring and selected outline on paper |
| `ink-2` | neutral-700 | answers, secondary text (10.4:1 on paper) |
| `ink-3` | neutral-600 | metadata, line numbers, column heads (7.8:1 on paper, 7.2:1 on sunken) |
| `chrome` | neutral-950 | top bar, status line, drawer header, primary button, `verified` fill |
| `chrome-2` | neutral-900 | hover on chrome, source caption band |
| `chrome-rule` | neutral-800 | kbd borders on chrome (decoration only, never text) |
| `on-chrome` | neutral-50 | text and focus ring on chrome; the current view's fill |
| `on-chrome-2` | neutral-400 | secondary text on chrome (7.9:1 on chrome, 7.1:1 on chrome-2) |

neutral-400 on paper is for the dashed `unknown` border only, never text. neutral-700 is also the `confirmed by
you` fill. Pure black is not used (ink is neutral-950).

## Type
- One family: JetBrains Mono, self-hosted via `@fontsource/jetbrains-mono` (400, 500, 700 imported in
  `web/src/main.tsx`). No Google Fonts, no second face; `font-sans` aliases mono.
- Weights: 400 body · 500 buttons, column heads, the path, the selected row · 700 wordmark, counts, the item ID in
  the drawer, cited line numbers, `CONFLICT`.
- Scale, three sizes (Tailwind's names, C's values): `text-xs` 11px/1.5 (kbd, labels, column heads, line listings,
  status line, metadata) · `text-sm` 13px/1.55 (list rows, buttons, inputs, drawer body; the body default) ·
  `text-base` 14px/1.45 (the command-line path, the question in the drawer, Home prose and its one h1). No display
  type anywhere.
- `tabular-nums` globally. Headings are roman, never italic. View names and column heads are lowercase; prose,
  answers and button labels are sentence case.

## Density and spacing
- Tailwind's 4px scale; used steps 4, 8, 12, 16, 24. Page gutter 16px at every width.
- Fixed heights: top bar 36px · list row 28px (one line, ellipsis) · section row and list header 24px · drawer
  header 32px · status line 28px · buttons 28px · filter toggles, search input and view tabs 24px.
- App views are full width: the work column is `minmax(0, 1fr)`, the drawer 34rem. The body between bar and
  status line is `100dvh` minus both; the list scrolls inside its own container on both axes (min width 56rem) so
  the page never scrolls sideways. Home caps at `max-w-3xl`.
- Radius 0 everywhere. Borders 1px (2px only for `conflict` and the selected/focus outline). No shadows.

## Components
- **List row** (Run grid). A `<table>`, `table-layout: fixed`. Columns: cursor (2ch) · id · label · conf (right)
  · src (right) · question · answer (`ink-2`) · approval. One 28px line per item; cells never wrap, the full text
  is in the drawer. Header: sticky, `text-xs` 500 `ink-2`, 1px ink bottom rule. Rows: 1px `rule` between them.
  Hover: `sunken`. Selected (drawer open on it): `sunken`, inset 2px ink outline, 500 weight, `>` in the cursor
  column (`aria-hidden`); never a side stripe. Section rows: `# section name`, `text-xs`, `ink-3`, 24px, a
  `rule-strong` line under. Pending rows: all text `ink-3`, answer reads `answering…`.
  Confidence is two decimals; it shows `—` for `confirmed by you` and `not applicable`. Approval reads `Approved`
  or `Draft, not approved` (in `ink-3`), in the grid, the drawer and the export alike.
- **Label chip.** The word is always there; fill or border is the second cue. `text-xs` 500, lowercase, min width
  9ch, 18px line, `px-1`, no radius: `verified` chrome fill, on-chrome text · `confirmed by you` neutral-700 fill,
  on-chrome text · `partial` 1px ink border · `conflict` 2px ink border, 700, uppercase `CONFLICT` · `unknown` 1px
  dashed neutral-400 border, `ink-2` text · `not applicable` no border, `ink-3` text.
- **Citation and line listing.** A `<figure>` with a 1px `rule-strong` border. Caption on `chrome-2`: `[n]` and
  the file name in 700 on-chrome, then a facts line in on-chrome-2: kind · status · date (effective / as of / audit
  period) · scope · stance. Under it an `<ol>` of numbered lines, `text-xs`, line height 1.7, in three columns:
  gutter (`>` on a cited line), line number (right aligned, `select-none`, `rule-strong` divider), text. Context
  lines `ink-3`; cited lines `ink` on `sunken`, gutter and line number 700; the quoted span in `<mark>` (`mark`
  background, ink text, 1px underline, offset 2px). Footnote refs in the answer are `[n]` superscripts, 700.
- **Conflict pair.** The drafted question in the answer box, then both sources under `sources (2)`, newer record
  first, with the rule named in the drawer's key-value list (`date rule · newer record first`).
- **Dropped evidence.** A ruled list under `dropped evidence (n)`: reason in 700 uppercase (`PLACEHOLDER`,
  `NOT EVIDENCE`, `CONTAINMENT`, `INJECTION`, `NEGATION`), `file:line`, then one sentence in `ink-2`. Dropped
  text is never shown as a quote.
- **Inspector drawer** (Evidence). Right column, 34rem, `paper`, 1px ink left edge, own scroll; not modal, the list
  stays usable. Header 32px on `chrome`: `AC-04 · evidence` (700) left, `esc close` right (quiet on-chrome-2,
  hover on-chrome on chrome-2). Body, gap 16px: the question (`text-base` 500), a key-value list (label · value ·
  confidence · approval · rule; keys `ink-3`, 11ch), the answer in a `rule-strong` box, `sources (n)` and
  `dropped evidence (n)` subheads (`text-xs` 500 `ink-2`, 1px ink rule under), then the actions. Under 900px it is
  full screen (`position: fixed; inset: 0`), takes focus on open, traps it, and returns it to the row on close.
- **Buttons with key hints.** Every action shows its key in a `<kbd>` before the label: 28px, `px-2`, `text-sm`
  500, `whitespace-nowrap`. Secondary: `paper`, 1px ink border, kbd `ink-3` on `rule-strong`. Primary (one per
  view, plus one in the drawer): `chrome` fill, on-chrome text, kbd on-chrome-2 on neutral-600. Quiet (drawer
  close): text only. Hover: secondary → `sunken`, primary → neutral-800. Active: 1px down. Disabled: `rule-strong`
  border, `ink-3` text, `paper` fill, `not-allowed`, the key does nothing. Loading: the label becomes the verb in
  progress ("Exporting…"), width held, key ignored until done. Success is silent (the list or status line shows
  the result); an error shows below the control in words, prefixed `Error:`.
- **Inputs.** 24px (filter line) or 28px (forms), `paper`, 1px `rule-strong`, `px-2`, `text-sm`, no radius.
  Placeholder `ink-3`. Hover: neutral-500 border. Focus: the global ring. Disabled: `sunken` fill. Error: 2px ink
  border plus a message below in words, prefixed `Error:`. Selects and textareas match.
- **Filter line.** Under the command line, on `sunken`, `rule-strong` rule under. Left: one toggle per label
  (`aria-pressed`): `<kbd>` + label chip + count (700). Pressed: 1px ink border on `paper`. Right: `/` kbd and the
  search input ("question text or ID").
- **Command line.** The view's h1 as a path, `text-base` 500 (`kestrelyn / vsq-a.xlsx / run 3`, separators
  `ink-3`), a `text-xs` `ink-3` metadata line under it, and the view's actions right; wraps under 900px.
- **Top bar.** `chrome`, 36px: wordmark `VART` (700, tracked 0.12em) · views as `<kbd>n</kbd> name`, lowercase,
  on-chrome-2; current view filled on-chrome with ink text, 500, `aria-current="page"`; the views scroll sideways
  inside the bar and never wrap · workspace expiry right (`expires 23h41m`, on-chrome-2, hidden under 900px).
  Home shows the wordmark and `synthetic demo data` only.
- **Status line.** `chrome`, 28px, `text-xs`, on-chrome-2: a mode block (`RUN`, `HOME`, …; on-chrome fill, ink
  text, 700) · cursor (`AC-04 · 4/60`) · the keys that matter in this view · credit right ("VART · labels decided
  by code · synthetic demo data · MIT", hidden under 900px). Under 480px only the first two key hints show.

## Keyboard map
Single keys fire only when focus is not in a text field (Esc always works; in the search field it clears and
leaves). Letters are case sensitive. Every key below is shown as a hint on the control it drives.

| Key | Action | Where |
|---|---|---|
| `s` / `o` | try with a sample company / use your own files | Home |
| `1`–`6` | workspace · run · questions for you · export · audit log · gap check | everywhere in a workspace |
| `v` `p` `c` `u` `y` `x` | toggle the filter: verified · partial · conflict · unknown · confirmed by you · not applicable | Run |
| `g` `i` `p` `d` `s` `o` `a` | scope: govern · identify · protect · detect · respond · recover · all core | Gap check |
| `/` | focus search | Run, Audit log |
| `j` / `k` (and ↓ / ↑) | move the cursor down / up a row | lists |
| `enter` | open the Evidence drawer on the cursor row | lists |
| `esc` | close the drawer (or the key sheet); clear search | everywhere |
| `r` | re-run live | Run |
| `e` | export xlsx | Run, Export |
| `A` (shift+a) | approve all verified | Run |
| `i` | answer this question | the cursor item or open drawer |
| `a` | approve | the cursor item or open drawer; disabled while unanswered or in conflict |
| `n` | mark not applicable (asks for a reason) | the cursor item or open drawer |
| `r` | start a run on the confirmed questionnaire | Workspace |
| `l` / `q` / `w` | load the sample documents / sample questionnaire A / sample questionnaire B | Workspace |
| `r` | run the gap check, or check again (counts under the run limit, even when nothing changed) | Gap check |
| `e` | export the gap report (xlsx) | Gap check |
| `R` (shift+r) | reset the workspace: delete everything now, after a confirm | Workspace |
| `ctrl+enter` | send an answer (in its text field) | Questions for you |
| `?` | show all keys (a sheet listing this table; esc closes) | everywhere |

Row actions in the Workspace tables (`edit` a document, `open` or `delete` a questionnaire) are text buttons named
for their row ("Delete vsq-a.xlsx"), reached with Tab and pressed with Enter or Space; they have no single key, since
a single key cannot say which row. Enter in a form submits it from any field, a focused select included.

## Accessibility
- Focus ring: 2px, instant, never animated. On paper it is `ink`, offset 1px. Inside chrome (top bar, drawer
  header, status line; mark the region `data-chrome`) it switches to `on-chrome` so it reads at 19:1 against
  neutral-950. On a filled row it is an inset outline (offset -2px) so the row's neighbours do not clip it.
- Contrast: every text pair passes 4.5:1, and the resting pairs in the token table reach 7:1. The lowest is a
  kbd hint on the hovered primary button (on-chrome-2 on neutral-800, 6.0:1). Labels never rely on fill alone;
  the word is always present. Exemption: a disabled view tab in the top bar (no run yet) is on-chrome-2 at 60%
  opacity, about 3.4:1; it is an inactive control (WCAG 1.4.3 exempts it) and carries `aria-disabled="true"`.
- Key hints and screen readers: the control gets `aria-keyshortcuts` (`r`, `Shift+A`, `1`, …) and the `<kbd>`
  inside it is `aria-hidden="true"`, so the accessible name is the label alone ("Re-run live"), not "r Re-run
  live". The search field's `/` hint is likewise hidden and the field has a visible-to-SR label "search".
- The list is a `<table>` with `aria-rowcount`; rows use a roving tabindex (one row at `tabindex=0`), the
  selected row has `aria-selected="true"`, and the cursor glyph is `aria-hidden`. The drawer is an `<aside
  aria-labelledby>` pointing at the question; under 900px it is a modal dialog (`role="dialog" aria-modal`).
- Mobile: no horizontal page scroll at 320/375/414/768 (`overflow-x: clip` on html and body); labels and buttons
  never wrap; wrapping long words use `overflow-wrap: anywhere; min-width: 0`.

## Motion
- Motion-cut. Only: drawer open (200ms translateX 16px + opacity, `ease-out`), close (150ms, `ease-in`); hover
  background (100ms colour); the 1px press on buttons. No reveals, no row animation as the list fills (rows
  appear; counts update).
- Reduced motion: transitions collapse to a 120ms opacity fade, animations off (global rule in `index.css`).

## Copy
- Labels in words, never colour or icon alone. Plain verbs: "Re-run live", "Export xlsx", "Approve all verified
  (31)", "Answer this question", "Approve", "Mark not applicable". Drafts read "Draft, not approved" everywhere.
  Errors say what happened and what to do. No invented metrics on Home.

## Directions considered
- A "ledger" (IBM Plex Sans + Mono, light ruled sheet, tab bar; `run-grid.html`) and B "paper"
  (`run-grid-b.html`). Both read well but read as documents, and A sits close to PriorPath's look.
- C "console" chosen: the users are security staff working through 60 items at a sitting, so the UI is a
  keyboard-first instrument (a key on every action, one line per item, inverted chrome) and is visibly distinct
  from PriorPath.

## Change log
- 2026-10-05 · System locked (design branch): direction A, tokens, type, components, two mockups.
- 2026-10-05 · Relocked to direction C "console": JetBrains Mono self-hosted, C tokens (paper white, chrome
  scale), keyboard map, Home redone in C. "Draft" approval wording replaced by "Draft, not approved".
- 2026-10-06 · Workspace keys: l, q, w for the sample buttons, R resets the workspace after a confirm, r starts a
  run from the workspace; `ctrl+enter` (send an answer, Questions for you) added to the table to match the key
  sheet. Exemption recorded for the disabled view tabs' contrast (60% opacity, inactive controls).
- 2026-10-06 · Workspace row actions (edit, open, delete) are Tab-reached text buttons with row-named labels, no
  single key; Enter submits a form from a select too. The upload notices split: one for documents (redaction and
  its known gaps), one for questionnaires (stored and sent as written).
- 2026-10-06 · Gap check (Plan 6B): view 6 in the Workbench layout; scope keys g i p d s o a; gap label chips
  (covered fill, partly 1px, not met 1px bold, DISAGREE 2px uppercase, gap dashed, confirmed by you neutral-700
  fill, not answered quiet); the filter toggles are Tab-reached with no single keys (g i p d s o a r e are taken);
  the coverage line sits in the status line's cursor slot. An outcome marked N/A reads `not applicable` (the
  questionnaire chip) with its own filter count; a failed outcome has no chip and shows its failure sentence; `r`
  with nothing changed says "Nothing changed since the last check." under the review line.
- 2026-10-07 · Guided tour (Plan 4 Task 3b): a non-modal card, bottom right (22rem) from 900 px and full width above
  the status line below it, under the key sheet; ink outline on the step's element; keys → ← Esc only while focus is
  in the card (Enter presses the focused button), and t or the Tour button starts it again on the sample run. It
  opens every time the precomputed sample run opens; Skip closes it for that visit.
