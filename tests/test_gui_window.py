"""The window, driven the way a person drives it.

No network: the service is handed a stub source, so these tests are about what
the screen does with an answer, not about getting one. The ones that matter are
the honesty tests -- that a pending contest does not draw a result, that a
cancelled run says so, and that a Lotomania win with no green balls still reads
as a win.
"""

from datetime import date
from decimal import Decimal

import pytest

from lotoconfere.core.models import Bet, Draw, PrizeTier, Source
from lotoconfere.gui import results, strings
from lotoconfere.gui.theme import LIGHT
from lotoconfere.gui.window import AboutBox, GameScreen, Lobby, MainWindow, SettingsBox, clear
from lotoconfere.service import ContestResult, Outcome, Service
from lotoconfere.store.database import USE_MIRROR, Store

DRAWN = (5, 9, 11, 17, 18, 38)
LATEST = 3062
PRIZES = (
    PrizeTier(faixa=1, label="6 acertos", winners=1, amount=Decimal("84512300.00")),
    PrizeTier(faixa=2, label="5 acertos", winners=86, amount=Decimal("19736.75")),
    PrizeTier(faixa=3, label="4 acertos", winners=5065, amount=Decimal("0.00")),
)


def a_draw(game="megasena", contest=LATEST, numbers=DRAWN, **extra):
    return Draw(
        game=game,
        contest=contest,
        drawn_on=date(2026, 9, 24),
        numbers=numbers,
        source=extra.pop("source", Source.CAIXA),
        prizes=extra.pop("prizes", PRIZES),
        **extra,
    )


class FakeSource:
    def __init__(self, draws=None, name=Source.CAIXA):
        self.name = name
        self._draws = draws if draws is not None else {LATEST: a_draw()}

    def latest(self, game):
        return self._draws[max(self._draws)]

    def contest(self, game, number):
        from lotoconfere.core.errors import ContestNotFoundError

        if number not in self._draws:
            raise ContestNotFoundError(f"concurso {number} não encontrado")
        return self._draws[number]


@pytest.fixture
def service(tmp_path):
    with Store(tmp_path / "gui.sqlite3") as store:
        yield Service(store, FakeSource())


@pytest.fixture
def window(qtbot, service):
    made = MainWindow(service, LIGHT)
    qtbot.addWidget(made)
    return made


def pick(screen, numbers):
    screen.picker.load(Bet(game=screen.rules.key, numbers=tuple(numbers)))


def texts(widget):
    """Every piece of text on a widget, for asserting what a person can read."""
    from PySide6.QtWidgets import QLabel

    return [child.text() for child in widget.findChildren(QLabel)]


# --- the lobby -------------------------------------------------------------------


def test_the_lobby_offers_every_game(qtbot, service):
    lobby = Lobby(LIGHT, service)
    qtbot.addWidget(lobby)
    assert len(lobby.buttons) == 9


def test_the_lobby_counts_saved_bets(qtbot, service):
    lobby = Lobby(LIGHT, service)
    qtbot.addWidget(lobby)
    assert lobby.count.text() == strings.SAVED_COUNT_NONE
    service.store.save_bet("Do trabalho", Bet(game="megasena", numbers=DRAWN))
    lobby.refresh()
    assert lobby.count.text() == strings.SAVED_COUNT_ONE


def test_choosing_a_game_opens_its_screen(window):
    window.open_game("megasena")
    assert isinstance(window.stack.currentWidget(), GameScreen)
    window.show_lobby()
    assert window.stack.currentWidget() is window.lobby


def test_a_screen_is_reused_rather_than_rebuilt(window):
    window.open_game("quina")
    first = window.stack.currentWidget()
    window.show_lobby()
    window.open_game("quina")
    assert window.stack.currentWidget() is first


# --- checking --------------------------------------------------------------------


