"""Understat: expected goals, shot locations, pressing and expected points.

No API key. Understat has no documented API either -- these routes were read
out of the site's own JavaScript bundles. Two things follow:

* **The old scraping recipe is dead.** Every tutorial and the ``understat``
  PyPI package regex ``JSON.parse('...')`` out of the page HTML. The pages now
  fetch their data over AJAX and that payload is no longer in the HTML at all.
* **These routes are undocumented and may break.** They are pinned here in one
  module so a break is a one-file fix, and the disk cache means a break does
  not take yesterday's charts with it.

Coordinates are normalised 0-1 on a pitch the shooting team always attacks
left to right -- the same convention StatsBomb uses, just scaled. See
``shots()`` for the conversion.
"""

from __future__ import annotations

import html

import pandas as pd
import requests

from ..cache import cached
from ..config import CURRENT_SEASON

BASE = "https://understat.com/main"

#: Understat serves these routes only to what looks like its own front end.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}

TIMEOUT = 30

#: StatsBomb's pitch, so figures can share plotting code with the shot map.
PITCH_LENGTH = 120.0
PITCH_WIDTH = 80.0


def _text(value):
    """Understat serves HTML-escaped names: ``Dara O&#039;Shea``, ``Gro&szlig;``.

    Left alone these reach the charts verbatim and break every name join, so
    every string out of this module goes through here.
    """
    return html.unescape(value) if isinstance(value, str) else value


