"""Fixture difficulty, which is the one project that models rather than plots.

The shrinkage is the part worth pinning down: without it, three matches of
noise become a confident claim about how hard someone's October looks.
"""

import pandas as pd

from football.projects.schedule import (
    HOME_ADVANTAGE,
    PRIOR_MATCHES,
    team_ratings,
)


class FakeSeason:
    """Just enough Season to exercise the rating maths."""

    def __init__(self, frame):
        self._frame = frame

    def table(self):
        return self._frame


def _table(rows):
    return pd.DataFrame(
        [
            {"team_key": k, "team": k.title(), "played": n, "npxg": f, "npxga": a}
            for k, n, f, a in rows
        ]
    )


def test_rating_is_shrunk_towards_average():
    # Three matches at +1.5 xGD per match is a good week, not a +1.5 side.
    season = FakeSeason(_table([("arsenal", 3, 6.0, 1.5)]))
    row = team_ratings(season).iloc[0]
    assert row["observed"] == 1.5
    expected = 1.5 * (3 / (3 + PRIOR_MATCHES))
    assert row["rating"] == expected
    assert abs(row["rating"]) < abs(row["observed"])


def test_shrinkage_fades_as_the_season_runs():
    early = team_ratings(FakeSeason(_table([("a", 3, 6.0, 1.5)]))).iloc[0]
    late = team_ratings(FakeSeason(_table([("a", 30, 60.0, 15.0)]))).iloc[0]
    # Same per-match performance, far more evidence behind the later one.
    assert early["observed"] == late["observed"]
    assert late["rating"] > early["rating"]
    assert late["rating"] / late["observed"] > 0.8


def test_shrinkage_pulls_both_directions():
    season = FakeSeason(_table([("bad", 3, 1.5, 6.0)]))
    row = team_ratings(season).iloc[0]
    assert row["observed"] == -1.5
    assert row["rating"] > row["observed"]  # less negative
    assert row["rating"] < 0  # still a bad side


def test_home_advantage_is_a_real_offset():
    # Not a test of taste: the constant must actually separate the two venues,
    # or the venue column on the grid is decoration.
    assert HOME_ADVANTAGE > 0
