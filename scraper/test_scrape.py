import gzip
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from day import ranking_day
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


if __name__ == "__main__":
    unittest.main()
