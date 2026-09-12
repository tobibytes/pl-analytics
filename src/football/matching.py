"""Matching player names between Understat and FPL.

Understat uses the broadcast name; FPL uses the full legal name. Matching the
raw strings gets about 76% of the league and silently drops the rest, which
would quietly bias every scatter plot -- the players who go missing are not
random, they skew towards non-English names.

Six kinds of failure, five of them mechanical:

    Alvaro Rodríguez        / Álvaro Rodríguez                accents
    Djordje Petrovic        / Đorđe Petrović                  letters NFKD won't split
    Alejandro Garnacho      / Alejandro Garnacho Ferreyra     fuller legal name
    Iyenoma Destiny Udogie  / Destiny Udogie                  fuller *short* name
    Ao Tanaka               / Tanaka Ao                       name order
    Abduqodir Khusanov      / Abdukodir Khusanov              transliteration

And one that is not a name problem at all: **transfers**. Understat files a
player under the club they played those minutes for, FPL under the club that
owns them now, so Enzo Fernández is Chelsea in one feed and Man City in the
other. Club-restricted matching alone therefore cannot be the whole answer.

The cascade runs club-first because that is where a wrong match is least
likely -- roughly 30 candidates rather than 656 -- then falls back to a
league-wide pass under stricter rules to pick up the transfers. Confident
matches claim their candidate, so a genuinely ambiguous name like Arsenal's
"Gabriel" can still resolve once Martinelli and Jesus have been taken.

Anything still unresolved is reported, never guessed at.
"""

from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass, field

#: Below this, a fuzzy match is more likely to be two different players.
FUZZY_THRESHOLD = 0.85

#: Letters that are not a base letter plus a combining mark, so NFKD leaves
#: them intact and accent-stripping alone never reconciles the spellings.
TRANSLITERATE = str.maketrans(
    {
        "Đ": "D", "đ": "d", "Ð": "D", "ð": "d",
        "Ø": "O", "ø": "o", "Œ": "Oe", "œ": "oe",
        "Ł": "L", "ł": "l", "Þ": "Th", "þ": "th",
        "Æ": "Ae", "æ": "ae", "ß": "ss", "İ": "I", "ı": "i",
    }
)


def strip_accents(text: str) -> str:
    """"Đorđe Petrović" -> "Dorde Petrovic"."""
    decomposed = unicodedata.normalize("NFKD", text.translate(TRANSLITERATE))
    return "".join(c for c in decomposed if not unicodedata.combining(c))


#: Apostrophes are elided, not spaced -- "N'Golo" must normalise to the same
#: thing as "NGolo", and "n golo" would match neither. Same rule as
#: ``football.teams.normalise``; the two must not drift apart.
_ELIDED = "'\u2019\u02bc."


def normalise(name: str) -> str:
    """Accent-free, lowercase, punctuation-free, single-spaced."""
    text = strip_accents(name).lower()
    text = "".join(c for c in text if c not in _ELIDED)
    text = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    return " ".join(text.split())


def tokens(name: str) -> frozenset[str]:
    return frozenset(normalise(name).split())


@dataclass
class MatchReport:
    """How a join went, so the caller can be honest about coverage."""

    matched: dict[str, str] = field(default_factory=dict)
    unmatched: list[str] = field(default_factory=list)
    by_stage: dict[str, int] = field(default_factory=dict)

    @property
    def rate(self) -> float:
        total = len(self.matched) + len(self.unmatched)
        return len(self.matched) / total if total else 0.0

    def summary(self) -> str:
        stages = ", ".join(f"{k}={v}" for k, v in sorted(self.by_stage.items()))
        return (
            f"matched {len(self.matched)}/{len(self.matched) + len(self.unmatched)}"
            f" ({self.rate:.0%}) [{stages}]"
        )


