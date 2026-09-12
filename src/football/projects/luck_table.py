"""The luck table: the standings beside the standings the play deserved.

Every team's real points against their expected points, sorted by the gap.
xPTS is what the quality of chances in each match was worth, resolved into a
points expectation -- so the gap is everything the table records that the play
did not earn: finishing, goalkeeping, deflections, a red card, a bad week for
the opposition's striker.

Two claims, and it is worth being precise about which is which:

* **The gap is real.** It is not a modelling artefact. A team seven points
  clear of their xPTS genuinely has banked more than they created.
* **The gap is not destiny.** It narrows over a season, on average, because
  finishing runs end. It does not narrow for every team, and a squad with an
  outstanding goalkeeper can hold a positive gap for a long time.

So this chart is a list of candidates for regression, not a table of frauds,
and the subtitle says how many matches it is standing on.

Bars diverge from zero: warm to the right for teams above expectation, cool to
the left for teams below, grey for the ones sitting on it. Position change --
where a team would sit if the table were ordered by xPTS -- rides alongside,
because "4th but deserves 11th" is the sentence people actually want.
"""

from __future__ import annotations

from .. import theme
from ..season import Season

#: Below this many points of gap, the difference is not worth a colour.
NOISE_BAND = 0.05


def figure(season: Season | None = None, top: int | None = None):
    """Build the luck table. Returns ``(fig, table)``."""
    season = season or Season()
    table = season.table()
    table = table[table["played"] > 0].copy()
    if table.empty:
        raise ValueError("No matches played yet this season.")

    table = table.sort_values("luck", ascending=True).reset_index(drop=True)
    if top:
        keep = table.reindex(
            table["luck"].abs().sort_values(ascending=False).index[:top]
        )
        table = keep.sort_values("luck", ascending=True).reset_index(drop=True)

    height = max(6.0, 0.42 * len(table) + 3.0)
    fig, ax = theme.new_figure(11.5, height)
    theme.style_axes(ax, grid_axis="x")

    span = float(table["luck"].abs().max()) or 1.0
    colors = [theme.diverging(v, span) for v in table["luck"]]

    ax.barh(
        table.index, table["luck"], color=colors,
        height=0.62, zorder=3, edgecolor=theme.SURFACE, linewidth=1.5,
    )
    ax.axvline(0, color=theme.INK_MUTED, linewidth=1.0, zorder=4)

    ax.set_yticks(table.index)
    ax.set_yticklabels(table["team"], fontsize=9, color=theme.INK)
    ax.set_xlabel("Points above or below what the chances were worth  (points − xPTS)")

    _annotate(ax, table, span)
    _legend(ax)

    ax.set_xlim(-span * 1.45, span * 1.45)
    ax.set_ylim(-0.8, len(table) - 0.2)

    theme.title_block(
        fig,
        "The table, and the table they deserve",
        f"{season.label} Premier League  ·  after {season.matches_played} matches  ·  "
        f"sorted by the gap between points banked and points earned",
    )
    theme.credit(
        fig,
        "Understat (xG, xPTS)",
        "Early-season samples are small — a list of candidates, not a verdict",
    )
    return fig, table


def _annotate(ax, table, span: float) -> None:
    """Put the numbers where the eye already is: at the end of each bar."""
    pad = span * 0.05
    for i, row in enumerate(table.itertuples()):
        right = row.luck >= 0
        ax.text(
            row.luck + (pad if right else -pad),
            i,
            f"{row.luck:+.1f}",
            fontsize=8.2,
            color=theme.INK,
            va="center",
            ha="left" if right else "right",
            zorder=5,
        )
        # The sentence people want: where they are, where the xG puts them.
        move = row.position_delta
        if move == 0:
            note = f"{row.position}  ·  xG agrees"
        else:
            direction = "would drop to" if move > 0 else "would rise to"
            note = f"{row.position}  ·  {direction} {row.xg_position}"
        ax.text(
            -span * 1.42,
            i,
            note,
            fontsize=7.6,
            color=theme.INK_FAINT,
            va="center",
            ha="left",
            zorder=5,
        )


def _legend(ax) -> None:
    from matplotlib.patches import Patch

    ax.legend(
        handles=[
            Patch(
                facecolor=theme.POLE_NEGATIVE,
                label="below expectation — due a correction up",
            ),
            Patch(facecolor=theme.MIDPOINT, label="about right"),
            Patch(
                facecolor=theme.POLE_POSITIVE,
                label="above expectation — riding something",
            ),
        ],
        loc="lower right",
        bbox_to_anchor=(1.0, 1.005),
        ncol=3,
        fontsize=8,
        handlelength=1.2,
        handleheight=1.0,
        columnspacing=1.4,
    )
