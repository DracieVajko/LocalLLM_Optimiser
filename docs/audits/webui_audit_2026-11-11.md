# WebUI audit — LM Studio Auto Optimizer (2026-11-11)

Scope: `lm_optimizer/ui/` — templates, JS modules, CSS, screenshot capture via
`tools/html_shot.py`. Pages reviewed: `/`, `/sandbox`, `/history`, `/lab`,
`/experiments`, `/settings`, `/results/{id}`. No console errors were observed on
any page.

## 1. Visual polish & animations

- **Dashboard spacing is now centered** (was: 4-column grid with 2 cards left-aligned,
  leaving empty space on the right; fixed to `max-w-4xl mx-auto`).
- **Theme toggle icon** was mojibake (`dYOT`). Fixed to the proper moon/sun glyph
  (user's edit).
- **Transitions are inconsistent.** Cards, tables and the status badge have
  `transition` on some elements but not others; the sandbox history detail panel
  appears instantly. Recommend a single `150ms ease-out` on `.card`, `.badge`,
  and `.btn` (already defined in `app.css` lines 871-893) applied globally.
- **Empty states are plain text.** Sandbox history, results list and lab task
  list show a grey sentence. Add a small icon + heading + action button.
- **Loading is a spinner only.** Results page renders a spinner then swaps; a
  skeleton would reduce layout shift. Non-blocking improvement.
- **Tailwind via CDN** produces a console warning on every page and ships
  ~3 MB of unused CSS. Acceptable for a local tool, but a PostCSS build would
  remove the warning and ~90 % of the payload.
- **No entrance animation** on tab/section switches. The dashboard swaps content
  in place; a 100 ms fade would soften it.

## 2. Functionality & logical integrity

- **Sandbox history "View" button did nothing** (fixed): `showSandboxRunDetail`
  sat outside the IIFE that defines `esc()`, so the click threw `ReferenceError`.
  Moved inside the IIFE; renamed the helper to `resultBadge` and added a status
  row.
- **History list fetched 200 runs while the detail endpoint used 1000** (fixed):
  `history.js` now requests `limit=1000`, matching `/sandbox/run/{index}`.
- **History still uses the old flat table.** It does not group by model, unlike
  the sandbox page. Task 7 in `docs/plans/2026-11-10-remaining-work.md`.
- **WebSocket is optional and handled.** `app.js` wraps it in try/catch and
  continues without live updates. Good.
- **`beforeunload` guard only on the dashboard.** Sandbox and results pages do
  not warn on an active run. Minor.
- **`model_detail.js`** navigates via `window.location.href`; full reload each
  time. Acceptable for a local tool.
- **No unhandled promise rejections observed** in any page load.

## 3. File architecture, modularity & code quality

- **No bundler, no types.** Templates load Tailwind and Chart.js from a CDN;
  JS is ES modules with `?v=17` cache busting. Fine for a local tool, but the
  cache-bust string must be bumped on every change (it is, manually).
- **`history.js` is 680 lines** and duplicates the sandbox history renderer.
  Both should share one module.
- **Semantic HTML is thin.** 3-9 `aria-*`/`role` per template; inputs do have
  labels (good). Tab groups and modal dialogs lack `role="dialog"` and focus
  management.
- **No memoization.** Vanilla JS re-renders whole sections on every fetch; for
  a local tool with small data this is not a bottleneck.
- **Accessibility gaps:** no skip-to-content link, no focus trap on the run-detail
  modal, colour contrast on `badge-warning` is borderline in dark mode.

## 4. Actionable refactoring

Already applied this round:

- `history.js`: `limit=200 -> 1000` (index consistency).
- `ui.js`: dashboard status/hardware grid centred (`max-w-4xl mx-auto`).
- `sandbox.js`: View button fixed, history grouped per model, `NOT MEASURED`
  badge, `Status` row in the detail view, `blend_file` path shown.
- `sandbox.js`: per-run **Pin** and **Compare** buttons; Compare opens a
  two-column split view (metrics, failing checks, HTML/code preview) for two
  runs side by side.
- `history.js`: the sandbox section is now collapsible per model instead of a
  flat table.
- `theme.js`: moon/sun glyph restored (user's edit).

Recommended next:

```js
// ui.js - global transition for cards and badges
.card, .badge { transition: box-shadow 150ms ease, transform 150ms ease; }
.card:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,.06); }
```

```js
// history.js - reuse the sandbox grouping instead of re-implementing
import { renderModelHistory } from './sandbox.js';
```

## 5. Prioritization roadmap

**Critical / blocking**
- None. All pages load without console errors; the View button works again.

**File architecture & code quality**
- Split `history.js` (680 lines) into `history/model-list.js` and
  `history/run-detail.js`.
- Bump the `?v=17` cache-bust string on every UI change (or add a build step).
- Add `role="dialog"` and focus management to the run-detail panel.

**UI/UX, layout & animation polish**
- Add a 100 ms fade on section swap (`main.innerHTML` → `opacity` transition).
- Replace plain-text empty states with icon + heading + action.
- Apply the existing `.card:hover` / `.badge` transitions globally.
- Replace the Tailwind CDN with a local build to remove the console warning.

## Evidence

- Screenshots: `results/audit_dashboard.png`, `audit_sandbox.png`,
  `audit_history.png`, `audit_lab.png`, `audit_experiments.png`,
  `audit_settings.png` (all captured with `tools/html_shot.py`, 6 s settle).
- No console errors on any page.
- `node --check` passes on every file in `lm_optimizer/ui/static/js/`.
- `tools/audit_tasks.py` and `tools/audit_screenshots.py` cover the scoring side.
