"""Discover a ranking day's floor once, then emit the slices this firing has
to fetch, as workflow outputs."""

import json
import os
import sys
from datetime import datetime, timezone

from day import ranking_day
from floor import deepest_offset
from manifest import depths_of, incomplete_slices, merge_manifest, read_manifest
from scrape import fetch_body
from slices import RANKS_PER_PAGE, WORLDS


def fetch_page(region, world_id, page):
    """
    One page of a world's ranking, parsed into ``{"totalCount", "ranks"}``.

    This is the one place in the service that reads a response body's
    content, and it does not break the rule that a body is never parsed: that
    rule protects the bytes that get *published*, and nothing read here is
    ever written into an asset. deepest_offset's binary search decides a
    range; it throws every page it reads away. The slice path in scrape.py
    still moves bytes from urlopen into the gzip file undecoded.

    Pacing and the User-Agent are Task 2's fetch_body, reused rather than
    duplicated - there is no second HTTP path.
    """
    offset = (page - 1) * RANKS_PER_PAGE + 1
    body = fetch_body(region, world_id, offset, {"blocked_once": False})
    if body is None:
        # A page the search cannot get an answer for is treated as past the
        # boundary, so a run of failures ends the search rather than hanging
        # on a hole. The margin covers a boundary guessed slightly short.
        return {"totalCount": 0, "ranks": []}
    return json.loads(body)


day = ranking_day(datetime.now(timezone.utc))
previous = read_manifest(day)
depths = depths_of(previous)

if not depths:
    # The first firing of a ranking day. About 157 requests from this one
    # runner, and then it does nothing else.
    depths = {}
    for world in WORLDS:
        deepest = deepest_offset(fetch_page, world["region"], world["world_id"])
        if deepest is not None:
            depths[f"{world['region']}/{world['world_id']}"] = deepest
    print(f"{day}: searched the floor: {depths}", file=sys.stderr)
else:
    print(f"{day}: reusing the recorded depths: {depths}", file=sys.stderr)

manifest = merge_manifest(day, previous, {}, depths)
work = incomplete_slices(manifest)

# One workflow, one rule: fetch whatever the manifest says is missing. At
# 18:05 UTC that is everything; an hour later it is usually nothing and the run
# ends here in seconds. The repair path is therefore the same code that runs
# every day, not a second one that only executes when something has already
# gone wrong.
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
    # The depths this ranking day is fixed against - recorded, not just what
    # this firing searched, so a later firing that reused them republishes the
    # same value rather than losing it if this firing's search is discarded.
    f"depths={json.dumps(depths_of(manifest), separators=(',', ':'))}",
]

destination = os.environ.get("GITHUB_OUTPUT")
if destination:
    with open(destination, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
else:
    print("\n".join(lines))
