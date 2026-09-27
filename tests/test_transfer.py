"""Saved bets in and out, and everything an imported file is not allowed to be."""

import json

import pytest

from lotoconfere.core.models import Bet
from lotoconfere.store.database import SavedBet
from lotoconfere.store.transfer import (
    FORMAT,
    FORMAT_KEY,
    MAX_IMPORT_BYTES,
    BetFileError,
    export_bets,
    import_bets,
)

MEGA = Bet(game="megasena", numbers=(5, 9, 11, 17, 18, 38))
SUPER = Bet(game="supersete", columns=tuple((d,) for d in (9, 2, 4, 7, 5, 5, 2)))
MILIONARIA = Bet(game="maismilionaria", numbers=(3, 5, 12, 33, 38, 45), clovers=(3, 6))
TIME = Bet(game="timemania", numbers=tuple(range(1, 11)), extra="CRB /AL")


def saved(bet, name="Minha aposta", run_start=None, run_count=None):
    return SavedBet(id=1, name=name, bet=bet, run_start=run_start, run_count=run_count)


def a_file(**changes):
    row = {
        "nome": "Do trabalho",
        "jogo": "megasena",
        "numeros": [5, 9, 11, 17, 18, 38],
    }
    row.update(changes)
    return json.dumps({FORMAT_KEY: FORMAT, "apostas": [row]})


@pytest.mark.parametrize("bet", [MEGA, SUPER, MILIONARIA, TIME])
def test_every_shape_survives_a_round_trip(bet):
    text = export_bets([saved(bet)])
    back = import_bets(text)
    assert len(back) == 1
    assert back[0].bet == bet
    assert back[0].name == "Minha aposta"


def test_a_teimosinha_survives_a_round_trip():
    text = export_bets([saved(MEGA, run_start=3060, run_count=8)])
    back = import_bets(text)
    assert (back[0].run_start, back[0].run_count) == (3060, 8)


def test_an_empty_list_is_fine():
    assert import_bets(export_bets([])) == []


def test_bytes_are_accepted_as_well_as_text():
    assert len(import_bets(export_bets([saved(MEGA)]).encode("utf-8"))) == 1


# --- what an imported file is not allowed to be ------------------------------


def test_a_file_too_large_is_refused_before_it_is_parsed():
    with pytest.raises(BetFileError, match="grande demais"):
        import_bets(b"{" + b" " * MAX_IMPORT_BYTES)


def test_something_that_is_not_json_is_refused():
    with pytest.raises(BetFileError, match="formato"):
        import_bets("nao sou json")


def test_bytes_that_are_not_utf8_are_refused():
    with pytest.raises(BetFileError, match="formato"):
        import_bets(b"\xff\xfe\x00nonsense")


def test_json_that_is_not_a_bet_file_is_refused():
    with pytest.raises(BetFileError, match="exportado pelo LotoConfere"):
        import_bets(json.dumps({"alguma": "coisa"}))


def test_a_file_from_another_format_version_is_refused():
    with pytest.raises(BetFileError, match="formato"):
        import_bets(json.dumps({FORMAT_KEY: 99, "apostas": []}))


def test_a_file_without_a_list_of_bets_is_refused():
    with pytest.raises(BetFileError, match="lista de apostas"):
        import_bets(json.dumps({FORMAT_KEY: FORMAT, "apostas": "nenhuma"}))


def test_too_many_bets_is_refused():
    payload = {FORMAT_KEY: FORMAT, "apostas": [{"nome": "x"}] * 10_001}
    with pytest.raises(BetFileError, match="apostas demais"):
        import_bets(json.dumps(payload))


def test_a_bet_that_is_not_an_object_is_refused():
    with pytest.raises(BetFileError, match="formato inesperado"):
        import_bets(json.dumps({FORMAT_KEY: FORMAT, "apostas": ["uma aposta"]}))


@pytest.mark.parametrize("name", [None, "", "   ", 42])
def test_a_bet_without_a_usable_name_is_refused(name):
    with pytest.raises(BetFileError, match="falta o nome"):
        import_bets(a_file(nome=name))


def test_an_absurdly_long_name_is_refused():
    with pytest.raises(BetFileError, match="longo demais"):
        import_bets(a_file(nome="a" * 500))


def test_a_bet_without_a_game_is_refused():
    with pytest.raises(BetFileError, match="falta o jogo"):
        import_bets(a_file(jogo=None))


def test_a_bet_naming_a_game_we_do_not_know_is_refused():
    with pytest.raises(BetFileError, match="jogo desconhecido"):
        import_bets(a_file(jogo="lotogato"))


def test_a_bet_that_breaks_its_games_rules_is_refused_by_name():
    # The file is well formed; the bet is not playable. Both are refusals, and
    # the message says which bet so it can be fixed.
    with pytest.raises(BetFileError, match="Do trabalho"):
        import_bets(a_file(numeros=[1, 2, 3]))


def test_a_number_out_of_range_is_refused():
    with pytest.raises(BetFileError, match="numeros vao de"):
        import_bets(a_file(numeros=[1, 2, 3, 4, 5, 99]))


@pytest.mark.parametrize("numeros", ["cinco", {"a": 1}])
def test_numbers_in_the_wrong_shape_are_refused(numeros):
    with pytest.raises(BetFileError, match="formato inesperado"):
        import_bets(a_file(numeros=numeros))


@pytest.mark.parametrize("bad", ["5", True, 1.5, None])
def test_a_number_that_is_not_a_whole_number_is_refused(bad):
    with pytest.raises(BetFileError, match="valor invalido"):
        import_bets(a_file(numeros=[5, 9, 11, 17, 18, bad]))


def test_columns_in_the_wrong_shape_are_refused():
    with pytest.raises(BetFileError, match="colunas em formato"):
        import_bets(a_file(jogo="supersete", numeros=[], colunas="nove"))


def test_an_extra_field_that_is_not_text_is_refused():
    with pytest.raises(BetFileError, match="campo extra"):
        import_bets(a_file(extra=7))


def test_an_extra_field_of_only_spaces_reads_as_absent():
    # Which then fails validation for a game that needs one, rather than being
    # saved as a team called "   ".
    with pytest.raises(BetFileError, match="Time do Coracao"):
        import_bets(a_file(jogo="timemania", numeros=list(range(1, 11)), extra="   "))


@pytest.mark.parametrize("bad", [0, -3, "tres", True, 1.5])
def test_an_impossible_teimosinha_is_refused(bad):
    with pytest.raises(BetFileError, match="teimosinha invalida"):
        import_bets(a_file(teimosinha_inicio=bad))


def test_a_bet_file_cannot_smuggle_in_a_host_or_a_path():
    # A bet is numbers, a game and a name. Anything else in the file is ignored,
    # never acted on.
    text = a_file(url="https://exemplo.invalido/x", caminho="C:/Windows/System32")
    imported = import_bets(text)
    assert imported[0].bet.game == "megasena"
    assert not hasattr(imported[0], "url")
