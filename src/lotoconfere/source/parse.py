"""Turning endpoint JSON into core types. Shared by both sources; trusts neither.

Every value arrives as `object` rather than `Any` on purpose: the shape has to be
proven before the value can be used, so a field that is not what it should be
raises here instead of becoming a plausible-looking number three layers down.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from lotoconfere.core.errors import InvalidDrawError
from lotoconfere.core.models import PrizeTier
from lotoconfere.core.rules import GameRules

# Caixa sends a run of these where a name would go on games that have no team or
# month. Not a string to display, and not an error either -- simply absent.
NUL = "\u0000"


@dataclass(frozen=True)
class PrizeFields:
    """What one source calls the three columns of a prize row."""

    label: str
    winners: str
    amount: str


def text_or_none(value: object) -> str | None:
    """A trimmed string, or None when the field is absent or all NUL characters."""
    if not isinstance(value, str):
        return None
    cleaned = value.replace(NUL, "").strip()
    return cleaned or None


def required(payload: dict[str, object], key: str, contest: object = "?") -> object:
    """Read a field that must be there, or refuse."""
    if key not in payload:
        raise InvalidDrawError(f"concurso {contest}: resposta sem o campo {key}")
    return payload[key]


def parse_date(value: object, contest: object = "?") -> date:
    """`dd/mm/yyyy` into a real date. The string shape never reaches the rest of the app."""
    if not isinstance(value, str):
        raise InvalidDrawError(f"concurso {contest}: data ausente")
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except ValueError:
        raise InvalidDrawError(f"concurso {contest}: data invalida: {value!r}") from None


def parse_numbers(
    value: object, contest: object = "?", *, keep_order: bool = False
) -> tuple[int, ...]:
    """Zero-padded strings into ints. Padding is a display concern, not a value.

    Sorted, except for Super Sete: there the position IS the meaning, one digit
    per column, and sorting would quietly turn a column result into a set.
    """
    if not isinstance(value, list):
        raise InvalidDrawError(f"concurso {contest}: lista de dezenas ausente")
    numbers = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int | str):
            raise InvalidDrawError(f"concurso {contest}: dezena invalida: {item!r}")
        try:
            numbers.append(int(str(item).strip()))
        except ValueError:
            raise InvalidDrawError(f"concurso {contest}: dezena invalida: {item!r}") from None
    return tuple(numbers) if keep_order else tuple(sorted(numbers))


def parse_contest(value: object) -> int:
    """The contest number, which every other identifier hangs off."""
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise InvalidDrawError(f"numero de concurso invalido: {value!r}")
    try:
        return int(value)
    except ValueError:
        raise InvalidDrawError(f"numero de concurso invalido: {value!r}") from None


def parse_money(value: object, contest: object = "?") -> Decimal:
    """A published prize into Decimal, via str so binary floating point never touches money."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise InvalidDrawError(f"concurso {contest}: valor de premio invalido: {value!r}")
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise InvalidDrawError(f"concurso {contest}: valor de premio invalido: {value!r}") from None


def hits_in_label(label: str | None) -> int | None:
    """The leading integer of "6 acertos", or None when the label is not that shape."""
    if not label:
        return None
    head = label.strip().split(" ", 1)[0]
    return int(head) if head.isdigit() else None


def parse_prizes(
    rows: object,
    rules: GameRules,
    contest: object,
    fields: PrizeFields,
) -> tuple[PrizeTier, ...] | None:
    """A published prize table into tiers, or None when it has not been published.

    Rows are joined to the rule table by **position**, and each keeps Caixa's own
    faixa number. Position rather than the label, because Dupla Sena lists two
    faixas called "6 acertos" and only their order says which draw each belongs
    to. The label is then used to check the assumption whenever it carries a
    number, because a silently reordered table would pay the wrong prize for the
    right hits and nothing downstream could notice.
    """
    if not rows:
        return None
    if not isinstance(rows, list):
        raise InvalidDrawError(f"concurso {contest}: tabela de premios em formato inesperado")
    if len(rows) != len(rules.tiers):
        raise InvalidDrawError(
            f"concurso {contest}: a tabela tem {len(rows)} faixas, "
            f"e {rules.name} paga {len(rules.tiers)}"
        )

    tiers = []
    for spec, row in zip(rules.tiers, rows, strict=True):
        if not isinstance(row, dict):
            raise InvalidDrawError(f"concurso {contest}: faixa de premio em formato inesperado")
        label = text_or_none(row.get(fields.label)) or spec.label
        stated = hits_in_label(label)
        if spec.hits is not None and stated is not None and stated != spec.hits:
            raise InvalidDrawError(
                f"concurso {contest}: a faixa diz {label!r} onde {spec.hits} acertos eram esperados"
            )
        winners = row.get(fields.winners, 0)
        if isinstance(winners, bool) or not isinstance(winners, int):
            raise InvalidDrawError(
                f"concurso {contest}: numero de ganhadores invalido em {label!r}"
            )
        tiers.append(
            PrizeTier(
                faixa=spec.faixa,
                label=label,
                winners=winners,
                amount=parse_money(row.get(fields.amount), contest),
            )
        )
    return tuple(tiers)
