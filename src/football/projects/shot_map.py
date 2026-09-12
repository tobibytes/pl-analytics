"""Shot map for a single match, sized by xG.

Works from either source, because both put shots on the same pitch:

``understat``   any match in the current season. The reason this project can
                cover 2026/27 at all.
``statsbomb``   the open-data archive -- World Cups, Euros, the 2015/16
                Premier League. Richer events, but nothing recent.

Understat stores shot coordinates normalised 0-1; ``sources.understat.shots``
scales them to StatsBomb's 120x80 before they arrive here, so everything below
is source-agnostic.

Both feeds normalise every shot to attack left -> right, which would stack both
teams on the same goal. One team is therefore mirrored through the centre of
the pitch in **both** axes, so the map reads as a real match with each side
shooting at the goal it actually attacked.

Marker **area** is proportional to xG, never radius: a penalty at roughly 0.79
is a large disc and a hopeful strike from 30 yards is a dot.
"""

from __future__ import annotations

import pandas as pd
from mplsoccer import Pitch

from .. import theme
from ..sources import understat

PITCH_LENGTH = 120.0
PITCH_WIDTH = 80.0

SIZE_BASE = 90
SIZE_PER_XG = 1500
SIZE_LEGEND_VALUES = (0.05, 0.25, 0.50)

#: Shots from an identical spot -- two penalties -- are fanned apart by under
#: two yards, so one circle never silently stands for two goals.
DUPLICATE_SPACING = 1.8


def figure(match_id: int | str, source: str = "understat", competition: str = ""):
    """Build a shot map. Returns ``(fig, shots)``."""
    if source == "understat":
        shots, home, away, note = _from_understat(match_id)
    elif source == "statsbomb":
        shots, home, away, note = _from_statsbomb(match_id)
    else:
        raise ValueError(f"source must be 'understat' or 'statsbomb', not {source!r}")

    if shots.empty:
        raise ValueError(f"No shots found for match {match_id} on {source}.")

    shots = _add_plot_coordinates(shots, team_attacking_right=home)
    shots = _nudge_duplicates(shots)
    colors = {home: theme.BLUE, away: theme.RED}

    theme.apply()
    pitch = Pitch(
        pitch_type="statsbomb",
        pitch_color=theme.SURFACE,
        line_color=theme.LINES,
        linewidth=1,
        goal_type="box",
    )
    fig, axs = pitch.grid(
        figheight=9.5, title_height=0.13, title_space=0.0,
        endnote_height=0.09, endnote_space=0.0, grid_height=0.74, axis=False,
    )
    fig.set_facecolor(theme.SURFACE)
    fig.canvas.draw()

    _draw_shots(axs["pitch"], fig, pitch, shots, colors, home, away)
    _draw_title(axs["title"], shots, colors, home, away, competition or note)
    _draw_endnote(axs["endnote"], source)
    return fig, shots


def _from_understat(match_id):
    """Understat has no match-level metadata block -- the kick-off date is
    carried on each shot, so it is read from there."""
    shots = understat.shots(match_id)
    home = shots[shots["home"]]["team"].iloc[0]
    away = shots[~shots["home"]]["team"].iloc[0]
    raw = understat.match_data(match_id)
    payload = raw.get("response", raw)
    sample = (payload["shots"]["h"] or payload["shots"]["a"])[0]
    date = str(sample.get("date", ""))[:10]
    return shots, home, away, f"Premier League{'  ·  ' + date if date else ''}"


def _from_statsbomb(match_id):
    """StatsBomb open data, via the loader the original shot map used."""
    from ..sources import statsbomb

    raw = statsbomb.load_shots(int(match_id))
    shots = pd.DataFrame(
        {
            "minute": raw["clock"],
            "player": raw["short_name"],
            "team": raw["team"],
            "x": raw["x"],
            "y": raw["y"],
            "xg": raw["xg"],
            "is_goal": raw["is_goal"],
        }
    )
    teams = list(dict.fromkeys(raw["team"]))
    home, away = teams[0], teams[1]
    shootout = statsbomb.shootout_score(int(match_id))
    note = ""
    if shootout is not None:
        note = (
            f"after extra time  ·  {home} won "
            f"{shootout.get(home, 0)}-{shootout.get(away, 0)} on penalties"
        )
    return shots, home, away, note


def _add_plot_coordinates(shots: pd.DataFrame, team_attacking_right: str) -> pd.DataFrame:
    """Mirror the other team so the two sides attack opposite goals."""
    shots = shots.copy()
    mirrored = shots["team"] != team_attacking_right
    shots["plot_x"] = shots["x"].where(~mirrored, PITCH_LENGTH - shots["x"])
    shots["plot_y"] = shots["y"].where(~mirrored, PITCH_WIDTH - shots["y"])
    return shots


