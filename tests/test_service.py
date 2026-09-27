"""The service: single checks, teimosinha runs, and the three honest outcomes.

No network here. The sources are stubs, which is the point -- the rules about
pending and unavailable are decisions the service makes, not things the endpoint
tells it.
"""

from datetime import date
from decimal import Decimal

import pytest

from lotoconfere.core.errors import (
    ContestNotFoundError,
    InvalidBetError,
    SourceUnavailableError,
)
from lotoconfere.core.models import Bet, Draw, PrizeTier, Source
from lotoconfere.service import Outcome, Service
from lotoconfere.store.database import Store

DRAWN = (5, 9, 11, 17, 18, 38)
LATEST = 3062

PRIZES = (
    PrizeTier(faixa=1, label="6 acertos", winners=0, amount=Decimal("0.0")),
    PrizeTier(faixa=2, label="5 acertos", winners=86, amount=Decimal("19736.75")),
    PrizeTier(faixa=3, label="4 acertos", winners=5065, amount=Decimal("552.38")),
)


def a_draw(contest=LATEST, prizes=PRIZES, source=Source.CAIXA, numbers=DRAWN):
    return Draw(
        game="megasena",
        contest=contest,
        drawn_on=date(2026, 9, 24),
        numbers=numbers,
        source=source,
        prizes=prizes,
    )


class FakeSource:
    """A source that answers from a dict, and counts what it was asked."""

    def __init__(self, draws=None, name=Source.CAIXA, latest_contest=LATEST):
        self.name = name
        self._draws = draws if draws is not None else {LATEST: a_draw()}
        self._latest = latest_contest
        self.asked = []

    def latest(self, game):
        self.asked.append("latest")
        if self._latest is None:
            raise SourceUnavailableError("nao foi possivel conectar ao servidor")
        return self._draws[self._latest]

    def contest(self, game, number):
        self.asked.append(number)
        if number not in self._draws:
            raise ContestNotFoundError(f"concurso {number} nao encontrado")
        return self._draws[number]


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "test.sqlite3") as opened:
        yield opened


def a_bet(numbers=DRAWN):
    return Bet(game="megasena", numbers=tuple(numbers))


# --- one contest ----------------------------------------------------------------


def test_a_checked_contest_carries_its_result(store):
    service = Service(store, FakeSource())
    answer = service.check_one(a_bet(), LATEST)
    assert answer.outcome is Outcome.CHECKED
    assert answer.result is not None
    assert answer.result.hit_count == 6
    assert answer.draw is not None


def test_a_contest_after_the_latest_is_pending_and_never_requested(store):
    source = FakeSource()
    service = Service(store, source)
    answer = service.check_one(a_bet(), LATEST + 1)
    assert answer.outcome is Outcome.PENDING
    assert answer.result is None
    # Caixa answers 500 for an undrawn contest, so the question is not asked.
    assert LATEST + 1 not in source.asked


def test_a_contest_that_cannot_be_fetched_is_unavailable_not_zero_hits(store):
    service = Service(store, FakeSource(draws={LATEST: a_draw()}))
    answer = service.check_one(a_bet(), 3000)
    assert answer.outcome is Outcome.UNAVAILABLE
    assert answer.result is None
    assert answer.reason is not None


def test_an_invalid_bet_is_refused_before_anything_is_fetched(store):
    source = FakeSource()
    service = Service(store, source)
    with pytest.raises(InvalidBetError):
        service.check_one(Bet(game="megasena", numbers=(1, 2, 3)), LATEST)
    assert source.asked == []


# --- the cache ------------------------------------------------------------------


def test_a_complete_contest_is_answered_from_the_cache_the_second_time(store):
    source = FakeSource()
    service = Service(store, source)
    service.check_one(a_bet(), LATEST)
    asked_once = list(source.asked)
    service.check_one(a_bet(), LATEST, latest=LATEST)
    assert source.asked == asked_once  # nothing new was requested


