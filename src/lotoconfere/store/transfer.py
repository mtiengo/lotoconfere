"""Saved bets in and out as JSON.

An exported file is ours. An imported one is a file from wherever the person got
it, so it is treated like any other untrusted input: a size cap before parsing, a
schema checked field by field, every bet validated against its game's rules, and
a plain pt-BR error naming what was wrong. Nothing in a bet file may choose a
game we do not know, a number out of range, or a field we did not ask for.

Format 2 holds batches: a name, a game and a teimosinha shared by one or more
bets. Format 1 held one bet per entry, and still imports, each bet becoming a
batch of one.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass

from lotoconfere.core.errors import InvalidBetError, LotoConfereError, UnknownGameError
from lotoconfere.core.models import Bet
from lotoconfere.core.rules import rules_for, validate_bet
from lotoconfere.store.database import SavedBatch

# The format version, so a future change can refuse an old file out loud instead
# of misreading it.
FORMAT = 2
FORMAT_ONE_BET_EACH = 1
FORMAT_KEY = "lotoconfere_apostas"

# A few thousand bets would not reach this. Anything larger is not a bet file.
MAX_IMPORT_BYTES = 1_000_000
MAX_NAME_LENGTH = 120
# Counted across every batch, so many small batches cannot add up past it.
MAX_BETS = 10_000


class BetFileError(LotoConfereError):
    """An imported file could not be read as saved bets."""


@dataclass(frozen=True)
class ImportedBatch:
    """A batch read from a file, every bet already validated, not yet saved."""

    name: str
    bets: tuple[Bet, ...]
    run_start: int | None = None
    run_count: int | None = None


def export_bets(batches: Iterable[SavedBatch]) -> str:
    """Saved batches as JSON text, ready to write to a file."""
    payload = {
        FORMAT_KEY: FORMAT,
        "grupos": [
            {
                "nome": saved.name,
                "jogo": saved.game,
                "apostas": [
                    {
                        "numeros": list(bet.numbers),
                        "extra": bet.extra,
                        "trevos": list(bet.clovers),
                        "colunas": [list(column) for column in bet.columns],
                    }
                    for bet in saved.bets
                ],
                "teimosinha_inicio": saved.run_start,
                "teimosinha_quantidade": saved.run_count,
            }
            for saved in batches
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def import_bets(raw: bytes | str) -> list[ImportedBatch]:
    """Read an exported file back, refusing anything that is not one."""
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(data) > MAX_IMPORT_BYTES:
        raise BetFileError("o arquivo é grande demais para ser uma lista de apostas")
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BetFileError("o arquivo não está em um formato que o LotoConfere entenda") from None

    if not isinstance(payload, dict) or FORMAT_KEY not in payload:
        raise BetFileError("o arquivo não parece ter sido exportado pelo LotoConfere")
    version = payload.get(FORMAT_KEY)
    if version == FORMAT_ONE_BET_EACH:
        return _format_one(payload.get("apostas"))
    if version == FORMAT:
        return _format_two(payload.get("grupos"))
    raise BetFileError(
        f"o arquivo está no formato {version!r}, e esta versão lê os formatos "
        f"{FORMAT_ONE_BET_EACH} e {FORMAT}"
    )


def _format_one(rows: object) -> list[ImportedBatch]:
    rows = _list_of_entries(rows)
    if len(rows) > MAX_BETS:
        raise BetFileError("o arquivo tem apostas demais")
    batches = []
    for position, row in enumerate(rows, start=1):
        where = f"aposta {position}"
        entry = _entry(row, where)
        name = _name(entry.get("nome"), where)
        game = _game(entry.get("jogo"), where)
        batches.append(
            ImportedBatch(
                name=name,
                bets=(_bet(entry, game, f"aposta {position} ({name})"),),
                run_start=_optional_int(entry.get("teimosinha_inicio"), where),
                run_count=_optional_int(entry.get("teimosinha_quantidade"), where),
            )
        )
    return batches


def _format_two(rows: object) -> list[ImportedBatch]:
    rows = _list_of_entries(rows)
    # Counted before anything is parsed: an oversized file is refused for its
    # size, not for whichever bet in it happens to be wrong first.
    total = sum(
        len(row["apostas"])
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("apostas"), list)
    )
    if total > MAX_BETS:
        raise BetFileError("o arquivo tem apostas demais")
    batches = []
    for position, row in enumerate(rows, start=1):
        where = f"grupo {position}"
        entry = _entry(row, where)
        name = _name(entry.get("nome"), where)
        game = _game(entry.get("jogo"), where)
        bet_rows = entry.get("apostas")
        if not isinstance(bet_rows, list) or not bet_rows:
            raise BetFileError(f"{where} ({name}): não tem apostas")
        bets = tuple(
            _bet(_entry(bet_row, where), game, f"{where} ({name}), aposta {number}")
            for number, bet_row in enumerate(bet_rows, start=1)
        )
        batches.append(
            ImportedBatch(
                name=name,
                bets=bets,
                run_start=_optional_int(entry.get("teimosinha_inicio"), where),
                run_count=_optional_int(entry.get("teimosinha_quantidade"), where),
            )
        )
    return batches


def _list_of_entries(rows: object) -> list[object]:
    if not isinstance(rows, list):
        raise BetFileError("o arquivo não tem uma lista de apostas")
    return rows


def _entry(row: object, where: str) -> dict[str, object]:
    if not isinstance(row, dict):
        raise BetFileError(f"{where}: formato inesperado")
    return row


def _name(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BetFileError(f"{where}: falta o nome")
    if len(value) > MAX_NAME_LENGTH:
        raise BetFileError(f"{where}: o nome é longo demais")
    return value.strip()


def _game(value: object, where: str) -> str:
    if not isinstance(value, str):
        raise BetFileError(f"{where}: falta o jogo")
    try:
        rules_for(value)
    except UnknownGameError:
        raise BetFileError(f"{where}: jogo desconhecido: {value}") from None
    return value


def _bet(row: dict[str, object], game: str, where: str) -> Bet:
    """One bet's marks, validated against the game its batch names."""
    bet = Bet(
        game=game,
        numbers=_ints(row.get("numeros"), where, "números"),
        extra=_text(row.get("extra"), where),
        clovers=_ints(row.get("trevos"), where, "trevos"),
        columns=_columns(row.get("colunas"), where),
    )
    try:
        validate_bet(bet)
    except InvalidBetError as error:
        raise BetFileError(f"{where}: {error}") from None
    return bet


def _ints(value: object, where: str, what: str) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise BetFileError(f"{where}: {what} em formato inesperado")
    numbers = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise BetFileError(f"{where}: {what} com valor inválido: {item!r}")
        numbers.append(item)
    return tuple(numbers)


def _columns(value: object, where: str) -> tuple[tuple[int, ...], ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise BetFileError(f"{where}: colunas em formato inesperado")
    return tuple(_ints(column, where, "colunas") for column in value)


def _text(value: object, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise BetFileError(f"{where}: campo extra em formato inesperado")
    return value.strip() or None


def _optional_int(value: object, where: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BetFileError(f"{where}: teimosinha inválida: {value!r}")
    return value
