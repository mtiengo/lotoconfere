"""The community mirror: a fallback, never the source of truth.

This looks like a copy of caixa.py and is not one. The two read different
schemas -- `dezenas` against `listaDezenas`, `premiacoes` against
`listaRateioPremio` -- into the same core types, through the same validation.
What must not be duplicated, the types and the rules, is shared already; the
field names are the part that genuinely differs. Merging them would mean one
parser with a flag, which is how a schema change in one source starts corrupting
the other.

Off by default. A result from here is labelled on screen and replaced by Caixa's
the next time Caixa answers.
"""

import httpx

from lotoconfere.core.errors import InvalidDrawError
from lotoconfere.core.models import Draw, Source
from lotoconfere.core.rules import Shape, rules_for, validate_draw
from lotoconfere.source import http
from lotoconfere.source.parse import (
    PrizeFields,
    parse_contest,
    parse_date,
    parse_numbers,
    parse_prizes,
    required,
    text_or_none,
)

BASE_URL = "https://loteriascaixa-api.herokuapp.com/api"

FIELDS = PrizeFields(label="descricao", winners="ganhadores", amount="valorPremio")


def url_for(game: str, number: int | None = None) -> str:
    """Latest, or one contest by number."""
    return f"{BASE_URL}/{game}/latest" if number is None else f"{BASE_URL}/{game}/{number}"


def parse(payload: object, game: str) -> Draw:
    """One mirror response into a validated Draw."""
    if not isinstance(payload, dict):
        raise InvalidDrawError("resposta do espelho em formato inesperado")
    rules = rules_for(game)
    contest = parse_contest(required(payload, "concurso"))
    # The mirror keeps the second draw in the same list as the first for Dupla
    # Sena, so it is split rather than read from a field of its own.
    numbers = parse_numbers(
        required(payload, "dezenas", contest),
        contest,
        keep_order=rules.shape is Shape.COLUMNS,
    )
    second: tuple[int, ...] | None = None
    if rules.shape is Shape.DOUBLE and len(numbers) == rules.drawn_count * 2:
        first_half = parse_numbers(list(payload["dezenas"])[: rules.drawn_count], contest)
        second = parse_numbers(list(payload["dezenas"])[rules.drawn_count :], contest)
        numbers = first_half
    draw = Draw(
        game=game,
        contest=contest,
        drawn_on=parse_date(required(payload, "data", contest), contest),
        numbers=numbers,
        source=Source.MIRROR,
        prizes=parse_prizes(payload.get("premiacoes"), rules, contest, FIELDS),
        second_numbers=second,
        extra=text_or_none(payload.get("timeCoracao")) or text_or_none(payload.get("mesSorte")),
        clovers=parse_numbers(payload.get("trevos") or [], contest),
    )
    validate_draw(draw)
    return draw


class MirrorSource:
    """The fallback source."""

    name = Source.MIRROR

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def latest(self, game: str) -> Draw:
        rules_for(game)
        return parse(http.get_json(url_for(game), self._client), game)

    def contest(self, game: str, number: int) -> Draw:
        rules_for(game)
        return parse(http.get_json(url_for(game, number), self._client), game)
