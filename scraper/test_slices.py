import unittest

from slices import (
    PAGES_PER_WORLD,
    RANKS_PER_PAGE,
    WORLDS,
    asset_name,
    offsets_of,
    slices,
)


class SliceArithmetic(unittest.TestCase):
    def test_twelve_slices_cover_every_offset_exactly_once(self):
        all_slices = slices()
        self.assertEqual(len(all_slices), len(WORLDS) * 2)

        seen = set()
        for one in all_slices:
            for offset in offsets_of(one):
                key = (one["region"], one["world_id"], offset)
                self.assertNotIn(key, seen, f"{key} is covered twice")
                seen.add(key)

        self.assertEqual(len(seen), len(WORLDS) * PAGES_PER_WORLD)

        # No gap: every offset the archive will ask for is in the set. Built
        # from the constants rather than from slices(), so a boundary that is
        # wrong in the module cannot make itself right here.
        for world in WORLDS:
            for page in range(PAGES_PER_WORLD):
                offset = page * RANKS_PER_PAGE + 1
                key = (world["region"], world["world_id"], offset)
                self.assertIn(key, seen, f"{key} is covered by no slice")

    def test_a_slice_is_five_hundred_pages(self):
        for one in slices():
            self.assertEqual(one["pages_expected"], 500)
            self.assertEqual(len(offsets_of(one)), 500)

    def test_the_ranges_are_the_two_halves_of_a_world(self):
        first_world = [
            (one["from"], one["to"])
            for one in slices()
            if one["region"] == "na" and one["world_id"] == 1
        ]

        self.assertEqual(first_world, [(1, 4991), (5001, 9991)])

    def test_an_asset_name_sorts_by_offset_and_names_its_world(self):
        self.assertEqual(asset_name("na", 1, 1, 4991), "na-1-00001-04991.ndjson.gz")

    def test_the_specification_values_are_what_the_design_says(self):
        # Deliberately restates what the module declares. Every other test here
        # derives its expectations from WORLDS and PAGES_PER_WORLD, so without
        # this one a world quietly dropped from the list would leave the whole
        # suite green while twelve slices stopped covering what they must.
        # A real change - MapleStory adding a world - has to touch two places.
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
        self.assertEqual(PAGES_PER_WORLD, 1000)
        self.assertEqual(RANKS_PER_PAGE, 10)


if __name__ == "__main__":
    unittest.main()
