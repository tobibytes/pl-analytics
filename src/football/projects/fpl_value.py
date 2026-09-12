"""FPL value: what a player costs against what they are worth.

Small multiples, one panel per position, because price means different things
in different positions -- a £5.0m defender and a £5.0m forward are not
competing for the same job, and putting them on one axis invites a comparison
that does not exist. This is also why a single scatter with four colours would
be the wrong form here.

    x  price now (£m)
    y  expected goal involvements per 90  (npxG + xA, penalty-free)

Expected involvements rather than points scored, deliberately. Points are the
outcome and they are noisy this early; xGI is the process, and it is what the
points converge to. A player sitting high on xGI with low points has been
unlucky and is usually still cheap -- which is the entire trade.

The fitted line is what the market charges for production. Above it, a player
is producing more than their price implies; below it, less. Distance from that
line is the only "value" claim this chart makes, and it is a claim about the
last few weeks, not the season.

Ownership is drawn as marker size, so a cheap, productive, *unowned* player --
the thing everyone is actually looking for -- shows up as a small dot high
above the line.
"""

from __future__ import annotations

import numpy as np

from .. import theme
from ..season import Season

DEFAULT_MIN_MINUTES = 180

#: Goalkeepers are deliberately absent. Their npxG + xA is zero to three
#: decimal places, so the panel ranks them on rounding noise and implies a
#: goalkeeper with 0.12 is worth more than one with 0.00. Judging a keeper
#: needs save quality and goals prevented, which is a different chart with a
#: different y axis -- not a fifth panel on this one. Pass positions=("GK",)
#: to see the bad version for yourself.
POSITION_ORDER = ("DEF", "MID", "FWD")
POSITION_TITLE = {
    "GK": "Goalkeepers",
    "DEF": "Defenders",
    "MID": "Midfielders",
    "FWD": "Forwards",
}

LABELS_PER_PANEL = 5
MARKER_BASE = 22
MARKER_PER_PERCENT = 9


def figure(
    season: Season | None = None,
    min_minutes: int = DEFAULT_MIN_MINUTES,
    max_price: float | None = None,
    available_only: bool = True,
    positions: tuple[str, ...] = POSITION_ORDER,
):
    """Build the FPL value panels. Returns ``(fig, frame)``."""
    season = season or Season()
    pool = season.player_pool(
        min_minutes=min_minutes,
        max_price=max_price,
        available_only=available_only,
    )
    if pool.empty:
        raise ValueError("No players match those filters. Try lowering min_minutes.")

    theme.apply()
    import matplotlib.pyplot as plt

    # Three panels read better in a row than in a 2x2 grid with a hole in it.
    ncols = len(positions) if len(positions) <= 3 else 2
    nrows = -(-len(positions) // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.0 * ncols, 5.8 * nrows))
    axes = np.atleast_1d(axes).ravel()

    for ax, position in zip(axes, positions, strict=False):
        panel = pool[pool["fpl_position"] == position]
        _panel(ax, panel, position, fig)

    for ax in axes[len(positions):]:
        ax.set_visible(False)

    theme.title_block(
        fig,
        "Price against production",
        f"{season.label} Premier League  ·  {min_minutes}+ minutes  ·  "
        f"marker size = ownership  ·  line = what the market charges for production",
        y=0.99,
    )
    theme.credit(
        fig,
        "Understat (xG, xA), Fantasy Premier League (price, ownership)",
        f"After {season.matches_played} matches"
        + ("  ·  injured and suspended players excluded" if available_only else ""),
    )
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    return fig, pool


def _panel(ax, panel, position: str, fig) -> None:
    theme.style_axes(ax)
    ax.set_title(
        POSITION_TITLE.get(position, position),
        fontsize=11, color=theme.INK, loc="left", pad=8,
    )

    if panel.empty:
        ax.text(
            0.5, 0.5, "no players", transform=ax.transAxes,
            ha="center", va="center", color=theme.INK_FAINT, fontsize=9,
        )
        return

    x = panel["price"].to_numpy(dtype=float)
    y = panel["npxgi_per_90"].to_numpy(dtype=float)
    ownership = panel["selected_by_percent"].to_numpy(dtype=float)
    sizes = MARKER_BASE + ownership * MARKER_PER_PERCENT

    residual = _residual(x, y)
    # Name the biggest positive residuals: cheap for what they produce.
    order = np.argsort(-residual)
    labelled = set(order[:LABELS_PER_PANEL].tolist())
    mask = np.array([i in labelled for i in range(len(panel))])

    ax.scatter(
        x[~mask], y[~mask], s=sizes[~mask],
        facecolor=theme.NEUTRAL_MARK, edgecolor="none", alpha=0.55, zorder=2,
    )
    ax.scatter(
        x[mask], y[mask], s=sizes[mask],
        facecolor=theme.ACCENT, edgecolor=theme.SURFACE, linewidth=1.1, zorder=3,
    )

    _draw_fit(ax, x, y)

    ax.set_xlabel("Price (£m)")
    ax.set_ylabel("npxG + xA per 90")
    # Breathing room, so a label on an edge point still lands inside the panel.
    ax.margins(x=0.14, y=0.12)

    # Labels last, once the panel's limits are settled.
    picked = np.nonzero(mask)[0]
    theme.place_labels(
        ax,
        fig,
        ((x[i], y[i], panel.iloc[i]["web_name"]) for i in picked),
        size=7.8,
    )


def _residual(x, y):
    """Vertical distance from the price/production trend."""
    if len(x) < 3 or np.ptp(x) == 0:
        return np.zeros_like(y)
    slope, intercept = np.polyfit(x, y, 1)
    return y - (slope * x + intercept)


def _draw_fit(ax, x, y) -> None:
    if len(x) < 3 or np.ptp(x) == 0:
        return
    slope, intercept = np.polyfit(x, y, 1)
    span = np.linspace(x.min(), x.max(), 2)
    ax.plot(
        span, slope * span + intercept,
        color=theme.INK_FAINT, linewidth=1.2, linestyle=(0, (5, 4)), zorder=1,
    )
