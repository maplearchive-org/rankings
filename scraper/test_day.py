import unittest
from datetime import datetime, timezone

from day import ranking_day


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


class RankingDay(unittest.TestCase):
    def test_the_window_is_named_after_the_date_it_opens(self):
        self.assertEqual(ranking_day(at("2026-09-06T18:00:00")), "2026-09-06")
        self.assertEqual(ranking_day(at("2026-09-06T17:59:00")), "2026-09-05")
        self.assertEqual(ranking_day(at("2026-09-07T02:00:00")), "2026-09-06")

    def test_it_crosses_a_month_boundary(self):
        self.assertEqual(ranking_day(at("2026-10-01T02:00:00")), "2026-09-30")


if __name__ == "__main__":
    unittest.main()
