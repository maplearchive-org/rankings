"""Fetch one slice of a ranking day and write it, without parsing anything."""

import argparse
import gzip
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from day import ranking_day
from line import slice_line
from slices import RANKS_PER_PAGE, asset_name, offsets_of

API_BASE = "https://www.nexon.com/api/maplestory/no-auth/ranking/v2"

# A complete browser string rather than the bare "Mozilla/5.0" this used to
# send. A stub identifies nothing and looks like exactly what it is.
#
# The same string the archive sends from its own address (its src/config.ts).
# The archive still sends it for detect's own character lookups, and one
# project presenting two different faces to the same endpoint is a difference
# nobody would find until it mattered. Change this and the archive's
# USER_AGENT together, or change neither.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)

# 0.3 seconds, from an address that will make at most PAGES_PER_SLICE
# requests and then be thrown away. That ceiling was halved in slices.py
# after the first production run lost pages well short of the 500 it used to
# be - see that module's comment for the measurement. Nothing here narrows
# the pacing to match; the run that motivated the cut lost pages from
# throttling at a fixed pace, not from a pace that was too fast on its own,
# so there is no evidence 0.3s itself needs to move, only that fewer requests
# should be asked of one address before it is thrown away.
REQUEST_INTERVAL_S = 0.3

# Four attempts. The archive's five-minute wait belongs to a world with one
# address; here a failed slice is retried an hour later on a new runner.
TRANSIENT_BACKOFF_S = [1, 2, 4, 8]

# A 403 gets one 60-second wait and one retry, because a block might have
# lapsed within the minute. A second 403 ends the slice as blocked, because
# waiting does not clear a per-address block - the next hourly run gets a
# fresh runner, which is the actual cure.
BLOCK_WAIT_S = 60

_RANK = re.compile(rb'"characterName"\s*:')

# The prefix line.py always writes, matched on raw bytes so that recovering
# an offset never requires opening the body that follows it. json.loads
# would work too, but decoding and re-encoding is exactly what line.py's own
# docstring says a line surviving from an earlier wave must never go
# through - a huge exp value that round-trips through Python's json module
# unchanged today is not a guarantee, and the whole point of carrying a line
# over as bytes is to not need that guarantee.
_OFFSET_PREFIX = re.compile(rb'^\{"o":(\d+),"r":')

_next_request_at = 0.0


class Blocked(Exception):
    """Nexon answered 403: this address is blocked for some window."""


def _throttle():
    global _next_request_at
    wait = _next_request_at - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _next_request_at = time.monotonic() + REQUEST_INTERVAL_S


def rank_count(body):
    """How many rank objects a body carries, counted without parsing it."""
    return len(_RANK.findall(body))


