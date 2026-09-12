"""Reconciling club names across sources.

The three sources disagree about what to call almost half the league:

    Understat          FPL             football-data.org
    Manchester United  Man Utd         Manchester United FC
    Tottenham          Spurs           Tottenham Hotspur FC
    Nottingham Forest  Nott'm Forest   Nottingham Forest FC
    Brighton           Brighton        Brighton & Hove Albion FC

Joining on the raw strings silently drops rows -- a team just goes missing
from a chart, which is much worse than an error. So everything joins on a
**key** produced here instead.

The set of clubs is taken from Understat at runtime rather than hard-coded, so
promotion and relegation need no edit. Only the irregular spellings below do,
and an unresolvable name raises rather than disappearing.
"""

from __future__ import annotations

import functools
import re

#: Spellings that no amount of normalising will reconcile, mapped to the
#: normalised form of the club's full name.
ALIASES = {
    "spurs": "tottenham",
    "man city": "manchester city",
    "man utd": "manchester united",
    "man united": "manchester united",
    "nottm forest": "nottingham forest",
    "wolves": "wolverhampton wanderers",
    "west brom": "west bromwich albion",
    "sheffield utd": "sheffield united",
    "west ham": "west ham united",
    "leicester": "leicester city",
    "norwich": "norwich city",
    "luton": "luton town",
}

#: Club-type suffixes and prefixes that carry no identifying information.
_NOISE = re.compile(r"\b(fc|afc|cf)\b")
#: Apostrophes are elided, not spaced: FPL writes "Nott'm Forest", and
#: "nott m forest" would match nothing.
_ELIDED = re.compile(r"[\u2019\u02bc\'.]+")
_PUNCT = re.compile(r"[^a-z0-9 ]+")


def normalise(name: str) -> str:
    """Lowercase, strip club-type noise and punctuation, collapse whitespace."""
    text = _ELIDED.sub("", name.lower())
    text = _PUNCT.sub(" ", text)
    text = _NOISE.sub(" ", text)
    return " ".join(text.split())


@functools.lru_cache(maxsize=1)
def _known() -> tuple[str, ...]:
    """The normalised full names of the clubs currently in the league.

    Imported lazily: ``teams`` is used by every project, and importing it must
    not force a network call at import time.
    """
    from .sources import understat

    data = understat.league_data()
    return tuple(
        sorted(normalise(understat._text(t["title"])) for t in data["teams"].values())
    )


class UnknownTeam(KeyError):
    """A club name that could not be matched to any team in the league."""

    def __init__(self, name: str, known: tuple[str, ...]):
        super().__init__(
            f"Could not match team name {name!r} to any club in the league.\n"
            f"Known: {', '.join(known)}\n"
            f"If this is a real club, add its spelling to football.teams.ALIASES."
        )


def team_key(name: str) -> str:
    """Map any source's spelling of a club to a stable join key.

    Resolution order: exact match, then the alias table, then a prefix match
    in either direction -- which covers "Hull" against "Hull City", "Leeds"
    against "Leeds United" and "Brighton" against "Brighton & Hove Albion".
    """
    text = normalise(name)
    known = _known()

    if text in known:
        return text

    aliased = ALIASES.get(text)
    if aliased and aliased in known:
        return aliased

    matches = [k for k in known if k.startswith(text) or text.startswith(k)]
    if len(matches) == 1:
        return matches[0]

    raise UnknownTeam(name, known)


def add_team_key(frame, column: str = "team"):
    """Add a ``team_key`` column to a DataFrame, for joining across sources."""
    result = frame.copy()
    result["team_key"] = result[column].map(team_key)
    return result
