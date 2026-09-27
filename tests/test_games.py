"""The other eight games: their rule entries, and the four shapes beyond plain pick.

Every value asserted here comes from that game's own page on
loterias.caixa.gov.br, read 2026-09-26, and each test names what the page says.
Draws come from the recorded fixtures, so the shapes are exercised against
responses the endpoint really sent.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from lotoconfere.core.check import check_bet, column_combinations
from lotoconfere.core.errors import InvalidBetError, InvalidDrawError
from lotoconfere.core.models import Bet, Draw, PrizeTier, Source
from lotoconfere.core.rules import (
    DIA_DE_SORTE,
    DUPLA_SENA,
    GAMES,
    LOTOFACIL,
    LOTOMANIA,
    MAIS_MILIONARIA,
    QUINA,
    SUPER_SETE,
    TIMEMANIA,
    Shape,
    rules_for,
    validate_bet,
    validate_draw,
)
from lotoconfere.source import caixa

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_draw(game):
    """The recorded latest contest for a game, parsed."""
    payload = json.loads((FIXTURES / f"caixa_{game}_latest.json").read_bytes())
    return caixa.parse(payload, game)


def labels(result):
    return [t.label for t in result.tiers]


# --- the rule table ---------------------------------------------------------


def test_all_nine_games_are_in_the_table():
    assert len(GAMES) == 9


@pytest.mark.parametrize("key", sorted(GAMES))
def test_every_game_cites_the_page_its_values_came_from(key):
    rules = GAMES[key]
    assert rules.source_url.startswith("https://loterias.caixa.gov.br/")
    assert rules.verified_on <= date.today()
    assert rules.tiers, "a game with no prize tiers would silently never pay"


@pytest.mark.parametrize("key", sorted(GAMES))
def test_every_faixa_is_numbered_the_way_caixa_numbers_them(key):
    # The faixa is the join key between the rule table and the prize table.
    assert [t.faixa for t in GAMES[key].tiers] == list(range(1, len(GAMES[key].tiers) + 1))


def test_lotofacil_matches_its_page():
    # "marque entre 15 e 20 numeros dentre os 25"; "acertar 11, 12, 13, 14 ou 15".
    assert (LOTOFACIL.first_number, LOTOFACIL.last_number) == (1, 25)
    assert LOTOFACIL.drawn_count == 15
    assert LOTOFACIL.bet_sizes == tuple(range(15, 21))
    assert tuple(t.hits for t in LOTOFACIL.tiers) == (15, 14, 13, 12, 11)


def test_quina_matches_its_page():
    # "Marque de 5 a 15 numeros dentre os 80"; "acertadores de 2, 3, 4 ou 5".
    assert (QUINA.first_number, QUINA.last_number) == (1, 80)
    assert QUINA.drawn_count == 5
    assert QUINA.bet_sizes == tuple(range(5, 16))
    assert tuple(t.hits for t in QUINA.tiers) == (5, 4, 3, 2)


def test_lotomania_matches_its_page():
    # "marque 50 numeros"; "acertos de 20, 19, 18, 17, 16, 15 ou nenhum numero".
    assert (LOTOMANIA.first_number, LOTOMANIA.last_number) == (0, 99)
    assert LOTOMANIA.drawn_count == 20
    assert LOTOMANIA.bet_sizes == (50,)
    assert tuple(t.hits for t in LOTOMANIA.tiers) == (20, 19, 18, 17, 16, 15, 0)


def test_dupla_sena_matches_its_page():
    # "marque de 6 a 15 numeros dentre os 50"; "3, 4, 5 ou 6 no primeiro e/ou segundo".
    assert (DUPLA_SENA.first_number, DUPLA_SENA.last_number) == (1, 50)
    assert DUPLA_SENA.bet_sizes == tuple(range(6, 16))
    assert len(DUPLA_SENA.tiers) == 8
    assert [t.draw for t in DUPLA_SENA.tiers] == [0, 0, 0, 0, 1, 1, 1, 1]


def test_timemania_matches_its_page():
    # "marque dez numeros entre os oitenta e um Time do Coracao"; "de tres a sete".
    assert (TIMEMANIA.first_number, TIMEMANIA.last_number) == (1, 80)
    assert TIMEMANIA.drawn_count == 7
    assert TIMEMANIA.bet_sizes == (10,)
    assert tuple(t.hits for t in TIMEMANIA.tiers if t.hits is not None) == (7, 6, 5, 4, 3)
    assert TIMEMANIA.tiers[-1].extra is True


def test_dia_de_sorte_matches_its_page():
    # "Marque de 7 a 15 numeros dentre os 31 e mais 1 Mes de Sorte".
    assert (DIA_DE_SORTE.first_number, DIA_DE_SORTE.last_number) == (1, 31)
    assert DIA_DE_SORTE.bet_sizes == tuple(range(7, 16))
    assert tuple(t.hits for t in DIA_DE_SORTE.tiers if t.hits is not None) == (7, 6, 5, 4)
    assert DIA_DE_SORTE.tiers[-1].extra is True


def test_super_sete_matches_its_page():
    # "7 colunas com 10 numeros (de 0 a 9)"; "totalizando 21 numeros no maximo".
    assert (SUPER_SETE.first_number, SUPER_SETE.last_number) == (0, 9)
    assert SUPER_SETE.column_count == 7
    assert SUPER_SETE.bet_sizes == tuple(range(7, 22))
    assert tuple(t.hits for t in SUPER_SETE.tiers) == (7, 6, 5, 4, 3)


def test_mais_milionaria_matches_its_page():
    # "6 numeros entre 1 e 50"; "2 trevos entre 1 e 6"; ten faixas.
    assert (MAIS_MILIONARIA.first_number, MAIS_MILIONARIA.last_number) == (1, 50)
    assert (MAIS_MILIONARIA.clover_first, MAIS_MILIONARIA.clover_last) == (1, 6)
    assert MAIS_MILIONARIA.clovers_drawn == 2
    assert len(MAIS_MILIONARIA.tiers) == 10


# --- plain pick, the other three --------------------------------------------


def test_a_lotofacil_bet_is_checked_against_a_real_draw():
    draw = fixture_draw("lotofacil")
    bet = Bet(game="lotofacil", numbers=draw.numbers)
    result = check_bet(bet, draw)
    assert result.hit_count == 15
    assert labels(result) == ["15 acertos"]


def test_an_expanded_lotofacil_bet_wins_several_tiers():
    draw = fixture_draw("lotofacil")
    extra = [n for n in range(1, 26) if n not in draw.numbers][:1]
    bet = Bet(game="lotofacil", numbers=tuple(sorted(draw.numbers + tuple(extra))))
    result = check_bet(bet, draw)
    # 16 numbers, all 15 drawn among them: one 15 and fifteen 14s.
    assert [(t.label, t.combinations) for t in result.tiers] == [
        ("15 acertos", 1),
        ("14 acertos", 15),
    ]


def test_hitting_nothing_in_lotomania_is_a_prize_tier():
    draw = fixture_draw("lotomania")
    missed = [n for n in range(100) if n not in draw.numbers][:50]
    result = check_bet(Bet(game="lotomania", numbers=tuple(missed)), draw)
    assert result.hit_count == 0
    assert labels(result) == ["0 acertos"]
    assert result.won is True  # zero hits pays, and must not read as a loss


def test_a_quina_bet_below_the_paying_tiers_wins_nothing():
    draw = fixture_draw("quina")
    missed = tuple(n for n in range(1, 81) if n not in draw.numbers)[:5]
    result = check_bet(Bet(game="quina", numbers=missed), draw)
    assert result.tiers == ()


# --- Dupla Sena: two draws ---------------------------------------------------


def test_dupla_sena_is_checked_against_both_draws():
    draw = fixture_draw("duplasena")
    assert draw.second_numbers is not None
    bet = Bet(game="duplasena", numbers=draw.numbers)
    result = check_bet(bet, draw)

    assert result.hit_counts[0] == 6
    assert [m.label for m in result.matches] == ["1o sorteio", "2o sorteio"]
    assert labels(result) == ["6 acertos (1o sorteio)"]


def test_a_dupla_sena_bet_can_win_in_the_second_draw_alone():
    draw = fixture_draw("duplasena")
    assert draw.second_numbers is not None
    result = check_bet(Bet(game="duplasena", numbers=draw.second_numbers), draw)
    assert result.hit_counts[1] == 6
    assert labels(result) == ["6 acertos (2o sorteio)"]


def test_a_dupla_sena_draw_without_its_second_half_is_rejected():
    draw = fixture_draw("duplasena")
    broken = Draw(
        game=draw.game,
        contest=draw.contest,
        drawn_on=draw.drawn_on,
        numbers=draw.numbers,
        source=draw.source,
        second_numbers=None,
    )
    with pytest.raises(InvalidDrawError, match="segundo sorteio"):
        validate_draw(broken)


# --- Timemania and Dia de Sorte: one extra field -----------------------------


def test_the_team_is_matched_separately_from_the_numbers():
    draw = fixture_draw("timemania")
    assert draw.extra is not None
    missed = tuple(n for n in range(1, 81) if n not in draw.numbers)[:10]
    result = check_bet(Bet(game="timemania", numbers=missed, extra=draw.extra), draw)
    assert result.hit_count == 0
    assert result.extra_matched is True
    assert labels(result) == ["Time do Coracao"]


def test_the_padding_caixa_sends_around_a_team_name_does_not_lose_the_match():
    # Caixa returns "CRB              /AL"; a bet saying "CRB /AL" is the same team.
    draw = fixture_draw("timemania")
    assert draw.extra is not None
    tidy = " ".join(draw.extra.split()).lower()
    missed = tuple(n for n in range(1, 81) if n not in draw.numbers)[:10]
    result = check_bet(Bet(game="timemania", numbers=missed, extra=tidy), draw)
    assert result.extra_matched is True


def test_a_wrong_team_matches_nothing():
    draw = fixture_draw("timemania")
    missed = tuple(n for n in range(1, 81) if n not in draw.numbers)[:10]
    result = check_bet(Bet(game="timemania", numbers=missed, extra="Time Inexistente"), draw)
    assert result.extra_matched is False
    assert result.tiers == ()


def test_the_month_is_matched_separately_in_dia_de_sorte():
    draw = fixture_draw("diadesorte")
    assert draw.extra is not None
    bet = Bet(game="diadesorte", numbers=draw.numbers, extra=draw.extra)
    result = check_bet(bet, draw)
    assert result.hit_count == 7
    assert labels(result) == ["7 acertos", "Mes da Sorte"]


def test_a_bet_on_a_game_with_an_extra_must_carry_it():
    with pytest.raises(InvalidBetError, match="Mes da Sorte"):
        validate_bet(Bet(game="diadesorte", numbers=(1, 2, 3, 4, 5, 6, 7)))


def test_a_draw_missing_its_extra_is_rejected():
    draw = fixture_draw("diadesorte")
    broken = Draw(
        game=draw.game,
        contest=draw.contest,
        drawn_on=draw.drawn_on,
        numbers=draw.numbers,
        source=draw.source,
        extra=None,
    )
    with pytest.raises(InvalidDrawError, match="Mes da Sorte"):
        validate_draw(broken)


# --- +Milionaria: tiers are pairs --------------------------------------------


def test_the_top_tier_needs_the_numbers_and_both_trevos():
    draw = fixture_draw("maismilionaria")
    bet = Bet(game="maismilionaria", numbers=draw.numbers, clovers=draw.clovers)
    result = check_bet(bet, draw)
    assert result.hit_count == 6
    assert result.clovers_matched == 2
    assert labels(result) == ["6 acertos + 2 trevos"]


def test_the_same_numbers_with_no_trevos_fall_to_the_second_tier():
    draw = fixture_draw("maismilionaria")
    wrong = tuple(c for c in range(1, 7) if c not in draw.clovers)[:2]
    bet = Bet(game="maismilionaria", numbers=draw.numbers, clovers=wrong)
    result = check_bet(bet, draw)
    assert result.clovers_matched == 0
    assert labels(result) == ["6 acertos + 1 ou nenhum trevo"]


def test_two_numbers_and_one_trevo_is_the_smallest_prize():
    draw = fixture_draw("maismilionaria")
    misses = tuple(n for n in range(1, 51) if n not in draw.numbers)[:4]
    bet = Bet(
        game="maismilionaria",
        numbers=tuple(sorted(draw.numbers[:2] + misses)),
        clovers=(draw.clovers[0], next(c for c in range(1, 7) if c not in draw.clovers)),
    )
    result = check_bet(bet, draw)
    assert (result.hit_count, result.clovers_matched) == (2, 1)
    assert labels(result) == ["2 acertos + 1 trevo"]


def test_two_numbers_and_no_trevo_pays_nothing():
    draw = fixture_draw("maismilionaria")
    misses = tuple(n for n in range(1, 51) if n not in draw.numbers)[:4]
    wrong = tuple(c for c in range(1, 7) if c not in draw.clovers)[:2]
    bet = Bet(
        game="maismilionaria",
        numbers=tuple(sorted(draw.numbers[:2] + misses)),
        clovers=wrong,
    )
    assert check_bet(bet, draw).tiers == ()


@pytest.mark.parametrize(
    ("clovers", "match"),
    [((1,), "trevos"), ((1, 1), "repetidos"), ((1, 9), "trevos vão de")],
)
def test_a_bad_trevo_selection_is_refused(clovers, match):
    with pytest.raises(InvalidBetError, match=match):
        validate_bet(Bet(game="maismilionaria", numbers=(1, 2, 3, 4, 5, 6), clovers=clovers))


def test_a_draw_with_the_wrong_number_of_trevos_is_rejected():
    draw = fixture_draw("maismilionaria")
    broken = Draw(
        game=draw.game,
        contest=draw.contest,
        drawn_on=draw.drawn_on,
        numbers=draw.numbers,
        source=draw.source,
        clovers=(3,),
    )
    with pytest.raises(InvalidDrawError, match="trevos"):
        validate_draw(broken)


def test_a_trevo_outside_the_range_is_rejected():
    draw = fixture_draw("maismilionaria")
    broken = Draw(
        game=draw.game,
        contest=draw.contest,
        drawn_on=draw.drawn_on,
        numbers=draw.numbers,
        source=draw.source,
        clovers=(3, 99),
    )
    with pytest.raises(InvalidDrawError, match="trevo fora"):
        validate_draw(broken)


# --- Super Sete: position is the meaning -------------------------------------


def test_a_super_sete_draw_keeps_its_column_order_and_its_repeats():
    draw = fixture_draw("supersete")
    # Contest 903 drew 9,2,4,7,5,5,2 -- two 5s and two 2s, in column order.
    assert draw.numbers == (9, 2, 4, 7, 5, 5, 2)
    assert len(set(draw.numbers)) < len(draw.numbers)


def test_matching_every_column_wins_the_top_tier():
    draw = fixture_draw("supersete")
    bet = Bet(game="supersete", columns=tuple((digit,) for digit in draw.numbers))
    result = check_bet(bet, draw)
    assert result.hit_count == 7
    assert labels(result) == ["7 acertos"]


def test_the_right_digit_in_the_wrong_column_is_not_a_hit():
    # The whole point of the shape: 9 belongs to column 1, nowhere else.
    draw = fixture_draw("supersete")
    shifted = tuple((digit,) for digit in (draw.numbers[1:] + draw.numbers[:1]))
    result = check_bet(Bet(game="supersete", columns=shifted), draw)
    assert result.hit_count < 7


def test_an_expanded_super_sete_bet_counts_every_embedded_bet():
    draw = fixture_draw("supersete")
    # Two digits in the first column, one of them right; single right digit elsewhere.
    wrong = next(d for d in range(10) if d != draw.numbers[0])
    columns = ((draw.numbers[0], wrong), *tuple((d,) for d in draw.numbers[1:]))
    result = check_bet(Bet(game="supersete", columns=columns), draw)
    # Two embedded bets: one hits all seven, the other hits six.
    assert [(t.label, t.combinations) for t in result.tiers] == [("7 acertos", 1), ("6 acertos", 1)]


def test_the_column_breakdown_sums_to_every_embedded_bet():
    # Marking 2 in each of 7 columns is 2^7 single-pick bets, however they land.
    counts = column_combinations((True, True, False, True, False, True, True), (2,) * 7)
    assert sum(counts) == 2**7


@pytest.mark.parametrize(
    ("columns", "match"),
    [
        (((1,), (2,), (3,)), "colunas"),
        # 16 marks puts the bet in the 15-21 band, where every column needs at
        # least 2 -- so a single-digit column is out of band, not merely small.
        (((1,), (1, 2, 3), (1, 2, 3), (1, 2, 3), (1, 2), (1, 2), (1, 2)), "cada coluna leva"),
        (((1, 1), (1, 2), (1, 2), (1, 2), (1, 2), (1, 2), (1, 2)), "repetidos"),
        (((1, 99), (1, 2), (1, 2), (1, 2), (1, 2), (1, 2), (1, 2)), "números vão de"),
    ],
)
def test_a_bad_super_sete_bet_is_refused(columns, match):
    with pytest.raises(InvalidBetError, match=match):
        validate_bet(Bet(game="supersete", columns=columns))


def test_a_super_sete_bet_with_too_many_marks_is_refused():
    with pytest.raises(InvalidBetError, match="de 7 a 21"):
        validate_bet(Bet(game="supersete", columns=tuple((0, 1, 2, 3) for _ in range(7))))


# --- shared ------------------------------------------------------------------


def test_the_prize_for_a_tier_comes_from_its_own_faixa():
    draw = fixture_draw("duplasena")
    assert draw.prizes is not None
    # Faixa 5 is "6 acertos" in the SECOND draw; nothing may confuse it with faixa 1.
    second_top = next(p for p in draw.prizes if p.faixa == 5)
    assert second_top.label.startswith("6 acertos")


def test_a_tier_result_carries_the_published_prize():
    draw = fixture_draw("quina")
    prizes = (
        PrizeTier(faixa=1, label="5 acertos", winners=1, amount=Decimal("1000000.00")),
        PrizeTier(faixa=2, label="4 acertos", winners=10, amount=Decimal("5000.00")),
        PrizeTier(faixa=3, label="3 acertos", winners=100, amount=Decimal("100.00")),
        PrizeTier(faixa=4, label="2 acertos", winners=1000, amount=Decimal("3.00")),
    )
    priced = Draw(
        game=draw.game,
        contest=draw.contest,
        drawn_on=draw.drawn_on,
        numbers=draw.numbers,
        source=Source.CAIXA,
        prizes=prizes,
    )
    result = check_bet(Bet(game="quina", numbers=draw.numbers), priced)
    assert result.tiers[0].prize == Decimal("1000000.00")


@pytest.mark.parametrize("key", sorted(GAMES))
def test_every_shape_in_the_table_has_a_checker(key):
    assert GAMES[key].shape in set(Shape)


def test_an_unknown_game_is_refused():
    with pytest.raises(Exception, match="jogo desconhecido"):
        rules_for("lotogato")


def test_the_mirror_splits_dupla_senas_two_draws_out_of_one_list():
    # The mirror returns all twelve numbers in `dezenas`; Caixa has a field for
    # the second draw. Same contest, same two draws, either way.
    from lotoconfere.source import mirror

    payload = json.loads((FIXTURES / "mirror_duplasena_latest.json").read_bytes())
    from_mirror = mirror.parse(payload, "duplasena")
    from_caixa = fixture_draw("duplasena")
    assert from_mirror.numbers == from_caixa.numbers
    assert from_mirror.second_numbers == from_caixa.second_numbers


def test_an_extra_that_is_absent_on_either_side_never_matches():
    # Reachable only by calling directly: validation already demands both. The
    # guard stays because a missing team must read as "no", never as a match.
    from lotoconfere.core.check import _same_extra

    assert _same_extra(None, "CRB /AL") is False
    assert _same_extra("CRB /AL", None) is False


def test_a_clover_game_skips_tiers_that_are_not_pairs():
    # Every +Milionaria faixa is a (hits, trevos) pair today. If one ever is not
    # -- an extra-style tier, say -- it must be skipped, not read as zero trevos.
    from dataclasses import replace

    from lotoconfere.core.check import _check_clovers
    from lotoconfere.core.rules import TierSpec

    draw = fixture_draw("maismilionaria")
    doctored = replace(
        MAIS_MILIONARIA,
        tiers=(*MAIS_MILIONARIA.tiers, TierSpec(faixa=11, label="Alguma coisa", extra=True)),
    )
    bet = Bet(game="maismilionaria", numbers=draw.numbers, clovers=draw.clovers)
    result = _check_clovers(bet, draw, doctored)
    assert [t.label for t in result.tiers] == ["6 acertos + 2 trevos"]


# --- Lotomania's Aposta-Espelho ----------------------------------------------


def test_the_mirror_bet_is_the_other_fifty_numbers():
    from lotoconfere.core.rules import mirror_bet

    original = Bet(game="lotomania", numbers=tuple(range(50)))
    mirrored = mirror_bet(original)
    assert mirrored.numbers == tuple(range(50, 100))
    assert not set(original.numbers) & set(mirrored.numbers)
    assert len(mirrored.numbers) == 50


def test_mirroring_twice_gives_the_original_bet_back():
    from lotoconfere.core.rules import mirror_bet

    original = Bet(game="lotomania", numbers=tuple(range(0, 100, 2)))
    assert mirror_bet(mirror_bet(original)) == original


def test_the_mirror_of_a_real_draw_hits_what_the_original_missed():
    from lotoconfere.core.rules import mirror_bet

    draw = fixture_draw("lotomania")
    missed = tuple(n for n in range(100) if n not in draw.numbers)[:50]
    original = check_bet(Bet(game="lotomania", numbers=missed), draw)
    mirrored = check_bet(mirror_bet(Bet(game="lotomania", numbers=missed)), draw)
    # Every drawn number is in one bet or the other, so the hits add to twenty.
    assert original.hit_count + mirrored.hit_count == 20


@pytest.mark.parametrize("game", ["megasena", "quina", "lotofacil"])
def test_only_lotomania_has_a_mirror_bet(game):
    from lotoconfere.core.rules import mirror_bet

    rules = GAMES[game]
    numbers = tuple(range(rules.first_number, rules.first_number + rules.minimum_bet_size))
    with pytest.raises(InvalidBetError, match="aposta-espelho"):
        mirror_bet(Bet(game=game, numbers=numbers))


def test_an_unplayable_bet_has_no_mirror():
    from lotoconfere.core.rules import mirror_bet

    with pytest.raises(InvalidBetError):
        mirror_bet(Bet(game="lotomania", numbers=(1, 2, 3)))
