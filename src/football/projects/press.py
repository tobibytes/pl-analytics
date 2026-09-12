"""Press profiles: how a team defends, not just how well.

Two axes that describe a defensive *style* rather than a defensive grade:

    x  PPDA          opposition passes allowed per defensive action, in their
                     half. Low means the press starts high and bites early.
                     High means the team sits off and defends its own box.
    y  xGA per match the quality of chances the approach actually concedes.

Both axes are inverted so that "good" is up and right in the usual way: the
x axis runs from high PPDA on the left to low PPDA on the right, so pressing
teams sit right; the y axis runs from high xGA at the bottom to low at the top,
so solid teams sit high.

The point of plotting style against outcome is that neither quadrant is simply
correct. A high press that concedes little is Arsenal. A low block that
concedes little is a perfectly good plan executed well. A high press that
concedes a lot is a team whose press is being played through -- the most
diagnostic quadrant on the chart, and the one that tends to change manager.

PPDA is computed as a ratio of season totals, not a mean of match ratios, so a
single match with few defensive actions cannot dominate the number.
"""

from __future__ import annotations

from .. import theme
from ..season import Season

MARKER_BASE = 40
MARKER_PER_DEEP = 2.0


def figure(season: Season | None = None, highlight: list[str] | None = None):
    """Build the press profile scatter. Returns ``(fig, table)``."""
    season = season or Season()
    table = season.table()
    table = table[table["played"] > 0].copy()
    if table.empty:
        raise ValueError("No matches played yet this season.")

    table["xga_per_match"] = table["xga"] / table["played"]
    table["deep_per_match"] = table["deep"] / table["played"]

    fig, ax = theme.new_figure(11.0, 8.0)

    x = table["ppda"]
    y = table["xga_per_match"]
    sizes = MARKER_BASE + table["deep_per_match"] * MARKER_PER_DEEP * 10

    wanted = {h.lower() for h in (highlight or [])}
    is_highlight = table["team"].str.lower().isin(wanted)

    ax.scatter(
        x[~is_highlight], y[~is_highlight], s=sizes[~is_highlight],
        facecolor=theme.NEUTRAL_MARK, edgecolor=theme.SURFACE,
        linewidth=1.2, alpha=0.85, zorder=2,
    )
    if is_highlight.any():
        ax.scatter(
            x[is_highlight], y[is_highlight], s=sizes[is_highlight],
            facecolor=theme.ACCENT, edgecolor=theme.SURFACE, linewidth=1.4, zorder=3,
        )

    _quadrants(ax, x.median(), y.median())

    # Inverted: low PPDA (heavy press) to the right, low xGA (solid) at the top.
    ax.invert_xaxis()
    ax.invert_yaxis()
    ax.set_xlabel(
        "←  sits off          PPDA — opposition passes per defensive action"
        "          presses high  →"
    )
    ax.set_ylabel("xG against per match  —  higher on the chart is meaner")

    # Labels go on last. place_labels() resolves collisions in display space,
    # so every limit and inversion must already be final -- otherwise the
    # geometry it solved against is not the geometry that gets drawn.
    ordered = table.assign(_priority=is_highlight.astype(int)).sort_values(
        "_priority", ascending=False
    )
    theme.place_labels(
        ax,
        fig,
        zip(ordered["ppda"], ordered["xga_per_match"], ordered["team"], strict=True),
        size=7.8,
        color=theme.INK_MUTED,
    )

    theme.title_block(
        fig,
        "How each side defends, and what it costs them",
        f"{season.label} Premier League  ·  marker size = deep completions per match "
        f"(their own territory gained)",
    )
    theme.credit(
        fig,
        "Understat",
        f"After {season.matches_played} matches",
    )
    return fig, table


def _quadrants(ax, mx: float, my: float) -> None:
    """Median crosshairs with the four styles named."""
    ax.axvline(mx, color=theme.LINES, linewidth=0.8, linestyle=(0, (4, 4)), zorder=1)
    ax.axhline(my, color=theme.LINES, linewidth=0.8, linestyle=(0, (4, 4)), zorder=1)

    corners = {
        (0.02, 0.97): "sits off, solid",
        (0.98, 0.97): "presses, solid",
        (0.02, 0.03): "sits off, leaky",
        (0.98, 0.03): "presses, played through",
    }
    for (fx, fy), label in corners.items():
        ax.text(
            fx, fy, label, transform=ax.transAxes,
            fontsize=8, color=theme.INK_FAINT,
            ha="left" if fx < 0.5 else "right",
            va="top" if fy > 0.5 else "bottom",
            zorder=1,
        )
