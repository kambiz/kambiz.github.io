# kambiz.github.io

This is a repository to host my homepage, https://kambiz.github.io/

## Writing a blog post

Add a Markdown file to `_posts/` named `YYYY-MM-DD-slug.md`:

```markdown
---
title: "The post's title"
description: "Optional. One sentence for search results and link previews."
---
The first paragraph doubles as the preview text when there's no description.
```

It's published at `/blog/<year>/<slug>/` in the site's own style, with dark mode
and link previews, and listed on `/blog/`. While `_posts/` is empty the blog
hides itself: no Blog link in the nav, no mention on the home page, and `/blog/`
is marked `noindex`. The first post brings all of that back.

## Data pages

Two pages render a CSV that lives at the repo root. Both fetch it at runtime and
parse it in the browser, so refreshing the data is just replacing the file — no
build step, no code changes. Each page caches its processed result in
`localStorage`, keyed on the file's `Last-Modified` and row count, so a new
export invalidates the cache on its own.

| Page | Data file | Source |
|---|---|---|
| [`/exercise`](https://kambiz.github.io/exercise/) | `kambizkamrani_workouts.csv` | Peloton profile export |
| [`/music`](https://kambiz.github.io/music/) | `kambizkamrani_lastfm.csv` | Last.fm scrobble export |

### Refreshing the music data

This happens automatically. The **Refresh Last.fm data** workflow
(`.github/workflows/refresh-lastfm.yml`) runs once a day and does three things:

1. Runs `tools/refresh_lastfm.py`, which asks the Last.fm API for everything
   scrobbled since the CSV's newest row and adds it at the top. Plays that
   reached Last.fm late (from an offline phone, say) are slotted in where
   they belong if they fall within the last two days the CSV covers.
   Existing rows are never rewritten or dropped.
2. Runs `tools/fetch_lastfm_tags.py`, which fetches genre tags for any newly
   qualifying artists.
3. Commits both files to `master`, which redeploys the site.

To run it on demand, use *Actions → Refresh Last.fm data → Run workflow*.

Setup, once:

- Add a **secret** named `LASTFM_API_KEY` under *Settings → Secrets and
  variables → Actions*. Without it the workflow skips, with a warning.
- Optionally add a **variable** named `LASTFM_TZ`, an IANA zone such as
  `America/Los_Angeles`. It's needed if the export's timestamps are in a
  local zone rather than UTC, which is the default.
  - The export carries no zone of its own, so every run first re-fetches the
    last two days the CSV already holds. It checks that `LASTFM_TZ`
    reproduces them exactly.
  - If they don't match, it writes nothing and fails, naming the offset it
    found.

Locally: `LASTFM_API_KEY=... python3 tools/refresh_lastfm.py`.

A full re-export still works too. Replace the file and commit. The expected
shape is four columns, no header, newest first:

```
artist,album,track,"20 Sep 2026, 23:49"
```

### Genre labels (optional)

The scrobble export has no genre column — Last.fm attaches genre to the
*artist*, as community tags. `/music` therefore resolves each artist to a single
genre in this order:

1. A hand-curated list inside `music.html` (~220 artists, about 55% of plays).
   It deliberately overrides the crowd, which is unreliable exactly where it
   matters: short artist names collide, and non-Western music gets flattened
   into "world".
2. `lastfm_artist_tags.json`, if present — top tags from the Last.fm API, mapped
   through the taxonomy in `music.html` and resolved to the highest-weighted tag
   that maps to anything.
3. `Unclassified`, stated plainly rather than guessed at.

That JSON is optional; without it the genre charts still work, on the curated
list alone, and the page reports its own coverage. To generate it:

```sh
export LASTFM_API_KEY=...        # free: https://www.last.fm/api/account/create
python3 tools/fetch_lastfm_tags.py
```

The run is rate-limited, resumable and incremental — it only fetches artists it
does not already have, so re-running after a new export is cheap. It stores raw
tags rather than genres, so the taxonomy can be changed in `music.html` without
re-fetching anything. Commit the JSON next to the CSV.

The API key is read from the environment and is never written to the file. Only
the `api_key` is needed; `artist.getTopTags` is a read method, so the account's
shared secret is not used.
