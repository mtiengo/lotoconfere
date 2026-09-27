"""The checker: one bet against one draw, hit count first, then the tiers.

One function per `Shape`, and the rule table says which. There is no per-game
branch here and there must not become one -- a game that seems to need one needs
a field in `GameRules`, or a shape it already fits.
"""

from decimal import Decimal
from math import comb

from lotoconfere.core.models import (
    Bet,
    CheckResult,
    Draw,
    DrawMatch,
    PrizeTier,
    TierResult,
)
from lotoconfere.core.rules import (
    GameRules,
    Shape,
    TierSpec,
    rules_for,
    validate_bet,
    validate_draw,
)


def embedded_combinations(hits: int, bet_size: int, minimum_size: int, tier_hits: int) -> int:
    """How many minimum-size bets inside this one landed exactly `tier_hits` hits.

    Caixa pays an expanded bet per embedded minimum-size combination, so a single
    bet can win several tiers at once. Choosing which of the `hits` matched
    numbers to spend on the tier, and filling the rest from the misses:

        N_j = C(h, j) * C(k - h, m - j)

    `comb` returns 0 whenever a term is impossible, which is the right answer
    here -- you cannot spend 6 hits when only 5 landed.
    """
    return comb(hits, tier_hits) * comb(bet_size - hits, minimum_size - tier_hits)


def column_combinations(column_hits: tuple[bool, ...], marks: tuple[int, ...]) -> list[int]:
    """Super Sete: how many single-pick bets land each hit count, per column position.

    An expanded Super Sete bet is every way of taking one marked digit from each
    column, so the count for exactly j hits is the coefficient of x^j in

        product over columns of (hit_i * x + miss_i)

    where a column contributes 1 winning digit if the drawn digit was marked, and
    its remaining marks as losing ones. Built up column by column rather than
    with a formula, because the columns are not interchangeable.
    """
    counts = [1]
    for hit, marked in zip(column_hits, marks, strict=True):
        winning = 1 if hit else 0
        losing = marked - winning
        nxt = [0] * (len(counts) + 1)
        for index, value in enumerate(counts):
            nxt[index] += value * losing
            nxt[index + 1] += value * winning
        counts = nxt
    return counts


def prize_for(draw: Draw, faixa: int) -> Decimal | None:
    """The published gross prize for a faixa, or None when the table is not out yet.

    None and zero are different answers and are never collapsed: one means Caixa
    has not said, the other means Caixa said nobody won it.
    """
    if draw.prizes is None:
        return None
    match: PrizeTier | None = next((t for t in draw.prizes if t.faixa == faixa), None)
    return match.amount if match is not None else None


def tier(spec: TierSpec, combinations: int, draw: Draw) -> TierResult:
    return TierResult(
        faixa=spec.faixa,
        label=spec.label,
        combinations=combinations,
        prize=prize_for(draw, spec.faixa),
    )


def numeric_tier_results(
    rules: GameRules,
    draw: Draw,
    hits: int,
    bet_size: int,
    which_draw: int = 0,
) -> list[TierResult]:
    """Every hit-count tier of one draw that this bet reached."""
    results = []
    for spec in rules.tiers:
        if spec.hits is None or spec.extra or spec.draw != which_draw:
            continue
        combinations = embedded_combinations(
            hits=hits,
            bet_size=bet_size,
            minimum_size=rules.minimum_bet_size,
            tier_hits=spec.hits,
        )
        if combinations:
            results.append(tier(spec, combinations, draw))
    return results


def check_bet(bet: Bet, draw: Draw) -> CheckResult:
    """Check one bet against one draw.

    Both are validated against the rule table first: a bet that could not have
    been played, or a draw that could not have happened, produces a refusal
    rather than a number.
    """
    if bet.game != draw.game:
        raise ValueError(f"aposta de {bet.game} contra sorteio de {draw.game}")
    validate_bet(bet)
    validate_draw(draw)

    rules = rules_for(bet.game)
    checkers = {
        Shape.PICK: _check_pick,
        Shape.DOUBLE: _check_double,
        Shape.EXTRA: _check_extra,
        Shape.CLOVERS: _check_clovers,
        Shape.COLUMNS: _check_columns,
    }
    return checkers[rules.shape](bet, draw, rules)


