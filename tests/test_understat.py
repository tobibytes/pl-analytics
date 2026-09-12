"""Understat feed quirks that are easy to reintroduce."""

from football.sources.understat import _ratio, _text


def test_html_entities_are_unescaped():
    # Understat serves names HTML-escaped. Left alone, "Dara O&#039;Shea"
    # reaches the chart verbatim and matches no FPL record.
    assert _text("Dara O&#039;Shea") == "Dara O'Shea"
    assert _text("Gro&szlig;") == "Groß"
    assert _text("Nico O&#039;Reilly") == "Nico O'Reilly"


def test_text_passes_through_non_strings():
    assert _text(None) is None
    assert _text(7) == 7


def test_ppda_is_a_ratio_of_counts():
    assert _ratio({"att": 355, "def": 11}) == 355 / 11


def test_ppda_with_no_defensive_actions_is_nan():
    # A team can finish a match with zero qualifying actions; that must not
    # raise, and must not silently become zero (which would read as the most
    # intense press in the league).
    assert _ratio({"att": 10, "def": 0}) != _ratio({"att": 10, "def": 0})
