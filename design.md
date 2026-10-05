# Design — VART v2

Locked design system. Future Hallmark runs read this file first; every view defers to it. Amend intentionally,
with a line in the change log at the bottom. Tokens live in `web/src/index.css` (`@theme`); that file is the
source of truth and this one explains it. Mockups: `design/mockups/home.html`, `design/mockups/run-grid.html`.

## System
- Genre · modern-minimal (dev/B2B tool), pushed toward an audit ledger: dense, ruled, precise
- Macrostructure · Home: Index-First (a short paragraph, then the two ways in as rows). Every other view: app shell
  (tab bar, a view header, one working surface, an optional right drawer)
- Theme · custom (vibe: "audit ledger, dense, monochrome, every line cited")
- Axes · light / grotesk-sans / neutral (no accent hue; ink is the accent)
- Hard rule · black, white and `neutral-*` only (`scripts/check_monochrome.py`). No hex, rgb(), oklch() under
  `web/src`. Distinctness from PriorPath comes from type (Plex), density, rules and the citation block.

## Tokens (`web/src/index.css`, Tailwind v4 `@theme`, all aliases of the neutral scale)
| Token / utility | Alias | Use |
|---|---|---|
| `paper` (`bg-paper`) | neutral-50 | page background |
| `surface` | white | the ledger sheet: grid, drawer, inputs, cards |
| `sunken` | neutral-100 | row hover, table header band, passage context |
| `mark` | neutral-200 | the quoted span inside a cited passage |
| `rule` | neutral-200 | hairline between rows |
| `rule-strong` | neutral-300 | panel edges, input borders, drawer edge |
| `ink` | neutral-950 | text, primary fill, focus ring, the selected row's edge |
| `ink-2` | neutral-700 | secondary text |
| `ink-3` | neutral-500 | metadata on `surface` or `paper` only (4.7:1 on white, 4.5:1 on paper). On `sunken` it drops to 4.3:1, so text there steps up to `ink-2` |
| `on-ink` | white | text on a filled ink control |

neutral-400 is for dashed borders only, never text. Pure black is not used for text or fills (ink is neutral-950).

## Type
- `font-sans` IBM Plex Sans 400 (body) and 600 (headings, primary buttons, the selected label). Two weights only.
- `font-mono` IBM Plex Mono 400/500: item IDs, file names, line numbers, quoted passages, dates, counts,
  confidence, the audit log. Anything a person might copy or compare is mono.
- Loaded from Google Fonts (`@import` at the top of `index.css`, `display=swap`).
- Scale (Tailwind defaults plus one): `text-label` 12px/16px, +0.06em, uppercase, mono (column heads, metadata
  keys) · `text-sm` 14px (grid cells, drawer body, buttons) · `text-base` 16px (prose, question text in the drawer)
  · `text-lg` 18px (view titles) · `text-2xl` 24px (Home h1 only). Five sizes, no display type anywhere.
- `tabular-nums` on every table, count and date. Headings are roman, sentence case, never italic.

## Space and density
- Tailwind's 4px scale; the only half steps (2px, 6px) are inside status labels. Grid row: `px-3 py-2`, min height 36px, text-sm. Header band 32px. Section gaps `gap-6`.
- Page gutter 16px (`px-4`) at every width; app views are full width, Home caps at `max-w-3xl`.
- Radius 0 everywhere (ruled paper). Borders 1px. No shadows, except the drawer on narrow screens
  (none: it covers the page instead).

## Components
- **Grid row.** `<table>` with a sticky header band (`bg-sunken`, `text-label`). Columns: ID (mono) · Question
  · Answer · Label · Conf. (mono, right) · Sources (mono, right) · Approval. Rows separated by `border-rule`.
  Hover: `bg-sunken`. Selected (drawer open on it): `bg-sunken` plus an inset 2px ink outline on the whole row,
  never a side stripe. Section rows (questionnaire headings) span all columns, `text-label`, `bg-paper`.
  Keyboard: rows are focusable (roving tabindex); ↑/↓ moves, Enter opens the drawer, Esc closes it.
  The table sits in its own scroll container (both axes, height capped to the viewport) so the sticky header
  works and the page never scrolls sideways. Answers clamp to two lines; the full text is in the drawer.
