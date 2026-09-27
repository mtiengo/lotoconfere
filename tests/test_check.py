"""The checker, against Caixa's own worked numbers.

The expanded-bet arithmetic is pinned to the table on
https://loterias.caixa.gov.br/Paginas/Mega-Sena.aspx (read 2026-09-26), which
lists what each bet size costs in whole six-number bets: 7 numbers is 7 bets,
10 is 210, 15 is 5.005, 20 is 38.760. A breakdown that agrees only with itself
proves nothing, so that column is the oracle here.
"""

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lotoconfere.core.check import check_bet, embedded_combinations
from lotoconfere.core.models import Bet, Draw, PrizeTier, Source

# Mega-Sena 3062, as Caixa returned it on 2026-09-26.
DRAWN = (5, 9, 11, 17, 18, 38)

# "Quantidade de numeros" -> "Quantidade de Apostas", straight off Caixa's page.
BETS_PER_SIZE = {
    6: 1,
    7: 7,
    8: 28,
    9: 84,
    10: 210,
    11: 462,
    12: 924,
    13: 1_716,
    14: 3_003,
    15: 5_005,
    16: 8_008,
    17: 12_376,
    18: 18_564,
    19: 27_132,
    20: 38_760,
}


def a_draw(prizes=None, numbers=DRAWN):
    return Draw(
        game="megasena",
        contest=3062,
        drawn_on=date(2026, 9, 24),
        numbers=numbers,
        source=Source.CAIXA,
        prizes=prizes,
    )


def a_bet(numbers):
    return Bet(game="megasena", numbers=tuple(numbers))


def misses(count):
    """Numbers that cannot be in DRAWN, for padding a bet out to a size."""
    return [n for n in range(50, 61) if n not in DRAWN][:count]


def test_a_plain_bet_that_hit_everything():
    result = check_bet(a_bet(DRAWN), a_draw())
    assert result.hit_count == 6
    assert result.matched == tuple(sorted(DRAWN))
    assert [(t.label, t.combinations) for t in result.tiers] == [("6 acertos", 1)]


def test_a_plain_bet_that_hit_nothing_wins_nothing():
    result = check_bet(a_bet(misses(6)), a_draw())
    assert result.hit_count == 0
    assert result.tiers == ()
    assert result.won is False


@pytest.mark.parametrize(
    ("hits", "expected"),
    [(4, [("4 acertos", 1)]), (5, [("5 acertos", 1)]), (6, [("6 acertos", 1)])],
)
def test_a_plain_bet_reaches_exactly_one_tier(hits, expected):
    numbers = list(DRAWN[:hits]) + misses(6 - hits)
    result = check_bet(a_bet(numbers), a_draw())
    assert result.hit_count == hits
    assert [(t.label, t.combinations) for t in result.tiers] == expected


def test_three_hits_pays_nothing_but_is_still_counted():
    # The count is reported whether or not it won; the tiers explain it.
    result = check_bet(a_bet(list(DRAWN[:3]) + misses(3)), a_draw())
    assert result.hit_count == 3
    assert result.tiers == ()


def test_an_expanded_bet_wins_several_tiers_at_once():
    # Seven numbers, all six drawn among them: one sena, and the seventh number
    # replaces each drawn one in turn for six quinas.
    result = check_bet(a_bet(list(DRAWN) + misses(1)), a_draw())
    assert result.hit_count == 6
    assert [(t.label, t.combinations) for t in result.tiers] == [("6 acertos", 1), ("5 acertos", 6)]


def test_an_expanded_bet_with_five_hits():
    # Eight numbers, five of them drawn: C(5,5)*C(3,1) quinas, C(5,4)*C(3,2) quadras.
    result = check_bet(a_bet(list(DRAWN[:5]) + misses(3)), a_draw())
    assert [(t.label, t.combinations) for t in result.tiers] == [
        ("5 acertos", 3),
        ("4 acertos", 15),
    ]


@pytest.mark.parametrize("size", sorted(BETS_PER_SIZE))
def test_a_full_hit_breakdown_sums_to_caixas_bet_count(size):
    """Every embedded six-number bet must land in some tier, and Caixa counts them."""
    total = sum(
        embedded_combinations(hits=6, bet_size=size, minimum_size=6, tier_hits=j) for j in range(7)
    )
    assert total == BETS_PER_SIZE[size]


def test_the_prize_comes_from_the_contests_own_table():
    prizes = (
        PrizeTier(faixa=1, label="6 acertos", winners=1, amount=Decimal("120000000.00")),
        PrizeTier(faixa=2, label="5 acertos", winners=100, amount=Decimal("45000.50")),
        PrizeTier(faixa=3, label="4 acertos", winners=9000, amount=Decimal("900.25")),
    )
    result = check_bet(a_bet(list(DRAWN) + misses(1)), a_draw(prizes=prizes))
    assert [t.prize for t in result.tiers] == [Decimal("120000000.00"), Decimal("45000.50")]


def test_an_unpublished_prize_table_reads_as_unknown_not_zero():
    result = check_bet(a_bet(DRAWN), a_draw(prizes=None))
    assert result.tiers[0].prize is None
    assert result.draw.prize_table_published is False


def test_a_tier_missing_from_the_table_is_unknown_not_zero():
    # A published table that simply has no line for this tier.
    prizes = (PrizeTier(faixa=3, label="4 acertos", winners=9000, amount=Decimal("900.25")),)
    result = check_bet(a_bet(DRAWN), a_draw(prizes=prizes))
    assert result.tiers[0].prize is None


def test_a_bet_and_a_draw_from_different_games_is_refused():
    with pytest.raises(ValueError, match=r"quina|megasena|sorteio"):
        check_bet(Bet(game="quina", numbers=DRAWN), a_draw())


# --- invariants ----------------------------------------------------------------


@given(
    bet_size=st.integers(min_value=6, max_value=20),
    hits=st.integers(min_value=0, max_value=6),
)
def test_the_breakdown_always_sums_to_every_embedded_bet(bet_size, hits):
    from math import comb

    hits = min(hits, bet_size)
    total = sum(
        embedded_combinations(hits=hits, bet_size=bet_size, minimum_size=6, tier_hits=j)
        for j in range(7)
    )
    assert total == comb(bet_size, 6)


@given(index=st.integers(min_value=0, max_value=14))
def test_hits_never_exceed_the_bet_or_the_draw(index):
    size = sorted(BETS_PER_SIZE)[index]
    numbers = sorted(set(DRAWN) | set(range(20, 20 + size)))[:size]
    result = check_bet(a_bet(numbers), a_draw())
    assert result.hit_count <= min(size, len(DRAWN))
    assert all(t.combinations >= 1 for t in result.tiers)
