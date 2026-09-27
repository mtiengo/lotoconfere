"""The local database: what it keeps, what it refetches, and what it refuses."""

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from lotoconfere.core.models import Bet, Draw, PrizeTier, Source
from lotoconfere.store.database import SCHEMA_VERSION, Store, StoreError, default_path

PRIZES = (
    PrizeTier(faixa=1, label="6 acertos", winners=0, amount=Decimal("0.0")),
    PrizeTier(faixa=2, label="5 acertos", winners=86, amount=Decimal("19736.75")),
    PrizeTier(faixa=3, label="4 acertos", winners=5065, amount=Decimal("552.38")),
)


def a_draw(contest=3062, prizes=PRIZES, source=Source.CAIXA):
    return Draw(
        game="megasena",
        contest=contest,
        drawn_on=date(2026, 9, 24),
        numbers=(5, 9, 11, 17, 18, 38),
        source=source,
        prizes=prizes,
    )


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "data" / "test.sqlite3") as opened:
        yield opened


def test_it_creates_its_own_directory_and_file(tmp_path):
    path = tmp_path / "nested" / "deeper" / "test.sqlite3"
    with Store(path):
        pass
    assert path.exists()


def test_the_default_path_is_in_the_user_data_directory():
    assert default_path().name == "lotoconfere.sqlite3"


def test_a_draw_survives_a_round_trip(store):
    store.remember(a_draw())
    recalled = store.recall("megasena", 3062)
    assert recalled == a_draw()


def test_money_comes_back_as_the_same_decimal(store):
    store.remember(a_draw())
    recalled = store.recall("megasena", 3062)
    assert recalled is not None
    assert recalled.prizes is not None
    assert recalled.prizes[1].amount == Decimal("19736.75")


def test_which_source_a_result_came_from_is_kept(store):
    store.remember(a_draw(source=Source.MIRROR))
    recalled = store.recall("megasena", 3062)
    assert recalled is not None
    assert recalled.source is Source.MIRROR


def test_a_contest_that_was_never_cached_is_none(store):
    assert store.recall("megasena", 1) is None


def test_a_draw_without_a_prize_table_is_marked_for_refetching(store):
    store.remember(a_draw(prizes=None))
    assert store.incomplete_contests("megasena") == (3062,)
    recalled = store.recall("megasena", 3062)
    assert recalled is not None
    assert recalled.prizes is None


def test_a_complete_draw_is_not_marked_for_refetching(store):
    store.remember(a_draw())
    assert store.incomplete_contests("megasena") == ()


def test_caching_the_same_contest_again_replaces_it(store):
    store.remember(a_draw(prizes=None))
    store.remember(a_draw(prizes=PRIZES))
    assert store.incomplete_contests("megasena") == ()
    recalled = store.recall("megasena", 3062)
    assert recalled is not None
    assert recalled.prizes == PRIZES


def test_the_newest_cached_contest_is_the_offline_horizon(store):
    assert store.latest_cached("megasena") is None
    store.remember(a_draw(contest=3060))
    store.remember(a_draw(contest=3062))
    assert store.latest_cached("megasena") == 3062


def test_a_file_from_a_newer_version_is_refused_not_opened(tmp_path):
    path = tmp_path / "future.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    connection.close()
    with pytest.raises(StoreError, match="versao mais nova"):
        Store(path)


# --- saved bets -------------------------------------------------------------


def test_a_bet_can_be_saved_listed_and_deleted(store):
    bet = Bet(game="megasena", numbers=(1, 2, 3, 4, 5, 6))
    bet_id = store.save_bet("Do trabalho", bet)
    saved = list(store.saved_bets())
    assert len(saved) == 1
    assert saved[0].name == "Do trabalho"
    assert saved[0].bet == bet
    assert saved[0].has_run is False

    store.delete_bet(bet_id)
    assert list(store.saved_bets()) == []


def test_a_saved_bet_can_carry_a_teimosinha_run(store):
    bet = Bet(game="megasena", numbers=(1, 2, 3, 4, 5, 6))
    store.save_bet("Teimosinha", bet, run_start=3060, run_count=8)
    saved = next(iter(store.saved_bets()))
    assert (saved.run_start, saved.run_count) == (3060, 8)
    assert saved.has_run is True


def test_a_saved_bet_can_be_edited(store):
    bet = Bet(game="megasena", numbers=(1, 2, 3, 4, 5, 6))
    bet_id = store.save_bet("Antigo", bet)
    changed = Bet(game="megasena", numbers=(10, 20, 30, 40, 50, 60))
    store.update_bet(bet_id, "Novo", changed, run_start=3070, run_count=4)
    saved = next(iter(store.saved_bets()))
    assert saved.name == "Novo"
    assert saved.bet == changed
    assert (saved.run_start, saved.run_count) == (3070, 4)


def test_a_name_with_a_quote_in_it_is_just_a_name(store):
    # Parameterised queries only; this is the test that says so out loud.
    nasty = "'; DROP TABLE saved_bet; --"
    store.save_bet(nasty, Bet(game="megasena", numbers=(1, 2, 3, 4, 5, 6)))
    saved = list(store.saved_bets())
    assert len(saved) == 1
    assert saved[0].name == nasty
