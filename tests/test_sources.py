"""Both parsers, against responses the endpoints really sent.

The fixtures under tests/fixtures/ were recorded once by scripts/record_fixtures.py
and are evidence: index.json carries a SHA-256 of each one, and the first test
here fails if a fixture was edited to suit the code.
"""

import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import cast

import httpx
import pytest

from lotoconfere.core.errors import (
    InvalidDrawError,
    SourceUnavailableError,
    UnknownGameError,
)
from lotoconfere.core.models import Source
from lotoconfere.source import caixa, http, mirror, parse
from lotoconfere.source.base import ResultsSource

FIXTURES = Path(__file__).parent / "fixtures"
INDEX = json.loads((FIXTURES / "index.json").read_text(encoding="utf-8"))


def load(name):
    return json.loads((FIXTURES / name).read_bytes())


class FakeStream:
    """Stands in for httpx.Client.stream()'s context manager."""

    def __init__(self, status_code=200, chunks=(b"{}",)):
        self.status_code = status_code
        self._chunks = chunks

    def iter_bytes(self):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeClient:
    def __init__(self, response=None, error=None):
        self._response = response or FakeStream()
        self._error = error
        self.closed = False
        self.urls = []

    def stream(self, _method, url, **_kwargs):
        self.urls.append(url)
        if self._error:
            raise self._error
        return self._response

    def close(self):
        self.closed = True


def as_client(fake: FakeClient) -> httpx.Client:
    """The stub is not an httpx.Client; say so out loud rather than loosening the source."""
    return cast(httpx.Client, fake)


# --- the fixtures are evidence --------------------------------------------------


@pytest.mark.parametrize("name", sorted(INDEX))
def test_every_fixture_matches_the_digest_recorded_when_it_was_fetched(name):
    digest = hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
    assert digest == INDEX[name]["sha256"], f"{name} was edited after it was recorded"


@pytest.mark.parametrize("name", sorted(INDEX))
def test_every_fixture_says_where_and_when_it_came_from(name):
    entry = INDEX[name]
    assert entry["source"] in {"caixa", "mirror"}
    assert entry["url"].startswith("https://")
    assert date.fromisoformat(entry["fetched_on"]) <= date.today()


# --- Caixa ----------------------------------------------------------------------


def test_caixa_parses_a_real_contest():
    draw = caixa.parse(load("caixa_megasena_3062.json"), "megasena")
    assert draw.contest == 3062
    assert draw.numbers == (5, 9, 11, 17, 18, 38)
    assert draw.drawn_on == date(2026, 9, 24)
    assert draw.source is Source.CAIXA


def test_caixa_reads_the_published_prize_table():
    draw = caixa.parse(load("caixa_megasena_3062.json"), "megasena")
    assert draw.prizes is not None
    sena, quina, quadra = draw.prizes
    assert (sena.faixa, sena.winners, sena.amount) == (1, 0, Decimal("0.0"))
    assert (quina.faixa, quina.winners, quina.amount) == (2, 86, Decimal("19736.75"))
    assert (quadra.faixa, quadra.winners, quadra.amount) == (3, 5065, Decimal("552.38"))


def test_a_published_table_with_no_winner_is_not_an_unpublished_table():
    # The sena had no winner and Caixa published that. Zero here is an answer.
    draw = caixa.parse(load("caixa_megasena_3062.json"), "megasena")
    assert draw.prize_table_published is True
    assert draw.prizes is not None
    assert draw.prizes[0].amount == 0


def test_an_absent_prize_table_reads_as_unpublished():
    payload = load("caixa_megasena_3062.json")
    payload["listaRateioPremio"] = []
    draw = caixa.parse(payload, "megasena")
    assert draw.prizes is None
    assert draw.prize_table_published is False


def test_the_nul_string_field_is_present_in_the_fixture_and_ignored():
    # Caixa sends NUL characters where a team or month name would go.
    raw = (FIXTURES / "caixa_megasena_3062.json").read_bytes()
    assert b"\\u0000" in raw or b"\x00" in raw
    caixa.parse(load("caixa_megasena_3062.json"), "megasena")  # parses anyway


