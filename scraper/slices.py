"""The six worlds, and how a run is cut up."""

# The IDs were determined by probing id=0..70 in both regions; every other ID
# answers totalCount 0. These are the same six the archive scrapes, and the two
# lists must agree - a world here that the archive does not know would have its
# slices refused by the manifest check on that side.
WORLDS = [
    {"region": "na", "world_id": 1},
    {"region": "na", "world_id": 19},
    {"region": "na", "world_id": 45},
    {"region": "na", "world_id": 70},
    {"region": "eu", "world_id": 30},
    {"region": "eu", "world_id": 46},
]

RANKS_PER_PAGE = 10

# A slice is 500 requests from one address, and that number is the one thing
# the level floor did not change: the evidence says the ceiling behaves like
# roughly 800 requests per five-minute window per address, and 500 is about
# two thirds of it. What changed is how many slices there are - about 45 a
# day rather than twelve - because a world's depth is discovered each morning.
PAGES_PER_SLICE = 500

# Six digits, not five. Kronos reaches offset 153,791 today; at :05d that
# renders as six characters while every shallower world stays at five, and a
# listing of mixed widths does not sort by offset - which is the only thing
# the padding is for. Six covers a world of a million characters at the floor.
OFFSET_DIGITS = 6


def asset_name(region, world_id, first, last):
    """The file a slice writes. Zero-padded so a listing sorts by offset."""
    return (
        f"{region}-{world_id}-"
        f"{first:0{OFFSET_DIGITS}d}-{last:0{OFFSET_DIGITS}d}.ndjson.gz"
    )


def slices(depths):
    """
    Every slice of a run, over the ranges this ranking day discovered.

    `depths` maps "<region>/<world_id>" to the deepest offset that world's
    last slice must reach. A world that is not in it produces no slices at
    all rather than a guess: an empty world and a world nobody searched are
    different things, and inventing a range for either would publish offsets
    no page exists at.

    The last slice of a world is short. Rounding it up to a full 500 would
    declare offsets that never existed, and the archive walks to what the
    manifest declares - it would ask for every one of them and count them as
    pages no source had, which is the number that says whether a release has
    holes in it.
    """
    out = []
    for world in WORLDS:
        deepest = depths.get(f"{world['region']}/{world['world_id']}")
        if deepest is None:
            continue
        pages = (deepest - 1) // RANKS_PER_PAGE + 1
        for start in range(0, pages, PAGES_PER_SLICE):
            count = min(PAGES_PER_SLICE, pages - start)
            first = start * RANKS_PER_PAGE + 1
            last = (start + count - 1) * RANKS_PER_PAGE + 1
            out.append(
                {
                    "region": world["region"],
                    "world_id": world["world_id"],
                    "from": first,
                    "to": last,
                    "pages_expected": count,
                    "asset": asset_name(
                        world["region"], world["world_id"], first, last
                    ),
                }
            )
    return out


def offsets_of(one):
    """
    The page_index values a slice covers.

    page_index is a rank offset, not a page counter: its value is the first
    rank returned and every answer holds ten, so the offsets step by ten.
    """
    return list(range(one["from"], one["to"] + 1, RANKS_PER_PAGE))
