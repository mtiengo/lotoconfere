"""Drawing each shape's result, and starting the app.

Every game draws differently, and the differences are the parts that can be
wrong quietly: Dupla Sena has two rows, Super Sete's hits are positional, a
+Milionaria trevo is matched separately, and a Lotomania win shows no green at
all.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from lotoconfere.core.check import check_bet
from lotoconfere.core.models import Bet, Draw, PrizeTier, Source
from lotoconfere.gui import results, strings
from lotoconfere.gui.theme import LIGHT
from lotoconfere.gui.widgets import BallButton, label, row
from lotoconfere.service import ContestResult, Outcome, RunSummary
from lotoconfere.source import caixa

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_draw(game):
    return caixa.parse(json.loads((FIXTURES / f"caixa_{game}_latest.json").read_bytes()), game)


def texts(widget):
    return [child.text() for child in widget.findChildren(QLabel)]


def block_for(bet, draw):
    answer = ContestResult(
        contest=draw.contest, outcome=Outcome.CHECKED, result=check_bet(bet, draw)
    )
    return results.contest_block(answer, LIGHT)


def balls(widget):
    """Every ball on screen, with whether it is marked as a hit."""
    return [
        (child.text(), child.accessibleDescription() == "acertou")
        for child in widget.findChildren(QLabel)
        if child.accessibleName()
    ]


# --- one shape at a time -----------------------------------------------------------


def test_a_plain_result_marks_the_numbers_that_hit(qtbot):
    draw = fixture_draw("megasena")
    block = block_for(Bet(game="megasena", numbers=draw.numbers), draw)
    qtbot.addWidget(block)
    assert all(hit for _, hit in balls(block))
    assert strings.hits(6) in texts(block)


def test_dupla_sena_shows_both_draws_with_their_own_labels(qtbot):
    draw = fixture_draw("duplasena")
    block = block_for(Bet(game="duplasena", numbers=draw.numbers), draw)
    qtbot.addWidget(block)
    shown = texts(block)
    assert strings.FIRST_DRAW in shown
    assert strings.SECOND_DRAW in shown
    # Twelve balls: six from each draw.
    assert len(balls(block)) == 12


def test_super_sete_marks_by_position_not_by_value(qtbot):
    # Contest 903 drew 9,2,4,7,5,5,2. Matching only column 1 must light exactly
    # one ball, even though the digit 9 appears nowhere else.
    draw = fixture_draw("supersete")
    columns = ((draw.numbers[0],), *tuple((0 if d != 0 else 1,) for d in draw.numbers[1:]))
    block = block_for(Bet(game="supersete", columns=columns), draw)
    qtbot.addWidget(block)
    assert sum(1 for _, hit in balls(block) if hit) == 1


def test_a_trevo_is_matched_and_shown_separately(qtbot):
    draw = fixture_draw("maismilionaria")
    bet = Bet(game="maismilionaria", numbers=draw.numbers, clovers=draw.clovers)
    block = block_for(bet, draw)
    qtbot.addWidget(block)
    shown = texts(block)
    assert strings.CLOVERS in shown
    # Six numbers plus two trevos, all of them hits.
    assert len([1 for _, hit in balls(block) if hit]) == 8


def test_the_team_is_named_and_marked_when_it_matches(qtbot):
    draw = fixture_draw("timemania")
    missed = tuple(n for n in range(1, 81) if n not in draw.numbers)[:10]
    block = block_for(Bet(game="timemania", numbers=missed, extra=draw.extra), draw)
    qtbot.addWidget(block)
    assert any(draw.extra in line for line in texts(block))
    assert any(strings.PRIZED.lower() in line for line in texts(block))


def test_a_lotomania_win_with_no_hits_still_reads_as_a_win(qtbot):
    # The whole reason the chip exists: not one ball is green here.
    draw = fixture_draw("lotomania")
    missed = tuple(n for n in range(100) if n not in draw.numbers)[:50]
    block = block_for(Bet(game="lotomania", numbers=missed), draw)
    qtbot.addWidget(block)
    assert not any(hit for _, hit in balls(block))
    assert strings.PRIZED in texts(block)
    assert strings.NO_HITS in texts(block)


# --- what a result says about itself ------------------------------------------------


def a_draw(prizes):
    return Draw(
        game="megasena",
        contest=3062,
        drawn_on=fixture_draw("megasena").drawn_on,
        numbers=(5, 9, 11, 17, 18, 38),
        source=Source.CAIXA,
        prizes=prizes,
    )


def test_a_prize_table_not_out_yet_says_so_rather_than_showing_nothing(qtbot):
    block = block_for(Bet(game="megasena", numbers=(5, 9, 11, 17, 18, 38)), a_draw(None))
    qtbot.addWidget(block)
    assert strings.PRIZE_NOT_PUBLISHED in texts(block)


def test_a_published_prize_is_shown_as_money(qtbot):
    prizes = (
        PrizeTier(faixa=1, label="6 acertos", winners=1, amount=Decimal("1000.50")),
        PrizeTier(faixa=2, label="5 acertos", winners=1, amount=Decimal("1.00")),
        PrizeTier(faixa=3, label="4 acertos", winners=1, amount=Decimal("1.00")),
    )
    block = block_for(Bet(game="megasena", numbers=(5, 9, 11, 17, 18, 38)), a_draw(prizes))
    qtbot.addWidget(block)
    assert "R$ 1.000,50" in texts(block)


def test_a_pending_contest_draws_no_numbers(qtbot):
    block = results.contest_block(ContestResult(contest=3063, outcome=Outcome.PENDING), LIGHT)
    qtbot.addWidget(block)
    assert strings.NOT_DRAWN in texts(block)
    assert balls(block) == []


def test_an_unavailable_contest_shows_why(qtbot):
    block = results.contest_block(
        ContestResult(contest=3000, outcome=Outcome.UNAVAILABLE, reason="sem rede"),
        LIGHT,
    )
    qtbot.addWidget(block)
    shown = texts(block)
    assert strings.UNAVAILABLE in shown
    assert "sem rede" in shown


def test_an_unavailable_contest_without_a_reason_still_renders(qtbot):
    block = results.contest_block(ContestResult(contest=3000, outcome=Outcome.UNAVAILABLE), LIGHT)
    qtbot.addWidget(block)
    assert strings.UNAVAILABLE in texts(block)


def test_the_source_is_named_either_way():
    assert results.source_name(Source.CAIXA) == strings.FROM_CAIXA
    assert results.source_name(Source.MIRROR) == strings.FROM_MIRROR


def test_a_finished_run_summary_mentions_only_what_happened():
    summary = RunSummary(results=(ContestResult(contest=1, outcome=Outcome.CHECKED),), requested=1)
    line = results.run_summary_line(summary)
    assert strings.RUN_PENDING.format(count=1) not in line
    assert strings.RUN_UNAVAILABLE.format(count=1) not in line


# --- small pieces ---------------------------------------------------------------------


def test_a_row_takes_layouts_as_well_as_widgets(qtbot):
    holder = QWidget()
    qtbot.addWidget(holder)
    inner = row(label("a"))
    outer = row(label("b"), inner)
    holder.setLayout(outer)
    assert outer.count() >= 2


def test_a_ball_button_paints_itself(qtbot):
    # It is a bare QAbstractButton, so the stylesheet and paintEvent are all
    # there is; grabbing it is what proves the drawing path runs.
    button = BallButton(7, LIGHT)
    qtbot.addWidget(button)
    assert not button.grab().isNull()


def test_a_worker_turns_an_unexpected_failure_into_a_message(qtbot):
    from lotoconfere.gui.worker import RunWorker

    def explode():
        raise RuntimeError("algo quebrou")
        yield  # pragma: no cover - never reached, makes this a generator

    worker = RunWorker(explode)
    seen: list[str] = []
    worker.failed.connect(seen.append)
    worker.run()
    assert seen == ["algo quebrou"]


# --- starting the app --------------------------------------------------------------------


def test_the_app_builds_a_window(qapp, tmp_path, monkeypatch):
    from lotoconfere.gui import app as application
    from lotoconfere.store import database

    monkeypatch.setattr(database, "default_path", lambda: tmp_path / "app.sqlite3")
    window = application.build(qapp)
    window.close()
    assert window.windowTitle() == strings.APP_NAME
    assert application.ICON.is_file()


def test_running_the_app_shows_the_window_and_returns_its_code(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from lotoconfere.gui import app as application
    from lotoconfere.store import database

    monkeypatch.setattr(database, "default_path", lambda: tmp_path / "app.sqlite3")
    monkeypatch.setattr(application, "configure", lambda: tmp_path / "app.log")
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    assert application.run() == 0


def test_escape_goes_back_to_the_lobby(qtbot, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent

    from lotoconfere.gui.window import MainWindow
    from lotoconfere.service import Service
    from lotoconfere.store.database import Store

    with Store(tmp_path / "escape.sqlite3") as store:
        window = MainWindow(Service(store), LIGHT)
        qtbot.addWidget(window)
        window.open_game("quina")
        pressed = QKeyEvent(
            QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
        window.keyPressEvent(pressed)
        assert window.stack.currentWidget() is window.lobby
        # From the lobby it is not a shortcut to anywhere, so it falls through.
        window.keyPressEvent(pressed)
        assert window.stack.currentWidget() is window.lobby


@pytest.mark.parametrize("game", ["megasena", "supersete"])
def test_clearing_a_layout_of_results_leaves_nothing(qtbot, game):
    from lotoconfere.gui.window import clear

    holder = QWidget()
    qtbot.addWidget(holder)
    box = QVBoxLayout(holder)
    draw = fixture_draw(game)
    bet = (
        Bet(game=game, columns=tuple((d,) for d in draw.numbers))
        if game == "supersete"
        else Bet(game=game, numbers=draw.numbers)
    )
    box.addWidget(block_for(bet, draw))
    clear(box)
    assert box.count() == 0


# --- the last few paths -------------------------------------------------------------


def test_clicking_a_number_updates_the_typed_field(qtbot):
    # The grid and the field stay in step whichever one is used.
    from lotoconfere.core.rules import GAMES
    from lotoconfere.gui.pickers import GridPicker

    picker = GridPicker(GAMES["megasena"], LIGHT)
    qtbot.addWidget(picker)
    picker._buttons[7].click()
    assert picker.typed.text() == "07"
    assert picker.chosen() == (7,)


def test_an_extra_picker_loads_a_bet_with_no_extra(qtbot):
    from lotoconfere.core.rules import GAMES
    from lotoconfere.gui.pickers import picker_for

    picker = picker_for(GAMES["diadesorte"], LIGHT)
    qtbot.addWidget(picker)
    picker.load(Bet(game="diadesorte", numbers=tuple(range(1, 8))))
    assert picker.bet().numbers == tuple(range(1, 8))


def test_a_run_summary_counts_the_prized_ones():
    draw = fixture_draw("megasena")
    won = ContestResult(
        contest=draw.contest,
        outcome=Outcome.CHECKED,
        result=check_bet(Bet(game="megasena", numbers=draw.numbers), draw),
    )
    line = results.run_summary_line(RunSummary(results=(won,), requested=1))
    assert strings.RUN_PRIZED.format(count=1) in line


def test_a_font_that_will_not_load_is_counted_honestly(qapp, monkeypatch):
    from PySide6.QtGui import QFontDatabase

    from lotoconfere.gui import theme

    monkeypatch.setattr(QFontDatabase, "addApplicationFont", lambda _: -1)
    assert theme.load_fonts() == 0