def test_the_special_contest_flag_is_ignored():
    # It is 1 on this ordinary contest; nothing may depend on it.
    payload = load("caixa_megasena_3062.json")
    assert payload["indicadorConcursoEspecial"] == 1
    payload["indicadorConcursoEspecial"] = 0
    assert caixa.parse(payload, "megasena").contest == 3062


def test_caixa_url_shapes():
    assert caixa.url_for("megasena").endswith("/megasena/")
    assert caixa.url_for("megasena", 3062).endswith("/megasena/3062")


# --- the mirror -----------------------------------------------------------------


def test_the_mirror_parses_the_same_contest_into_the_same_draw():
    from_caixa = caixa.parse(load("caixa_megasena_3062.json"), "megasena")
    from_mirror = mirror.parse(load("mirror_megasena_3062.json"), "megasena")
    assert from_mirror.numbers == from_caixa.numbers
    assert from_mirror.contest == from_caixa.contest
    assert from_mirror.drawn_on == from_caixa.drawn_on
    assert from_mirror.prizes == from_caixa.prizes
    assert from_mirror.source is Source.MIRROR  # and it says so


def test_mirror_url_shapes():
    assert mirror.url_for("megasena").endswith("/megasena/latest")
    assert mirror.url_for("megasena", 3062).endswith("/megasena/3062")


# --- what the parsers refuse ----------------------------------------------------


@pytest.mark.parametrize("parser", [caixa.parse, mirror.parse])
def test_a_response_that_is_not_an_object_is_refused(parser):
    with pytest.raises(InvalidDrawError, match="formato inesperado"):
        parser([1, 2, 3], "megasena")


def test_a_missing_field_is_refused():
    payload = load("caixa_megasena_3062.json")
    del payload["listaDezenas"]
    with pytest.raises(InvalidDrawError, match="listaDezenas"):
        caixa.parse(payload, "megasena")


def test_a_draw_that_breaks_the_rules_is_rejected_not_repaired():
    payload = load("caixa_megasena_3062.json")
    payload["listaDezenas"] = ["05", "09", "11", "17", "18", "99"]
    with pytest.raises(InvalidDrawError, match="numeros vao de"):
        caixa.parse(payload, "megasena")


def test_a_short_draw_is_rejected():
    payload = load("caixa_megasena_3062.json")
    payload["listaDezenas"] = ["05", "09"]
    with pytest.raises(InvalidDrawError, match="6 numeros"):
        caixa.parse(payload, "megasena")


@pytest.mark.parametrize("bad", ["24-09-2026", "", None, 20260924])
def test_a_date_that_is_not_ddmmyyyy_is_refused(bad):
    payload = load("caixa_megasena_3062.json")
    payload["dataApuracao"] = bad
    with pytest.raises(InvalidDrawError, match="data"):
        caixa.parse(payload, "megasena")


@pytest.mark.parametrize("bad", ["cinco", None, True, {"a": 1}])
def test_a_dezena_that_is_not_a_number_is_refused(bad):
    payload = load("caixa_megasena_3062.json")
    payload["listaDezenas"] = ["05", "09", "11", "17", "18", bad]
    with pytest.raises(InvalidDrawError, match="dezena invalida"):
        caixa.parse(payload, "megasena")


@pytest.mark.parametrize("bad", ["abc", None, True])
def test_a_contest_number_that_is_not_a_number_is_refused(bad):
    payload = load("caixa_megasena_3062.json")
    payload["numero"] = bad
    with pytest.raises(InvalidDrawError, match="concurso invalido"):
        caixa.parse(payload, "megasena")


def test_a_reordered_prize_table_is_refused():
    # The label is what catches it: position says sena, the row says 4 acertos.
    payload = load("caixa_megasena_3062.json")
    payload["listaRateioPremio"] = list(reversed(payload["listaRateioPremio"]))
    with pytest.raises(InvalidDrawError, match="acertos eram esperados"):
        caixa.parse(payload, "megasena")


def test_a_prize_table_with_the_wrong_number_of_tiers_is_refused():
    payload = load("caixa_megasena_3062.json")
    payload["listaRateioPremio"] = payload["listaRateioPremio"][:2]
    with pytest.raises(InvalidDrawError, match="faixas"):
        caixa.parse(payload, "megasena")


