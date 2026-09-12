"""football-data.org: the fixture and table spine.

Needs a free token in ``FOOTBALL_DATA_TOKEN``. The free tier covers twelve
competitions including the Premier League, at **10 requests per minute** --
the response header ``x-requests-available-minute`` reports what is left.

What it is good for: canonical team ids, official crests, referees, venues,
half-time scores, matchday numbers and a clean league table. What it does not
have, checked directly against ``matches/{id}``: no goals, bookings,
substitutions or lineups at any level, and odds are a paid add-on. So this is
the spine, and Understat supplies the analysis.
"""

from __future__ import annotations

import pandas as pd
import requests

from ..cache import cached
from ..config import football_data_token

BASE = "https://api.football-data.org/v4"
COMPETITION = "PL"
TIMEOUT = 30


def _get(path: str) -> dict:
    response = requests.get(
        f"{BASE}/{path}",
        headers={"X-Auth-Token": football_data_token()},
        timeout=TIMEOUT,
    )
    if response.status_code == 429:
        raise RuntimeError(
            "football-data.org rate limit hit (10 requests/minute). "
            "Wait a minute, or rely on the cache."
        )
    response.raise_for_status()
    return response.json()


def _standings_payload() -> dict:
    """The raw standings response, shared by the table and the matchday."""
    return cached(
        "football_data",
        "standings",
        lambda: _get(f"competitions/{COMPETITION}/standings"),
    )


def standings() -> pd.DataFrame:
    """The official league table, with crests and canonical team ids."""
    data = _standings_payload()
    table = data["standings"][0]["table"]
    return pd.DataFrame(
        [
            {
                "position": row["position"],
                "team": row["team"]["name"],
                "short_name": row["team"]["shortName"],
                "tla": row["team"]["tla"],
                "crest": row["team"]["crest"],
                "fd_team_id": row["team"]["id"],
                "played": row["playedGames"],
                "won": row["won"],
                "drawn": row["draw"],
                "lost": row["lost"],
                "points": row["points"],
                "goals_for": row["goalsFor"],
                "goals_against": row["goalsAgainst"],
                "goal_difference": row["goalDifference"],
            }
            for row in table
        ]
    )


def current_matchday() -> int:
    return int(_standings_payload()["season"]["currentMatchday"])


def matches(matchday: int | None = None) -> pd.DataFrame:
    """Fixtures with venue, referee and half-time score."""
    path = f"competitions/{COMPETITION}/matches"
    key = "matches-all"
    if matchday is not None:
        path += f"?matchday={matchday}"
        key = f"matches-md{matchday}"

    data = cached("football_data", key, lambda: _get(path))
    rows = []
    for m in data["matches"]:
        referees = m.get("referees") or [{}]
        rows.append(
            {
                "fd_match_id": m["id"],
                "matchday": m["matchday"],
                "kickoff": pd.to_datetime(m["utcDate"]),
                "status": m["status"],
                "home": m["homeTeam"]["name"],
                "away": m["awayTeam"]["name"],
                "home_tla": m["homeTeam"]["tla"],
                "away_tla": m["awayTeam"]["tla"],
                "home_goals": m["score"]["fullTime"]["home"],
                "away_goals": m["score"]["fullTime"]["away"],
                "home_goals_ht": m["score"]["halfTime"]["home"],
                "away_goals_ht": m["score"]["halfTime"]["away"],
                "referee": referees[0].get("name"),
            }
        )
    return pd.DataFrame(rows)


def scorers(limit: int = 20) -> pd.DataFrame:
    """The official top-scorer list."""
    data = cached(
        "football_data",
        f"scorers-{limit}",
        lambda: _get(f"competitions/{COMPETITION}/scorers?limit={limit}"),
    )
    return pd.DataFrame(
        [
            {
                "player": s["player"]["name"],
                "nationality": s["player"]["nationality"],
                "team": s["team"]["shortName"],
                "goals": s["goals"],
                "assists": s["assists"],
                "penalties": s["penalties"],
                "played": s["playedMatches"],
            }
            for s in data["scorers"]
        ]
    )
