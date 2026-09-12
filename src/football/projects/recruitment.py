"""Recruitment scatter: who creates, who finishes, and who does both.

Two axes, both per 90 minutes and both penalty-free:

    x  npxG per 90   the quality of the chances a player gets on the end of
    y  xA per 90     the quality of the chances they lay on for someone else

Per 90 rather than totals, because a substitute who plays 200 minutes and a
first choice who plays 900 are otherwise incomparable. Penalty-free, because
penalty duty is a job, not a skill, and it inflates a striker's xG by a
constant that says nothing about their play.

The diagonal is the combined number. Players above it contribute more per
minute than players below, whichever way they split it, and the labelled
points are the ones furthest out -- a shortlist rather than a name on every
dot.

The read that matters is the **gap between a player's marker and their
finishing**: marker position is what the chances were worth, and a striker
sitting high on x with poor actual goals is either unlucky or a bad finisher.
Small samples make that gap noisy, which is exactly why ``min_minutes``
defaults conservatively and the subtitle says how small the sample is.
"""

from __future__ import annotations

import numpy as np

from .. import theme
from ..season import Season

#: Below about three full matches, a per-90 is mostly noise.
DEFAULT_MIN_MINUTES = 270

#: Defaults to attacking positions. Including defenders and goalkeepers piles
#: half the league into a blob at the origin -- they are not bad on these axes,
#: the axes are simply not about their job -- and it drags both medians down to
#: near zero, which makes the quadrants meaningless. Pass ``position=None``
#: explicitly for the whole league.
DEFAULT_POSITIONS = ("MID", "FWD")

#: How many players to name. More than this and the labels become a wall.
DEFAULT_LABELS = 12

MARKER_BASE = 28
MARKER_PER_90 = 11


def figure(
    season: Season | None = None,
    position: str | list[str] | None = DEFAULT_POSITIONS,
    min_minutes: int = DEFAULT_MIN_MINUTES,
    max_age: int | None = None,
    max_price: float | None = None,
    labels: int = DEFAULT_LABELS,
    highlight: list[str] | None = None,
):
    """Build the recruitment scatter. Returns ``(fig, frame)``."""
    season = season or Season()
    pool = season.player_pool(
        min_minutes=min_minutes,
        position=position,
        max_age=max_age,
        max_price=max_price,
    )
    if pool.empty:
        raise ValueError(
            f"No players match: min_minutes={min_minutes}, position={position}, "
            f"max_age={max_age}, max_price={max_price}. Try relaxing a filter."
        )

    pool = pool.sort_values("npxgi_per_90", ascending=False).reset_index(drop=True)
    fig, ax = theme.new_figure(11.5, 8.0)

    x = pool["npxg_per_90"]
    y = pool["xa_per_90"]
    # Marker area carries minutes, so a big dot is a bigger sample and the eye
    # discounts the small ones without being told to.
    sizes = MARKER_BASE + (pool["minutes"] / 90.0) * MARKER_PER_90

    named = set(highlight or [])
    shortlist = pool.head(labels)
    to_label = pool[pool["player"].isin(named)] if named else shortlist

    is_labelled = pool["player"].isin(set(to_label["player"]))

    ax.scatter(
        x[~is_labelled], y[~is_labelled], s=sizes[~is_labelled],
        facecolor=theme.NEUTRAL_MARK, edgecolor="none", alpha=0.55, zorder=2,
    )
    ax.scatter(
        x[is_labelled], y[is_labelled], s=sizes[is_labelled],
        facecolor=theme.ACCENT, edgecolor=theme.SURFACE, linewidth=1.2, zorder=3,
    )

    _draw_median_guides(ax, x, y)

    ax.set_xlabel("Non-penalty xG per 90  →  chance quality they get on the end of")
    ax.set_ylabel("xA per 90  →  chance quality they create for others")
    ax.set_xlim(left=min(0, x.min() * 1.1))
    ax.set_ylim(bottom=min(0, y.min() * 1.1))

    # After the limits, never before: place_labels() solves collisions in
    # display space, and changing the limits afterwards would move every box.
    theme.place_labels(
        ax, fig,
        zip(
            to_label["npxg_per_90"],
            to_label["xa_per_90"],
            to_label["web_name"],
            strict=True,
        ),
    )

    who = _describe(position, max_age, max_price)
    theme.title_block(
        fig,
        "Who is creating, who is finishing",
        f"{season.label} Premier League  ·  {who}  ·  "
        f"{min_minutes}+ minutes  ·  {len(pool)} players  ·  "
        f"marker size = minutes played",
    )
    theme.credit(
        fig,
        "Understat (xG), Fantasy Premier League (price, age)",
        f"After {season.matches_played} matches — small sample, "
        "read as a shortlist not a ranking",
    )
    return fig, pool


def _draw_median_guides(ax, x, y) -> None:
    """Median crosshairs, so each quadrant has a plain meaning."""
    mx, my = float(np.median(x)), float(np.median(y))
    ax.axvline(mx, color=theme.LINES, linewidth=0.8, linestyle=(0, (4, 4)), zorder=1)
    ax.axhline(my, color=theme.LINES, linewidth=0.8, linestyle=(0, (4, 4)), zorder=1)
    ax.text(
        mx, ax.get_ylim()[1], "  league median", fontsize=7.5,
        color=theme.INK_FAINT, va="top", ha="left",
    )


def _describe(position, max_age, max_price) -> str:
    parts = []
    if position:
        parts.append(position if isinstance(position, str) else "/".join(position))
    else:
        parts.append("all positions")
    if max_age:
        parts.append(f"under {max_age + 1}")
    if max_price:
        parts.append(f"£{max_price}m or less")
    return "  ·  ".join(parts)
