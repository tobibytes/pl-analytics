"""Fixture run difficulty: who has a kind month and who hits a wall.

A grid — one row per club, one column per upcoming fixture — shaded by how
hard that fixture looks. The point is the *run*, not any single match: a cheap
forward with five soft fixtures is worth more than a better one facing the top
four, and that trade is invisible on a per-player chart.

## How difficulty is scored

An opponent's quality is their **non-penalty expected goal difference per
match** — how much better their chances have been than their opponents'. It
uses both ends of the pitch in one number, and being xG-based it reads the
performance rather than the results, so a side riding a hot streak does not
look artificially hard.

Two corrections matter more than the metric itself:

**Shrinkage.** Three matches is not enough to know anything. A club with
+4.9 npxGD over three games is not a +4.9-per-match side; they are a decent
side who had a good week. Every rating is therefore pulled towards the league
average in proportion to how little evidence there is:

    rating = observed x n / (n + PRIOR_MATCHES)

With ``PRIOR_MATCHES`` at 6, a club three games in is credited with a third of
its apparent strength, and the grid says so in the subtitle. By March the
shrinkage is doing almost nothing and the ratings stand on their own. The
league average npxGD is exactly zero by construction, which is what makes this
a plain multiplication rather than a weighted mean.

**Venue.** Home advantage in this league is worth roughly a fifth of a goal of
xG difference, so an away trip is scored harder than the same opponent at home.

The scale is therefore in goals of expected difference per match, and a
positive number means the opponent is expected to outcreate you.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, Normalize

from .. import theme
from ..season import Season

DEFAULT_COUNT = 6

#: Matches of imaginary league-average evidence mixed into every rating. Set by
#: how quickly xG stabilises: around six games a club's xG difference starts to
#: carry real signal, so six is the point where observation outweighs the prior.
PRIOR_MATCHES = 6.0

#: Home advantage, in goals of expected difference per match.
HOME_ADVANTAGE = 0.20

#: Hard ceiling on how much of a run to draw before the cells stop being
#: readable and the whole thing becomes decoration.
MAX_COUNT = 12

#: The colour scale is anchored at this percentile of |difficulty| rather than
#: at the maximum. One away trip to the runaway leaders would otherwise set the
#: scale for the whole grid and flatten the other 119 cells into one shade.
#: Values beyond it clip, which is the correct trade: they are already "brutal".
SCALE_PERCENTILE = 88


def figure(
    season: Season | None = None,
    count: int = DEFAULT_COUNT,
    highlight: list[str] | None = None,
):
    """Build the fixture-run grid. Returns ``(fig, frame)``."""
    season = season or Season()
    count = max(1, min(count, MAX_COUNT))

    ratings = team_ratings(season)
    grid = upcoming_runs(season, ratings, count)
    if grid.empty:
        raise ValueError("No upcoming fixtures — the season looks finished.")

    order = (
        grid.groupby("team")["difficulty"].mean().sort_values().index.tolist()
    )
    rows = {team: i for i, team in enumerate(order)}

    fig, ax = theme.new_figure(2.0 + count * 1.35, 1.6 + len(order) * 0.42)
    theme.style_axes(ax, grid_axis="none")

    span = float(np.percentile(np.abs(grid["difficulty"]), SCALE_PERCENTILE)) or 1.0
    norm = Normalize(vmin=-span, vmax=span)
    cmap = _difficulty_cmap()

    wanted = {h.lower() for h in (highlight or [])}

    for cell in grid.itertuples():
        y = rows[cell.team]
        x = cell.slot
        colour = cmap(norm(cell.difficulty))
        ax.add_patch(
            plt_rect(x, y, facecolor=colour, edgecolor=theme.SURFACE),
        )
        ax.text(
            x, y, f"{cell.opponent_short}\n{'H' if cell.home else 'A'}",
            ha="center", va="center", fontsize=7.6, linespacing=1.25,
            color=_ink_for(cell.difficulty, span), zorder=3,
        )

    ax.set_xlim(-0.5, count - 0.5)
    ax.set_ylim(len(order) - 0.5, -0.5)
    ax.set_xticks(range(count))
    ax.set_xticklabels([f"next {i + 1}" for i in range(count)], fontsize=8)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels(order, fontsize=9, color=theme.INK)
    ax.tick_params(length=0)
    for label in ax.get_yticklabels():
        if label.get_text().lower() in wanted:
            label.set_color(theme.ACCENT)
            label.set_fontweight("bold")

    _run_totals(ax, grid, order, count)
    _legend(fig, ax, cmap, norm, span)

    # Per-club, from the table — clubs can be a match apart after a postponement.
    played = int(season.table()["played"].median())
    theme.title_block(
        fig,
        "Who has the kind run",
        f"{season.label} Premier League  ·  each club's next {count} fixtures  ·  "
        f"shaded by opponent strength, adjusted for venue  ·  "
        f"easiest run at the top",
    )
    theme.credit(
        fig,
        "Understat (xG)",
        f"Ratings shrunk towards league average — {played} matches played, "
        f"so each club is credited with {played / (played + PRIOR_MATCHES):.0%} "
        f"of its apparent strength",
    )
    return fig, grid


def team_ratings(season: Season) -> pd.DataFrame:
    """Each club's shrunk non-penalty xG difference per match.

    Positive is a strong side. Because the league's total npxG difference is
    zero by construction, shrinking towards the average is a straight scaling
    towards zero rather than a weighted mean against some estimated centre.
    """
    table = season.table()
    observed = (table["npxg"] - table["npxga"]) / table["played"]
    weight = table["played"] / (table["played"] + PRIOR_MATCHES)
    return pd.DataFrame(
        {
            "team_key": table["team_key"],
            "team": table["team"],
            "observed": observed,
            "rating": observed * weight,
        }
    )


def upcoming_runs(season: Season, ratings: pd.DataFrame, count: int) -> pd.DataFrame:
    """One row per club per upcoming fixture, with a difficulty score.

    Counted as each club's own next ``count`` matches rather than by gameweek:
    the schedule is not always level, and "what do I face next" is the question
    being asked anyway.
    """
    rating = dict(zip(ratings["team_key"], ratings["rating"], strict=True))
    name = dict(zip(ratings["team_key"], ratings["team"], strict=True))

    fixtures = season.fixtures
    upcoming = fixtures[~fixtures["played"]].sort_values("kickoff")

    rows = []
    for team_key, team in name.items():
        mine = upcoming[
            (upcoming["home_key"] == team_key) | (upcoming["away_key"] == team_key)
        ].head(count)

        for slot, fixture in enumerate(mine.itertuples()):
            home = fixture.home_key == team_key
            opponent_key = fixture.away_key if home else fixture.home_key
            strength = rating.get(opponent_key, 0.0)
            rows.append(
                {
                    "team": team,
                    "team_key": team_key,
                    "slot": slot,
                    "kickoff": fixture.kickoff,
                    "home": home,
                    "opponent": name.get(opponent_key, opponent_key),
                    "opponent_short": (
                        fixture.away_short if home else fixture.home_short
                    ),
                    "opponent_rating": strength,
                    # Away from home is harder, so the advantage is subtracted
                    # from your side of the ledger and added to theirs.
                    "difficulty": strength + (0.0 if home else HOME_ADVANTAGE),
                }
            )
    return pd.DataFrame(rows)


def plt_rect(x, y, **kwargs):
    from matplotlib.patches import Rectangle

    # A 2px-equivalent gap between cells, so adjacent fixtures stay separable.
    return Rectangle((x - 0.46, y - 0.44), 0.92, 0.88, linewidth=1.4, **kwargs)


def _difficulty_cmap():
    """Diverging, because difficulty has a natural centre: the league average.

    Two poles and a neutral middle, the same encoding the luck table uses for
    the same reason — the sign carries meaning, so a one-hue ramp would throw
    away the distinction between "kinder than average" and "barely anything".
    Green-to-red is avoided on purpose: it fails the most common colour-vision
    deficiency, and these are the project's validated poles.
    """
    return LinearSegmentedColormap.from_list(
        "difficulty",
        [theme.POLE_NEGATIVE, "#3b5668", "#3f3f3e", "#8c4044", theme.POLE_POSITIVE],
    )


def _ink_for(difficulty: float, span: float) -> str:
    """Dark ink on the saturated ends, light ink through the muted middle."""
    return theme.SURFACE if abs(difficulty) > span * 0.75 else theme.INK


def _run_totals(ax, grid, order, count) -> None:
    """The run's average difficulty, printed beside it — the row's summary."""
    means = grid.groupby("team")["difficulty"].mean()
    ax.text(
        count - 0.35, -1.15, "run",
        fontsize=8, color=theme.INK_MUTED, ha="left", va="center",
    )
    for team, y in ((t, i) for i, t in enumerate(order)):
        ax.text(
            count - 0.35, y, f"{means[team]:+.2f}",
            fontsize=8, color=theme.INK_MUTED, ha="left", va="center",
        )


def _legend(fig, ax, cmap, norm, span) -> None:
    """A short ramp with both ends named, rather than a full colourbar."""
    import matplotlib.cm as cm

    mappable = cm.ScalarMappable(norm=norm, cmap=cmap)
    bar = fig.colorbar(
        mappable, ax=ax, orientation="horizontal",
        fraction=0.028, pad=0.09, aspect=45,
    )
    bar.outline.set_visible(False)
    bar.ax.tick_params(length=0, labelsize=7.5, colors=theme.INK_MUTED)
    bar.set_ticks([-span, 0, span])
    bar.set_ticklabels(["kinder than average", "average", "harder than average"])
    bar.set_label(
        "Opponent's expected goal difference per match, adjusted for venue",
        fontsize=8, color=theme.INK_MUTED,
    )
