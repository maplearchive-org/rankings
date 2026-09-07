"""The ranking day a moment belongs to."""

from datetime import timedelta

RANKING_UPDATE_HOUR_UTC = 18


def ranking_day(now):
    """
    The window runs from 18:00 UTC to 17:59 the next day and is named after the
    date it starts, so shifting back eighteen hours and taking the date is
    exactly that.
    """
    return (now - timedelta(hours=RANKING_UPDATE_HOUR_UTC)).date().isoformat()