def _nudge_duplicates(shots: pd.DataFrame, spacing: float = DUPLICATE_SPACING):
    shots = shots.copy()
    keys = list(
        zip(
            shots["team"],
            shots["plot_x"].round(2),
            shots["plot_y"].round(2),
            strict=True,
        )
    )
    for key in {k for k in keys if keys.count(k) > 1}:
        rows = [i for i, k in enumerate(keys) if k == key]
        for rank, row in enumerate(rows):
            shift = (rank - (len(rows) - 1) / 2) * spacing
            shots.iloc[row, shots.columns.get_loc("plot_y")] += shift
    return shots


def _marker_size(xg):
    """Marker *area* in points squared, proportional to xG."""
    return SIZE_BASE + xg * SIZE_PER_XG


def _draw_shots(ax, fig, pitch, shots, colors, home, away) -> None:
    for team, group in shots.groupby("team"):
        color = colors[team]
        misses = group[~group["is_goal"]]
        goals = group[group["is_goal"]]

        # Non-goals read as texture behind the goals.
        pitch.scatter(
            misses["plot_x"], misses["plot_y"], s=_marker_size(misses["xg"]), ax=ax,
            facecolor="none", edgecolor=color, linewidth=1.5, alpha=0.85, zorder=2,
        )
        # Goals: solid, with a surface ring so overlaps stay readable.
        pitch.scatter(
            goals["plot_x"], goals["plot_y"], s=_marker_size(goals["xg"]), ax=ax,
            facecolor=color, edgecolor=theme.SURFACE, linewidth=2, zorder=3,
        )

    goals = shots[shots["is_goal"]]
    theme.place_labels(
        ax,
        fig,
        (
            (row.plot_x, row.plot_y, f"{row.player} {row.minute}'")
            for row in goals.itertuples()
        ),
    )

    ax.text(2.5, 78.5, f"{home} attacking →", color=colors[home],
            fontsize=8.5, ha="left", va="center", zorder=4)
    ax.text(117.5, 78.5, f"← {away} attacking", color=colors[away],
            fontsize=8.5, ha="right", va="center", zorder=4)


def _draw_title(ax, shots, colors, home, away, note) -> None:
    scored = shots[shots["is_goal"]].groupby("team").size()
    xg_totals = shots.groupby("team")["xg"].sum()

    ax.text(0.5, 0.92, f"{scored.get(home, 0)} - {scored.get(away, 0)}",
            color=theme.INK, fontsize=27, fontweight="bold", ha="center", va="top")
    if note:
        ax.text(0.5, 0.34, note, color=theme.INK_MUTED, fontsize=9.5,
                ha="center", va="top")

    for team, x, align in ((home, 0.30, "right"), (away, 0.70, "left")):
        ax.text(x, 0.92, team.upper(), color=theme.INK, fontsize=15,
                fontweight="bold", ha=align, va="top")
        ax.text(x, 0.44, f"{xg_totals.get(team, 0):.2f} xG", color=colors[team],
                fontsize=11, ha=align, va="top")

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)


def _draw_endnote(ax, source: str) -> None:
    from matplotlib.lines import Line2D

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)

    ax.text(0.0, 0.80, "Marker size = xG", color=theme.INK, fontsize=9, va="center")
    for i, value in enumerate(SIZE_LEGEND_VALUES):
        x = 0.035 + i * 0.055
        ax.scatter(x, 0.40, s=_marker_size(value), facecolor="none",
                   edgecolor=theme.INK_MUTED, linewidth=1.5)
        ax.text(x, 0.05, f"{value:.2f}", color=theme.INK_MUTED, fontsize=7.5,
                ha="center", va="center")

    ax.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="none", markersize=8,
                   markerfacecolor=theme.INK, markeredgecolor=theme.SURFACE,
                   label="Goal"),
            Line2D([], [], marker="o", linestyle="none", markersize=8,
                   markerfacecolor="none", markeredgecolor=theme.INK_MUTED,
                   label="Shot, no goal"),
        ],
        loc="center left", bbox_to_anchor=(0.30, 0.45), frameon=False,
        labelcolor=theme.INK, fontsize=8.5, handletextpad=0.6, labelspacing=0.6,
    )

    ax.text(1.0, 0.62,
            "xG = the chance an average player scores from that position and situation.",
            color=theme.INK_FAINT, fontsize=8, ha="right", va="center")
    credit = "StatsBomb open data" if source == "statsbomb" else "Understat"
    ax.text(1.0, 0.22, f"Data: {credit}", color=theme.INK_FAINT,
            fontsize=8, ha="right", va="center")


def latest_match_id(season: int | None = None) -> int:
    """The most recently played fixture, for a sensible default."""
    fixtures = understat.fixtures(season) if season else understat.fixtures()
    played = fixtures[fixtures["played"]]
    if played.empty:
        raise ValueError("No matches have been played yet this season.")
    return int(played.iloc[-1]["match_id"])
