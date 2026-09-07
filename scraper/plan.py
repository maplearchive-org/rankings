"""Discover a ranking day's floor once per world, then emit the slices this
firing has to fetch, as workflow outputs."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from day import ranking_day
from floor import deepest_offset
from manifest import (
    count_pages,
    depths_of,
    incomplete_slices,
    merge_manifest,
    read_manifest,
)
from scrape import Blocked, fetch_body as _fetch_body
from slices import RANKS_PER_PAGE, WORLDS


class ProbeFailed(Exception):
    """A probe fetch_body could not answer after exhausting its own retries."""


def fetch_page(region, world_id, page, state, fetch_body=None):
    """
    One page of a world's ranking, parsed into ``{"totalCount", "ranks"}``.

    This is the one place in the service that reads a response body's
    content, and it does not break the rule that a body is never parsed:
    that rule protects the bytes that get *published*, and nothing read here
    is ever written into an asset. deepest_offset's binary search decides a
    range; it throws every page it reads away. The slice path in scrape.py
    still moves bytes from urlopen into the gzip file undecoded.

    A page fetch_body cannot answer - its own transient retries exhausted,
    which is different from the Blocked it raises on its own for a
    confirmed block - must not be read as "past the end". Doing so would
    turn a network hiccup into a boundary, and the search would have no way
    to tell the difference between a hole and the world actually ending
    there; the twenty-page margin only covers an off-by-one in the
    arithmetic, not a lying probe. Raising instead hands the decision to the
    caller, which is exactly what search_missing does with it.

    `state` is supplied by the caller and shared across every probe of one
    search rather than created fresh per page: a fresh dict per page would
    forget an earlier 403 and pay the sixty-second grace again on every
    single probe of an address that is, in fact, blocked.

    Pacing and the User-Agent are Task 2's fetch_body, reused rather than
    duplicated - there is no second HTTP path.

    `fetch_body` defaults to None rather than binding `_fetch_body` directly
    in the signature. A default argument is evaluated once, at definition
    time, so binding the real network fetcher there would freeze in
    whatever `_fetch_body` was when the module loaded - a later
    `patch("plan._fetch_body", ...)` would rebind the module attribute but
    never reach a call that already closed over the old function object.
    Resolving it here, on every call, is what lets a test replace the
    network path at all; getting this wrong is what sent about 300 live
    requests to Nexon from a test suite in this project already.
    """
    fetch_body = fetch_body or _fetch_body
    offset = (page - 1) * RANKS_PER_PAGE + 1
    body = fetch_body(region, world_id, offset, state)
    if body is None:
        raise ProbeFailed(f"{region}/{world_id} page {page} (offset {offset})")
    return json.loads(body)


def search_missing(recorded, fetch_body=None):
    """
    The depths found by searching every world `recorded` does not already
    name - never the ones it does, because a depth already recorded must
    never move.

    A world whose search raises ProbeFailed is left out of the result rather
    than guessed at: it stays missing, which is what lets a later firing -
    this same run's repair wave, or a future day - search it again.

    A Blocked address stops the search rather than raising out of this
    function: every further probe from this runner would fail too, so
    trying the remaining worlds would only spend an hour finding that out
    one probe at a time. What was already found for earlier worlds this
    call is kept - losing it would turn one blocked probe into losing
    progress on every world, which is worse than the block itself.

    `fetch_body` defaults to None for the same reason fetch_page's does:
    main() calls this with no override at all, so if the default bound the
    real network fetcher at definition time, no test could ever replace it
    here - a `patch("plan._fetch_body", ...)` would leave this function
    still holding the object it closed over when the module loaded.
    """
    fetch_body = fetch_body or _fetch_body
    found = {}
    state = {"blocked_once": False}

    def fetch(region, world_id, page):
        return fetch_page(region, world_id, page, state, fetch_body=fetch_body)

    for world in WORLDS:
        key = f"{world['region']}/{world['world_id']}"
        if key in recorded:
            continue
        try:
            deepest = deepest_offset(fetch, world["region"], world["world_id"])
        except ProbeFailed as error:
            print(
                f"{key}: could not be searched this firing ({error}) - "
                "leaving it for a later one.",
                file=sys.stderr,
            )
            continue
        except Blocked as error:
            print(
                f"{key}: {error} Abandoning the rest of this search - a "
                "blocked address will not answer the remaining worlds "
                "either.",
                file=sys.stderr,
            )
            break
        if deepest is not None:
            found[key] = deepest
    return found


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--depths", default="{}")
    # None on the first wave: nothing has been fetched yet, so every slice is
    # missing and {} says so correctly. The repair wave sets this to the
    # directory the first wave's artifacts were downloaded into, so the
    # manifest this invocation builds reflects what actually arrived rather
    # than starting the day over - without it, read_manifest(day) is still
    # None (publish.py has not run yet), counted would stay {}, and
    # incomplete_slices would hand back every slice instead of the handful
    # that actually failed.
    parser.add_argument("--out-dir", default=None)
    args = parser.parse_args()

    day = ranking_day(datetime.now(timezone.utc))
    previous = read_manifest(day)

    # Depths already known, from whichever source has them: a committed
    # manifest first - a recorded depth never moves - then depths handed in
    # from an earlier invocation of this same firing. The repair wave calls
    # this script a second time before publish has ever run, so
    # read_manifest(day) alone cannot see what the first invocation found;
    # --depths is how that carries forward without searching the same world
    # twice, or landing on a different page and moving its partition.
    recorded = dict(depths_of(previous))
    for key, value in json.loads(args.depths).items():
        recorded.setdefault(key, value)

    missing = [
        world
        for world in WORLDS
        if f"{world['region']}/{world['world_id']}" not in recorded
    ]

    if missing:
        found = search_missing(recorded)
        recorded.update(found)
        print(f"{day}: searched the floor: {found}", file=sys.stderr)
    else:
        print(f"{day}: reusing the recorded depths: {recorded}", file=sys.stderr)

    counted = count_pages(args.out_dir) if args.out_dir else {}
    manifest = merge_manifest(day, previous, counted, recorded)
    work = incomplete_slices(manifest)

    # One workflow, one rule: fetch whatever the manifest says is missing. At
    # 18:05 UTC that is everything; later in the same run it is usually
    # nothing and the run ends here in seconds. The repair wave is therefore
    # the same code that runs every time, not a second one that only
    # executes when something has already gone wrong.
    matrix = [
        {
            "region": one["region"],
            "world_id": one["world_id"],
            "from": one["from"],
            "to": one["to"],
        }
        for one in work
    ]

    print(
        f"{day}: {len(work)} of {len(manifest['slices'])} slices to fetch.",
        file=sys.stderr,
    )

    lines = [
        f"day={day}",
        f"any={'true' if work else 'false'}",
        f"slices={json.dumps(matrix, separators=(',', ':'))}",
        # The depths this ranking day is fixed against so far - not just what
        # this invocation searched, so a repair-wave invocation can pass it
        # straight back in and neither invocation re-searches a world the
        # other one already found.
        f"depths={json.dumps(depths_of(manifest), separators=(',', ':'))}",
    ]

    destination = os.environ.get("GITHUB_OUTPUT")
    if destination:
        with open(destination, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    else:
        print("\n".join(lines))

    return 0


if __name__ == "__main__":
    sys.exit(main())