- **Status label** (words always; the border style is a second cue, never the only one):
  `Verified` filled ink, on-ink text · `Confirmed by you` filled neutral-700, on-ink text · `Partial` 1px solid
  ink border · `Conflict` 2px solid ink border, 600 weight · `Unknown` 1px dashed neutral-400 border, ink-2 text
  · `Not applicable` no border, ink-3 text. All: `text-label` mono uppercase, `px-1.5 py-0.5`, no radius.
  Approval is a separate column in words: `Approved` / `Draft` (the drawer and the export say `Draft, not approved`).
- **Citation block.** A header line in mono `text-label`: file name · kind · status · date (effective / as of /
  audit period) · scope · stance. Under it the passage as numbered lines (mono text-sm, line number column ink-3,
  right aligned, `select-none`, `ink-2`). Context lines on `sunken`; the cited line(s) on `surface` with the quoted span in
  `<mark>` (`bg-mark`, ink text, 1px ink underline). The line number of a cited line is ink and 500 weight.
- **Conflict pair.** Two citation blocks under a one-line rule header (`Conflict · date rule · newer record
  first`), newer first, each with its date in the header. The drafted question sits above them in body text.
- **Dropped evidence.** A ruled list: reason as a mono label (`CONTAINMENT`, `PLACEHOLDER`, `INJECTION`,
  `NOT EVIDENCE`, `NEGATION`), then file and line, then one sentence. Never shows dropped text as a quote.
- **Drawer** (Evidence). Right column, 30rem, `bg-surface`, 1px `rule-strong` left edge, full height, own scroll.
  Not modal: the grid stays usable. Header: item ID, close button with `Esc` hint. Opens with a 200ms translate +
  fade (`ease-out`); reduced motion: 120ms fade. Under 900px it covers the viewport and traps focus.
- **Buttons.** Primary: `bg-ink text-on-ink`, 600, `px-3 py-1.5 text-sm`. Secondary: `bg-surface`, 1px ink
  border. Quiet: text only, underline on hover. One primary per view. Hover: primary → neutral-800, secondary →
  `bg-sunken`. Active: 1px down. Disabled: neutral-300 border, ink-3 text, no fill. Loading: the label changes
  to the verb in progress ("Exporting…"), width held. Labels never wrap (`whitespace-nowrap`).
- **Inputs.** `bg-surface`, 1px `rule-strong`, `px-2 py-1.5 text-sm`, no radius. Focus: the global ring. Error:
  2px ink border plus a message below in words, prefixed "Error:". Selects match.
- **Tally bar** (Run grid). Per-label counts as toggle buttons (`aria-pressed`), mono counts, each using its status
  label style; filters the grid.

## Navigation and footer
- Nav · N9 edge-aligned tab bar: wordmark `VART` (mono 500, tracked) left; view tabs (Workspace · Run ·
  Questions for you `7` · Export · Audit log); workspace expiry right in mono ink-3. Current tab: 2px ink
  underline and `aria-current="page"`. On narrow screens the tabs scroll sideways inside the bar; they never wrap.
  Home shows only the wordmark and "Synthetic demo data".
- Footer · Ft2 inline single line above a hairline: "VART · labels decided by code · synthetic demo data · MIT".

## Motion
- Motion-cut. Only: drawer open/close (200ms transform + opacity, `ease-out` in, `ease-in` out), hover background
  (100ms colour). No reveals, no row animation as the grid fills (rows appear; the tally counts update).
- Focus ring is instant. Reduced motion: transitions collapse to a 120ms opacity fade (global rule in index.css).

## Copy
- Labels in words, never colour or icon alone. Plain verbs on buttons: "Approve all verified", "Re-run live",
  "Export xlsx". Errors say what happened and what to do. No invented metrics on Home.

## Change log
- 2026-10-05 · System locked (design branch): tokens, type, components, two mockups.
