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
PAGES_PER_WORLD = 1000

# Two slices to a world, and not one. A whole world is 1,000 requests from a
# single address, and the evidence says the ceiling behaves like roughly 800
# requests per five-minute window per address - so one slice per world would
# meet it near the end, every day, reproducibly. 500 is about two thirds of it.
SLICES_PER_WORLD = 2


def asset_name(region, world_id, first, last):
    """The file a slice writes. Zero-padded so a listing sorts by offset."""
    return f"{region}-{world_id}-{first:05d}-{last:05d}.ndjson.gz"


def slices():
    """Every slice of a full run, in a stable order."""
    pages_per_slice = PAGES_PER_WORLD // SLICES_PER_WORLD
    out = []
    for world in WORLDS:
        for index in range(SLICES_PER_WORLD):
            first_page = index * pages_per_slice
            first = first_page * RANKS_PER_PAGE + 1
            last = (first_page + pages_per_slice - 1) * RANKS_PER_PAGE + 1
            out.append(
                {
                    "region": world["region"],
                    "world_id": world["world_id"],
                    "from": first,
                    "to": last,
                    "pages_expected": pages_per_slice,
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
