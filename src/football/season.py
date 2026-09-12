"""The joined season: one object every project reads from.

This is the "SDK" layer. Each project is a thin function over the frames
below, which means the projects can also read each other's numbers -- the FPL
value chart can filter by the luck table's regression candidates, the
recruitment scatter can colour players by how hard their club presses.

Frames are cached per season on the instance, so building all five figures in
one run costs one fetch of each source.
"""

from __future__ import annotations

import functools

import pandas as pd

from . import matching
from .config import CURRENT_SEASON, season_label
from .sources import fpl, understat
from .teams import team_key

#: A player needs roughly a full match before a per-90 means anything.
MIN_MINUTES_DEFAULT = 90


class Season:
    """Every source for one season, joined and tidy.

    >>> season = Season()
    >>> season.table().head(3)[["team", "points", "xpts", "luck"]]
    """

    def __init__(self, year: int = CURRENT_SEASON):
        self.year = year
        self.label = season_label(year)

    def __repr__(self) -> str:
        return f"<Season {self.label}: {self.matches_played} matches played>"

    # ----------------------------------------------------------------- teams

    @functools.cached_property
    def team_matches(self) -> pd.DataFrame:
        """One row per team per match, with xG, xPTS, PPDA and territory."""
        frame = understat.team_matches(self.year)
        frame["team_key"] = frame["team"].map(team_key)
        return frame

    @functools.cached_property
    def fixtures(self) -> pd.DataFrame:
        """All 380 fixtures, played and upcoming, with xG and forecasts."""
        frame = understat.fixtures(self.year)
        frame["home_key"] = frame["home"].map(team_key)
        frame["away_key"] = frame["away"].map(team_key)
        return frame

    @property
    def matches_played(self) -> int:
        return int(self.fixtures["played"].sum())

    def table(self) -> pd.DataFrame:
        """The league table beside the table the underlying numbers imply.

        ``luck`` is real points minus expected points. Positive means a team
        has banked more than their chances deserved; over a season it tends
        towards zero, which is the whole premise of the luck table.
        """
        grouped = self.team_matches.groupby(["team", "team_key"], as_index=False).agg(
            played=("points", "size"),
            points=("points", "sum"),
            xpts=("xpts", "sum"),
            goals_for=("goals_for", "sum"),
            goals_against=("goals_against", "sum"),
            xg=("xg", "sum"),
            xga=("xga", "sum"),
            npxg=("npxg", "sum"),
            npxga=("npxga", "sum"),
            deep=("deep", "sum"),
            deep_allowed=("deep_allowed", "sum"),
        )
        grouped["goal_difference"] = grouped["goals_for"] - grouped["goals_against"]
        grouped["xgd"] = grouped["xg"] - grouped["xga"]
        grouped["npxgd"] = grouped["npxg"] - grouped["npxga"]
        grouped["luck"] = grouped["points"] - grouped["xpts"]
        grouped["finishing"] = grouped["goals_for"] - grouped["xg"]
        grouped["keeping"] = grouped["xga"] - grouped["goals_against"]

        # PPDA is a ratio of sums, not a mean of ratios: a team that made few
        # defensive actions in one match must not dominate the season figure.
        ppda = self._ppda_totals()
        grouped = grouped.merge(ppda, on="team_key", how="left")

        grouped = grouped.sort_values(
            ["points", "goal_difference", "goals_for"], ascending=False
        ).reset_index(drop=True)
        grouped["position"] = grouped.index + 1

        xg_order = grouped.sort_values("xpts", ascending=False).reset_index(drop=True)
        xg_position = {row.team_key: i + 1 for i, row in enumerate(xg_order.itertuples())}
        grouped["xg_position"] = grouped["team_key"].map(xg_position)
        grouped["position_delta"] = grouped["xg_position"] - grouped["position"]
        return grouped

    def _ppda_totals(self) -> pd.DataFrame:
        """Season PPDA rebuilt from the underlying counts."""
        raw = understat.league_data(self.year)["teams"]
        rows = []
        for team in raw.values():
            passes = sum(m["ppda"]["att"] for m in team["history"])
            actions = sum(m["ppda"]["def"] for m in team["history"])
            allowed_passes = sum(m["ppda_allowed"]["att"] for m in team["history"])
            allowed_actions = sum(m["ppda_allowed"]["def"] for m in team["history"])
            rows.append(
                {
                    "team_key": team_key(understat._text(team["title"])),
                    "ppda": passes / actions if actions else float("nan"),
                    "ppda_allowed": (
                        allowed_passes / allowed_actions
                        if allowed_actions
                        else float("nan")
                    ),
                }
            )
        return pd.DataFrame(rows)

    def form(self) -> pd.DataFrame:
        """Cumulative points against cumulative xPTS, match by match.

        The shape to look for is the two lines converging: that is regression
        happening in public.
        """
        frame = self.team_matches.sort_values(["team", "date"]).copy()
        frame["match_number"] = frame.groupby("team").cumcount() + 1
        for column in ("points", "xpts", "xg", "xga", "goals_for", "goals_against"):
            frame[f"cum_{column}"] = frame.groupby("team")[column].cumsum()
        frame["cum_luck"] = frame["cum_points"] - frame["cum_xpts"]
        return frame

    # --------------------------------------------------------------- players

    @functools.cached_property
    def _player_join(self) -> tuple[dict[str, str], matching.MatchReport]:
        understat_players = understat.players(self.year)
        fpl_players = fpl.players()
        left = {r.player: team_key(r.team) for r in understat_players.itertuples()}
        right = {r.player: team_key(r.team) for r in fpl_players.itertuples()}
        report = matching.match_players(left, right)
        return report.matched, report

    @property
    def join_report(self) -> matching.MatchReport:
        """How well Understat and FPL player names lined up. Worth printing."""
        return self._player_join[1]

    @functools.cached_property
    def players(self) -> pd.DataFrame:
        """Every player with both an Understat and an FPL record.

        Understat contributes the shot-quality metrics (npxG, xA, xGChain,
        xGBuildup) and the minutes they were earned in. FPL contributes price,
        ownership, availability, age and set-piece duty. Per-90s are computed
        from Understat minutes, since that is what the numerators came from.
        """
        mapping, _ = self._player_join
        u = understat.players(self.year).copy()
        f = fpl.players().copy()

        u["fpl_name"] = u["player"].map(mapping)
        # Understat's `position` is a compound string like "M S" (midfielder,
        # used as substitute); FPL's is the clean GK/DEF/MID/FWD that filters
        # want. Keep both, and keep Understat's club, which is the club the
        # minutes were actually played for.
        f = f.rename(columns={"position": "fpl_position", "team": "fpl_team"})
        merged = u.merge(
            f,
            left_on="fpl_name",
            right_on="player",
            how="inner",
            suffixes=("", "_fpl"),
        )

        merged["team_key"] = merged["team"].map(team_key)
        merged["age"] = _age_from(merged["birth_date"])

        per90 = merged["minutes"] / 90.0
        safe = per90.where(per90 > 0)
        for source, name in (
            ("npxg", "npxg_per_90"),
            ("xa", "xa_per_90"),
            ("xgchain", "xgchain_per_90"),
            ("xgbuildup", "xgbuildup_per_90"),
            ("shots", "shots_per_90"),
            ("key_passes", "key_passes_per_90"),
        ):
            merged[name] = merged[source] / safe

        merged["npxgi_per_90"] = merged["npxg_per_90"] + merged["xa_per_90"]
        merged["goals_minus_xg"] = merged["goals"] - merged["xg"]
        merged["points_per_million"] = merged["total_points"] / merged["price"]
        merged["available"] = merged["status"] == "a"

        return merged.drop(columns=["player_fpl"], errors="ignore")

    def player_pool(
        self,
        min_minutes: int = MIN_MINUTES_DEFAULT,
        position: str | list[str] | None = None,
        max_age: int | None = None,
        max_price: float | None = None,
        available_only: bool = False,
    ) -> pd.DataFrame:
        """``players`` with the filters every project wants, in one place.

        ``position`` takes FPL's vocabulary: GK, DEF, MID, FWD.
        """
        frame = self.players
        frame = frame[frame["minutes"] >= min_minutes]
        if position:
            wanted = [position] if isinstance(position, str) else position
            wanted = [p.upper() for p in wanted]
            frame = frame[frame["fpl_position"].isin(wanted)]
        if max_age is not None:
            frame = frame[frame["age"] <= max_age]
        if max_price is not None:
            frame = frame[frame["price"] <= max_price]
        if available_only:
            frame = frame[frame["available"]]
        return frame.reset_index(drop=True)


def _age_from(birth_dates: pd.Series) -> pd.Series:
    """Age in years today, from FPL's ISO birth dates."""
    born = pd.to_datetime(birth_dates, errors="coerce")
    today = pd.Timestamp.now().normalize()
    return ((today - born).dt.days / 365.25).round(1)
