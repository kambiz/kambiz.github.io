#!/usr/bin/env python3
"""
Fetch Last.fm community tags for the artists in a scrobble export.

The scrobble CSV carries no genre — Last.fm attaches genre to the *artist*, as
crowd-sourced tags, not to the play. This script closes that gap: it reads the
export, counts plays per artist, and asks the Last.fm API for each artist's top
tags, writing them to a JSON file the /music page reads at runtime.

It does NOT decide genres. It stores the raw tags and their weights; the
mapping from tags to a canonical genre lives in music.html, so the taxonomy can
be changed without re-fetching anything.

Usage:
    export LASTFM_API_KEY=...            # free: https://www.last.fm/api/account/create
    python3 tools/fetch_lastfm_tags.py

    # narrow or widen the net (default: artists with 3+ plays)
    python3 tools/fetch_lastfm_tags.py --min-plays 1
    python3 tools/fetch_lastfm_tags.py --limit 500

The run is resumable and incremental: artists already present in the output are
skipped, so an interrupted run — or a later export with new artists in it — only
fetches what it is missing. Re-fetch everything with --refresh.
"""

import argparse
import collections
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Overridable so the script can be exercised against a local stand-in; nothing
# but a test should ever set it.
API_ROOT = os.environ.get('LASTFM_API_ROOT', 'https://ws.audioscrobbler.com/2.0/')
DEFAULT_CSV = 'kambizkamrani_lastfm.csv'
DEFAULT_OUT = 'lastfm_artist_tags.json'

# Last.fm asks for no more than ~5 requests/second per key. A quarter-second
# floor keeps us comfortably inside that with room for jitter.
MIN_INTERVAL = 0.25

# Tags are returned with a 0–100 weight. Anything this faint is one person's
# idiosyncratic label rather than a signal about the artist.
MIN_TAG_WEIGHT = 10
KEEP_TAGS = 8           # per artist; the tail past this is noise


def load_artist_counts(path):
    """Play counts per artist, from the 4-column headerless export."""
    counts = collections.Counter()
    with open(path, encoding='utf-8-sig', newline='') as fh:
        for row in csv.reader(fh):
            if len(row) == 4 and row[0].strip():
                counts[row[0].strip()] += 1
    return counts


def fetch_tags(artist, api_key, timeout=20):
    """Top tags for one artist. Returns a list of [tag, weight], or None."""
    qs = urllib.parse.urlencode({
        'method': 'artist.gettoptags',
        'artist': artist,
        'api_key': api_key,
        'format': 'json',
        'autocorrect': '1',
    })
    req = urllib.request.Request(
        API_ROOT + '?' + qs,
        # Last.fm blocks the default urllib agent.
        headers={'User-Agent': 'kambiz.github.io-genre-fetch/1.0'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.load(resp)

    if 'error' in payload:
        # 6 = "artist not found", which is normal for odd or misspelled names.
        if payload.get('error') == 6:
            return []
        raise RuntimeError(f"Last.fm error {payload['error']}: {payload.get('message')}")

    raw = payload.get('toptags', {}).get('tag', [])
    if isinstance(raw, dict):      # the API returns a bare object for a single tag
        raw = [raw]

    out = []
    for tag in raw:
        try:
            weight = int(tag.get('count', 0))
        except (TypeError, ValueError):
            continue
        name = (tag.get('name') or '').strip()
        if name and weight >= MIN_TAG_WEIGHT:
            out.append([name, weight])
        if len(out) >= KEEP_TAGS:
            break
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--csv', default=DEFAULT_CSV, help=f'scrobble export (default: {DEFAULT_CSV})')
    ap.add_argument('--out', default=DEFAULT_OUT, help=f'output JSON (default: {DEFAULT_OUT})')
    ap.add_argument('--min-plays', type=int, default=3,
                    help='skip artists below this many plays (default: 3)')
    ap.add_argument('--limit', type=int, default=0,
                    help='stop after this many artists (0 = no limit)')
    ap.add_argument('--refresh', action='store_true',
                    help='re-fetch artists already in the output file')
    args = ap.parse_args()

    api_key = os.environ.get('LASTFM_API_KEY', '').strip()
    if not api_key:
        sys.exit('LASTFM_API_KEY is not set. Get a free key at '
                 'https://www.last.fm/api/account/create, then:\n'
                 '    export LASTFM_API_KEY=your_key_here')

    if not os.path.exists(args.csv):
        sys.exit(f'No such export: {args.csv}')

    counts = load_artist_counts(args.csv)
    wanted = [a for a, n in counts.most_common() if n >= args.min_plays]
    if args.limit:
        wanted = wanted[:args.limit]

    existing = {}
    if os.path.exists(args.out) and not args.refresh:
        with open(args.out, encoding='utf-8') as fh:
            existing = json.load(fh).get('artists', {})

    todo = [a for a in wanted if a not in existing]
    covered = sum(counts[a] for a in wanted)
    print(f'{len(counts):,} artists in export; {len(wanted):,} at {args.min_plays}+ plays '
          f'({100*covered/sum(counts.values()):.1f}% of scrobbles)')
    print(f'{len(existing):,} already fetched, {len(todo):,} to go '
          f'(~{len(todo)*MIN_INTERVAL/60:.0f} min)\n')
    if not todo:
        print('Nothing to do.')
        return

    results = dict(existing)
    failures = 0
    started = time.time()

    def save():
        tmp = args.out + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump({
                'generated': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'source': 'last.fm artist.getTopTags',
                'min_plays': args.min_plays,
                'artists': results,
            }, fh, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
        os.replace(tmp, args.out)   # atomic: an interrupted run never truncates the file

    for i, artist in enumerate(todo, 1):
        tick = time.time()
        try:
            results[artist] = fetch_tags(artist, api_key)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                print('  rate limited — backing off 10s')
                time.sleep(10)
                try:
                    results[artist] = fetch_tags(artist, api_key)
                except Exception as retry_exc:      # noqa: BLE001 - report and move on
                    print(f'  ! {artist}: {retry_exc}')
                    failures += 1
            elif exc.code == 403:
                sys.exit(f'\n403 from Last.fm — the API key looks invalid or revoked.')
            else:
                print(f'  ! {artist}: HTTP {exc.code}')
                failures += 1
        except Exception as exc:                     # noqa: BLE001 - network is flaky
            print(f'  ! {artist}: {exc}')
            failures += 1

        if i % 25 == 0 or i == len(todo):
            save()
            rate = i / max(1e-9, time.time() - started)
            left = (len(todo) - i) / max(1e-9, rate)
            print(f'  {i:,}/{len(todo):,}  ({rate:.1f}/s, ~{left/60:.0f} min left)')

        elapsed = time.time() - tick
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)

    save()
    tagged = sum(1 for v in results.values() if v)
    print(f'\nWrote {args.out}: {len(results):,} artists, {tagged:,} with tags, '
          f'{failures:,} failed.')
    print('Commit it next to the CSV and /music will pick it up.')


if __name__ == '__main__':
    main()
