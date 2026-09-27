"""The rule table: the single home for every game value in this project.

Nothing else in the codebase restates a range, a bet size or a prize tier. Every
entry records the Caixa page its values came from and the date someone read it,
because a value without a citation is a value nobody can re-check.

Adding a game is one entry here plus its tests. Each entry names a `Shape`, which
is how the checker knows what kind of matching the game needs -- five shapes for
nine games, because Super Sete's draw is positional, Dupla Sena draws twice,
Timemania and Dia de Sorte draw a team or a month, and +Milionaria's tiers are
pairs of hits and trevos. Adding a tenth game means picking a shape, not writing
one. Procedure: the `add-game` skill.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from lotoconfere.core.errors import InvalidBetError, InvalidDrawError, UnknownGameError
from lotoconfere.core.models import Bet, Draw


class Shape(StrEnum):
    """How a game is matched. Five of these cover all nine games."""

    PICK = "pick"
    DOUBLE = "double"
    EXTRA = "extra"
    CLOVERS = "clovers"
    COLUMNS = "columns"


@dataclass(frozen=True)
class TierSpec:
    """One prize faixa, in the order Caixa lists it.

    `faixa` is Caixa's own number for it, and it is the join key: Dupla Sena has
    two faixas labelled "6 acertos" and only their position says which draw each
    one belongs to.
    """

    faixa: int
    label: str
    hits: int | None = None
    draw: int = 0
    clovers_min: int | None = None
    clovers_max: int | None = None
    extra: bool = False


@dataclass(frozen=True)
class ColumnBand:
    """Super Sete's marks-per-column rule, which depends on how many were marked."""

    total_min: int
    total_max: int
    per_column_min: int
    per_column_max: int


@dataclass(frozen=True)
class GameRules:
    """Everything the checker needs to know about one game."""

    key: str
    name: str
    shape: Shape
    first_number: int
    last_number: int
    drawn_count: int
    bet_sizes: tuple[int, ...]
    tiers: tuple[TierSpec, ...]
    source_url: str
    verified_on: date
    extra_label: str = ""
    clover_first: int = 0
    clover_last: int = 0
    clover_sizes: tuple[int, ...] = ()
    clovers_drawn: int = 0
    column_count: int = 0
    column_bands: tuple[ColumnBand, ...] = field(default=())
    has_mirror: bool = False

    @property
    def minimum_bet_size(self) -> int:
        """The smallest playable bet, which is also the combination size Caixa pays on."""
        return self.bet_sizes[0]


# --- the nine games -------------------------------------------------------------

MEGA_SENA = GameRules(
    key="megasena",
    name="Mega-Sena",
    shape=Shape.PICK,
    first_number=1,
    last_number=60,
    drawn_count=6,
    bet_sizes=tuple(range(6, 21)),
    # Sena, quina, quadra.
    tiers=(
        TierSpec(faixa=1, label="6 acertos", hits=6),
        TierSpec(faixa=2, label="5 acertos", hits=5),
        TierSpec(faixa=3, label="4 acertos", hits=4),
    ),
    source_url="https://loterias.caixa.gov.br/Paginas/Mega-Sena.aspx",
    verified_on=date(2026, 9, 26),
)

LOTOFACIL = GameRules(
    key="lotofacil",
    name="Lotofacil",
    shape=Shape.PICK,
    first_number=1,
    last_number=25,
    drawn_count=15,
    bet_sizes=tuple(range(15, 21)),
    tiers=tuple(
        TierSpec(faixa=i, label=f"{hits} acertos", hits=hits)
        for i, hits in enumerate((15, 14, 13, 12, 11), start=1)
    ),
    source_url="https://loterias.caixa.gov.br/Paginas/Lotofacil.aspx",
    verified_on=date(2026, 9, 26),
)

QUINA = GameRules(
    key="quina",
    name="Quina",
    shape=Shape.PICK,
    first_number=1,
    last_number=80,
    drawn_count=5,
    bet_sizes=tuple(range(5, 16)),
    tiers=tuple(
        TierSpec(faixa=i, label=f"{hits} acertos", hits=hits)
        for i, hits in enumerate((5, 4, 3, 2), start=1)
    ),
    source_url="https://loterias.caixa.gov.br/Paginas/Quina.aspx",
    verified_on=date(2026, 9, 26),
)

