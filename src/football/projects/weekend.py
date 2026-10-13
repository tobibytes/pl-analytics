"""The weekend round-up: every match in the latest round, chances against goals.

One row per match. Each side's xG runs out from the centre as a bar -- home to
the left, away to the right -- and a dot marks the goals they actually scored,
so a dot far past its bar is a side that finished above its chances and a dot
short of it is one that left goals on the pitch. The score sits in the middle.

The question the chart answers is the one people ask on a Monday: which results
did the play deserve? A match is flagged when the side with more xG did not
win, and only when the xG gap is big enough to mean something -- 1.4 against
1.3 is a coin toss, not a robbery.

xG here is the **sum of shot xG**, not Understat's match-level figure. The two
disagree by a tenth or two in some matches (the match figure is computed
separately and not documented), and the shot sum is the one that agrees with
the shot maps and lets penalties be split out.
"""

from __future__ import annotations

import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.transforms import blended_transform_factory

from .. import theme
from ..season import Season

#: Kick-offs further apart than this belong to different rounds. A Friday to
#: Monday weekend never has a gap past ~28 hours; a Sunday to Tuesday midweek
#: turnaround is ~50. 36 sits cleanly between them.
ROUND_GAP_HOURS = 36

#: A shot worth this much xG or more counts as a big chance. Opta's "big
#: chance" is an analyst's judgement; 0.3 xG is the usual numeric stand-in.
BIG_CHANCE_XG = 0.3

#: Below this xG gap the "better" side did not really create more.
XG_MARGIN = 0.5

#: Room in the middle of each row for the score, in xG units.
CENTRE_GAP = 0.55


def latest_round(fixtures: pd.DataFrame, since: str | None = None) -> pd.DataFrame:
    """The played fixtures in the most recent round.

    With ``since``, every played fixture on or after that date instead -- for
    the week a round is split by a cup tie or a rearranged match.
    """
    played = fixtures[fixtures["played"]].sort_values("kickoff")
    if played.empty:
        raise ValueError("No matches have been played yet this season.")
    if since:
        chosen = played[played["kickoff"] >= pd.Timestamp(since)]
        if chosen.empty:
            raise ValueError(f"No played matches on or after {since}.")
        return chosen.reset_index(drop=True)

    # Walk back from the latest kick-off until the schedule goes quiet.
    times = played["kickoff"].tolist()
    start = len(times) - 1
    # to_timedelta, not Timedelta: the constructor trips a NumPy 2.5
    # deprecation inside pandas 2.3 that will become an error.
    gap = pd.to_timedelta(ROUND_GAP_HOURS, unit="h")
    while start > 0 and times[start] - times[start - 1] <= gap:
        start -= 1
    return played.iloc[start:].reset_index(drop=True)


def team_summary(fixtures: pd.DataFrame, shots: pd.DataFrame) -> pd.DataFrame:
    """One row per team per match: goals, xG, npxG, shots, big chances.

    Goals come from the fixture, not the shot list: an own goal counts for a
    side that never took the shot, and the scoreline is the one number nobody
    argues about.
    """
    shots = shots.assign(
        penalty=shots["situation"].eq("Penalty"),
        big=shots["xg"] >= BIG_CHANCE_XG,
    )
    shots["npxg"] = shots["xg"].where(~shots["penalty"], 0.0)

    rows = []
    for match in fixtures.itertuples():
        in_match = shots[shots["match_id"] == match.match_id]
        for venue, team, opponent, goals, conceded in (
            ("home", match.home, match.away, match.home_goals, match.away_goals),
            ("away", match.away, match.home, match.away_goals, match.home_goals),
        ):
            mine = in_match[in_match["home"] == (venue == "home")]
            rows.append(
                {
                    "match_id": match.match_id,
                    "kickoff": match.kickoff,
                    "venue": venue,
                    "team": team,
                    "opponent": opponent,
                    "goals": int(goals),
                    "conceded": int(conceded),
                    "xg": float(mine["xg"].sum()),
                    "npxg": float(mine["npxg"].sum()),
                    "shots": len(mine),
                    "big_chances": int(mine["big"].sum()),
                }
            )
    frame = pd.DataFrame(rows)
    frame["xg_against"] = (
        frame.groupby("match_id")["xg"].transform("sum") - frame["xg"]
    )
    frame["result"] = frame.apply(
        lambda r: "W" if r.goals > r.conceded else "L" if r.goals < r.conceded else "D",
        axis=1,
    )
    frame["against_the_play"] = (frame["xg_against"] - frame["xg"] >= XG_MARGIN) & (
        frame["result"] != "L"
    )
    return frame


