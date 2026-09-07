import unittest

from slices import (
    RANKS_PER_PAGE,
    WORLDS,
    asset_name,
    offsets_of,
    slices,
)


class SliceArithmetic(unittest.TestCase):
    def test_a_full_slice_is_five_hundred_pages(self):
        # A depth that lands exactly on two full slices - the shape every
        # world had before the level floor made the last slice of a world
        # short. Task 1's reasoning about why a slice is 500 requests is
        # untouched; only how many slices there are changed.
        for one in slices({"na/1": 9991}):
            self.assertEqual(one["pages_expected"], 500)
            self.assertEqual(len(offsets_of(one)), 500)

    def test_an_asset_name_sorts_by_offset_and_names_its_world(self):
        self.assertEqual(
            asset_name("na", 1, 1, 4991), "na-1-000001-004991.ndjson.gz"
        )

    def test_the_specification_values_are_what_the_design_says(self):
        # Deliberately restates what the module declares. A real change -
        # MapleStory adding a world - has to touch two places.
        self.assertEqual(
            WORLDS,
            [
                {"region": "na", "world_id": 1},
                {"region": "na", "world_id": 19},
                {"region": "na", "world_id": 45},
                {"region": "na", "world_id": 70},
                {"region": "eu", "world_id": 30},
                {"region": "eu", "world_id": 46},
            ],
        )
        self.assertEqual(RANKS_PER_PAGE, 10)

    def test_the_slices_cover_a_discovered_range_with_no_gap(self):
        # The test that matters, with the range as an input rather than a
        # constant. An overlap is harmless - the archive writes with INSERT OR
        # REPLACE - and a gap is a page nobody ever fetches.
        depths = {"na/45": 153991, "eu/30": 3311}

        seen = set()
        for one in slices(depths):
            for offset in offsets_of(one):
                key = (one["region"], one["world_id"], offset)
                self.assertNotIn(key, seen, f"{key} is covered twice")
                seen.add(key)

        for key, deepest in depths.items():
            region, world_id = key.split("/")
            for offset in range(1, deepest + 1, RANKS_PER_PAGE):
                self.assertIn(
                    (region, int(world_id), offset), seen, f"{key} {offset} uncovered"
                )

    def test_the_last_slice_of_a_world_is_short_and_not_rounded_up(self):
        # A slice that declared 500 offsets when only 120 pages remain would
        # make the archive ask for 380 offsets no page ever existed at and
        # count them as pages no source had - the one number that says
        # whether a release has holes in it.
        world = [one for one in slices({"eu/30": 3311}) if one["world_id"] == 30]

        self.assertEqual([one["pages_expected"] for one in world], [332])
        self.assertEqual(world[-1]["to"], 3311)

    def test_a_world_with_no_discovered_depth_produces_no_slices(self):
        self.assertEqual(slices({}), [])

    def test_asset_names_sort_by_offset_across_the_deepest_world(self):
        # Six digits, not five. Kronos reaches offset 153,791: at :05d that
        # renders as six characters while every shallower world stays at five,
        # and a listing of mixed widths stops sorting by offset - which is the
        # only thing the padding is for.
        names = [one["asset"] for one in slices({"na/45": 153991})]

        self.assertEqual(names, sorted(names))
        self.assertEqual(names[0], "na-45-000001-004991.ndjson.gz")


if __name__ == "__main__":
    unittest.main()