def test_a_contest_without_a_prize_table_is_fetched_again(store):
    incomplete = a_draw(prizes=None)
    store.remember(incomplete)
    source = FakeSource(draws={LATEST: a_draw(prizes=PRIZES)})
    service = Service(store, source)
    answer = service.check_one(a_bet(), LATEST, latest=LATEST)
    assert answer.result is not None
    assert answer.result.draw.prize_table_published is True


def test_an_incomplete_cached_draw_is_still_used_when_the_fetch_fails(store):
    store.remember(a_draw(prizes=None))
    service = Service(store, FakeSource(draws={}, latest_contest=None))
    answer = service.check_one(a_bet(), LATEST, latest=LATEST)
    assert answer.outcome is Outcome.CHECKED
    assert answer.result is not None
    assert answer.result.draw.prize_table_published is False


def test_offline_falls_back_to_the_cached_horizon(store):
    store.remember(a_draw())
    service = Service(store, FakeSource(latest_contest=None))
    assert service.latest_contest("megasena") == LATEST


# --- the mirror -----------------------------------------------------------------


def test_the_mirror_is_not_consulted_unless_it_was_supplied(store):
    service = Service(store, FakeSource(draws={}))
    answer = service.check_one(a_bet(), 3000, latest=LATEST)
    assert answer.outcome is Outcome.UNAVAILABLE


def test_the_mirror_answers_when_caixa_fails_and_says_it_was_the_mirror(store):
    mirror = FakeSource(
        draws={3000: a_draw(contest=3000, source=Source.MIRROR)}, name=Source.MIRROR
    )
    service = Service(store, FakeSource(draws={LATEST: a_draw()}), fallback=mirror)
    answer = service.check_one(a_bet(), 3000, latest=LATEST)
    assert answer.outcome is Outcome.CHECKED
    assert answer.draw is not None
    assert answer.draw.source is Source.MIRROR


# --- teimosinha -----------------------------------------------------------------


def test_a_run_reports_every_contest_separately(store):
    draws = {n: a_draw(contest=n) for n in (3060, 3061, 3062)}
    service = Service(store, FakeSource(draws=draws))
    summary = service.check_run(a_bet(), start=3060, count=5)

    assert summary.total == 5
    assert [r.contest for r in summary.results] == [3060, 3061, 3062, 3063, 3064]
    assert len(summary.checked) == 3
    assert len(summary.pending) == 2  # 3063 and 3064 have not been drawn
    assert summary.unavailable == ()


def test_a_run_counts_only_what_was_actually_checked(store):
    # "5 de 8 sorteados" must never include a contest nobody could check.
    draws = {3060: a_draw(contest=3060, numbers=(1, 2, 3, 4, 5, 6)), 3062: a_draw()}
    service = Service(store, FakeSource(draws=draws))
    summary = service.check_run(a_bet(), start=3060, count=4)

    assert len(summary.checked) == 2
    assert len(summary.unavailable) == 1  # 3061 could not be fetched
    assert len(summary.pending) == 1  # 3063 is not drawn
    assert summary.best_hits == 6
    assert [r.contest for r in summary.winning] == [3062]


def test_a_run_with_nothing_checked_has_no_best_hit_count(store):
    service = Service(store, FakeSource(draws={LATEST: a_draw()}))
    summary = service.check_run(a_bet(), start=3000, count=2)
    assert summary.best_hits is None
    assert summary.winning == ()


def test_the_horizon_is_read_once_for_a_whole_run(store):
    source = FakeSource(draws={n: a_draw(contest=n) for n in range(3060, 3063)})
    service = Service(store, source)
    service.check_run(a_bet(), start=3060, count=3)
    assert source.asked.count("latest") == 1


def test_a_run_of_no_contests_is_refused(store):
    service = Service(store, FakeSource())
    with pytest.raises(ValueError, match="pelo menos um concurso"):
        service.check_run(a_bet(), start=3060, count=0)


