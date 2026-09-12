"""Shared chart conventions.

One place for the palette, the surface, the type and the furniture, so five
figures read as one set. Extends the two-hue scheme the shot map already used.

The palette was validated, not eyeballed, against the dark surface on the
all-pairs pairlist that scatter plots require:

    slots #3D9BE0 / #E5484D / #c98500
    lightness band  PASS      chroma floor PASS     contrast vs surface PASS
    normal vision   PASS  (worst pair dE 15.6, floor 15)
    CVD separation  WARN  (worst pair dE 6.3 deutan, 12.2 tritan)

The CVD warning is in the 6-8 band, which is legal **only** with a secondary
encoding. Every chart here therefore carries direct labels, and no chart asks
colour alone to carry identity. Adding a fourth hue is not free -- re-run
``validate_palette.js`` before trying.
"""

from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt

# Surfaces and ink.
SURFACE = "#1a1a19"
LINES = "#4a4a48"
INK = "#ededeb"
INK_MUTED = "#9a9a97"
INK_FAINT = "#6a6a67"

# Categorical slots, in fixed order. Never cycled, never reordered per chart.
SERIES = ("#3D9BE0", "#E5484D", "#c98500")
BLUE, RED, AMBER = SERIES

# Diverging: two poles and a neutral grey midpoint. Used wherever a value has
# a sign -- points above expectation, xG difference, price value.
POLE_POSITIVE = RED
POLE_NEGATIVE = BLUE
MIDPOINT = "#6a6a67"

# A single hue for "everyone", with an accent for the few worth naming.
NEUTRAL_MARK = "#5a7d93"
ACCENT = AMBER

TITLE_SIZE = 17
SUBTITLE_SIZE = 9.5
LABEL_SIZE = 8.5
TICK_SIZE = 8


def apply() -> None:
    """Set the rcParams every figure in this project shares."""
    mpl.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "text.color": INK,
            "axes.labelcolor": INK_MUTED,
            "axes.edgecolor": LINES,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "xtick.labelsize": TICK_SIZE,
            "ytick.labelsize": TICK_SIZE,
            "axes.labelsize": LABEL_SIZE,
            "axes.titlesize": TITLE_SIZE,
            "grid.color": LINES,
            "grid.alpha": 0.35,
            "grid.linewidth": 0.6,
            "legend.frameon": False,
            "legend.labelcolor": INK,
            "legend.fontsize": LABEL_SIZE,
            "figure.dpi": 110,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
        }
    )


def style_axes(ax, grid_axis: str = "both") -> None:
    """Recessive furniture: no box, a faint grid behind the marks."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(LINES)
        ax.spines[side].set_linewidth(0.8)
    if grid_axis != "none":
        ax.grid(True, axis=grid_axis, zorder=0)
        ax.set_axisbelow(True)


def title_block(fig, title: str, subtitle: str = "", x: float = 0.0, y: float = 1.0):
    """A left-aligned title with a muted subtitle under it."""
    fig.text(x, y, title, fontsize=TITLE_SIZE, fontweight="bold", color=INK, va="top")
    if subtitle:
        fig.text(
            x,
            y - 0.042,
            subtitle,
            fontsize=SUBTITLE_SIZE,
            color=INK_MUTED,
            va="top",
        )


def credit(fig, sources: str, note: str = "", y: float = -0.01):
    """The source line. Understat's licence is informal; credit it anyway."""
    text = f"Data: {sources}"
    if note:
        text = f"{note}  ·  {text}"
    fig.text(1.0, y, text, fontsize=7.5, color=INK_FAINT, ha="right", va="top")


def diverging(value: float, span: float) -> str:
    """Colour for a signed value: warm above zero, cool below, grey at nothing."""
    if abs(value) < span * 0.05:
        return MIDPOINT
    return POLE_POSITIVE if value > 0 else POLE_NEGATIVE


def new_figure(width: float = 11.0, height: float = 7.5):
    """A styled figure and axes."""
    apply()
    fig, ax = plt.subplots(figsize=(width, height))
    style_axes(ax)
    return fig, ax


# Right first, then left, then diagonals, then progressively further vertically.
# Reading order for a scatter, and it keeps labels off the axes where possible.
_LABEL_OFFSETS = [
    (10, 0), (-10, 0), (10, 10), (-10, 10), (10, -10), (-10, -10),
    (0, 12), (0, -12), (0, 26), (0, -26), (0, 40), (0, -40),
]

#: Past this far from its marker, a label needs a line back to it.
_LEADER_AT = 22


def place_labels(ax, fig, points, size: float = LABEL_SIZE, color: str = INK) -> int:
    """Label scattered points without letting any label detach from its marker.

    ``points`` is an iterable of ``(x, y, text)`` in data coordinates.

    Collision is decided in *display* space, because "do these two overlap" is
    a question about pixels, not about two axes with different units. Each
    label tries a ring of offsets around its marker and takes the first that
    hits nothing already placed; if it ends up far from home, a hair line is
    drawn back so the pairing stays unambiguous. Returns how many were placed.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    placed: list[tuple[float, float, float, float]] = []
    count = 0

    for x, y, label in points:
        chosen = None
        for dx, dy in _LABEL_OFFSETS:
            ha = "left" if dx > 0 else ("right" if dx < 0 else "center")
            va = "bottom" if dy > 0 else ("top" if dy < 0 else "center")
            text = ax.annotate(
                label, (x, y), xytext=(dx, dy), textcoords="offset points",
                fontsize=size, color=color, ha=ha, va=va, zorder=5,
            )
            box = text.get_window_extent(renderer=renderer)
            candidate = (box.x0 - 2, box.y0 - 2, box.x1 + 2, box.y1 + 2)
            if not any(_boxes_overlap(candidate, other) for other in placed):
                placed.append(candidate)
                chosen = (dx, dy)
                count += 1
                break
            text.remove()

        if chosen and abs(chosen[0]) + abs(chosen[1]) > _LEADER_AT:
            px, py = ax.transData.transform((x, y))
            scale = fig.dpi / 72
            lx, ly = ax.transData.inverted().transform(
                (px + chosen[0] * scale, py + chosen[1] * scale)
            )
            ax.plot(
                [x, lx], [y, ly],
                color=INK_FAINT, linewidth=0.6, zorder=1, solid_capstyle="butt",
            )

    return count


def _boxes_overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
