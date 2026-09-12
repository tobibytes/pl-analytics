# Project context

Premier League analytics — five figures over one shared data layer. Python,
pandas, matplotlib, mplsoccer. Built to learn the craft, so the reasoning
behind a choice matters as much as the choice.

Currently tracking **2026/27**. `config.CURRENT_SEASON` is the single place
that knows which season is "now"; sources label a season by the year it starts.

## Environment

`uv`, **0.12 or newer** — `pyproject.toml` enforces this. Older uv writes its
editable-install `.pth` with the macOS `UF_HIDDEN` flag, and CPython 3.13's
`site.addpackage()` skips hidden `.pth` files, so `import football` dies with a
bare `ModuleNotFoundError` and nothing explains why. Verified: 0.8.22 broken,
0.12.13 fine.

    uv sync
    uv run football luck
    uv run --group dev pytest

Python is pinned to 3.13 in `.python-version`; dependencies are locked in
`uv.lock`. Do not add a `requirements.txt` back.

## Architecture

    sources/   one module per upstream feed. Returns tidy DataFrames. No plotting.
    season.py  Season — joins every source. The only thing projects should read.
    projects/  one module per figure. figure(season, **options) -> (fig, frame).
    theme.py   palette, type, label placement. No data.
    cli.py     one subcommand per project.

A project must never fetch directly. Going through `Season` is what gives you
the disk cache, the club-name reconciliation and the player-name join — and it
is what lets projects read each other's numbers, which is the point of the
shared layer.

Every figure returns its DataFrame alongside the figure, so `--csv` works and
so the chart is never the only way to get at the rows.

## Data sources, and what each is for

| Source | Key | Role |
|---|---|---|
| Understat | no | xG, xA, shot locations, PPDA, xPTS. The analysis. |
| FPL | no | price, ownership, availability, age. The human context. |
| football-data.org | free tier | fixtures, referees, crests, canonical ids. |
| StatsBomb open data | no | full events — **archive only**, no current season. |

`docs/data-sources.md` has the full research with real payloads. Read it before
adding a source; it also records what each source does *not* have, which is
usually the more expensive thing to discover.

**Understat has no public API.** The routes are read out of the site's own JS
and are pinned in `sources/understat.py`. If a chart empties out, suspect these
first. They need a browser `User-Agent` and `X-Requested-With`.

**StatsBomb requires attribution.** Every figure carries it. Keep it.

**API-Football is not usable for the current season.** Its free plan is capped
at seasons 2022–2024 — `/leagues` will happily list 2026 with every coverage
flag true, but that is the catalogue, not your entitlement. Do not build
against it without checking `/status` first.

## Data gotchas worth knowing

- **Understat serves HTML-escaped names** — `Dara O&#039;Shea`, `Gro&szlig;`.
  Unescaped they reach the chart verbatim *and* break every name join.
  `understat._text()` handles it; use it on any new string field you read.
- **Clubs are spelled differently by every source.** Join on `team_key`, never
  on the raw name — a mismatch silently drops a team from a chart rather than
  raising. `teams.py` resolves 52 observed spellings to 20 clubs.
- **Players are matched by a cascade, not by name.** Raw names get 76%.
  `matching.py` gets 99% through accent stripping, transliteration of letters
  NFKD cannot decompose (`Đ`, `Ø`, `Ł`), bidirectional token subsets, and a
  league-wide pass for transfers. Ambiguity is refused, never guessed —
  Arsenal field three players called Gabriel. `season.join_report` reports it.
- **Transfers break club-restricted joins.** Understat files a player under the
  club they played those minutes for; FPL under the club that owns them now.
- **PPDA is a ratio of season totals**, never a mean of per-match ratios, or one
  match with few defensive actions dominates the number.
- **Penalties inflate xG by a constant** that says nothing about play. Use
  `npxg` for anything comparing players.
- **FPL returns most numerics as strings**, and nulls as empty strings.
- StatsBomb `minute` is *elapsed*, so a goal 22:41 in is minute 22 — football
  calls that the 23rd. The shot-map path adds the +1.
- The **penalty shoot-out is StatsBomb period 5** and its penalties are ordinary
  `Shot` events. Excluded by default: not part of match xG, and they stack on
  the spot.

## Pitch coordinates

StatsBomb's **120 x 80**, origin top-left, y increasing downwards.
`Pitch(pitch_type="statsbomb")` matches. Understat stores 0–1 normalised;
`sources.understat.shots()` scales to 120 x 80 so both feeds share one
coordinate system and one plotting path.

Both feeds normalise every shot to attack **left → right**, which would stack
both teams on the same goal. `projects/shot_map._add_plot_coordinates()`
mirrors one team through the centre in **both** axes, and is the only place
that should.

## Chart conventions

- Dark surface `#1a1a19`. Categorical slots in fixed order, never cycled:
  `#3D9BE0` / `#E5484D` / `#c98500`. Diverging uses the blue and red poles with
  a grey midpoint.
- That palette was **validated, not eyeballed**, on the all-pairs pairlist that
  scatter plots need: lightness, chroma, contrast and normal-vision all pass;
  CVD separation lands at ΔE 6.3 deutan, which is the 6–8 floor band and is
  legal **only** with a secondary encoding. Every chart therefore carries direct
  labels and none asks colour alone to carry identity. **Re-run the validator
  before adding a fourth hue.**
- Marker **area** encodes magnitude, never radius.
- Text wears neutral ink (`#ededeb` / `#9a9a97` / `#6a6a67`); colour lives in
  the marks.
- Label selectively — a shortlist, never a name on every point.
- **`theme.place_labels()` for any scatter.** It resolves collisions in display
  space and draws a leader line when a label lands far from its marker. Call it
  **after every limit and inversion is final** — it solves against the geometry
  that exists when it runs, so changing the limits afterwards silently invalidates
  the collision layout.
- No dual axes, ever. Two measures of different scale means two charts.

## Conventions

- Comments explain *why*, not what. A comment restating the code is noise; a
  comment recording why a default is 270 minutes, or why a stage refuses to
  guess, is the thing worth keeping.
- Tests cover the pure logic — matching, reconciliation, caching — and never
  touch the network.
- Refusing to answer beats guessing. An unmatched player is reported; a
  mismatched one corrupts a chart silently.
