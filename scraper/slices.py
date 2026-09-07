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

# 250, not the 500 the first production run shipped with. 500 was chosen
# against an assumed ceiling of about 800 requests per five-minute window per
# address, on the theory that two thirds of it left margin. Run 34127322901
# said otherwise: slice after slice lost pages from roughly offset 480
# onward, in both the scrape wave and the repair wave that refetched it - the
# address was throttled well short of 500, not close to it. Whether the real
# ceiling is per address or per network neighbourhood (twenty concurrent
# runners share related Azure ranges) is not established, and this number
# does not try to establish it either; it just stops asking one address for
# as much.
#
# Halving what one address is asked for does not by itself fix anything - a
# slice that thins out at 96% of 500 would thin out at 96% of 250 too. What
# makes it work is that the repair wave now accumulates instead of replacing
# (see scrape_slice): a slice's first pass reaches most of the way, its
# second pass starts from there rather than from zero, and two passes each
# thinning out at their own end still cover the whole slice between them.
#
# The honest cost: about 90 slices a day instead of 45, and at twenty
# concurrent runners that is five waves of runners rather than three. A job
# spends about 55 seconds on setup regardless of how much it fetches, so
# halving the slice does not halve the day - it adds roughly two more waves'
# worth of that fixed setup cost on top of the same total fetching time.
PAGES_PER_SLICE = 250

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

    The last slice of a world is short. Rounding it up to a full
    PAGES_PER_SLICE would declare offsets that never existed, and the archive
    walks to what the manifest declares - it would ask for every one of them
    and count them as pages no source had, which is the number that says
    whether a release has holes in it.
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