def test_a_run_can_be_consumed_one_contest_at_a_time(store):
    # The GUI reports progress per contest, so the run has to be iterable.
    draws = {n: a_draw(contest=n) for n in (3060, 3061)}
    service = Service(store, FakeSource(draws=draws, latest_contest=3061))
    seen = [answer.contest for answer in service.iter_run(a_bet(), start=3060, count=2)]
    assert seen == [3060, 3061]


# --- cancelling a long run ------------------------------------------------------


def test_a_cancelled_run_keeps_what_it_found_and_says_it_stopped(store):
    import threading

    draws = {n: a_draw(contest=n) for n in range(3040, 3063)}
    service = Service(store, FakeSource(draws=draws))
    cancel = threading.Event()

    seen = []
    for answer in service.iter_run(a_bet(), start=3040, count=20, cancel=cancel):
        seen.append(answer)
        if len(seen) == 3:
            cancel.set()

    assert len(seen) == 3  # it stopped between contests, not mid-contest


def test_a_cancelled_summary_still_knows_how_many_were_asked_for(store):
    import threading

    draws = {n: a_draw(contest=n) for n in range(3040, 3063)}
    cancel = threading.Event()
    cancel.set()  # cancelled before it starts
    service = Service(store, FakeSource(draws=draws))
    summary = service.check_run(a_bet(), start=3040, count=20, cancel=cancel)

    assert summary.cancelled is True
    assert summary.attempted == 0
    assert summary.total == 20
    # Contests nobody reached are absent, not counted as unavailable.
    assert summary.unavailable == ()


def test_a_run_that_finished_is_not_marked_cancelled(store):
    import threading

    draws = {n: a_draw(contest=n) for n in (3060, 3061)}
    service = Service(store, FakeSource(draws=draws, latest_contest=3061))
    summary = service.check_run(a_bet(), start=3060, count=2, cancel=threading.Event())
    assert summary.cancelled is False
    assert summary.attempted == 2


# --- checking everything at once ------------------------------------------------


def test_check_all_checks_a_plain_bet_against_the_latest_contest(store):
    store.save_bet("Do trabalho", a_bet())
    service = Service(store, FakeSource())
    outcomes = service.check_all()

    assert len(outcomes) == 1
    assert outcomes[0].saved.name == "Do trabalho"
    assert outcomes[0].run is None
    assert outcomes[0].single is not None
    assert outcomes[0].single.outcome is Outcome.CHECKED
    assert len(outcomes[0].winning) == 1


def test_check_all_checks_a_saved_run_across_its_contests(store):
    store.save_bet("Teimosinha", a_bet(), run_start=3060, run_count=4)
    draws = {n: a_draw(contest=n) for n in (3060, 3061, 3062)}
    service = Service(store, FakeSource(draws=draws))
    outcomes = service.check_all()

    assert outcomes[0].single is None
    assert outcomes[0].run is not None
    assert outcomes[0].run.total == 4
    assert len(outcomes[0].results) == 4


def test_check_all_can_be_cancelled_between_bets(store):
    import threading

    for name in ("Uma", "Outra", "Terceira"):
        store.save_bet(name, a_bet())
    cancel = threading.Event()
    cancel.set()
    service = Service(store, FakeSource())
    assert service.check_all(cancel) == []


def test_a_game_with_nothing_known_yet_is_unavailable_not_zero_hits(store):
    store.save_bet("Do trabalho", a_bet())
    service = Service(store, FakeSource(latest_contest=None))
    outcome = service.check_all()[0]
    assert outcome.single is not None
    assert outcome.single.outcome is Outcome.UNAVAILABLE
    assert outcome.winning == ()


def test_the_mirror_turns_itself_on_when_the_preference_says_so(store):
    from lotoconfere.source.mirror import MirrorSource
    from lotoconfere.store.database import USE_MIRROR

    assert Service(store, FakeSource()).fallback is None
    store.set_flag(USE_MIRROR, True)
    assert isinstance(Service(store, FakeSource()).fallback, MirrorSource)