def _get(path: str) -> dict:
    response = requests.get(f"{BASE}/{path}", headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    # Responses are gzipped; requests decompresses transparently.
    return response.json()


def league_data(season: int = CURRENT_SEASON) -> dict:
    """The whole season in one request: teams, players and all 380 fixtures."""
    return cached(
        "understat", f"league-EPL-{season}", lambda: _get(f"getLeagueData/EPL/{season}")
    )


def match_data(match_id: int | str) -> dict:
    """Shots and per-player rosters for one match."""
    return cached(
        "understat",
        f"match-{match_id}",
        lambda: _get(f"getMatchData/{match_id}"),
        # A finished match never changes.
        max_age=365 * 24 * 60 * 60,
    )


def fixtures(season: int = CURRENT_SEASON) -> pd.DataFrame:
    """All 380 fixtures, with xG and Understat's own win/draw/loss forecast.

    ``played`` marks the ones with a result; upcoming fixtures carry the
    forecast but no goals.
    """
    rows = []
    for match in league_data(season)["dates"]:
        rows.append(
            {
                "match_id": int(match["id"]),
                "played": bool(match["isResult"]),
                "kickoff": pd.to_datetime(match["datetime"]),
                "home": _text(match["h"]["title"]),
                "away": _text(match["a"]["title"]),
                "home_short": _text(match["h"]["short_title"]),
                "away_short": _text(match["a"]["short_title"]),
                "home_goals": _maybe_int(match["goals"]["h"]),
                "away_goals": _maybe_int(match["goals"]["a"]),
                "home_xg": _maybe_float(match["xG"]["h"]),
                "away_xg": _maybe_float(match["xG"]["a"]),
                "p_home_win": _maybe_float(match.get("forecast", {}).get("w")),
                "p_draw": _maybe_float(match.get("forecast", {}).get("d")),
                "p_away_win": _maybe_float(match.get("forecast", {}).get("l")),
            }
        )
    return pd.DataFrame(rows).sort_values("kickoff").reset_index(drop=True)


def team_matches(season: int = CURRENT_SEASON) -> pd.DataFrame:
    """One row per team per match: the advanced metrics behind the table.

    ``xpts``   points the chance quality says the team deserved.
    ``npxg``   expected goals with penalties removed.
    ``ppda``   opposition passes allowed per defensive action. Low is a high
               press. Stored upstream as a fraction, divided out here.
    ``deep``   completed passes within 20 yards of goal -- territory, not chances.
    """
    rows = []
    for team in league_data(season)["teams"].values():
        for match in team["history"]:
            rows.append(
                {
                    "team": _text(team["title"]),
                    "team_id": int(team["id"]),
                    "date": pd.to_datetime(match["date"]),
                    "home": match["h_a"] == "h",
                    "result": match["result"],
                    "points": int(match["pts"]),
                    "xpts": float(match["xpts"]),
                    "goals_for": int(match["scored"]),
                    "goals_against": int(match["missed"]),
                    "xg": float(match["xG"]),
                    "xga": float(match["xGA"]),
                    "npxg": float(match["npxG"]),
                    "npxga": float(match["npxGA"]),
                    "ppda": _ratio(match["ppda"]),
                    "ppda_allowed": _ratio(match["ppda_allowed"]),
                    "deep": int(match["deep"]),
                    "deep_allowed": int(match["deep_allowed"]),
                }
            )
    return pd.DataFrame(rows).sort_values(["team", "date"]).reset_index(drop=True)


def players(season: int = CURRENT_SEASON) -> pd.DataFrame:
    """Season totals per player.

    ``xgchain``   total xG of every possession the player touched.
    ``xgbuildup`` the same, minus shots and assists -- credits the deep-lying
                  players who never show up in a goals-and-assists table.
    """
    rows = []
    for p in league_data(season)["players"]:
        rows.append(
            {
                "player_id": int(p["id"]),
                "player": _text(p["player_name"]),
                "team": _text(p["team_title"]),
                "position": p["position"],
                "matches": int(p["games"]),
                "minutes": int(p["time"]),
                "goals": int(p["goals"]),
                "npg": int(p["npg"]),
                "assists": int(p["assists"]),
                "shots": int(p["shots"]),
                "key_passes": int(p["key_passes"]),
                "xg": float(p["xG"]),
                "npxg": float(p["npxG"]),
                "xa": float(p["xA"]),
                "xgchain": float(p["xGChain"]),
                "xgbuildup": float(p["xGBuildup"]),
                "yellow_cards": int(p["yellow_cards"]),
                "red_cards": int(p["red_cards"]),
            }
        )
    return pd.DataFrame(rows)


def shots(match_id: int | str) -> pd.DataFrame:
    """Every shot in a match, on StatsBomb's 120x80 pitch.

    Understat stores ``X``/``Y`` normalised 0-1 with the shooter always
    attacking left to right. Scaling to 120x80 puts these rows on the same
    coordinate system as ``sources.statsbomb``, so both feed the same pitch
    plotting code.
    """
    data = match_data(match_id)
    payload = data.get("response", data)

    rows = []
    for side in ("h", "a"):
        for shot in payload["shots"][side]:
            rows.append(
                {
                    "shot_id": int(shot["id"]),
                    "match_id": int(shot["match_id"]),
                    "minute": int(shot["minute"]),
                    "player": _text(shot["player"]),
                    "player_id": int(shot["player_id"]),
                    "team": _text(shot[f"{side}_team"]),
                    "home": side == "h",
                    "x": float(shot["X"]) * PITCH_LENGTH,
                    "y": float(shot["Y"]) * PITCH_WIDTH,
                    "xg": float(shot["xG"]),
                    "result": shot["result"],
                    "is_goal": shot["result"] == "Goal",
                    "situation": shot["situation"],
                    "body_part": shot["shotType"],
                    "assisted_by": _text(shot["player_assisted"]),
                    "last_action": shot["lastAction"],
                }
            )
    return pd.DataFrame(rows).sort_values("minute").reset_index(drop=True)


def _ratio(value: dict) -> float:
    """PPDA arrives as {"att": passes, "def": actions}."""
    actions = value.get("def", 0)
    return float(value.get("att", 0)) / actions if actions else float("nan")


def _maybe_int(value) -> int | None:
    return None if value in (None, "") else int(value)


def _maybe_float(value) -> float | None:
    return None if value in (None, "") else float(value)
