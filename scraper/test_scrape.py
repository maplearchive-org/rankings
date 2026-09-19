import gzip
import os
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from day import ranking_day
from line import slice_line
from scrape import Blocked, scrape_slice


class ScrapeSliceBlockedImmediately(unittest.TestCase):
    def test_a_slice_blocked_at_its_first_offset_writes_zero_pages(self):
        day = ranking_day(datetime.now(timezone.utc))
        tmp_dir = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(tmp_dir)
        try:
            with patch(
                "scrape.fetch_body",
                side_effect=Blocked("403 at offset 1; this address is blocked."),
            ):
                exit_code = scrape_slice(day, "na", 45, 1, 1)

            self.assertEqual(exit_code, 0)

            with gzip.open(
                os.path.join("out", "na-45-000001-000001.ndjson.gz"), "rb"
            ) as handle:
                body = handle.read()

            # The same filter publish.py applies when it counts a slice's
            # pages from the file: a byte count of zero must read back as
            # zero pages, not as one blank line.
            pages = [line for line in body.split(b"\n") if line.strip()]
            self.assertEqual(pages, [])
        finally:
            os.chdir(cwd)
            shutil.rmtree(tmp_dir, ignore_errors=True)


class ScrapeSliceGapFilling(unittest.TestCase):
    """
    scrape_slice must treat an existing out/<asset> as a starting point to
    fill, not a file to overwrite - the exact defect the first production
    run exposed: the repair wave refetched a whole slice and its download
    clobbered the first wave's better file.
    """

    def setUp(self):
        self.day = ranking_day(datetime.now(timezone.utc))
        self.tmp_dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.tmp_dir)
        self.addCleanup(os.chdir, self.cwd)
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

    def _write_existing(self, name, lines):
        os.makedirs("out", exist_ok=True)
        with gzip.open(os.path.join("out", name), "wb") as handle:
            handle.write(b"".join(line + b"\n" for line in lines))

    def test_only_the_offsets_missing_from_the_file_are_fetched(self):
        # A slice of five offsets - 1, 11, 21, 31, 41 - with 21 and 41
        # already on disk from an earlier wave.
        existing_line_21 = slice_line(21, b'{"totalCount":1,"ranks":[21]}')
        existing_line_41 = slice_line(41, b'{"totalCount":1,"ranks":[41]}')
        self._write_existing(
            "na-45-000001-000041.ndjson.gz",
            [existing_line_21, existing_line_41],
        )

        requested = []

        def fake_fetch_body(region, world_id, offset, state):
            requested.append(offset)
            return (
                b'{"totalCount":1,"ranks":['
                + b",".join(b'{"characterName":"x"}' for _ in range(10))
                + b"]}"
            )

        with patch("scrape.fetch_body", side_effect=fake_fetch_body):
            exit_code = scrape_slice(self.day, "na", 45, 1, 41)

        self.assertEqual(exit_code, 0)
        # 21 and 41 were already present; only the other three were asked
        # for, and asked for exactly once each.
        self.assertEqual(sorted(requested), [1, 11, 31])

        with gzip.open(
            os.path.join("out", "na-45-000001-000041.ndjson.gz"), "rb"
        ) as handle:
            body = handle.read()
        pages = [line for line in body.split(b"\n") if line.strip()]

        # The union, ordered by offset ascending, regardless of which wave
        # a given line came from.
        offsets = [
            int(re.match(rb'\{"o":(\d+),', line).group(1)) for line in pages
        ]
        self.assertEqual(offsets, [1, 11, 21, 31, 41])

    def test_a_line_carried_over_from_an_earlier_wave_is_byte_identical(self):
        # A body carrying digits that would change under any decode/re-encode
        # round trip - the same hazard line.py's own tests guard against.
        carried_body = b'{"totalCount":1,"ranks":[{"exp":9007199254740993}]}'
        carried_line = slice_line(11, carried_body)
        self._write_existing("na-45-000001-000011.ndjson.gz", [carried_line])

        def fake_fetch_body(region, world_id, offset, state):
            return (
                b'{"totalCount":1,"ranks":['
                + b",".join(b'{"characterName":"x"}' for _ in range(10))
                + b"]}"
            )

        with patch("scrape.fetch_body", side_effect=fake_fetch_body):
            exit_code = scrape_slice(self.day, "na", 45, 1, 11)

        self.assertEqual(exit_code, 0)

        with gzip.open(
            os.path.join("out", "na-45-000001-000011.ndjson.gz"), "rb"
        ) as handle:
            body = handle.read()
        pages = [line for line in body.split(b"\n") if line.strip()]

        self.assertIn(carried_line, pages)

    def test_no_existing_file_behaves_exactly_as_before(self):
        def fake_fetch_body(region, world_id, offset, state):
            return (
                b'{"totalCount":1,"ranks":['
                + b",".join(b'{"characterName":"x"}' for _ in range(10))
                + b"]}"
            )

        with patch("scrape.fetch_body", side_effect=fake_fetch_body):
            exit_code = scrape_slice(self.day, "na", 45, 1, 21)

        self.assertEqual(exit_code, 0)

        with gzip.open(
            os.path.join("out", "na-45-000001-000021.ndjson.gz"), "rb"
        ) as handle:
            body = handle.read()
        pages = [line for line in body.split(b"\n") if line.strip()]
        offsets = [
            int(re.match(rb'\{"o":(\d+),', line).group(1)) for line in pages
        ]
        self.assertEqual(offsets, [1, 11, 21])


class ScrapeSliceUnusableBody(unittest.TestCase):
    """
    A page this worker cannot put on one line is one page lost, never the
    slice. scrape_slice writes what it has for every other soft failure -
    a 403, a short answer - and returns 0 so upload-artifact still runs.
    A body it cannot encode has to travel the same road: on 2026-09-18 it
    did not, and every one of the day's 101 slices exited non-zero, so the
    release was published carrying its manifest and not one page.
    """

    def setUp(self):
        self.day = ranking_day(datetime.now(timezone.utc))
        self.tmp_dir = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.tmp_dir)
        self.addCleanup(os.chdir, self.cwd)
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

    def test_a_page_with_an_interior_newline_is_left_out_not_raised(self):
        full_page = (
            b'{"totalCount":1,"ranks":['
            + b",".join(b'{"characterName":"x"}' for _ in range(10))
            + b"]}"
        )
        # A full page by rank_count's reckoning, so it reaches slice_line
        # rather than being filtered as a short answer - but carrying an
        # interior newline, which cannot go on one line.
        broken_page = full_page.replace(b'"ranks":[', b'"ranks":[\n', 1)

        def fake_fetch_body(region, world_id, offset, state):
            return broken_page if offset == 11 else full_page

        with patch("scrape.fetch_body", side_effect=fake_fetch_body):
            exit_code = scrape_slice(self.day, "na", 45, 1, 21)

        self.assertEqual(exit_code, 0)

        with gzip.open(
            os.path.join("out", "na-45-000001-000021.ndjson.gz"), "rb"
        ) as handle:
            body = handle.read()
        pages = [line for line in body.split(b"\n") if line.strip()]
        offsets = [
            int(re.match(rb'\{"o":(\d+),', line).group(1)) for line in pages
        ]

        # 11 is left out and stays in the archive's resume set. 1 and 21 are
        # kept, which is the whole reason for not raising.
        self.assertEqual(offsets, [1, 21])


if __name__ == "__main__":
    unittest.main()
