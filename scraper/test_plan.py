import json
import unittest
from unittest.mock import patch

from scrape import Blocked

from plan import ProbeFailed, fetch_page, search_missing


class FetchPageDoesNotFakeAnAnswer(unittest.TestCase):
    def test_a_probe_fetch_body_cannot_answer_raises_rather_than_faking_empty(self):
        # The bug this guards against: reading a failed probe as "past the
        # end" halves the remaining range downward on every such failure,
        # and the twenty-page margin does nothing against that - it only
        # covers an off-by-one in the arithmetic, not a lying probe.
        def unanswerable(region, world_id, offset, state):
            return None

        with self.assertRaises(ProbeFailed):
            fetch_page("na", 1, 5, {"blocked_once": False}, fetch_body=unanswerable)

    def test_an_answered_probe_is_parsed_normally(self):
        def answered(region, world_id, offset, state):
            return json.dumps(
                {"totalCount": 100, "ranks": [{"level": 300}]}
            ).encode()

        result = fetch_page("na", 1, 1, {"blocked_once": False}, fetch_body=answered)

        self.assertEqual(result["totalCount"], 100)

    def test_a_blocked_probe_still_raises_blocked_not_probe_failed(self):
        def blocked(region, world_id, offset, state):
            raise Blocked("blocked")

        with self.assertRaises(Blocked):
            fetch_page("na", 1, 1, {"blocked_once": False}, fetch_body=blocked)


class SearchMissing(unittest.TestCase):
    def test_a_world_whose_probe_fails_is_left_out_and_does_not_stop_the_rest(self):
        worlds = [{"region": "na", "world_id": 1}, {"region": "eu", "world_id": 30}]

        def flaky(region, world_id, offset, state):
            if region == "na":
                return None  # na/1's every probe fails
            return json.dumps({"totalCount": 10, "ranks": [{"level": 200}]}).encode()

        with patch("plan.WORLDS", worlds):
            found = search_missing({}, fetch_body=flaky)

        self.assertEqual(list(found), ["eu/30"])

    def test_a_world_already_recorded_is_never_searched_again(self):
        worlds = [{"region": "na", "world_id": 1}]

        def boom(region, world_id, offset, state):
            raise AssertionError("a recorded world must not be searched again")

        with patch("plan.WORLDS", worlds):
            found = search_missing({"na/1": 14211}, fetch_body=boom)

        self.assertEqual(found, {})

    def test_a_block_stops_the_search_but_keeps_what_was_already_found(self):
        worlds = [
            {"region": "na", "world_id": 1},
            {"region": "eu", "world_id": 30},
            {"region": "eu", "world_id": 46},
        ]
        calls = []

        def fetch_body(region, world_id, offset, state):
            calls.append((region, world_id))
            if region == "na":
                return json.dumps(
                    {"totalCount": 10, "ranks": [{"level": 200}]}
                ).encode()
            raise Blocked("blocked")

        with patch("plan.WORLDS", worlds):
            found = search_missing({}, fetch_body=fetch_body)

        # na/1 was found before the block; eu/46 was never even attempted -
        # the point of stopping rather than trying every remaining world.
        self.assertEqual(list(found), ["na/1"])
        self.assertNotIn(("eu", 46), calls)

    def test_one_state_is_shared_across_every_probe_of_the_search(self):
        # A fresh {"blocked_once": False} per page would pay the sixty-second
        # grace on every single 403 from a genuinely blocked address, instead
        # of once for the whole search. Assert on the object identity fed to
        # fetch_body rather than the timing, which would make this test slow
        # and flaky.
        worlds = [{"region": "na", "world_id": 1}]
        seen_states = []

        def fetch_body(region, world_id, offset, state):
            seen_states.append(id(state))
            return json.dumps({"totalCount": 10, "ranks": [{"level": 200}]}).encode()

        with patch("plan.WORLDS", worlds):
            search_missing({}, fetch_body=fetch_body)

        self.assertEqual(len(set(seen_states)), 1)


if __name__ == "__main__":
    unittest.main()
