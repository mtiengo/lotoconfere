"""Caixa's own endpoint: the primary source, and the source of truth.

Public but undocumented, so every field is treated as a moving target. What was
observed first-hand, including the parts that lie, is in internal_docs/ENDPOINT.md.
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

BASE_URL = "https://servicebus2.caixa.gov.br/portaldeloterias/api"

FIELDS = PrizeFields(label="descricaoFaixa", winners="numeroDeGanhadores", amount="valorPremio")


def url_for(game: str, number: int | None = None) -> str:
    """Latest, or one contest by number."""
    return f"{BASE_URL}/{game}/" if number is None else f"{BASE_URL}/{game}/{number}"


def parse(payload: object, game: str) -> Draw:
    """One Caixa response into a validated Draw.

    Three fields are deliberately not read, and each has a reason in ENDPOINT.md:
    `indicadorConcursoEspecial` (it was 1 on an ordinary contest),
    `dezenasSorteadasOrdemSorteio` (draw order is not a result), and
    `nomeTimeCoracaoMesSorte` (a run of NUL characters on games with neither).
    """
    if not isinstance(payload, dict):
        raise InvalidDrawError("resposta da Caixa em formato inesperado")
    rules = rules_for(game)
    contest = parse_contest(required(payload, "numero"))
    second = payload.get("listaDezenasSegundoSorteio")
    draw = Draw(
        game=game,
        contest=contest,
        drawn_on=parse_date(required(payload, "dataApuracao", contest), contest),
        numbers=parse_numbers(
            required(payload, "listaDezenas", contest),
            contest,
            keep_order=rules.shape is Shape.COLUMNS,
        ),
        source=Source.CAIXA,
        prizes=parse_prizes(payload.get("listaRateioPremio"), rules, contest, FIELDS),
        second_numbers=None if second is None else parse_numbers(second, contest),
        extra=text_or_none(payload.get("nomeTimeCoracaoMesSorte")),
        clovers=parse_numbers(payload.get("trevosSorteados") or [], contest),
    )
    validate_draw(draw)
    return draw


class CaixaSource:
    """The primary source. Same shape as the mirror, different schema."""

    name = Source.CAIXA

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def latest(self, game: str) -> Draw:
        rules_for(game)  # refuse an unknown game before making a request
        return parse(http.get_json(url_for(game), self._client), game)

    def contest(self, game: str, number: int) -> Draw:
        rules_for(game)
        return parse(http.get_json(url_for(game, number), self._client), game)
