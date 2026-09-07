import unittest

from floor import FLOOR
from manifest import depths_of, incomplete_slices, merge_manifest
from slices import WORLDS, slices

# A depth for every world, each landing on exactly two full 500-page slices -
# the same twelve-slice shape Tasks 1 and 2 built against, so these tests read
# the way they did before the level floor made a world's depth a discovery
# rather than a constant.
DEPTHS = {f"{one['region']}/{one['world_id']}": 9991 for one in WORLDS}


class MergeManifest(unittest.TestCase):
    def test_a_fresh_day_is_entirely_incomplete(self):
        manifest = merge_manifest("2026-09-06", None, {}, DEPTHS)

        self.assertEqual(len(manifest["slices"]), len(slices(DEPTHS)))
        self.assertEqual(len(incomplete_slices(manifest)), len(slices(DEPTHS)))
        self.assertTrue(
            all(one["status"] == "missing" for one in manifest["slices"])
        )

    def test_a_slice_with_all_its_pages_counted_is_complete(self):
        one = slices(DEPTHS)[0]
        manifest = merge_manifest("2026-09-06", None, {one["asset"]: 500}, DEPTHS)

        stored = next(
            s for s in manifest["slices"] if s["asset"] == one["asset"]
        )
        self.assertEqual(stored["status"], "complete")
        self.assertEqual(stored["pages_present"], 500)
        self.assertEqual(len(incomplete_slices(manifest)), len(slices(DEPTHS)) - 1)

    def test_a_short_slice_stays_partial_and_stays_in_the_work_list(self):
        one = slices(DEPTHS)[0]
        manifest = merge_manifest("2026-09-06", None, {one["asset"]: 499}, DEPTHS)

        stored = next(
            s for s in manifest["slices"] if s["asset"] == one["asset"]
        )
        self.assertEqual(stored["status"], "partial")
        self.assertIn(
            one["asset"], [s["asset"] for s in incomplete_slices(manifest)]
        )

    def test_a_slice_completed_by_an_earlier_run_is_not_scraped_again(self):
        one = slices(DEPTHS)[0]
        earlier = merge_manifest("2026-09-06", None, {one["asset"]: 500}, DEPTHS)

        # This run counted nothing for it, because it did not fetch it. It
        # also passes no depths - the earlier manifest already recorded them,
        # and a recorded depth is not searched for twice.
        now = merge_manifest("2026-09-06", earlier, {})

        stored = next(s for s in now["slices"] if s["asset"] == one["asset"])
        self.assertEqual(stored["status"], "complete")

    def test_the_counted_total_always_wins_over_an_earlier_claim(self):
        one = slices(DEPTHS)[0]
        lying = merge_manifest("2026-09-06", None, {one["asset"]: 500}, DEPTHS)

        corrected = merge_manifest("2026-09-06", lying, {one["asset"]: 12})

        stored = next(
            s for s in corrected["slices"] if s["asset"] == one["asset"]
        )
        self.assertEqual(stored["pages_present"], 12)

    def test_the_shape_is_the_one_the_archive_parses(self):
        # The archive refuses a manifest whose format_version or ranks_per_page
        # it does not recognise, and it reads exactly these slice fields. This
        # test is the contract between two repositories; changing it means
        # changing src/scrape/manifest.ts on the other side in the same breath.
        manifest = merge_manifest("2026-09-06", None, {}, DEPTHS)

        self.assertEqual(manifest["format_version"], 1)
        self.assertEqual(manifest["ranks_per_page"], 10)
        self.assertEqual(manifest["ranking_day"], "2026-09-06")
        self.assertIn("generated_at", manifest)
        self.assertEqual(
            sorted(manifest["slices"][0]),
            sorted(
                [
                    "region",
                    "world_id",
                    "from",
                    "to",
                    "asset",
                    "pages_expected",
                    "pages_present",
                    "status",
                ]
            ),
        )

    def test_the_manifest_states_the_floor_it_was_published_against(self):
        # The archive refuses a manifest whose floor is not its own. If this
        # service stopped at a higher level it would never publish a page
        # carrying a character below 275, so no world could ever show the
        # archive the sighting its completeness rule needs, and every ranking
        # day would stay incomplete for ever with nothing naming the cause.
        manifest = merge_manifest("2026-09-06", None, {}, {"na/1": 14211})

        self.assertEqual(manifest["floor"], FLOOR)

    def test_a_depth_is_discovered_once_and_then_fixed(self):
        first = merge_manifest("2026-09-06", None, {}, {"na/1": 14211})

        # A later firing searched again and got a different answer. It loses.
        later = merge_manifest("2026-09-06", first, {}, {"na/1": 14411})

        self.assertEqual(depths_of(later), {"na/1": 14211})

    def test_a_world_missing_from_the_recorded_depths_can_still_be_added(self):
        # The bug this guards against: treating the whole depths map as one
        # fixed-or-not unit freezes a world that failed to search out for the
        # rest of the day the moment any *other* world's depth is recorded.
        # The merge must be per world - na/1 already recorded never moves,
        # but eu/30, missing until now, is free to be added.
        first = merge_manifest("2026-09-06", None, {}, {"na/1": 14211})

        later = merge_manifest(
            "2026-09-06", first, {}, {"na/1": 999999, "eu/30": 3311}
        )

        self.assertEqual(depths_of(later), {"na/1": 14211, "eu/30": 3311})

    def test_a_moved_depth_would_have_moved_the_partition(self):
        # Why the test above matters: two searches disagreeing by a page move
        # every slice boundary after the first, and a page can then fall
        # between the old slices and the new ones and be fetched by neither.
        self.assertNotEqual(
            [one["asset"] for one in slices({"na/1": 14211})],
            [one["asset"] for one in slices({"na/1": 14411})],
        )


if __name__ == "__main__":
    unittest.main()