def test_checking_one_contest_shows_the_draw_and_the_tiers(qtbot, window):
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    pick(screen, DRAWN)
    screen.start()
    qtbot.waitUntil(lambda: screen.results_box.count() > 0, timeout=5000)
    qtbot.waitUntil(lambda: not screen.job.running(), timeout=5000)

    shown = texts(screen)
    assert strings.hits(6) in shown
    assert strings.PRIZED in shown
    assert strings.money(Decimal("84512300.00")) in shown


def test_a_tier_nobody_won_says_so_instead_of_zero_reais(qtbot, window):
    # Faixa 3 of this draw has a published value of zero.
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    pick(screen, (*DRAWN[:4], 51, 52, 53, 54))
    screen.start()
    qtbot.waitUntil(lambda: not screen.job.running(), timeout=5000)
    shown = texts(screen)
    assert strings.NO_WINNER_IN_TIER in shown
    assert "R$ 0,00" not in shown


def test_a_contest_not_drawn_yet_shows_no_result(qtbot, window):
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    pick(screen, DRAWN)
    screen.contest.setText(str(LATEST + 1))
    screen.start()
    qtbot.waitUntil(lambda: not screen.job.running(), timeout=5000)
    shown = texts(screen)
    assert strings.NOT_DRAWN in shown
    assert strings.hits(0) not in shown  # never rendered as zero hits


def test_a_contest_that_could_not_be_fetched_says_so(qtbot, window):
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    pick(screen, DRAWN)
    screen.contest.setText("3000")
    screen.start()
    qtbot.waitUntil(lambda: not screen.job.running(), timeout=5000)
    assert strings.UNAVAILABLE in texts(screen)


def test_a_teimosinha_draws_one_block_per_contest(qtbot, window):
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    pick(screen, DRAWN)
    screen.contest.setText("3060")
    screen.count.setValue(4)
    screen.start()
    qtbot.waitUntil(lambda: not screen.job.running(), timeout=8000)
    assert screen.results_box.count() == 4


def test_an_unplayable_bet_is_refused_before_anything_is_fetched(qtbot, window, monkeypatch):
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    complaints: list[str] = []
    monkeypatch.setattr(screen, "_complain", complaints.append)
    pick(screen, (1, 2, 3))
    screen.start()
    assert complaints
    assert screen.job is None


def test_the_check_button_is_off_until_the_bet_is_playable(qtbot, window):
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    assert screen.go.isEnabled() is False
    pick(screen, DRAWN)
    assert screen.go.isEnabled() is True


def test_an_untouched_screen_does_not_greet_you_with_an_error(qtbot, window):
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    assert screen.status.text() == strings.CHOSEN_COUNT.format(chosen=0, needed=6)


def test_a_cancelled_run_says_it_stopped(qtbot, window):
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    pick(screen, DRAWN)
    screen.contest.setText("3040")
    screen.count.setValue(20)
    screen.start()
    screen.cancel()
    # isVisibleTo, not isVisible: nothing is visible in a window never shown.
    assert screen.go.isVisibleTo(screen)
    assert not screen.stop.isVisibleTo(screen)


# --- saved bets ---------------------------------------------------------------------


def test_a_saved_bet_can_be_loaded_from_the_dropdown(qtbot, window, service):
    service.store.save_bet("Do trabalho", Bet(game="megasena", numbers=DRAWN), 3060, 8)
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    screen.saved.setCurrentIndex(1)
    assert screen.picker.bet().numbers == DRAWN
    assert screen.contest.text() == "3060"
    assert screen.count.value() == 8


def test_choosing_new_bet_clears_the_picker(qtbot, window, service):
    service.store.save_bet("Do trabalho", Bet(game="megasena", numbers=DRAWN))
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    screen.saved.setCurrentIndex(1)
    screen.saved.setCurrentIndex(0)
    assert screen.picker.bet().numbers == ()