LOTOMANIA = GameRules(
    key="lotomania",
    name="Lotomania",
    shape=Shape.PICK,
    # The only game whose range starts at zero: the volante is 00-99. The page
    # never says so in words, so it was confirmed against Caixa's own odds --
    # C(50,20)/C(100,20) is the published 1 in 11.372.635, and 15 hits is 1 in 112.
    first_number=0,
    last_number=99,
    drawn_count=20,
    # One size only, and it is also the minimum, so no bet is ever expanded.
    bet_sizes=(50,),
    # "Aposta-Espelho: efetue uma nova aposta com o sistema selecionando os
    # outros 50 numeros nao registrados no jogo original." Only Lotomania has it,
    # and it only works because the bet is exactly half the volante.
    has_mirror=True,
    # Hitting none of the twenty is the seventh faixa, not a loss.
    tiers=tuple(
        TierSpec(faixa=i, label=f"{hits} acertos", hits=hits)
        for i, hits in enumerate((20, 19, 18, 17, 16, 15, 0), start=1)
    ),
    source_url="https://loterias.caixa.gov.br/Paginas/Lotomania.aspx",
    verified_on=date(2026, 9, 26),
)

DUPLA_SENA = GameRules(
    key="duplasena",
    name="Dupla Sena",
    shape=Shape.DOUBLE,
    first_number=1,
    last_number=50,
    drawn_count=6,
    bet_sizes=tuple(range(6, 16)),
    # Eight faixas: the same four tiers for each draw, first draw then second.
    # Only the position says which draw a "6 acertos" belongs to.
    tiers=tuple(
        TierSpec(
            faixa=index,
            label=f"{hits} acertos ({draw + 1}o sorteio)",
            hits=hits,
            draw=draw,
        )
        for index, (draw, hits) in enumerate(
            [(0, 6), (0, 5), (0, 4), (0, 3), (1, 6), (1, 5), (1, 4), (1, 3)], start=1
        )
    ),
    source_url="https://loterias.caixa.gov.br/Paginas/Dupla-Sena.aspx",
    verified_on=date(2026, 9, 26),
)

TIMEMANIA = GameRules(
    key="timemania",
    name="Timemania",
    shape=Shape.EXTRA,
    first_number=1,
    last_number=80,
    drawn_count=7,
    bet_sizes=(10,),
    tiers=(
        TierSpec(faixa=1, label="7 acertos", hits=7),
        TierSpec(faixa=2, label="6 acertos", hits=6),
        TierSpec(faixa=3, label="5 acertos", hits=5),
        TierSpec(faixa=4, label="4 acertos", hits=4),
        TierSpec(faixa=5, label="3 acertos", hits=3),
        TierSpec(faixa=6, label="Time do Coracao", extra=True),
    ),
    extra_label="Time do Coracao",
    source_url="https://loterias.caixa.gov.br/Paginas/Timemania.aspx",
    verified_on=date(2026, 9, 26),
)

DIA_DE_SORTE = GameRules(
    key="diadesorte",
    name="Dia de Sorte",
    shape=Shape.EXTRA,
    first_number=1,
    last_number=31,
    drawn_count=7,
    bet_sizes=tuple(range(7, 16)),
    tiers=(
        TierSpec(faixa=1, label="7 acertos", hits=7),
        TierSpec(faixa=2, label="6 acertos", hits=6),
        TierSpec(faixa=3, label="5 acertos", hits=5),
        TierSpec(faixa=4, label="4 acertos", hits=4),
        TierSpec(faixa=5, label="Mes da Sorte", extra=True),
    ),
    extra_label="Mes da Sorte",
    source_url="https://loterias.caixa.gov.br/Paginas/Dia-de-Sorte.aspx",
    verified_on=date(2026, 9, 26),
)

SUPER_SETE = GameRules(
    key="supersete",
    name="Super Sete",
    shape=Shape.COLUMNS,
    # Digits, not numbers: each column holds 0 to 9, and the same digit can come
    # up in more than one column.
    first_number=0,
    last_number=9,
    drawn_count=7,
    bet_sizes=tuple(range(7, 22)),
    tiers=tuple(
        TierSpec(faixa=i, label=f"{hits} acertos", hits=hits)
        for i, hits in enumerate((7, 6, 5, 4, 3), start=1)
    ),
    column_count=7,
    # "Marque no minimo 1 e no maximo 2 numeros por coluna com 8 a 14 numeros
    # marcados, e no minimo 2 e no maximo 3 por coluna com 15 a 21 marcados."
    column_bands=(
        ColumnBand(total_min=7, total_max=7, per_column_min=1, per_column_max=1),
        ColumnBand(total_min=8, total_max=14, per_column_min=1, per_column_max=2),
        ColumnBand(total_min=15, total_max=21, per_column_min=2, per_column_max=3),
    ),
    source_url="https://loterias.caixa.gov.br/Paginas/Super-Sete.aspx",
    verified_on=date(2026, 9, 26),
)

