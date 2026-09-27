"""Saved bets in and out as JSON.

An exported file is ours. An imported one is a file from wherever the person got
it, so it is treated like any other untrusted input: a size cap before parsing, a
schema checked field by field, every bet validated against its game's rules, and
a plain pt-BR error naming what was wrong. Nothing in a bet file may choose a
game we do not know, a number out of range, or a field we did not ask for.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass

from lotoconfere.core.errors import InvalidBetError, LotoConfereError, UnknownGameError
from lotoconfere.core.models import Bet
from lotoconfere.core.rules import rules_for, validate_bet
from lotoconfere.store.database import SavedBet

# The format version, so a future change can refuse an old file out loud instead
# of misreading it.
FORMAT = 1
FORMAT_KEY = "lotoconfere_apostas"

# A few thousand bets would not reach this. Anything larger is not a bet file.
MAX_IMPORT_BYTES = 1_000_000
MAX_NAME_LENGTH = 120
MAX_BETS = 10_000


class BetFileError(LotoConfereError):
    """An imported file could not be read as saved bets."""


@dataclass(frozen=True)
class ImportedBet:
    """A bet read from a file, already validated, not yet saved."""

    name: str
    bet: Bet
    run_start: int | None = None
    run_count: int | None = None


def export_bets(bets: Iterable[SavedBet]) -> str:
    """Saved bets as JSON text, ready to write to a file."""
    payload = {
        FORMAT_KEY: FORMAT,
        "apostas": [
            {
                "nome": saved.name,
                "jogo": saved.bet.game,
                "numeros": list(saved.bet.numbers),
                "extra": saved.bet.extra,
                "trevos": list(saved.bet.clovers),
                "colunas": [list(column) for column in saved.bet.columns],
                "teimosinha_inicio": saved.run_start,
                "teimosinha_quantidade": saved.run_count,
            }
            for saved in bets
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def import_bets(raw: bytes | str) -> list[ImportedBet]:
    """Read an exported file back, refusing anything that is not one."""
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(data) > MAX_IMPORT_BYTES:
        raise BetFileError("o arquivo e grande demais para ser uma lista de apostas")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BetFileError("o arquivo nao esta em um formato que o LotoConfere entenda") from None

    if not isinstance(payload, dict) or FORMAT_KEY not in payload:
        raise BetFileError("o arquivo nao parece ter sido exportado pelo LotoConfere")
    if payload.get(FORMAT_KEY) != FORMAT:
        raise BetFileError(
            f"o arquivo esta no formato {payload.get(FORMAT_KEY)!r}, "
            f"e esta versao le o formato {FORMAT}"
        )

    rows = payload.get("apostas")
    if not isinstance(rows, list):
        raise BetFileError("o arquivo nao tem uma lista de apostas")
    if len(rows) > MAX_BETS:
        raise BetFileError("o arquivo tem apostas demais")
    return [_one_bet(row, position) for position, row in enumerate(rows, start=1)]


def _one_bet(row: object, position: int) -> ImportedBet:
    if not isinstance(row, dict):
        raise BetFileError(f"aposta {position}: formato inesperado")

    name = row.get("nome")
    if not isinstance(name, str) or not name.strip():
        raise BetFileError(f"aposta {position}: falta o nome")
    if len(name) > MAX_NAME_LENGTH:
        raise BetFileError(f"aposta {position}: o nome e longo demais")

    game = row.get("jogo")
    if not isinstance(game, str):
        raise BetFileError(f"aposta {position}: falta o jogo")
    try:
        rules_for(game)
    except UnknownGameError:
        raise BetFileError(f"aposta {position}: jogo desconhecido: {game}") from None

    bet = Bet(
        game=game,
        numbers=_ints(row.get("numeros"), position, "numeros"),
        extra=_text(row.get("extra"), position),
        clovers=_ints(row.get("trevos"), position, "trevos"),
        columns=_columns(row.get("colunas"), position),
    )
    try:
        validate_bet(bet)
    except InvalidBetError as error:
        raise BetFileError(f"aposta {position} ({name.strip()}): {error}") from None

    return ImportedBet(
        name=name.strip(),
        bet=bet,
        run_start=_optional_int(row.get("teimosinha_inicio"), position),
        run_count=_optional_int(row.get("teimosinha_quantidade"), position),
    )


def _ints(value: object, position: int, what: str) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise BetFileError(f"aposta {position}: {what} em formato inesperado")
    numbers = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise BetFileError(f"aposta {position}: {what} com valor invalido: {item!r}")
        numbers.append(item)
    return tuple(numbers)


def _columns(value: object, position: int) -> tuple[tuple[int, ...], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise BetFileError(f"aposta {position}: colunas em formato inesperado")
    return tuple(_ints(column, position, "colunas") for column in value)


def _text(value: object, position: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BetFileError(f"aposta {position}: campo extra em formato inesperado")
    return value.strip() or None


def _optional_int(value: object, position: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BetFileError(f"aposta {position}: teimosinha invalida: {value!r}")
    return value
