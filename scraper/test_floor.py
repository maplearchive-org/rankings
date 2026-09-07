import unittest

from floor import FLOOR, MARGIN_PAGES, deepest_offset
from slices import RANKS_PER_PAGE


def world_of(pages_at_floor, total_pages):
    """
    A world whose first `pages_at_floor` pages are entirely at or above the
    floor and whose later pages are below it. Level is non-increasing with
    rank in the real ranking, which is the only reason a binary search is
    allowed here at all.
    """
    calls = []

    def fetch_page(region, world_id, page):
        calls.append(page)
        if page > total_pages:
            return {"totalCount": total_pages * RANKS_PER_PAGE, "ranks": []}
        level = 300 if page <= pages_at_floor else FLOOR - 1
        return {
            "totalCount": total_pages * RANKS_PER_PAGE,
            "ranks": [
                {"rank": (page - 1) * RANKS_PER_PAGE + i + 1, "level": level}
                for i in range(RANKS_PER_PAGE)
            ],
        }

    return fetch_page, calls


class FindTheFloor(unittest.TestCase):
    def test_the_range_reaches_past_the_last_page_at_the_floor(self):
        fetch_page, _ = world_of(pages_at_floor=15381, total_pages=700000)

        deepest = deepest_offset(fetch_page, "na", 45)

        # The boundary page is 15382 - the first one carrying a character
        # below the floor, and the one the archive needs in order to call the
        # world whole. The margin puts the range comfortably past it.
        self.assertEqual(deepest, (15381 + MARGIN_PAGES - 1) * RANKS_PER_PAGE + 1)

    def test_the_boundary_page_is_always_inside_the_range(self):
        # The archive completes a world only when its deepest stored page
        # carries a character below the floor. A range that stopped on the
        # last page above it would truncate the world permanently, and the
        # day would be refused - correctly, and far too late.
        for pages in (1, 2, 311, 1420, 15381):
            fetch_page, _ = world_of(pages_at_floor=pages, total_pages=700000)
            deepest = deepest_offset(fetch_page, "na", 1)
            boundary = pages * RANKS_PER_PAGE + 1
            self.assertGreaterEqual(deepest, boundary, f"{pages} pages")

    def test_the_search_costs_a_few_dozen_requests_and_not_a_walk(self):
        fetch_page, calls = world_of(pages_at_floor=15381, total_pages=700000)

        deepest_offset(fetch_page, "na", 45)

        # Measured on 2026-09-07: about 157 requests for all six worlds. A
        # search that walked would be seventy thousand and would meet the
        # ceiling the whole design is built around avoiding.
        self.assertLess(len(calls), 40)

    def test_a_world_with_nobody_at_the_floor_still_publishes_its_first_pages(self):
        fetch_page, _ = world_of(pages_at_floor=0, total_pages=700000)

        deepest = deepest_offset(fetch_page, "na", 1)

        # Page 1 already carries a character below the floor, so the archive
        # completes the world on it. Publishing the margin anyway costs
        # twenty pages and keeps one shape for every world.
        self.assertGreaterEqual(deepest, 1)

    def test_an_empty_world_has_no_depth_at_all(self):
        def empty(region, world_id, page):
            return {"totalCount": 0, "ranks": []}

        self.assertIsNone(deepest_offset(empty, "na", 1))


if __name__ == "__main__":
    unittest.main()
