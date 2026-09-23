#!/usr/bin/env python3
"""
Append new Last.fm scrobbles to the /music export.

Reads kambizkamrani_lastfm.csv (newest first, 4 columns, no header), asks the
Last.fm API for everything scrobbled since its newest row, and adds the new
plays in the same shape. Plays that reached Last.fm late, with a time inside
the last two days the CSV already covers, are slotted into place too.
Existing rows are never rewritten or dropped.

Usage:
    export LASTFM_API_KEY=...            # free: https://www.last.fm/api/account/create
    python3 tools/refresh_lastfm.py      # LASTFM_TZ defaults to UTC

The export's timestamps carry no timezone, while the API reports UTC. So each
run first re-fetches the last couple of days the CSV already holds and checks
that converting them with LASTFM_TZ reproduces those rows exactly. If it does
not, the script writes nothing and exits non-zero, naming the offset it did
find, rather than appending plays on a different clock from the rest.

Exit status: 0 on success (whether or not anything was added), 1 on failure.
Prints `added=<n>` as its last line.
"""

import argparse
import collections
import csv
import datetime as dt
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

# Overridable so the script can be exercised against a local stand-in; nothing
# but a test should ever set it.
API_ROOT = os.environ.get('LASTFM_API_ROOT', 'https://ws.audioscrobbler.com/2.0/')
DEFAULT_CSV = 'kambizkamrani_lastfm.csv'
DEFAULT_USER = 'kambizkamrani'

MIN_INTERVAL = 0.25           # Last.fm asks for at most ~5 requests/second
PAGE_SIZE = 200               # the API maximum for user.getRecentTracks
OVERLAP = dt.timedelta(days=2)
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


def parse_ts(s):
    """'20 Sep 2026, 23:49' -> naive datetime (the export has no zone)."""
    return dt.datetime.strptime(s.strip(), '%d %b %Y, %H:%M')


def format_ts(d):
    # Spelled out rather than strftime('%b'), which follows the locale.
    return f'{d.day:02d} {MONTHS[d.month - 1]} {d.year}, {d.hour:02d}:{d.minute:02d}'


