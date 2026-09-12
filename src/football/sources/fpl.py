"""The official Fantasy Premier League API.

No key, no registration, no documented rate limit (be polite anyway -- the
disk cache handles that). Three endpoints carry everything:

``bootstrap-static/``   players, teams, gameweeks, and the stat vocabulary
``fixtures/``           all 380 fixtures with per-player event breakdowns
``element-summary/{id}``one player's gameweek-by-gameweek history

The player feed is more analytically useful than its name suggests: alongside
price and ownership it now carries Opta-derived expected goals, expected
assists and expected goals conceded, with per-90 versions. It is also the only
source here for availability -- injury text, chance of playing -- and for
set-piece order, which is the difference between a good underlying number and
a good fantasy asset.
"""

from __future__ import annotations

import pandas as pd
import requests

from ..cache import cached

BASE = "https://fantasy.premierleague.com/api"

HEADERS = {"User-Agent": "football-analytics (https://github.com/)"}
TIMEOUT = 30

#: FPL prices are in tenths of a million.
PRICE_DIVISOR = 10.0

POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _get(path: str) -> dict | list:
    response = requests.get(f"{BASE}/{path}", headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def bootstrap() -> dict:
    """Players, teams, gameweeks and settings. About 1.7 MB."""
    return cached("fpl", "bootstrap-static", lambda: _get("bootstrap-static/"))


def raw_fixtures() -> list:
    """All fixtures, each with a per-player breakdown of goals, cards and bonus."""
    return cached("fpl", "fixtures", lambda: _get("fixtures/"))


def element_summary(player_id: int) -> dict:
    """One player's full gameweek history and remaining fixtures."""
    return cached(
        "fpl", f"element-{player_id}", lambda: _get(f"element-summary/{player_id}/")
    )


def teams() -> pd.DataFrame:
    """The 20 clubs, with FPL's own strength ratings."""
    return pd.DataFrame(
        [
            {
                "fpl_team_id": t["id"],
                "team": t["name"],
                "short_name": t["short_name"],
                "strength_home": t["strength_overall_home"],
                "strength_away": t["strength_overall_away"],
            }
            for t in bootstrap()["teams"]
        ]
    )


def players() -> pd.DataFrame:
    """Every player, with price, ownership, availability and expected numbers.

    ``status`` is FPL's availability flag: ``a`` available, ``d`` doubtful,
    ``i`` injured, ``s`` suspended, ``u`` unavailable, ``n`` on loan.
    """
    data = bootstrap()
    team_names = {t["id"]: t["name"] for t in data["teams"]}

    rows = []
    for e in data["elements"]:
        rows.append(
            {
                "fpl_id": e["id"],
                "player": f"{e['first_name']} {e['second_name']}".strip(),
                "web_name": e["web_name"],
                "team": team_names[e["team"]],
                "position": POSITIONS.get(e["element_type"], "?"),
                "price": e["now_cost"] / PRICE_DIVISOR,
                "total_points": e["total_points"],
                "points_per_game": _f(e["points_per_game"]),
                "form": _f(e["form"]),
                "selected_by_percent": _f(e["selected_by_percent"]),
                "minutes": e["minutes"],
                "starts": e["starts"],
                "goals": e["goals_scored"],
                "assists": e["assists"],
                "clean_sheets": e["clean_sheets"],
                "saves": e["saves"],
                "bonus": e["bonus"],
                "xg": _f(e["expected_goals"]),
                "xa": _f(e["expected_assists"]),
                "xgi": _f(e["expected_goal_involvements"]),
                "xgc": _f(e["expected_goals_conceded"]),
                "xg_per_90": _f(e["expected_goals_per_90"]),
                "xa_per_90": _f(e["expected_assists_per_90"]),
                "xgi_per_90": _f(e["expected_goal_involvements_per_90"]),
                "ict_index": _f(e["ict_index"]),
                "defensive_contribution": e.get("defensive_contribution", 0),
                "status": e["status"],
                "news": e["news"],
                "chance_of_playing": e["chance_of_playing_next_round"],
                "penalties_order": e["penalties_order"],
                "corners_order": e["corners_and_indirect_freekicks_order"],
                "birth_date": e.get("birth_date"),
            }
        )
    return pd.DataFrame(rows)


def gameweeks() -> pd.DataFrame:
    """The 38 gameweeks, with deadlines and which one is live."""
    return pd.DataFrame(
        [
            {
                "gameweek": e["id"],
                "name": e["name"],
                "deadline": pd.to_datetime(e["deadline_time"]),
                "finished": e["finished"],
                "is_current": e["is_current"],
                "is_next": e["is_next"],
                "average_score": e["average_entry_score"],
                "highest_score": e["highest_score"],
            }
            for e in bootstrap()["events"]
        ]
    )


def current_gameweek() -> int:
    """The gameweek in progress, or the last finished one before the season starts."""
    gws = gameweeks()
    current = gws[gws["is_current"]]
    if not current.empty:
        return int(current.iloc[0]["gameweek"])
    finished = gws[gws["finished"]]
    return int(finished["gameweek"].max()) if not finished.empty else 0


def _f(value) -> float:
    """FPL returns most numerics as strings, and nulls as empty."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")