def _matched(bet: Bet, numbers: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(sorted(set(bet.numbers) & set(numbers)))


def _check_pick(bet: Bet, draw: Draw, rules: GameRules) -> CheckResult:
    """Mega-Sena, Lotofacil, Quina, Lotomania: set membership against one draw."""
    match = DrawMatch(matched=_matched(bet, draw.numbers))
    return CheckResult(
        bet=bet,
        draw=draw,
        matches=(match,),
        tiers=tuple(numeric_tier_results(rules, draw, match.hits, bet.size)),
    )


def _check_double(bet: Bet, draw: Draw, rules: GameRules) -> CheckResult:
    """Dupla Sena: the same bet against each of the contest's two draws."""
    second = draw.second_numbers or ()
    matches = (
        DrawMatch(matched=_matched(bet, draw.numbers), label="1o sorteio"),
        DrawMatch(matched=_matched(bet, second), label="2o sorteio"),
    )
    tiers: list[TierResult] = []
    for index, match in enumerate(matches):
        tiers.extend(numeric_tier_results(rules, draw, match.hits, bet.size, which_draw=index))
    return CheckResult(bet=bet, draw=draw, matches=matches, tiers=tuple(tiers))


def _check_extra(bet: Bet, draw: Draw, rules: GameRules) -> CheckResult:
    """Timemania and Dia de Sorte: numbers, plus a team or a month matched on its own.

    The extra tier is won or not won; it has no hit count and no combinations to
    spread across, so an expanded bet wins it once like any other.
    """
    match = DrawMatch(matched=_matched(bet, draw.numbers))
    tiers = numeric_tier_results(rules, draw, match.hits, bet.size)

    extra_matched = _same_extra(bet.extra, draw.extra)
    if extra_matched:
        extra_spec = next(spec for spec in rules.tiers if spec.extra)
        tiers.append(tier(extra_spec, 1, draw))
    return CheckResult(
        bet=bet,
        draw=draw,
        matches=(match,),
        tiers=tuple(tiers),
        extra_matched=extra_matched,
    )


def _same_extra(bet_extra: str | None, drawn_extra: str | None) -> bool:
    """Compare a team or a month forgivingly about case and spacing, nothing else.

    Caixa pads these ("CRB              /AL"), so an exact comparison would say a
    correct guess was wrong.
    """
    if not bet_extra or not drawn_extra:
        return False
    return " ".join(bet_extra.split()).casefold() == " ".join(drawn_extra.split()).casefold()


def _check_clovers(bet: Bet, draw: Draw, rules: GameRules) -> CheckResult:
    """+Milionaria: every tier is a pair -- so many numbers, with so many trevos."""
    match = DrawMatch(matched=_matched(bet, draw.numbers))
    clovers_matched = len(set(bet.clovers) & set(draw.clovers))

    tiers = []
    for spec in rules.tiers:
        if spec.hits is None or spec.clovers_min is None or spec.clovers_max is None:
            continue
        if not spec.clovers_min <= clovers_matched <= spec.clovers_max:
            continue
        combinations = embedded_combinations(
            hits=match.hits,
            bet_size=bet.size,
            minimum_size=rules.minimum_bet_size,
            tier_hits=spec.hits,
        )
        # An expanded trevo bet also carries several trevo pairs; the pairs that
        # land this tier multiply the number combinations.
        clover_ways = comb(clovers_matched, spec.clovers_max) * comb(
            len(bet.clovers) - clovers_matched, rules.clovers_drawn - spec.clovers_max
        )
        total = combinations * max(clover_ways, 1 if combinations else 0)
        if total:
            tiers.append(tier(spec, total, draw))
    return CheckResult(
        bet=bet,
        draw=draw,
        matches=(match,),
        tiers=tuple(tiers),
        clovers_matched=clovers_matched,
    )


def _check_columns(bet: Bet, draw: Draw, rules: GameRules) -> CheckResult:
    """Super Sete: seven columns, and a hit is the drawn digit appearing in that column.

    Position is everything here. The drawn digits are not a set -- the same digit
    can come up in two columns -- so nothing about this is set membership.
    """
    column_hits = tuple(
        drawn in marks for marks, drawn in zip(bet.columns, draw.numbers, strict=True)
    )
    marks = tuple(len(column) for column in bet.columns)
    counts = column_combinations(column_hits, marks)

    matched = tuple(draw.numbers[i] for i, hit in enumerate(column_hits) if hit)
    tiers = [
        tier(spec, counts[spec.hits], draw)
        for spec in rules.tiers
        if spec.hits is not None and spec.hits < len(counts) and counts[spec.hits]
    ]
    return CheckResult(
        bet=bet,
        draw=draw,
        matches=(DrawMatch(matched=matched),),
        tiers=tuple(tiers),
        column_hits=column_hits,
    )