def api_get(params, api_key, timeout=30):
    qs = urllib.parse.urlencode({**params, 'api_key': api_key, 'format': 'json'})
    req = urllib.request.Request(
        API_ROOT + '?' + qs,
        # Last.fm blocks the default urllib agent.
        headers={'User-Agent': 'kambiz.github.io-scrobble-refresh/1.0'},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                sys.exit('403 from Last.fm: the API key looks invalid or revoked.')
            if exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(5 * 2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < 3:
                time.sleep(5 * 2 ** attempt)
                continue
            raise
        if 'error' in payload:
            # 8 and 16 are Last.fm's "try again" errors.
            if payload['error'] in (8, 16) and attempt < 3:
                time.sleep(5 * 2 ** attempt)
                continue
            sys.exit(f"Last.fm error {payload['error']}: {payload.get('message')}")
        return payload
    raise RuntimeError('unreachable')


def fetch_scrobbles(user, api_key, since_uts):
    """Every completed scrobble at or after since_uts, as (uts, artist, album, track)."""
    out, page, pages = [], 1, 1
    while page <= pages:
        tick = time.time()
        payload = api_get({
            'method': 'user.getrecenttracks', 'user': user,
            'from': str(since_uts), 'limit': str(PAGE_SIZE), 'page': str(page),
        }, api_key)
        rt = payload.get('recenttracks', {})
        pages = int(rt.get('@attr', {}).get('totalPages', 1) or 1)
        tracks = rt.get('track', [])
        if isinstance(tracks, dict):      # a single result comes back as a bare object
            tracks = [tracks]
        for t in tracks:
            if t.get('@attr', {}).get('nowplaying') == 'true' or 'date' not in t:
                continue                  # still playing: not a scrobble yet
            out.append((int(t['date']['uts']),
                        t.get('artist', {}).get('#text', ''),
                        t.get('album', {}).get('#text', ''),
                        t.get('name', '')))
        page += 1
        elapsed = time.time() - tick
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--csv', default=DEFAULT_CSV)
    ap.add_argument('--user', default=os.environ.get('LASTFM_USER') or DEFAULT_USER)
    ap.add_argument('--tz', default=os.environ.get('LASTFM_TZ') or 'UTC',
                    help='IANA zone the export is written in (default: UTC)')
    args = ap.parse_args()

    api_key = os.environ.get('LASTFM_API_KEY', '').strip()
    if not api_key:
        sys.exit('LASTFM_API_KEY is not set.')
    tz = ZoneInfo(args.tz)

    with open(args.csv, encoding='utf-8-sig', newline='') as fh:
        text = fh.read()
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        sys.exit(f'{args.csv} is empty; there is nothing to anchor a refresh on.')
    newest = parse_ts(rows[0][3])
    window_start = newest - OVERLAP

    # The CSV's own tail of the overlap window, keyed on what survives a
    # round trip through the API. Album is left out: Last.fm lets it be edited.
    have = collections.Counter()
    for r in rows:
        t = parse_ts(r[3])
        if t < window_start:
            break
        have[(r[0], r[2], t)] += 1

    # Ask from well before the window: until the zone is confirmed, the
    # window's start in UTC is only known to within a day.
    since = int(window_start.replace(tzinfo=dt.timezone.utc).timestamp()) - 86400
    fetched = fetch_scrobbles(args.user, api_key, since)
    print(f'{len(fetched):,} scrobbles fetched since '
          f'{dt.datetime.fromtimestamp(since, dt.timezone.utc):%Y-%m-%d %H:%M} UTC')

    def local(uts):
        # Floored to the minute: the export has no seconds.
        return dt.datetime.fromtimestamp(uts, tz).replace(tzinfo=None, second=0)

    # 1. Confirm the zone: the overlap must reproduce the CSV's recent rows.
    got = collections.Counter((a, n, local(u)) for u, a, _, n in fetched
                              if window_start <= local(u) <= newest)
    matched = sum((have & got).values())
    need = sum(have.values())
    print(f'overlap check ({args.tz}): {matched}/{need} recent CSV rows reproduced')
    if matched < max(1, round(0.9 * need)):
        # Say which offset would have lined up, if any.
        keys = {(a, n): t for (a, n, t) in have}
        offsets = collections.Counter()
        for u, a, _, n in fetched:
            if (a, n) in keys:
                utc = dt.datetime.fromtimestamp(u, dt.timezone.utc).replace(tzinfo=None, second=0)
                offsets[keys[(a, n)] - utc] += 1
        hint = ''
        if offsets:
            off, _ = offsets.most_common(1)[0]
            hours = off.total_seconds() / 3600
            zone = 'UTC' if hours == 0 else 'the IANA zone for that (e.g. America/Los_Angeles)'
            hint = (f' The CSV looks like UTC{hours:+g} around {newest:%Y-%m-%d}; '
                    f'set LASTFM_TZ to {zone}.')
        print(f'Refusing to write: {args.tz} does not reproduce the export\'s '
              f'recent timestamps.{hint}', file=sys.stderr)
        sys.exit(1)

    # 2. What the CSV doesn't hold yet: everything after its newest row, plus
    #    plays inside the overlap that reached Last.fm late (an offline phone
    #    submits its backlog when it reconnects) or share the newest minute.
    missing = collections.Counter((a, n, local(u)) for u, a, _, n in fetched
                                  if local(u) >= window_start) - have
    fresh = []
    for u, a, al, n in sorted(fetched, key=lambda s: s[0], reverse=True):
        key = (a, n, local(u))
        if missing[key] > 0:
            missing[key] -= 1
            fresh.append([a, al, n, format_ts(key[2])])
    if not fresh:
        print('No new scrobbles.')
        print('added=0')
        return

    # Merge into the overlap rows, newest first. At equal minutes the existing
    # row stays first. Everything older than the overlap is carried over as
    # text, untouched.
    def serialize(rs):
        buf = io.StringIO()
        csv.writer(buf, lineterminator='\n').writerows(rs)
        return buf.getvalue()
    k = sum(have.values())
    head = serialize(rows[:k])
    if not text.startswith(head):
        sys.exit('The CSV does not round-trip through the csv module; refusing to '
                 'rewrite its head. Re-save it as plain RFC 4180 with \\n line endings.')
    merged = sorted([(parse_ts(r[3]), 0, i, r) for i, r in enumerate(rows[:k])] +
                    [(parse_ts(r[3]), 1, i, r) for i, r in enumerate(fresh)],
                    key=lambda x: (x[0], -x[1], -x[2]), reverse=True)
    tmp = args.csv + '.tmp'
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as fh:
        fh.write(serialize([m[3] for m in merged]) + text[len(head):])
    os.replace(tmp, args.csv)     # atomic: an interrupted run never truncates the file

    late = sum(1 for r in fresh if parse_ts(r[3]) <= newest)
    print(f'Added {len(fresh):,} scrobbles, {fresh[-1][3]} to {fresh[0][3]} ({args.tz})'
          + (f', {late} of them inside the previous export\'s range.' if late else '.'))
    print(f'added={len(fresh)}')


if __name__ == '__main__':
    main()
