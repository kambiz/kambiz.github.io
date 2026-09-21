# kambiz.github.io

This is a repository to host my homepage, https://kambiz.github.io/

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

Replace `kambizkamrani_lastfm.csv` with a new export and commit. The expected
shape is four columns, no header:

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