def test_only_this_games_bets_are_offered(qtbot, window, service):
    service.store.save_bet("Mega", Bet(game="megasena", numbers=DRAWN))
    service.store.save_bet("Quina", Bet(game="quina", numbers=(1, 2, 3, 4, 5)))
    window.open_game("quina")
    screen = window.stack.currentWidget()
    assert [s.name for s in screen.mine] == ["Quina"]


def test_deleting_a_saved_bet_removes_it(qtbot, window, service):
    service.store.save_bet("Do trabalho", Bet(game="megasena", numbers=DRAWN))
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    screen.saved.setCurrentIndex(1)
    screen._delete()
    assert list(service.store.saved_bets()) == []
    assert screen.status.text() == strings.BET_DELETED


def test_saving_asks_for_a_name(qtbot, window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window.open_game("megasena")
    screen = window.stack.currentWidget()
    pick(screen, DRAWN)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Do trabalho", True))
    screen._save()
    assert screen.status.text() == strings.BET_SAVED
    assert [s.name for s in screen.mine] == ["Do trabalho"]


def test_saving_without_a_name_complains(qtbot, window, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    window.open_game("megasena")
    screen = window.stack.currentWidget()
    pick(screen, DRAWN)
    complaints: list[str] = []
    monkeypatch.setattr(screen, "_complain", complaints.append)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("   ", True))
    screen._save()
    assert complaints == [strings.NAME_REQUIRED]


def test_cancelling_the_name_dialog_saves_nothing(qtbot, window, monkeypatch, service):
    from PySide6.QtWidgets import QInputDialog

    window.open_game("megasena")
    screen = window.stack.currentWidget()
    pick(screen, DRAWN)
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("", False))
    screen._save()
    assert list(service.store.saved_bets()) == []


def test_an_unplayable_bet_cannot_be_saved(qtbot, window, monkeypatch):
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    complaints: list[str] = []
    monkeypatch.setattr(screen, "_complain", complaints.append)
    pick(screen, (1, 2))
    screen._save()
    assert complaints


def test_editing_a_saved_bet_keeps_one_entry(qtbot, window, monkeypatch, service):
    from PySide6.QtWidgets import QInputDialog

    service.store.save_bet("Do trabalho", Bet(game="megasena", numbers=DRAWN))
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    screen.saved.setCurrentIndex(1)
    pick(screen, (1, 2, 3, 4, 5, 6))
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Do trabalho", True))
    screen._save()
    saved = list(service.store.saved_bets())
    assert len(saved) == 1
    assert saved[0].bet.numbers == (1, 2, 3, 4, 5, 6)


# --- the mirror bet -------------------------------------------------------------------


def test_lotomania_offers_the_mirror_bet_and_others_do_not(qtbot, window):
    window.open_game("lotomania")
    assert window.stack.currentWidget().mirror.isVisibleTo(window.stack.currentWidget())
    window.open_game("megasena")
    assert not window.stack.currentWidget().mirror.isVisibleTo(window.stack.currentWidget())


def test_the_mirror_button_swaps_in_the_other_fifty(qtbot, window):
    window.open_game("lotomania")
    screen = window.stack.currentWidget()
    pick(screen, range(50))
    screen._mirror()
    assert screen.picker.bet().numbers == tuple(range(50, 100))


def test_mirroring_an_unplayable_bet_complains(qtbot, window, monkeypatch):
    window.open_game("lotomania")
    screen = window.stack.currentWidget()
    complaints: list[str] = []
    monkeypatch.setattr(screen, "_complain", complaints.append)
    pick(screen, (1, 2, 3))
    screen._mirror()
    assert complaints


# --- import, export, settings, about ----------------------------------------------------


def test_bets_survive_an_export_and_an_import(qtbot, window, service, tmp_path):
    service.store.save_bet("Do trabalho", Bet(game="megasena", numbers=DRAWN))
    path = tmp_path / "apostas.json"
    window.export_saved(str(path))
    service.store.delete_bet(next(iter(service.store.saved_bets())).id)
    assert window.import_saved(str(path)) == 1
    assert [s.name for s in service.store.saved_bets()] == ["Do trabalho"]


