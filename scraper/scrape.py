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

# 0.3 seconds, from an address that will make 500 requests and then be thrown
# away. Do not raise it: 500 at this pace is about two thirds of the roughly
# 800-per-five-minute-window the evidence points at, and the whole design
# depends on staying under that rather than discovering exactly where it is.
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


def scrape_slice(day, region, world_id, first, last):
    one = {"region": region, "world_id": world_id, "from": first, "to": last}
    state = {"blocked_once": False}
    lines = []
    status = "complete"

    for offset in offsets_of(one):
        # Re-derived every page. Repairs run all day, so a late one can cross
        # 18:00 UTC - and pages from two ranking days under one release would
        # be corruption that can never be re-scraped, because the window is
        # over. Writing nothing is the only safe answer.
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

        lines.append(slice_line(offset, body))

    # Written even when incomplete: partial data is worth keeping, and the hole
    # is recorded in the manifest publish.py builds from the file itself.
    os.makedirs("out", exist_ok=True)
    name = asset_name(region, world_id, first, last)
    with gzip.open(os.path.join("out", name), "wb") as handle:
        handle.write(b"".join(line + b"\n" for line in lines))

    print(f"{name}: {len(lines)} pages, status {status}")
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