def test_a_prize_row_that_is_not_an_object_is_refused():
    payload = load("caixa_megasena_3062.json")
    payload["listaRateioPremio"] = ["6 acertos", "5 acertos", "4 acertos"]
    with pytest.raises(InvalidDrawError, match="faixa de premio"):
        caixa.parse(payload, "megasena")


@pytest.mark.parametrize("bad", ["muito", None, True])
def test_a_prize_value_that_is_not_a_number_is_refused(bad):
    payload = load("caixa_megasena_3062.json")
    payload["listaRateioPremio"][0]["valorPremio"] = bad
    with pytest.raises(InvalidDrawError, match="valor de premio"):
        caixa.parse(payload, "megasena")


@pytest.mark.parametrize("bad", ["muitos", None, 1.5])
def test_a_winner_count_that_is_not_a_whole_number_is_refused(bad):
    payload = load("caixa_megasena_3062.json")
    payload["listaRateioPremio"][0]["numeroDeGanhadores"] = bad
    with pytest.raises(InvalidDrawError, match="ganhadores"):
        caixa.parse(payload, "megasena")


def test_an_unknown_game_is_refused_before_any_request():
    client = FakeClient()
    with pytest.raises(UnknownGameError):
        caixa.CaixaSource(as_client(client)).latest("lotogato")
    assert client.urls == []  # nothing was asked of the network


# --- the HTTP layer -------------------------------------------------------------


def test_only_the_two_known_hosts_are_allowed():
    http.check_host("https://servicebus2.caixa.gov.br/portaldeloterias/api/megasena/")
    http.check_host("https://loteriascaixa-api.herokuapp.com/api/megasena/latest")
    with pytest.raises(SourceUnavailableError, match="host nao permitido"):
        http.check_host("https://exemplo.invalido/api/megasena/")


def test_a_non_200_is_a_plain_failure_not_a_parsed_body():
    # Caixa answers 500 with a .NET exception dump for an undrawn contest.
    client = FakeClient(FakeStream(status_code=500, chunks=(b'{"exceptionMessage": "..."}',)))
    with pytest.raises(SourceUnavailableError, match="resposta 500"):
        caixa.CaixaSource(as_client(client)).contest("megasena", 99999)


def test_an_oversized_response_is_abandoned():
    client = FakeClient(FakeStream(chunks=(b"z" * 100_000,) * 20))
    with pytest.raises(SourceUnavailableError, match="limite"):
        caixa.CaixaSource(as_client(client)).latest("megasena")


def test_a_body_that_is_not_json_is_refused():
    client = FakeClient(FakeStream(chunks=(b"<html>manutencao</html>",)))
    with pytest.raises(SourceUnavailableError, match="JSON"):
        caixa.CaixaSource(as_client(client)).latest("megasena")


def test_a_certificate_failure_says_so_in_plain_words():
    import ssl

    wrapped = httpx.ConnectError("handshake failed")
    wrapped.__cause__ = ssl.SSLCertVerificationError("unable to get local issuer certificate")
    client = FakeClient(error=wrapped)
    with pytest.raises(SourceUnavailableError, match="conexao segura"):
        caixa.CaixaSource(as_client(client)).latest("megasena")


def test_a_timeout_says_so():
    client = FakeClient(error=httpx.ConnectTimeout("slow"))
    with pytest.raises(SourceUnavailableError, match="nao respondeu a tempo"):
        caixa.CaixaSource(as_client(client)).latest("megasena")


def test_an_ordinary_network_failure_does_not_blame_the_certificate():
    client = FakeClient(error=httpx.ConnectError("no route"))
    with pytest.raises(SourceUnavailableError, match="conectar ao servidor"):
        caixa.CaixaSource(as_client(client)).latest("megasena")


def test_a_client_this_module_opened_is_closed_again(monkeypatch):
    opened = FakeClient(FakeStream(status_code=503))
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: opened)
    with pytest.raises(SourceUnavailableError, match="resposta 503"):
        http.get_json("https://servicebus2.caixa.gov.br/portaldeloterias/api/megasena/")
    assert opened.closed is True