MAIS_MILIONARIA = GameRules(
    key="maismilionaria",
    name="+Milionaria",
    shape=Shape.CLOVERS,
    first_number=1,
    last_number=50,
    drawn_count=6,
    # 6 to 12 numbers and 2 to 6 trevos, from Caixa's own bolao table.
    bet_sizes=tuple(range(6, 13)),
    clover_first=1,
    clover_last=6,
    clover_sizes=tuple(range(2, 7)),
    clovers_drawn=2,
    # Ten faixas, and each is a pair: hits and how many trevos came with them.
    # "1 ou nenhum trevo" is a range, which is why the bounds are separate.
    tiers=(
        TierSpec(faixa=1, label="6 acertos + 2 trevos", hits=6, clovers_min=2, clovers_max=2),
        TierSpec(
            faixa=2, label="6 acertos + 1 ou nenhum trevo", hits=6, clovers_min=0, clovers_max=1
        ),
        TierSpec(faixa=3, label="5 acertos + 2 trevos", hits=5, clovers_min=2, clovers_max=2),
        TierSpec(
            faixa=4, label="5 acertos + 1 ou nenhum trevo", hits=5, clovers_min=0, clovers_max=1
        ),
        TierSpec(faixa=5, label="4 acertos + 2 trevos", hits=4, clovers_min=2, clovers_max=2),
        TierSpec(
            faixa=6, label="4 acertos + 1 ou nenhum trevo", hits=4, clovers_min=0, clovers_max=1
        ),
        TierSpec(faixa=7, label="3 acertos + 2 trevos", hits=3, clovers_min=2, clovers_max=2),
        TierSpec(faixa=8, label="3 acertos + 1 trevo", hits=3, clovers_min=1, clovers_max=1),
        TierSpec(faixa=9, label="2 acertos + 2 trevos", hits=2, clovers_min=2, clovers_max=2),
        TierSpec(faixa=10, label="2 acertos + 1 trevo", hits=2, clovers_min=1, clovers_max=1),
    ),
    source_url="https://loterias.caixa.gov.br/Paginas/Mais-Milionaria.aspx",
    verified_on=date(2026, 9, 26),
)

GAMES: dict[str, GameRules] = {
    game.key: game
    for game in (
        MEGA_SENA,
        LOTOFACIL,
        QUINA,
        LOTOMANIA,
        DUPLA_SENA,
        TIMEMANIA,
        DIA_DE_SORTE,
        SUPER_SETE,
        MAIS_MILIONARIA,
    )
}


def rules_for(game: str) -> GameRules:
    """The rules for a game key, or a refusal if it is not a game we know."""
    try:
        return GAMES[game]
    except KeyError:
        raise UnknownGameError(f"jogo desconhecido: {game}") from None


# --- validation -----------------------------------------------------------------


def _check_range(rules: GameRules, numbers: tuple[int, ...], what: str) -> None:
    stray = [n for n in numbers if not rules.first_number <= n <= rules.last_number]
    if stray:
        raise InvalidBetError(
            f"{rules.name}: {what} vao de {rules.first_number} a {rules.last_number}, "
            f"e a aposta tem {sorted(stray)}"
        )


def validate_bet(bet: Bet) -> None:
    """Refuse a bet that breaks its game's rules. Silence means it is playable."""
    rules = rules_for(bet.game)
    if rules.shape is Shape.COLUMNS:
        _validate_column_bet(bet, rules)
        return

    if bet.size not in rules.bet_sizes:
        raise InvalidBetError(
            f"{rules.name}: uma aposta tem de {rules.bet_sizes[0]} a "
            f"{rules.bet_sizes[-1]} numeros, e esta tem {bet.size}"
        )
    if len(set(bet.numbers)) != bet.size:
        raise InvalidBetError(f"{rules.name}: a aposta tem numeros repetidos")
    _check_range(rules, bet.numbers, "os numeros")

    if rules.shape is Shape.CLOVERS:
        _validate_clovers(bet, rules)
    if rules.shape is Shape.EXTRA and not bet.extra:
        raise InvalidBetError(f"{rules.name}: a aposta precisa de um {rules.extra_label}")


def _validate_clovers(bet: Bet, rules: GameRules) -> None:
    if len(bet.clovers) not in rules.clover_sizes:
        raise InvalidBetError(
            f"{rules.name}: uma aposta tem de {rules.clover_sizes[0]} a "
            f"{rules.clover_sizes[-1]} trevos, e esta tem {len(bet.clovers)}"
        )
    if len(set(bet.clovers)) != len(bet.clovers):
        raise InvalidBetError(f"{rules.name}: a aposta tem trevos repetidos")
    stray = [c for c in bet.clovers if not rules.clover_first <= c <= rules.clover_last]
    if stray:
        raise InvalidBetError(
            f"{rules.name}: os trevos vao de {rules.clover_first} a {rules.clover_last}, "
            f"e a aposta tem {sorted(stray)}"
        )


