"""The rule table, checked against the page its values came from.

Every number asserted here appears on
https://loterias.caixa.gov.br/Paginas/Mega-Sena.aspx (read 2026-09-26):
"marque de 6 a 20 numeros", "os 6 numeros sorteados", "acertar 4 ou 5 numeros
dentre os 60 disponiveis".
"""

from datetime import date

import pytest

from lotoconfere.core.errors import InvalidBetError, InvalidDrawError, UnknownGameError
from lotoconfere.core.models import Bet, Draw, Source
from lotoconfere.core.rules import MEGA_SENA, rules_for, validate_bet, validate_draw


def a_draw(numbers=(5, 9, 11, 17, 18, 38), contest=3062, game="megasena"):
    return Draw(
        game=game,
        contest=contest,
        drawn_on=date(2026, 9, 24),
        numbers=numbers,
        source=Source.CAIXA,
    )


def test_mega_sena_matches_caixas_page():
    assert MEGA_SENA.first_number == 1
    assert MEGA_SENA.last_number == 60
    assert MEGA_SENA.drawn_count == 6
    assert MEGA_SENA.bet_sizes == tuple(range(6, 21))
    assert MEGA_SENA.minimum_bet_size == 6
    assert tuple(t.hits for t in MEGA_SENA.tiers) == (6, 5, 4)


def test_every_entry_cites_where_its_values_came_from():
    # A value nobody can re-check is a value that quietly goes stale.
    assert MEGA_SENA.source_url.startswith("https://loterias.caixa.gov.br/")
    assert MEGA_SENA.verified_on <= date.today()


def test_an_unknown_game_is_refused_not_guessed():
    with pytest.raises(UnknownGameError):
        rules_for("lotogato")


@pytest.mark.parametrize("size", [6, 7, 12, 20])
def test_playable_bet_sizes_are_accepted(size):
    validate_bet(Bet(game="megasena", numbers=tuple(range(1, size + 1))))


@pytest.mark.parametrize("size", [5, 21])
def test_unplayable_bet_sizes_are_refused(size):
    with pytest.raises(InvalidBetError, match="numeros"):
        validate_bet(Bet(game="megasena", numbers=tuple(range(1, size + 1))))


def test_a_repeated_number_is_refused():
    with pytest.raises(InvalidBetError, match="repetidos"):
        validate_bet(Bet(game="megasena", numbers=(1, 2, 3, 4, 5, 5)))


@pytest.mark.parametrize("stray", [0, 61, -1])
def test_a_number_outside_the_range_is_refused(stray):
    with pytest.raises(InvalidBetError, match="numeros vao de"):
        validate_bet(Bet(game="megasena", numbers=(1, 2, 3, 4, 5, stray)))


def test_a_real_draw_validates():
    validate_draw(a_draw())


def test_a_draw_with_the_wrong_count_is_rejected_whole():
    with pytest.raises(InvalidDrawError, match="6 numeros"):
        validate_draw(a_draw(numbers=(5, 9, 11, 17, 18)))


def test_a_draw_with_a_repeated_number_is_rejected():
    with pytest.raises(InvalidDrawError, match="repetidos"):
        validate_draw(a_draw(numbers=(5, 9, 11, 17, 18, 18)))


def test_a_draw_out_of_range_is_rejected():
    with pytest.raises(InvalidDrawError, match="numeros vao de"):
        validate_draw(a_draw(numbers=(5, 9, 11, 17, 18, 61)))


def test_a_nonsense_contest_number_is_rejected():
    with pytest.raises(InvalidDrawError, match="concurso invalido"):
        validate_draw(a_draw(contest=0))


def test_a_draw_for_an_unknown_game_is_refused():
    with pytest.raises(UnknownGameError):
        validate_draw(a_draw(game="lotogato"))