def match_players(left: dict[str, str], right: dict[str, str]) -> MatchReport:
    """Match ``left`` names to ``right`` names.

    Both arguments map a player name to their club's ``team_key``. Returns the
    mapping from left name to right name, plus what could not be resolved.
    """
    by_club: dict[str, list[str]] = {}
    for name, club in right.items():
        by_club.setdefault(club, []).append(name)

    report = MatchReport()
    claimed: set[str] = set()
    pending: list[str] = []

    # Pass 1: within the club, against everything.
    for name, club in left.items():
        found, stage = _best(name, by_club.get(club, []))
        if found is None:
            pending.append(name)
        else:
            report.matched[name] = found
            claimed.add(found)
            report.by_stage[stage] = report.by_stage.get(stage, 0) + 1

    # Pass 2: within the club, but only against players nobody claimed. An
    # ambiguous name resolves once its namesakes are spoken for.
    still_pending: list[str] = []
    for name in pending:
        free = [c for c in by_club.get(left[name], []) if c not in claimed]
        found, stage = _best(name, free)
        if found is None:
            still_pending.append(name)
        else:
            report.matched[name] = found
            claimed.add(found)
            key = f"{stage}-elim"
            report.by_stage[key] = report.by_stage.get(key, 0) + 1

    # Pass 3: the transfers. League-wide, unclaimed only, and no fuzzy stage --
    # without the club to constrain it, spelling drift is too weak a signal.
    everyone = [n for n in right if n not in claimed]
    for name in still_pending:
        found, stage = _best(name, everyone, allow_fuzzy=False, require_full=True)
        if found is None:
            report.unmatched.append(name)
        else:
            report.matched[name] = found
            claimed.add(found)
            everyone.remove(found)
            key = f"{stage}-moved"
            report.by_stage[key] = report.by_stage.get(key, 0) + 1

    return report


def _best(
    name: str,
    candidates: list[str],
    allow_fuzzy: bool = True,
    require_full: bool = False,
) -> tuple[str | None, str]:
    """Run the cascade, most certain stage first.

    ``require_full`` drops the single-token and surname stages, which are only
    safe when the club has already narrowed the field.
    """
    if not candidates:
        return None, "no-candidates"

    target = normalise(name)
    lookup = {normalise(c): c for c in candidates}

    # 1. The same name once accents and punctuation are gone.
    if target in lookup:
        return lookup[target], "exact"

    target_tokens = tokens(name)

    # 2. One name's parts are contained in the other's, in any order. Covers
    #    "Garnacho" -> "Garnacho Ferreyra", "Iyenoma Destiny Udogie" ->
    #    "Destiny Udogie", and "Ao Tanaka" -> "Tanaka Ao". Two shared tokens
    #    minimum, so a lone surname cannot match a team-mate who shares it.
    if len(target_tokens) >= 2:
        subset = [
            c
            for c in candidates
            if target_tokens <= tokens(c) or tokens(c) <= target_tokens
        ]
        if len(subset) == 1:
            return subset[0], "subset"

    if require_full:
        return None, "none"

    # 3. A single-word name, appearing in exactly one squad member's name:
    #    "Evanilson" -> "Francisco Evanilson de Lima Barbosa".
    if len(target_tokens) == 1:
        unique = [c for c in candidates if target_tokens <= tokens(c)]
        if len(unique) == 1:
            return unique[0], "single"

    # 4. Surname plus first initial -- the usual shape of a broadcast name.
    surname = target.split()[-1]
    same_surname = [
        c
        for c in candidates
        if surname in tokens(c) and normalise(c).startswith(target[0])
    ]
    if len(same_surname) == 1:
        return same_surname[0], "surname"

    # 5. Spelling drift: transliteration, hyphens, dropped particles.
    if allow_fuzzy:
        close = difflib.get_close_matches(
            target, list(lookup), n=1, cutoff=FUZZY_THRESHOLD
        )
        if close:
            return lookup[close[0]], "fuzzy"

    return None, "none"