def player_summary(shots: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Shooters and creators across the round.

    Returns ``(shooters, creators)``. Shooters are ranked on npxG, because a
    penalty says nothing about how a forward got into the box; creators on
    the xG of the shots they set up.
    """
    shots = shots.assign(
        npxg=shots["xg"].where(~shots["situation"].eq("Penalty"), 0.0)
    )
    shooters = (
        shots.groupby(["player", "team"], as_index=False)
        .agg(
            shots=("xg", "size"),
            goals=("is_goal", "sum"),
            xg=("xg", "sum"),
            npxg=("npxg", "sum"),
        )
        .assign(finishing=lambda d: d["goals"] - d["xg"])
        .sort_values("npxg", ascending=False, ignore_index=True)
    )
    creators = (
        shots[shots["assisted_by"].notna()]
        .groupby(["assisted_by", "team"], as_index=False)
        .agg(chances=("xg", "size"), xa=("xg", "sum"))
        .rename(columns={"assisted_by": "player"})
        .sort_values("xa", ascending=False, ignore_index=True)
    )
    return shooters, creators


def figure(season: Season | None = None, since: str | None = None):
    """Build the round-up chart. Returns ``(fig, teams)``."""
    season = season or Season()
    fixtures = latest_round(season.fixtures, since=since)
    shots = season.shots(fixtures["match_id"])
    teams = team_summary(fixtures, shots)

    n = len(fixtures)
    fig, ax = theme.new_figure(11.0, max(5.0, 0.62 * n + 2.6))
    theme.style_axes(ax, grid_axis="none")
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    span = max(float(teams["xg"].max()), float(teams["goals"].max()), 1.0)
    names = blended_transform_factory(ax.transAxes, ax.transData)

    for row, match in enumerate(fixtures.itertuples()):
        y = n - 1 - row  # first kick-off at the top
        pair = teams[teams["match_id"] == match.match_id].set_index("venue")
        for venue, sign, color in (("home", -1, theme.BLUE), ("away", 1, theme.RED)):
            side = pair.loc[venue]
            ax.barh(
                y, sign * side.xg, left=sign * CENTRE_GAP, height=0.5,
                color=color, alpha=0.85, zorder=3,
            )
            ax.scatter(
                sign * (CENTRE_GAP + side.goals), y, s=46, zorder=4,
                color=theme.INK, edgecolor=theme.SURFACE, linewidth=1.2,
            )
            ax.text(
                sign * (CENTRE_GAP + side.xg) + sign * 0.08, y - 0.38,
                f"{side.xg:.2f} xG",
                fontsize=7, color=theme.INK_MUTED,
                ha="right" if sign < 0 else "left", va="center", zorder=5,
            )
            ax.text(
                -0.01 if sign < 0 else 1.01, y, side.team,
                transform=names, fontsize=9.5, color=theme.INK,
                ha="right" if sign < 0 else "left", va="center",
            )

        flagged = pair["against_the_play"].any()
        ax.text(
            0, y, f"{int(match.home_goals)} – {int(match.away_goals)}",
            fontsize=10.5, fontweight="bold", ha="center", va="center", zorder=5,
            color=theme.ACCENT if flagged else theme.INK,
        )

    ax.axvline(0, color=theme.LINES, linewidth=0.6, zorder=1)
    ax.set_xlim(-(CENTRE_GAP + span * 1.12), CENTRE_GAP + span * 1.12)
    ax.set_ylim(-0.8, n - 0.4)

    ax.legend(
        handles=[
            Patch(facecolor=theme.BLUE, label="home xG"),
            Patch(facecolor=theme.RED, label="away xG"),
            Line2D([], [], marker="o", linestyle="", color=theme.INK,
                   markeredgecolor=theme.SURFACE, label="goals scored"),
            Line2D([], [], marker="s", linestyle="", color=theme.ACCENT,
                   label=f"score against the xG (gap ≥ {XG_MARGIN})"),
        ],
        loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4,
        fontsize=8, handlelength=1.2, columnspacing=1.6,
    )

    first, last = fixtures["kickoff"].min(), fixtures["kickoff"].max()
    against = int(teams.drop_duplicates("match_id")["match_id"].isin(
        teams.loc[teams["against_the_play"], "match_id"]).sum())
    theme.title_block(
        fig,
        "Did the results follow the chances?",
        f"{season.label} Premier League  ·  {first:%a %d %b} – {last:%a %d %b}  ·  "
        f"{n} matches, {int(teams['goals'].sum())} goals from "
        f"{teams['xg'].sum():.1f} xG  ·  {against} went against the play",
        y=1.04,
    )
    theme.credit(
        fig, "Understat (shot xG)",
        "One match is one sample — a finish or a save swings it",
    )
    return fig, teams
