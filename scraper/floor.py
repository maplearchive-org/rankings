"""Where a world stops: the last page still holding a character at the floor."""

from slices import RANKS_PER_PAGE

# Shared with the archive's src/config.ts, and written down in both
# repositories because there is nowhere else to put it. The manifest carries
# it and the archive refuses a manifest whose floor is not its own: a service
# stopping above the archive's floor publishes no page carrying a character
# below it, so no world could ever be completed and nothing would say why.
FLOOR = 275

# Pages published past the boundary the search found. A search that landed one
# page short would truncate the world permanently: the archive would refuse the
# day - loudly, which is correct - and a whole ranking day would be lost to an
# off-by-one, with no way to fetch it again once the window closed. Two hundred
# extra ranks across six worlds, against 22,334 pages, is not a cost.
MARGIN_PAGES = 20


def _offset_of(page):
    """Page 1 starts at offset 1, page 2 at offset 11, and so on."""
    return (page - 1) * RANKS_PER_PAGE + 1


def deepest_offset(fetch_page, region, world_id):
    """
    The offset this world's last slice must reach, or None if the world is
    empty.

    `fetch_page(region, world_id, page)` returns the parsed body of one page.
    Parsing is deliberate and does not break the rule that a body is never
    parsed: nothing read here is ever written into an asset. The search looks
    at `level` on pages it throws away, and the slice path in scrape.py still
    moves bytes from urlopen into the gzip file without decoding them.

    Level is non-increasing with rank, so "this page's last rank is at or
    above the floor" is monotone in the page number and the search is valid.
    It costs about sixteen to thirty-three requests per world - 157 for all
    six, measured on 2026-09-07 - from a runner that then does nothing else,
    which is far under the roughly 800-per-five-minute-window the slice size
    is built around.
    """
    first = fetch_page(region, world_id, 1)
    if not first["ranks"]:
        return None

    # Invariant: `low` is a page believed to hold the floor and `high` is one
    # that does not. `low` starts at 1 even when page 1 is already below the
    # floor - the archive completes such a world on its first page, and
    # publishing the margin anyway keeps one shape for every world.
    low = 1
    high = -(-first["totalCount"] // RANKS_PER_PAGE) + 1

    while high - low > 1:
        middle = (low + high) // 2
        ranks = fetch_page(region, world_id, middle)["ranks"]
        if ranks and ranks[-1]["level"] >= FLOOR:
            low = middle
        else:
            high = middle

    return _offset_of(low + MARGIN_PAGES)
