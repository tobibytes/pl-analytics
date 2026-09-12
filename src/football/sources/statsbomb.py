"""Load and shape StatsBomb open-data events.

Everything here reads StatsBomb's *free* open data through ``statsbombpy``.
No credentials are involved: the package pulls static JSON from the public
StatsBomb GitHub repo. The library warns once about the missing credentials
(``NoAuthWarning``); we silence it at import time because it is expected.

Pitch coordinates are StatsBomb's: 120 x 80, origin at the top-left, and the
attacking direction is always left -> right (the goal being attacked is at
x = 120), regardless of which half the team actually played in.
"""

from __future__ import annotations

import warnings

import pandas as pd
from statsbombpy import sb

try:  # the warning class moved around between statsbombpy releases
    from statsbombpy.api_client import NoAuthWarning
except ImportError:  # pragma: no cover - defensive
    NoAuthWarning = UserWarning

warnings.filterwarnings("ignore", category=NoAuthWarning)

PITCH_LENGTH = 120.0
PITCH_WIDTH = 80.0

#: StatsBomb encodes the penalty shoot-out as its own period.
SHOOTOUT_PERIOD = 5


def load_events(match_id: int) -> pd.DataFrame:
    """Return every event in a match as a tidy DataFrame."""
    return sb.events(match_id=match_id)


def player_short_names(match_id: int) -> dict[int, str]:
    """Map ``player_id`` to the name a broadcast would use.

    ``player`` on an event is the full legal name, which is the wrong label for
    a chart: Messi is "Lionel Andrés Messi Cuccittini" and Mbappé is "Kylian
    Mbappé Lottin", so naive "last word" logic prints *Cuccittini* and
    *Lottin*. The lineups feed carries the nickname ("Lionel Messi", "Ángel Di
    María"); dropping its first token gives the familiar short form and keeps
    compound surnames like "Di María" and "Kolo Muani" intact.
    """
    names: dict[int, str] = {}
    for lineup in sb.lineups(match_id=match_id).values():
        for player_id, full, nickname in lineup[
            ["player_id", "player_name", "player_nickname"]
        ].itertuples(index=False):
            label = nickname if isinstance(nickname, str) and nickname else full
            parts = label.split()
            names[player_id] = " ".join(parts[1:]) if len(parts) > 1 else label
    return names


def load_shots(match_id: int, include_shootout: bool = False) -> pd.DataFrame:
    """Return the shots of a match, one row per shot.

    Adds the columns downstream plotting code expects:

    ``x`` / ``y``      the shot location, unpacked from StatsBomb's ``[x, y]`` list
    ``xg``             alias for ``shot_statsbomb_xg``
    ``is_goal``        boolean, ``shot_outcome == "Goal"``
    ``short_name``     broadcast-style player name, for compact chart labels
    ``clock``          the minute as football reports it (see below)

    Shoot-out penalties are dropped by default: they are not part of the match
    xG story and they would all stack on the same penalty spot.
    """
    events = load_events(match_id)
    shots = events[events["type"] == "Shot"].copy()

    if not include_shootout:
        shots = shots[shots["period"] != SHOOTOUT_PERIOD]

    locations = pd.DataFrame(
        shots["location"].tolist(), columns=["x", "y"], index=shots.index
    )
    shots["x"] = locations["x"]
    shots["y"] = locations["y"]
    shots["xg"] = shots["shot_statsbomb_xg"].astype(float)
    shots["is_goal"] = shots["shot_outcome"] == "Goal"
    shots["short_name"] = shots["player_id"].map(player_short_names(match_id))
    shots["short_name"] = shots["short_name"].fillna(shots["player"])

    # StatsBomb's `minute` is elapsed minutes, so a goal 22:41 into the game is
    # minute 22. Football calls that the 23rd minute, hence the +1.
    shots["clock"] = shots["minute"] + 1

    return shots.sort_values(["period", "minute"]).reset_index(drop=True)


def add_plot_coordinates(shots: pd.DataFrame, team_attacking_right: str) -> pd.DataFrame:
    """Mirror one team's shots so the two teams attack opposite goals.

    StatsBomb normalises every team to attack left -> right. To read a match as
    left-vs-right we flip the *other* team through the centre of the pitch
    (both axes, so the geometry stays faithful) into ``plot_x`` / ``plot_y``.
    """
    shots = shots.copy()
    mirrored = shots["team"] != team_attacking_right
    shots["plot_x"] = shots["x"].where(~mirrored, PITCH_LENGTH - shots["x"])
    shots["plot_y"] = shots["y"].where(~mirrored, PITCH_WIDTH - shots["y"])
    return shots


def team_xg(shots: pd.DataFrame) -> pd.Series:
    """Total xG per team, highest first."""
    return shots.groupby("team")["xg"].sum().sort_values(ascending=False)


def shootout_score(match_id: int) -> pd.Series | None:
    """Goals scored per team in the penalty shoot-out, or ``None`` if there wasn't one."""
    shots = load_shots(match_id, include_shootout=True)
    shootout = shots[shots["period"] == SHOOTOUT_PERIOD]
    if shootout.empty:
        return None
    return shootout.groupby("team")["is_goal"].sum()
