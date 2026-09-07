import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from publish import main


class PublishRefusesAnEmptyManifest(unittest.TestCase):
    def _run(self, argv):
        tmp_dir = tempfile.mkdtemp()
        cwd = os.getcwd()
        os.chdir(tmp_dir)
        try:
            with patch("sys.argv", ["publish.py"] + argv):
                return main(), tmp_dir
        finally:
            os.chdir(cwd)

    def test_refuses_to_write_when_no_depth_was_ever_recorded(self):
        # A workflow bug that forgets --depths must not silently produce a
        # zero-slice manifest parseManifest accepts happily - the archive
        # would import nothing and report every world incomplete, with
        # nothing anywhere naming the cause.
        code, tmp_dir = self._run(["--day", "2026-09-06"])
        try:
            self.assertEqual(code, 1)
            self.assertFalse(
                os.path.exists(os.path.join(tmp_dir, "manifests", "2026-09-06.json"))
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_publishes_when_depths_are_given(self):
        code, tmp_dir = self._run(
            ["--day", "2026-09-06", "--depths", json.dumps({"na/1": 241})]
        )
        try:
            self.assertEqual(code, 0)
            with open(
                os.path.join(tmp_dir, "manifests", "2026-09-06.json"),
                encoding="utf-8",
            ) as handle:
                manifest = json.load(handle)
            self.assertTrue(manifest["slices"])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
