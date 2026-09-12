"""Command line entry point.

Every project is one subcommand. They share the season, the filters they have
in common, and the output path, so the shape of one command teaches the rest:

    football luck
    football recruit --position FWD --max-age 23
    football value --max-price 8
    football press --highlight Arsenal Brighton
    football shots --match latest

``--show`` opens the figure instead of writing a file; ``--csv`` writes the
frame behind the chart, because the chart is a summary and sometimes the rows
are the point.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import cache
from .config import OUTPUT_DIR, MissingCredential, season_label
from .season import Season


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "clear-cache":
        removed = cache.clear(args.source)
        print(f"Removed {removed} cached response{'s' if removed != 1 else ''}.")
        return 0

    try:
        return _run(args)
    except MissingCredential as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1


def _run(args) -> int:
    season = Season(args.season) if args.season else Season()

    if args.command == "table":
        return _print_table(season)

    if args.command == "fixtures":
        return _print_fixtures(args)

    fig, frame = _figure_for(args, season)

    if args.csv:
        path = Path(args.csv)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        print(f"Wrote {path}  ({len(frame)} rows)")

    if args.show:
        import matplotlib.pyplot as plt

        plt.show()
        return 0

    out = Path(args.output) if args.output else OUTPUT_DIR / f"{_slug(args)}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    print(f"Wrote {out}")
    return 0


def _figure_for(args, season: Season):
    if args.command == "luck":
        from .projects import luck_table

        return luck_table.figure(season, top=args.top)

    if args.command == "recruit":
        from .projects import recruitment

        return recruitment.figure(
            season,
            # argparse hands back None when the flag is absent, which would
            # override the module's MID/FWD default with "every position".
            position=args.position or recruitment.DEFAULT_POSITIONS,
            min_minutes=args.min_minutes,
            max_age=args.max_age,
            max_price=args.max_price,
            labels=args.labels,
            highlight=args.highlight,
        )

    if args.command == "value":
        from .projects import fpl_value

        return fpl_value.figure(
            season,
            min_minutes=args.min_minutes,
            max_price=args.max_price,
            available_only=not args.include_unavailable,
        )

    if args.command == "press":
        from .projects import press

        return press.figure(season, highlight=args.highlight)

    if args.command == "shots":
        from .projects import shot_map

        match = args.match
        if match == "latest":
            match = shot_map.latest_match_id(season.year)
            print(f"Latest played match: {match}")
        return shot_map.figure(match, source=args.source)

    raise ValueError(f"Unknown command {args.command!r}")


def _print_table(season: Season) -> int:
    """The luck table as text, for when a chart is more than you need."""
    table = season.table()
    print(f"\n  {season.label} Premier League — after {season.matches_played} matches\n")
    header = (
        f"  {'#':>2}  {'TEAM':<20}{'MP':>3}{'PTS':>5}"
        f"{'xPTS':>7}{'LUCK':>7}{'xGD':>7}{'PPDA':>7}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for row in table.itertuples():
        print(
            f"  {row.position:>2}  {row.team:<20}{row.played:>3}{row.points:>5}"
            f"{row.xpts:>7.1f}{row.luck:>+7.1f}{row.xgd:>+7.1f}{row.ppda:>7.1f}"
        )
    print()
    return 0


def _print_fixtures(args) -> int:
    """Upcoming matches, with the two things Understat does not carry:
    a confirmed kick-off time and the appointed referee."""
    from .sources import football_data

    matches = football_data.matches()
    upcoming = matches[matches["status"] != "FINISHED"].head(args.next)
    if upcoming.empty:
        print("\n  No upcoming fixtures found.\n")
        return 0

    print(f"\n  Next {len(upcoming)} fixtures\n")
    print(f"  {'WHEN':<18}{'MD':>3}  {'MATCH':<34}{'REFEREE'}")
    print("  " + "-" * 74)
    for row in upcoming.itertuples():
        fixture = f"{row.home_tla} v {row.away_tla}"
        when = row.kickoff.strftime("%a %d %b  %H:%M")
        print(f"  {when:<18}{row.matchday:>3}  {fixture:<34}{row.referee or '—'}")
    print()
    return 0


def _slug(args) -> str:
    """A filename that records the filters, so two runs do not overwrite."""
    parts = [args.command]
    for name in ("position", "max_age", "max_price", "match"):
        value = getattr(args, name, None)
        if not value:
            continue
        if isinstance(value, (list, tuple)):
            value = "-".join(str(v) for v in value)
        parts.append(str(value).replace(" ", "").replace(".", "p").lower())
    return "_".join(parts)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="football",
        description=f"Premier League analytics ({season_label()}). "
        "Every chart runs on free, keyless sources; only `fixtures` needs a "
        "football-data.org token.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  football luck                        the table vs the table deserved\n"
            "  football recruit --position FWD      under-24 forwards\n"
            "  football value --max-price 8.0       cheap production\n"
            "  football press --highlight Arsenal   pressing profiles\n"
            "  football shots --match latest        shot map, most recent game\n"
            "  football table                       the luck table as text\n"
            "  football fixtures --next 10          kick-off times and referees\n"
        ),
    )
    parser.add_argument(
        "--season", type=int, help="Season start year, e.g. 2026 for 2026/27."
    )
    sub = parser.add_subparsers(dest="command")

    def common(p):
        p.add_argument("-o", "--output", help="Where to write the PNG.")
        p.add_argument("--csv", help="Also write the underlying rows to this CSV.")
        p.add_argument(
            "--show", action="store_true", help="Open a window instead of saving."
        )
        return p

    luck = common(sub.add_parser("luck", help="Points banked against points deserved."))
    luck.add_argument("--top", type=int, help="Only the N biggest gaps.")

    rec = common(
        sub.add_parser("recruit", help="npxG vs xA per 90 — the shortlist scatter.")
    )
    rec.add_argument("--position", nargs="+", help="GK DEF MID FWD. Default MID FWD.")
    rec.add_argument("--min-minutes", type=int, default=270)
    rec.add_argument("--max-age", type=int)
    rec.add_argument("--max-price", type=float)
    rec.add_argument("--labels", type=int, default=12, help="How many players to name.")
    rec.add_argument("--highlight", nargs="+", help="Name these players instead.")

    val = common(sub.add_parser("value", help="FPL price against expected production."))
    val.add_argument("--min-minutes", type=int, default=180)
    val.add_argument("--max-price", type=float)
    val.add_argument(
        "--include-unavailable", action="store_true",
        help="Keep injured and suspended players in.",
    )

    pre = common(
        sub.add_parser("press", help="PPDA against xG conceded — defensive style.")
    )
    pre.add_argument("--highlight", nargs="+", help="Clubs to pick out.")

    sho = common(sub.add_parser("shots", help="Shot map for one match."))
    sho.add_argument(
        "--match", default="latest",
        help="Understat match id, a StatsBomb match id, or 'latest'.",
    )
    sho.add_argument(
        "--source", default="understat", choices=("understat", "statsbomb"),
        help="understat for this season; statsbomb for the open-data archive.",
    )

    sub.add_parser("table", help="Print the luck table as text.")

    fix = sub.add_parser(
        "fixtures", help="Upcoming matches with kick-off times and referees."
    )
    fix.add_argument("--next", type=int, default=10, help="How many to show.")

    clear = sub.add_parser("clear-cache", help="Drop cached API responses.")
    clear.add_argument(
        "source", nargs="?",
        choices=("understat", "fpl", "football_data"),
        help="Only this source. Default: all.",
    )

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