def _validate_column_bet(bet: Bet, rules: GameRules) -> None:
    """Super Sete: one band of marks per column, decided by the total marked."""
    if len(bet.columns) != rules.column_count:
        raise InvalidBetError(
            f"{rules.name}: a aposta tem {rules.column_count} colunas, "
            f"e esta tem {len(bet.columns)}"
        )
    total = bet.size
    band = next(
        (b for b in rules.column_bands if b.total_min <= total <= b.total_max),
        None,
    )
    if band is None:
        raise InvalidBetError(
            f"{rules.name}: uma aposta tem de {rules.bet_sizes[0]} a "
            f"{rules.bet_sizes[-1]} numeros, e esta tem {total}"
        )
    for position, column in enumerate(bet.columns, start=1):
        if not band.per_column_min <= len(column) <= band.per_column_max:
            raise InvalidBetError(
                f"{rules.name}: com {total} numeros marcados, cada coluna leva de "
                f"{band.per_column_min} a {band.per_column_max}, e a coluna {position} "
                f"tem {len(column)}"
            )
        if len(set(column)) != len(column):
            raise InvalidBetError(f"{rules.name}: a coluna {position} tem numeros repetidos")
        _check_range(rules, tuple(column), "os numeros")


def validate_draw(draw: Draw) -> None:
    """Refuse a draw that breaks its game's rules.

    This is the boundary check every parsed response passes through. A draw that
    fails here is rejected whole -- never trimmed, deduplicated or otherwise
    repaired into something plausible.
    """
    rules = rules_for(draw.game)
    where = f"{rules.name} concurso {draw.contest}"
    if draw.contest < 1:
        raise InvalidDrawError(f"{rules.name}: numero de concurso invalido: {draw.contest}")

    _validate_drawn_numbers(rules, draw.numbers, where)
    if rules.shape is Shape.DOUBLE:
        if draw.second_numbers is None:
            raise InvalidDrawError(f"{where}: falta o segundo sorteio")
        _validate_drawn_numbers(rules, draw.second_numbers, f"{where} (2o sorteio)")
    if rules.shape is Shape.EXTRA and not draw.extra:
        raise InvalidDrawError(f"{where}: falta o {rules.extra_label}")
    if rules.shape is Shape.CLOVERS:
        if len(draw.clovers) != rules.clovers_drawn:
            raise InvalidDrawError(
                f"{where}: o sorteio tem {rules.clovers_drawn} trevos, e vieram {len(draw.clovers)}"
            )
        stray = [c for c in draw.clovers if not rules.clover_first <= c <= rules.clover_last]
        if stray:
            raise InvalidDrawError(f"{where}: trevo fora do intervalo: {sorted(stray)}")


def _validate_drawn_numbers(rules: GameRules, numbers: tuple[int, ...], where: str) -> None:
    if len(numbers) != rules.drawn_count:
        raise InvalidDrawError(
            f"{where}: o sorteio tem {rules.drawn_count} numeros, e vieram {len(numbers)}"
        )
    # Super Sete draws one digit per column, so the same digit twice is ordinary.
    if rules.shape is not Shape.COLUMNS and len(set(numbers)) != len(numbers):
        raise InvalidDrawError(f"{where}: o sorteio tem numeros repetidos")
    stray = [n for n in numbers if not rules.first_number <= n <= rules.last_number]
    if stray:
        raise InvalidDrawError(
            f"{where}: os numeros vao de {rules.first_number} a {rules.last_number}, "
            f"e vieram {sorted(stray)}"
        )


# --- the mirror bet -------------------------------------------------------------


def mirror_bet(bet: Bet) -> Bet:
    """Lotomania's Aposta-Espelho: the other fifty numbers.

    Not a suggestion and not a generator -- it is the second bet Caixa sold
    alongside the first, worked out from the volante rather than guessed at. The
    app builds it so both can be checked; it never decides to play it.
    """
    rules = rules_for(bet.game)
    if not rules.has_mirror:
        raise InvalidBetError(f"{rules.name} nao tem aposta-espelho")
    validate_bet(bet)
    chosen = set(bet.numbers)
    other = tuple(n for n in range(rules.first_number, rules.last_number + 1) if n not in chosen)
    mirrored = Bet(game=bet.game, numbers=other)
    # The complement of a valid bet is a valid bet only because the volante is
    # exactly twice the bet size. Proven here rather than assumed.
    validate_bet(mirrored)
    return mirrored