def test_the_source_fetches_through_the_client_it_was_given():
    payload = (FIXTURES / "caixa_megasena_3062.json").read_bytes()
    client = FakeClient(FakeStream(chunks=(payload,)))
    draw = caixa.CaixaSource(as_client(client)).contest("megasena", 3062)
    assert draw.contest == 3062
    assert client.urls == ["https://servicebus2.caixa.gov.br/portaldeloterias/api/megasena/3062"]


def test_the_mirror_fetches_through_its_own_url():
    payload = (FIXTURES / "mirror_megasena_3062.json").read_bytes()
    client = FakeClient(FakeStream(chunks=(payload,)))
    draw = mirror.MirrorSource(as_client(client)).latest("megasena")
    assert draw.source is Source.MIRROR
    assert client.urls == ["https://loteriascaixa-api.herokuapp.com/api/megasena/latest"]


# --- drift ----------------------------------------------------------------------


@pytest.mark.live
def test_the_real_caixa_response_still_parses():
    """Run by hand with `pytest -m live`. Never in CI."""
    draw = caixa.CaixaSource().latest("megasena")
    assert draw.contest > 3000


@pytest.mark.live
def test_the_prize_table_signal_has_not_appeared_yet():
    """Watches for the state ENDPOINT.md says is still unconfirmed.

    If a freshly drawn contest ever comes back without a prize table, this fails
    and the moment gets recorded as a fixture instead of guessed at.
    """
    draw = caixa.CaixaSource().latest("megasena")
    assert draw.prize_table_published, (
        f"contest {draw.contest} has no prize table yet -- record it as a fixture "
        "and update internal_docs/ENDPOINT.md"
    )


def test_the_mirror_can_fetch_one_contest_too():
    payload = (FIXTURES / "mirror_megasena_3062.json").read_bytes()
    client = FakeClient(FakeStream(chunks=(payload,)))
    draw = mirror.MirrorSource(as_client(client)).contest("megasena", 3062)
    assert draw.contest == 3062
    assert client.urls == ["https://loteriascaixa-api.herokuapp.com/api/megasena/3062"]


def test_both_sources_satisfy_the_results_protocol():
    # The one Protocol in the project; it earns its place only if both fit it.
    def use(source: ResultsSource) -> Source:
        return source.name

    assert use(caixa.CaixaSource()) is Source.CAIXA
    assert use(mirror.MirrorSource()) is Source.MIRROR


@pytest.mark.parametrize("value", [None, 123, [], {"a": 1}])
def test_a_field_that_is_not_text_reads_as_absent(value):
    assert parse.text_or_none(value) is None


def test_a_field_of_only_nul_characters_reads_as_absent():
    assert parse.text_or_none(chr(0) * 12) is None
    assert parse.text_or_none("  Flamengo  ") == "Flamengo"


def test_a_dezena_list_that_is_not_a_list_is_refused():
    with pytest.raises(InvalidDrawError, match="lista de dezenas"):
        parse.parse_numbers("05 09 11", 3062)


def test_a_prize_table_that_is_not_a_list_is_refused():
    payload = load("caixa_megasena_3062.json")
    payload["listaRateioPremio"] = {"faixa": 1}
    with pytest.raises(InvalidDrawError, match="tabela de premios"):
        caixa.parse(payload, "megasena")


@pytest.mark.parametrize(
    ("label", "expected"), [("6 acertos", 6), ("Time do Coracao", None), ("", None), (None, None)]
)
def test_a_tier_label_yields_its_number_only_when_it_has_one(label, expected):
    assert parse.hits_in_label(label) == expected


def test_a_tier_without_a_numeric_label_is_accepted_on_position():
    # Games like Timemania label a tier by what it is, not by a hit count.
    payload = load("caixa_megasena_3062.json")
    for row in payload["listaRateioPremio"]:
        row["descricaoFaixa"] = "Faixa especial"
    draw = caixa.parse(payload, "megasena")
    assert draw.prizes is not None
    assert [t.faixa for t in draw.prizes] == [1, 2, 3]