def fetch_body(region, world_id, offset, state):
    """The raw bytes at one offset, or None when they could not be had."""
    url = (
        f"{API_BASE}/{region}?type=world&id={world_id}&page_index={offset}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for backoff in TRANSIENT_BACKOFF_S:
        _throttle()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 403:
                if state["blocked_once"]:
                    raise Blocked(
                        f"403 at offset {offset}; this address is blocked."
                    ) from error
                state["blocked_once"] = True
                print(
                    f"403 at offset {offset} - waiting {BLOCK_WAIT_S}s once, "
                    "then retrying; a second 403 ends this slice.",
                    file=sys.stderr,
                )
                time.sleep(BLOCK_WAIT_S)
                continue
            print(
                f"HTTP {error.code} at offset {offset} - retrying in {backoff}s",
                file=sys.stderr,
            )
            time.sleep(backoff)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            print(
                f"Offset {offset} failed ({error}) - retrying in {backoff}s",
                file=sys.stderr,
            )
            time.sleep(backoff)
    return None


def _existing_lines(path):
    """
    The offsets one slice's file already carries, keyed by offset, as the
    raw line bytes exactly as read - never decoded, never re-parsed.

    {} when the file does not exist yet, which is every first-wave call: the
    repair job is the only caller that will ever find something here, and
    the presence of the file is the only signal this function or its caller
    acts on. There is deliberately no flag for it.
    """
    lines = {}
    if not os.path.exists(path):
        return lines
    with gzip.open(path, "rb") as handle:
        body = handle.read()
    for line in body.split(b"\n"):
        if not line.strip():
            continue
        match = _OFFSET_PREFIX.match(line)
        if match:
            lines[int(match.group(1))] = line
    return lines


def scrape_slice(day, region, world_id, first, last):
    one = {"region": region, "world_id": world_id, "from": first, "to": last}
    state = {"blocked_once": False}
    name = asset_name(region, world_id, first, last)
    path = os.path.join("out", name)
    expected = offsets_of(one)

    # A repair slice starts from whatever the first wave already wrote,
    # rather than from nothing. Fetching an offset that file already carries
    # would throw away a page the first wave paid for, on an address that is
    # throttled by request count and gains nothing by re-asking for what it
    # already holds - which is exactly the mistake the first production run
    # made.
    lines = _existing_lines(path)
    status = "complete"

    for offset in expected:
        if offset in lines:
            continue

        # Re-derived every page. Repairs run all day, so a late one can cross
        # 18:00 UTC - and pages from two ranking days under one release would
        # be corruption that can never be re-scraped, because the window is
        # over. Returning now leaves the file exactly as it was read - which,
        # on a repair call, is the first wave's file, untouched - rather than
        # writing anything that could mix two days into one release.
        if ranking_day(datetime.now(timezone.utc)) != day:
            print(
                "Ranking day rolled over during this slice. Writing nothing.",
                file=sys.stderr,
            )
            return 1

        try:
            body = fetch_body(region, world_id, offset, state)
        except Blocked as error:
            print(str(error), file=sys.stderr)
            status = "blocked"
            break

        if body is None:
            status = "partial"
            continue

        found = rank_count(body)
        if found != RANKS_PER_PAGE:
            # A short answer is this API's own soft failure. Leaving it out
            # keeps the offset in the archive's resume set; writing it would
            # punch a permanent ten-rank hole behind a single warning line.
            print(
                f"Offset {offset} answered {found} ranks - left out.",
                file=sys.stderr,
            )
            status = "partial"
            continue

        lines[offset] = slice_line(offset, body)

    ordered = [lines[offset] for offset in expected if offset in lines]
    # Completeness is decided against the union just written, not against
    # what this call itself fetched: a repair call that finds nothing left
    # to fetch - every offset already carried over - must still read as
    # complete, and one that leaves even a single offset missing must not,
    # regardless of whether that offset came from this call's own failure or
    # was never there to begin with.
    if len(ordered) == len(expected):
        status = "complete"

    # Written even when incomplete: partial data is worth keeping, and the hole
    # is recorded in the manifest publish.py builds from the file itself.
    os.makedirs("out", exist_ok=True)
    with gzip.open(path, "wb") as handle:
        handle.write(b"".join(line + b"\n" for line in ordered))

    print(f"{name}: {len(ordered)} pages, status {status}")
    # 0 even when status is "partial" or "blocked": a non-zero exit would fail
    # the matrix job, and actions/upload-artifact in the next step would then
    # be skipped - discarding whatever pages this slice did manage to fetch,
    # which is the opposite of what partial data is written for. The slice's
    # real status travels in the manifest, which publish.py derives by
    # counting the file rather than by trusting this exit code.
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--world", required=True, type=int)
    # dest is spelled out because "from" cannot be an attribute name.
    parser.add_argument("--from", required=True, type=int, dest="first")
    parser.add_argument("--to", required=True, type=int, dest="last")
    args = parser.parse_args()

    return scrape_slice(args.day, args.region, args.world, args.first, args.last)


if __name__ == "__main__":
    sys.exit(main())
