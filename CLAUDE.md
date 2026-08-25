# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a static personal website hosted via GitHub Pages at `kambiz.github.io`. There is no build system, package manager, framework, or test suite — pages are hand-written HTML/CSS served as-is. Any change is deployed simply by committing to `master`, since GitHub Pages serves the repo directly.

## Local development

There is no build step. To preview changes, serve the repo root with any static file server and open the page in a browser, e.g.:

```
python3 -m http.server 8000
```

Then visit `http://localhost:8000/`, `/cv/`, `/blog/`, or `/exercise.html`.

## Structure

- `index.html` — homepage (bio/links).
- `cv/index.html` — CV page, served at `/cv`.
- `blog/index.html` — blog landing page, served at `/blog`.
- `css/main.css` — single shared stylesheet linked by every page via `/css/main.css` (absolute path).
- `exercise.html` — standalone Peloton workout dashboard (see below).
- `kambizkamrani_workouts.csv` — Peloton workout export data, consumed by `exercise.html`.
- `CNAME` — GitHub Pages custom domain file.

## Page conventions

Each top-level page (`index.html`, `cv/index.html`, `blog/index.html`) repeats the same structure: a `<nav>` with links to Home/CV/Blog, a `.container` > `.blurb` content block, and a `<footer>` with the same set of external profile links (GitHub, Facebook, Twitter, Doximity, LinkedIn, Medium). When adding a new top-level page, copy this nav/footer scaffold and link `/css/main.css` with an absolute path so it resolves correctly regardless of the page's directory depth.

## exercise.html (Peloton dashboard)

This page is self-contained (inline `<style>` and `<script>`, only external dependency is the Chart.js CDN) and works independently of the rest of the site's conventions (no shared nav/footer, no `main.css`). At runtime it:

1. Fetches `kambizkamrani_workouts.csv` from the same directory via `fetch()`.
2. Parses and validates the CSV against `REQUIRED_COLS`.
3. Caches the processed result in `localStorage` (key `CACHE_KEY`, currently `peloton_cache_v8`), keyed on the CSV's `Last-Modified` header and row count, falling back to the cached copy if the fetch fails.
4. Renders stat cards and Chart.js charts into `#app` (`renderDashboard`).

When the CSV's columns or shape change, update `REQUIRED_COLS`/`processData` together, and bump `CACHE_KEY`'s version suffix so stale cached data isn't reused.

To update the workout data, replace `kambizkamrani_workouts.csv` with a fresh Peloton export — the header row's column names must match `REQUIRED_COLS` in `exercise.html`.
