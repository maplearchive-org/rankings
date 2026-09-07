import gzip
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scrape import Blocked
from slices import asset_name

from plan import ProbeFailed, fetch_page, main, search_missing


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

    def test_a_malformed_200_raises_probe_failed_rather_than_json_decode_error(self):
        # scrape.py already documents this API as capable of a short or
        # malformed body on an ordinary success status. A probe that cannot
        # be parsed cannot say where the floor is any more than one that
        # never arrived can - it is the same fact as an unanswerable probe,
        # not a crash that should take down the search.
        def truncated(region, world_id, offset, state):
            return b'{"totalCount": 100, "ranks": ['  # cut off mid-body

        with self.assertRaises(ProbeFailed):
            fetch_page("na", 1, 1, {"blocked_once": False}, fetch_body=truncated)

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


class MainRespectsOutDir(unittest.TestCase):
    """
    plan.py's main() builds its manifest with merge_manifest(day, previous,
    {}, recorded) - an empty `counted`. That is right for the first
    invocation of a firing, where nothing has been fetched yet. It would be
    wrong for the repair wave, which runs before publish.py has ever written
    a manifest: read_manifest(day) is None, counted would stay {}, and
    incomplete_slices would hand back every slice rather than the handful
    that actually failed. --out-dir is what lets the repair wave hand in
    what really arrived instead.

    A single fake world, with a fetch_body that only ever answers pages 1
    and 2, is enough to exercise both halves of main() without depending on
    the real six worlds or their real depths - and small enough that the
    binary search's own path through it is easy to verify by hand: page 1
    reports totalCount 15, so `high` starts at 3; the loop tries only page 2
    before converging on low=2, giving a deepest offset of 211 and a single
    22-page slice.
    """

    WORLDS = [{"region": "na", "world_id": 1}]
    ASSET = asset_name("na", 1, 1, 211)
    SLICE = {"region": "na", "world_id": 1, "from": 1, "to": 211}

    @staticmethod
    def _fetch_body(region, world_id, offset, state):
        if offset == 1:
            return json.dumps(
                {"totalCount": 15, "ranks": [{"level": 300}] * 10}
            ).encode()
        if offset == 11:
            return json.dumps(
                {"totalCount": 15, "ranks": [{"level": 300}] * 5}
            ).encode()
        raise AssertionError(f"unexpected offset {offset} for this fake world")

    def _run(self, argv, tmp_dir):
        cwd = os.getcwd()
        os.chdir(tmp_dir)
        github_output = os.path.join(tmp_dir, "github_output")
        try:
            with patch("sys.argv", ["plan.py"] + argv), patch(
                "plan.WORLDS", self.WORLDS
            ), patch("plan._fetch_body", self._fetch_body), patch.dict(
                os.environ, {"GITHUB_OUTPUT": github_output}
            ):
                code = main()
            with open(github_output, encoding="utf-8") as handle:
                outputs = dict(
                    line.split("=", 1) for line in handle.read().splitlines() if line
                )
            return code, outputs
        finally:
            os.chdir(cwd)

    def test_with_no_out_dir_every_slice_is_planned(self):
        # The seam this guards: patch("plan._fetch_body", ...) has to reach
        # main() through search_missing and fetch_page's own defaults. Both
        # used to bind the real fetch_body at definition time, so this patch
        # would silently miss and the test would make a live request - the
        # wall time this whole file runs in is the evidence it did not.
        tmp_dir = tempfile.mkdtemp()
        try:
            code, outputs = self._run([], tmp_dir)
            self.assertEqual(code, 0)
            self.assertEqual(outputs["any"], "true")
            self.assertEqual(json.loads(outputs["slices"]), [self.SLICE])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_an_out_dir_holding_a_complete_slice_is_not_planned_again(self):
        # This is the repair wave's own shape: no committed manifest yet
        # (read_manifest(day) is None, same as the first wave), but the
        # slice's file is already sitting in --out-dir, complete. Without
        # --out-dir carrying that forward, this slice would be planned again
        # even though its 22 pages already arrived.
        tmp_dir = tempfile.mkdtemp()
        try:
            out_dir = os.path.join(tmp_dir, "out")
            os.makedirs(out_dir)
            with gzip.open(os.path.join(out_dir, self.ASSET), "wb") as handle:
                handle.write(b"{}\n" * 22)

            code, outputs = self._run(["--out-dir", out_dir], tmp_dir)

            self.assertEqual(code, 0)
            self.assertEqual(outputs["any"], "false")
            self.assertEqual(json.loads(outputs["slices"]), [])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
