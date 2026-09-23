# CLAUDE.md

Guidance for Claude Code sessions working in this repository.

## What this is

Kambiz Kamrani's personal site, served by GitHub Pages at https://kambiz.github.io
from `master`. Jekyll builds it, but every page is `layout: null`, so it's
self-contained: its own `<style>` and scripts, no shared layout or
stylesheet. The only shared pieces are the nav and footer includes (see
Shared conventions). Merging to `master` deploys. The "Site check" workflow
(`.github/workflows/site-check.yml`) builds the site and loads every page in
Chromium on each PR and push to `master`; run
`.github/scripts/check-site.mjs` locally against a served `_site` for the
same check.

| Page | File | Notes |
|---|---|---|
| `/` | `index.html` | Bio, theme-matched portrait (`assets/img/portrait-{light,dark}.webp`) |
| `/cv/` | `cv/index.html` | Static content plus two Chart.js charts |
| `/blog/` | `blog/index.html` | Post list via Liquid; `_posts/` is currently empty |
| `/exercise/` | `exercise.html` | Peloton dashboard from `kambizkamrani_workouts.csv` |
| `/music/` | `music.html` | Last.fm dashboard from `kambizkamrani_lastfm.csv` (+ `lastfm_artist_tags.json`) |

`README.md` covers refreshing the two datasets and `tools/fetch_lastfm_tags.py`.

## Build and preview

```sh
bundle exec ruby -e "require 'jekyll'; Jekyll::Commands::Build.process({})"
cd _site && python3 -m http.server 8123   # then open http://127.0.0.1:8123/
```

(`bundle exec jekyll build` may fail with a missing binstub; the line above
drives the same build through Ruby.) Serve `_site`, not the repo root. The
dashboards fetch their CSVs by absolute path and depend on Jekyll's
permalinks.

A successful build proves little here: see the Liquid guard below. Load the
pages in a browser (Playwright + the preinstalled Chromium works) and check
for page errors before merging anything that touches a script.

## The Liquid guard — read before editing any inline script

Jekyll runs Liquid over every page with front matter, including inline
JavaScript. Two adjacent braces in dense object literals (`scales:{{x:1}}`)
are read as a Liquid expression and silently rendered to nothing. The build
passes, the deploy succeeds, and the dashboard renders blank.

So the main script in `cv/index.html`, `exercise.html` and `music.html` sits
inside a `{% raw %}` … `{% endraw %}` guard:

- Put new JS **inside** the guard.
- Never write the literal closing tag inside it, even in a comment; that
  closes the guard early and fails the build ("Unknown tag 'endraw'").
- No Liquid works inside. If a script needs a Jekyll value, put it in a data
  attribute outside the guard and read it from the DOM.
- To confirm a change survived, diff the guarded script in the source
  against `_site/…/index.html`; only blank lines should differ.

## Shared conventions

The nav and footer are shared includes. Everything else in this section is
still copied into every page, so keep those copies in sync.

- **Nav:** one list in `_data/nav.yml` (Home · CV · Blog · Exercise · Music),
  rendered by `_includes/nav.html`. Each page passes its own title, e.g.
  `{% include nav.html current="CV" %}`, and that entry becomes
  `<span class="current">` instead of a link. Add, rename or reorder pages in
  the YAML only.
- **Footer:** `_includes/footer.html`, a horizontal social row (GitHub,
  Twitter, LinkedIn, Last.fm, Strava) above "Kambiz Kamrani ·
  kambiz.github.io". It takes an optional one-line note shown above the row:
  `note="…"` for static text, or `slot=true` to reserve an empty
  `.footer-note` that JS fills in.
- **Nav and footer on the dashboards:** `/exercise` and `/music` build their
  header and footer in JS inside the Liquid guard, where includes can't run.
  So each page renders the includes into `<template id="site-nav">` and
  `<template id="site-footer">` just above `#app`. The JS then inserts them
  with `siteNav()` and `siteFooter(note)`: a string fills the note slot, and
  `''` removes it. Change the markup in `_includes/`, not in the JS.
  The per-page CSS for `.nav-link`, `.footer` and `.footer-note` still lives
  in each page's `<style>`.
- **Theme tokens:** colours are CSS custom properties (`--bg`, `--fg`,
  `--muted`, `--faint`, `--border*`, `--accent`, …), defined on `:root`,
  redefined under `@media (prefers-color-scheme: dark)` guarded by
  `:not([data-theme="light"])`, and again under `:root[data-theme="dark"]`.
  Don't hard-code colours in page CSS.
- **Theme toggle:** a tiny script in `<head>` sets `data-theme` on `<html>`
  from `localStorage.theme` (else the system preference) before paint. The
  button's click handler lives in its own `<script>` right after the button,
  deliberately independent of Chart.js, and dispatches a `themechange`
  event that the chart code listens for.
- **Icons:** every page links `favicon.ico`, `favicon.svg` and
  `apple-touch-icon.png` in `<head>`.

## Dark mode for charts (`exercise.html`, `music.html`)

- Charts are always **built from the light design**: `C = PALETTE.light`, and
  `Chart.defaults.color` / `borderColor` stay on light values. Chart.js copies
  those defaults into each chart's scale options at build time, so letting
  them follow the theme double-darkens charts built on a dark page load.
- A `themeTracker` plugin (`afterInit`) captures each chart's colours by config
  path and maps them with `toDark()`. Neutral greys have their lightness
  carried from the light page's range onto the dark page's, which keeps
  contrast and rank. Saturated colours pass through, and the accent `#c0392b`
  maps to `#e0574a`. On `themechange`, `applyChartTheme()` re-maps every
  registered chart and calls `update('none')`.
- Colours painted at draw time by custom plugins go through `ink(color)`.
- Non-Chart.js visuals (calendars, the music hour heatmap) read the theme when
  drawn and are redrawn on `themechange`.
- Test all four states when changing any of this: light load, dark load,
  toggled to dark, toggled back. Dark-on-load and toggled-dark must match.

## Data and caching

- Both dashboards cache processed data in `localStorage` under a versioned key
  (`CACHE_KEY` near the top of each script, e.g. `peloton_cache_v15`,
  `lastfm_cache_v2`), invalidated automatically by the file's
  `Last-Modified` and row count. Bump the version **only** when the processed
  data's shape changes, not for styling or chart changes, since a bump makes
  every visitor re-parse the CSV.
- The Last.fm data refreshes itself. `.github/workflows/refresh-lastfm.yml`
  runs daily at 09:17 UTC. It runs `tools/refresh_lastfm.py`, which adds new
  scrobbles to the CSV (including late arrivals within its last two days), then `tools/fetch_lastfm_tags.py` for new
  artists, and commits the result to `master` as `github-actions[bot]`. Pull
  before editing either data file.
  - It needs the `LASTFM_API_KEY` secret, and skips with a warning without it.
  - The export's timestamps have no zone. `LASTFM_TZ` (a repository variable,
    default `UTC`) says which zone they're in. Every run checks that setting
    against the CSV's last two days, and refuses to write anything if it
    doesn't match.
  - The Peloton CSV is still refreshed by hand.
- Chart.js is vendored at `assets/js/chart-4.4.0.umd.js`; don't switch back to
  a CDN (a failed CDN load blanks both dashboards).

## Config notes

- `_config.yml` has no theme. Nothing uses a layout, and no Minima config
  remains.
- GitHub Pages renders Markdown files even without front matter, so any `.md`
  that shouldn't be public must be listed under `exclude` (as `README.md` and
  this file are).
- `CNAME` is empty; the site is served from the default `github.io` domain.
