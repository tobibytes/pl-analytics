"""The name-matching cascade, which is where a silent bug would hurt most.

A bad match puts one player's xG next to another's price. A missed match drops
a player from the chart with no error at all -- and the players who go missing
are not random, they skew towards non-English names. So the cases below are
the real ones observed in the 2026/27 feeds, kept as a regression net.
"""

from football.matching import match_players, normalise, strip_accents, tokens


class TestNormalise:
    def test_strips_combining_accents(self):
        assert strip_accents("Álvaro Rodríguez") == "Alvaro Rodriguez"
        assert strip_accents("Caoimhín Kelleher") == "Caoimhin Kelleher"

    def test_strips_letters_nfkd_cannot_decompose(self):
        # These are distinct letters, not base + combining mark, so accent
        # stripping alone leaves them untouched and the join fails.
        assert strip_accents("Đorđe Petrović") == "Dorde Petrovic"
        assert strip_accents("Martin Ødegaard") == "Martin Odegaard"
        assert strip_accents("Łukasz") == "Lukasz"

    def test_elides_apostrophes_rather_than_spacing_them(self):
        # "nott m forest" would match nothing.
        assert normalise("Nott'm Forest") == "nottm forest"

    def test_case_and_punctuation(self):
        assert normalise("Brighton & Hove Albion FC") == "brighton hove albion fc"
        assert tokens("Ao Tanaka") == tokens("Tanaka Ao")


class TestMatchPlayers:
    CLUB = {"a": "arsenal", "b": "chelsea"}

    def _match(self, left, right):
        return match_players(left, right)

    def test_exact_after_normalising(self):
        report = self._match(
            {"Martin Odegaard": "arsenal"}, {"Martin Ødegaard": "arsenal"}
        )
        assert report.matched == {"Martin Odegaard": "Martin Ødegaard"}

    def test_short_name_inside_legal_name(self):
        report = self._match(
            {"Alejandro Garnacho": "arsenal"},
            {"Alejandro Garnacho Ferreyra": "arsenal"},
        )
        assert report.matched["Alejandro Garnacho"] == "Alejandro Garnacho Ferreyra"

    def test_legal_name_inside_short_name(self):
        # The subset has to work in both directions: Understat is sometimes the
        # *longer* of the two.
        report = self._match(
            {"Iyenoma Destiny Udogie": "arsenal"}, {"Destiny Udogie": "arsenal"}
        )
        assert report.matched["Iyenoma Destiny Udogie"] == "Destiny Udogie"

    def test_reversed_name_order(self):
        report = self._match({"Ao Tanaka": "arsenal"}, {"Tanaka Ao": "arsenal"})
        assert report.matched["Ao Tanaka"] == "Tanaka Ao"

    def test_single_token_name_when_unambiguous(self):
        report = self._match(
            {"Evanilson": "arsenal"}, {"Francisco Evanilson de Lima Barbosa": "arsenal"}
        )
        assert report.matched["Evanilson"] == "Francisco Evanilson de Lima Barbosa"

    def test_ambiguous_single_token_is_refused_not_guessed(self):
        # Arsenal really do field three players called Gabriel. Guessing here
        # would attach one player's numbers to another's name.
        report = self._match(
            {"Gabriel": "arsenal"},
            {
                "Gabriel dos Santos Magalhães": "arsenal",
                "Gabriel Martinelli Silva": "arsenal",
                "Gabriel Fernando de Jesus": "arsenal",
            },
        )
        assert report.unmatched == ["Gabriel"]

    def test_elimination_resolves_once_namesakes_are_claimed(self):
        report = self._match(
            {
                "Gabriel Martinelli": "arsenal",
                "Gabriel Jesus": "arsenal",
                "Gabriel": "arsenal",
            },
            {
                "Gabriel Martinelli Silva": "arsenal",
                "Gabriel Fernando de Jesus": "arsenal",
                "Gabriel dos Santos Magalhães": "arsenal",
            },
        )
        assert report.matched["Gabriel"] == "Gabriel dos Santos Magalhães"
        assert not report.unmatched

    def test_transferred_player_found_league_wide(self):
        # Understat files a player under the club they played for; FPL under
        # the club that owns them now.
        report = self._match(
            {"Enzo Fernández": "chelsea"}, {"Enzo Fernández": "manchester city"}
        )
        assert report.matched["Enzo Fernández"] == "Enzo Fernández"
        assert any(k.endswith("-moved") for k in report.by_stage)

    def test_different_player_same_surname_is_refused(self):
        report = self._match(
            {"Mathis Cherki": "manchester city"}, {"Rayan Cherki": "manchester city"}
        )
        assert report.unmatched == ["Mathis Cherki"]

    def test_report_rate(self):
        report = self._match(
            {"A Player": "arsenal", "Ghost Person": "arsenal"},
            {"A Player": "arsenal"},
        )
        assert report.rate == 0.5
        assert "matched 1/2 (50%)" in report.summary()
