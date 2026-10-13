"""The weekend round-up: finding the round, and judging results against xG.

Round detection is the part that silently goes wrong -- merge a weekend into
the midweek before it and the chart is still drawn, just about the wrong games.
"""

import pandas as pd

from football.projects.weekend import latest_round, team_summary


def _fixtures(kickoffs, played=None):
    played = played or [True] * len(kickoffs)
    return pd.DataFrame(
        {
            "match_id": range(1, len(kickoffs) + 1),
            "played": played,
            "kickoff": pd.to_datetime(kickoffs),
            "home": "Home",
            "away": "Away",
            "home_goals": 1.0,
            "away_goals": 1.0,
        }
    )


def test_friday_to_monday_is_one_round():
    fixtures = _fixtures(
        [
            "2026-10-03 15:00",  # previous round
            "2026-10-09 20:00",
            "2026-10-10 12:30",
            "2026-10-11 16:30",
            "2026-10-12 20:00",
        ]
    )
    assert latest_round(fixtures)["match_id"].tolist() == [2, 3, 4, 5]


def test_midweek_is_not_merged_into_the_weekend_before():
    fixtures = _fixtures(
        ["2026-12-26 15:00", "2026-12-27 16:30", "2026-12-29 19:30", "2026-12-30 20:00"]
    )
    # Sunday 16:30 to Tuesday 19:30 is 51 hours: two rounds, not one.
    assert latest_round(fixtures)["match_id"].tolist() == [3, 4]


def test_unplayed_fixtures_are_ignored():
    fixtures = _fixtures(
        ["2026-10-10 15:00", "2026-10-11 15:00", "2026-10-17 15:00"],
        played=[True, True, False],
    )
    assert latest_round(fixtures)["match_id"].tolist() == [1, 2]


def test_since_overrides_detection():
    fixtures = _fixtures(["2026-10-01 15:00", "2026-10-05 15:00", "2026-10-10 15:00"])
    assert latest_round(fixtures, since="2026-10-04")["match_id"].tolist() == [2, 3]


def _shots(rows):
    return pd.DataFrame(
        [{"match_id": 1, "home": h, "xg": xg, "situation": s} for h, xg, s in rows]
    )


def test_a_draw_against_much_more_xg_is_flagged():
    fixtures = _fixtures(["2026-10-10 15:00"])
    shots = _shots([(True, 0.4, "OpenPlay"), (False, 1.2, "OpenPlay")])
    teams = team_summary(fixtures, shots).set_index("venue")
    assert teams.loc["home", "against_the_play"]  # 0.8 xG worse, still drew
    assert not teams.loc["away", "against_the_play"]


def test_a_coin_toss_is_not_flagged():
    fixtures = _fixtures(["2026-10-10 15:00"])
    shots = _shots([(True, 1.3, "OpenPlay"), (False, 1.4, "OpenPlay")])
    assert not team_summary(fixtures, shots)["against_the_play"].any()


def test_penalties_count_in_xg_but_not_npxg():
    fixtures = _fixtures(["2026-10-10 15:00"])
    shots = _shots([(True, 0.76, "Penalty"), (True, 0.2, "OpenPlay")])
    home = team_summary(fixtures, shots).set_index("venue").loc["home"]
    assert round(home["xg"], 2) == 0.96
    assert round(home["npxg"], 2) == 0.2
    assert home["big_chances"] == 1
