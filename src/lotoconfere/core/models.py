"""The types the checker speaks: what was played, what was drawn, what it is worth.

Frozen dataclasses, and numbers are `int` throughout -- the zero padding Caixa
sends (`"05"`) is a display concern and never reaches this layer.

Most games only use `numbers`. The other fields exist because four of the nine
genuinely need them: Dupla Sena draws twice, Timemania and Dia de Sorte draw a
team or a month alongside the numbers, +Milionaria draws two trevos, and Super
Sete draws one digit per column. A field left empty is a game that does not have
that thing, never a value nobody filled in.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum


class Source(StrEnum):
    """Where a result came from. Every result carries one; none is not an option."""

    CAIXA = "caixa"
    MIRROR = "mirror"


@dataclass(frozen=True)
class Bet:
    """The numbers someone played on one game.

    `columns` is Super Sete's shape: seven positions, each holding the digits
    marked in that column. Every other game uses `numbers`.
    """

    game: str
    numbers: tuple[int, ...] = ()
    extra: str | None = None
    clovers: tuple[int, ...] = ()
    columns: tuple[tuple[int, ...], ...] = ()

    @property
    def size(self) -> int:
        """How many marks the bet carries, which is what bet size means per game."""
        if self.columns:
            return sum(len(column) for column in self.columns)
        return len(self.numbers)


@dataclass(frozen=True)
class PrizeTier:
    """One line of Caixa's published prize table, kept in Caixa's own order.

    Joined to a tier by `faixa`, the number Caixa gives it, rather than by a hit
    count parsed out of its description: Dupla Sena has two faixas called
    "6 acertos" and only their position says which draw each belongs to.

    `amount` is the gross value Caixa published, exactly as published: no tax
    math, no estimate, no rounding of our own. Decimal, never float -- money that
    goes through binary floating point stops adding up.
    """

    faixa: int
    label: str
    winners: int
    amount: Decimal


@dataclass(frozen=True)
class Draw:
    """One contest as it was drawn.

    `prizes` is None when the prize table has not been published yet, which is a
    different thing from a table in which nobody won. The first must be said out
    loud; the second is a row of zeros Caixa itself published.

    For Super Sete, `numbers` is **positional**: one digit per column, in column
    order, and repeats are ordinary. For every other game it is a sorted set.
    """

    game: str
    contest: int
    drawn_on: date
    numbers: tuple[int, ...]
    source: Source
    prizes: tuple[PrizeTier, ...] | None = None
    second_numbers: tuple[int, ...] | None = None
    extra: str | None = None
    clovers: tuple[int, ...] = ()

    @property
    def prize_table_published(self) -> bool:
        return self.prizes is not None


@dataclass(frozen=True)
class DrawMatch:
    """What a bet matched in one draw. Two of these for Dupla Sena, one otherwise."""

    matched: tuple[int, ...]
    label: str = ""

    @property
    def hits(self) -> int:
        return len(self.matched)


@dataclass(frozen=True)
class TierResult:
    """One prize tier a bet reached.

    `combinations` is how many minimum-size bets embedded in this one landed in
    this tier -- 1 for a plain bet, more for an expanded one, because Caixa pays
    per embedded combination. `prize` is None when the table is not out yet.
    """

    faixa: int
    label: str
    combinations: int
    prize: Decimal | None


@dataclass(frozen=True)
class CheckResult:
    """What one bet did against one draw.

    The raw hit count comes first and the tiers explain it; the breakdown never
    replaces the count.
    """

    bet: Bet
    draw: Draw
    matches: tuple[DrawMatch, ...]
    tiers: tuple[TierResult, ...] = ()
    extra_matched: bool = False
    clovers_matched: int = 0
    column_hits: tuple[bool, ...] = field(default=())

    @property
    def hit_count(self) -> int:
        """Hits in the first draw, which is the only draw for eight of nine games."""
        return self.matches[0].hits if self.matches else 0

    @property
    def hit_counts(self) -> tuple[int, ...]:
        """Hits per draw. Dupla Sena is checked against both and reports both."""
        return tuple(match.hits for match in self.matches)

    @property
    def matched(self) -> tuple[int, ...]:
        return self.matches[0].matched if self.matches else ()

    @property
    def won(self) -> bool:
        return bool(self.tiers)
