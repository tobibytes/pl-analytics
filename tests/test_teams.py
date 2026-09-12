"""Club-name reconciliation.

Joining three feeds on raw club strings drops rows silently -- a team simply
vanishes from a chart. These cover the normaliser, which is pure; the
league-aware resolution in ``team_key`` needs the current squad list and is
exercised by ``test_smoke.py`` instead.
"""

import pytest

from football.teams import ALIASES, normalise


@pytest.mark.parametrize(
    ("spelling", "expected"),
    [
        ("Arsenal FC", "arsenal"),
        ("AFC Bournemouth", "bournemouth"),
        ("Brighton & Hove Albion FC", "brighton hove albion"),
        ("Hull City AFC", "hull city"),
        ("Nott'm Forest", "nottm forest"),
        ("Tottenham Hotspur FC", "tottenham hotspur"),
        ("  Leeds   United  ", "leeds united"),
    ],
)
def test_normalise_strips_club_noise(spelling, expected):
    assert normalise(spelling) == expected


def test_aliases_are_stored_normalised():
    # An alias whose key or value is not already normalised can never fire.
    for key, value in ALIASES.items():
        assert normalise(key) == key, f"alias key {key!r} is not normalised"
        assert normalise(value) == value, f"alias value {value!r} is not normalised"