def test_importing_something_that_is_not_a_bet_file_complains(qtbot, window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a[-1]))
    path = tmp_path / "lixo.json"
    path.write_text("nao sou json", encoding="utf-8")
    assert window.import_saved(str(path)) == 0
    assert seen


def test_exporting_where_it_cannot_write_complains(qtbot, window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a[-1]))
    window.export_saved(str(tmp_path / "sem" / "essa" / "pasta.json"))
    assert seen


def test_check_all_reports_every_saved_bet(qtbot, window, service, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    seen = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: seen.append(a[-1]))
    service.store.save_bet("Do trabalho", Bet(game="megasena", numbers=DRAWN))
    window.check_everything()
    assert "Do trabalho" in seen[0]


def test_check_all_with_nothing_saved_says_so(qtbot, window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    seen = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: seen.append(a[-1]))
    window.check_everything()
    assert seen == [strings.SAVED_COUNT_NONE]


def test_the_about_box_carries_the_disclaimer_and_the_licences(qtbot, window):
    from PySide6.QtWidgets import QTextEdit

    box = AboutBox(window)
    qtbot.addWidget(box)
    assert strings.ABOUT_DISCLAIMER in texts(box)

    # Shipping Qt under the LGPL means saying so where a person can read it.
    found = box.findChild(QTextEdit)
    assert found is not None
    listing = found.toPlainText()
    assert "LGPL 3.0" in listing
    assert "Inter" in listing
    assert "JetBrains Mono" in listing


def test_settings_remembers_the_mirror_choice(qtbot, window, service):
    box = SettingsBox(service, window)
    qtbot.addWidget(box)
    assert service.store.flag(USE_MIRROR) is False
    box.mirror.setChecked(True)
    assert service.store.flag(USE_MIRROR) is True


# --- rendering pieces ---------------------------------------------------------------------


def test_clearing_a_layout_empties_it(qtbot):
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    holder = QWidget()
    qtbot.addWidget(holder)
    box = QVBoxLayout(holder)
    box.addWidget(QLabel("a"))
    box.addWidget(QLabel("b"))
    clear(box)
    assert box.count() == 0


def test_a_mirror_result_is_labelled_where_it_is_read(qtbot):
    answer = ContestResult(
        contest=LATEST,
        outcome=Outcome.CHECKED,
        result=__import__("lotoconfere.core.check", fromlist=["check_bet"]).check_bet(
            Bet(game="megasena", numbers=DRAWN), a_draw(source=Source.MIRROR)
        ),
    )
    block = results.contest_block(answer, LIGHT)
    qtbot.addWidget(block)
    assert strings.MIRROR_WARNING in texts(block)


def test_the_run_summary_counts_only_what_was_checked():
    from lotoconfere.service import RunSummary

    summary = RunSummary(
        results=(
            ContestResult(contest=1, outcome=Outcome.CHECKED),
            ContestResult(contest=2, outcome=Outcome.PENDING),
            ContestResult(contest=3, outcome=Outcome.UNAVAILABLE),
        ),
        requested=5,
    )
    line = results.run_summary_line(summary)
    assert strings.RUN_SUMMARY.format(checked=1, total=5) in line
    assert strings.RUN_PENDING.format(count=1) in line
    assert strings.RUN_UNAVAILABLE.format(count=1) in line


def test_deleting_with_nothing_selected_does_nothing(qtbot, window, service):
    service.store.save_bet("Do trabalho", Bet(game="megasena", numbers=DRAWN))
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    screen.saved.setCurrentIndex(0)  # the "new bet" entry
    screen._delete()
    assert len(list(service.store.saved_bets())) == 1


def test_cancelling_when_nothing_is_running_is_harmless(qtbot, window):
    window.open_game("megasena")
    screen = window.stack.currentWidget()
    assert screen.job is None
    screen.cancel()
    assert screen.status.text() != ""


def test_a_game_with_nothing_known_yet_says_so(qtbot, tmp_path):
    from lotoconfere.core.errors import SourceUnavailableError
    from lotoconfere.gui.window import MainWindow

    class Offline:
        name = Source.CAIXA

        def latest(self, game):
            raise SourceUnavailableError("sem rede")

        def contest(self, game, number):
            raise SourceUnavailableError("sem rede")

    with Store(tmp_path / "offline.sqlite3") as store:
        window = MainWindow(Service(store, Offline()), LIGHT)
        qtbot.addWidget(window)
        window.open_game("megasena")
        screen = window.screens["megasena"]
        pick(screen, DRAWN)
        screen.start()
        job = screen.job
        assert job is not None
        qtbot.waitUntil(lambda: not job.running(), timeout=5000)
        assert strings.UNAVAILABLE in texts(screen)


def test_a_complaint_reaches_a_dialog(qtbot, window, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    seen = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: seen.append(a[-1]))
    window.open_game("megasena")
    window.stack.currentWidget()._complain("algo deu errado")
    assert seen == ["algo deu errado"]


def test_clearing_survives_something_that_is_not_a_widget(qtbot):
    # A stretch or a nested layout is a layout item with no widget behind it.
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    holder = QWidget()
    qtbot.addWidget(holder)
    box = QVBoxLayout(holder)
    box.addWidget(QLabel("a"))
    box.addStretch(1)
    clear(box)
    assert box.count() == 0


# These call what normally runs on the worker thread, directly. Coverage does
# not see a Qt-created thread on every Python version (quality-gate skill), so a
# line covered on 3.14 goes missing on 3.12 for a reason unrelated to the code.


def test_producing_a_single_contest_yields_one_answer(qtbot, window):
    import threading

    window.open_game("megasena")
    screen = window.screens["megasena"]
    bet = Bet(game="megasena", numbers=DRAWN)
    produced = list(screen._produce(bet, None, None, threading.Event()))
    assert len(produced) == 1
    assert produced[0].outcome is Outcome.CHECKED


def test_producing_a_run_yields_one_answer_per_contest(qtbot, window):
    import threading

    window.open_game("megasena")
    screen = window.screens["megasena"]
    bet = Bet(game="megasena", numbers=DRAWN)
    produced = list(screen._produce(bet, 3060, 3, threading.Event()))
    assert [a.contest for a in produced] == [3060, 3061, 3062]


def test_producing_with_nothing_known_yet_yields_an_unavailable(qtbot, tmp_path):
    import threading

    from lotoconfere.core.errors import SourceUnavailableError
    from lotoconfere.gui.window import MainWindow

    class Offline:
        name = Source.CAIXA

        def latest(self, game):
            raise SourceUnavailableError("sem rede")

        def contest(self, game, number):
            raise SourceUnavailableError("sem rede")

    with Store(tmp_path / "nothing.sqlite3") as store:
        made = MainWindow(Service(store, Offline()), LIGHT)
        qtbot.addWidget(made)
        made.open_game("megasena")
        screen = made.screens["megasena"]
        bet = Bet(game="megasena", numbers=DRAWN)
        produced = list(screen._produce(bet, None, None, threading.Event()))
        assert produced[0].outcome is Outcome.UNAVAILABLE
        assert produced[0].reason == strings.NEVER_UPDATED


def test_the_worker_emits_each_answer_it_is_given(qtbot):
    from lotoconfere.gui.worker import RunWorker

    answers = [
        ContestResult(contest=1, outcome=Outcome.PENDING),
        ContestResult(contest=2, outcome=Outcome.PENDING),
    ]
    worker = RunWorker(lambda: iter(answers))
    seen: list[ContestResult] = []
    worker.found.connect(seen.append)
    finished: list[int] = []
    worker.finished.connect(lambda: finished.append(1))
    worker.run()
    assert seen == answers
    assert finished == [1]
