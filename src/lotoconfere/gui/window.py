"""The window: a lobby of games, and one screen per game.

A game screen holds one or more bets, each on its own volante, because a paper
ticket usually carries several. They share the contest and the teimosinha, and
are saved, checked and reported as separate bets.

Thin by design. Every question it asks goes to `service.py`, and every value it
shows comes back from there; nothing here decides what a bet is worth, whether
one is legal, or what a contest did. What this module owns is arrangement,
wording lookups and keeping the network off the UI thread.
"""

import threading
from collections.abc import Iterator

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from lotoconfere import __version__, notices
from lotoconfere.core.errors import LotoConfereError
from lotoconfere.core.models import Bet
from lotoconfere.core.rules import GAMES, GameRules, mirror_bet, rules_for, validate_bet
from lotoconfere.gui import results, strings
from lotoconfere.gui.pickers import picker_for
from lotoconfere.gui.theme import Palette, game_colour, icon
from lotoconfere.gui.widgets import Dot, label, pane, row, rule
from lotoconfere.gui.worker import Job
from lotoconfere.service import BetAnswer, ContestResult, SavedBetOutcome, Service
from lotoconfere.store.database import USE_MIRROR, SavedBatch
from lotoconfere.store.transfer import BetFileError, export_bets, import_bets

LOBBY_COLUMNS = 3


def clear(box: QVBoxLayout) -> None:
    """Empty a layout, deleting what was in it."""
    while box.count():
        item = box.takeAt(0)
        if item is None:  # pragma: no cover - takeAt is only None past the end
            break
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def check_all_report(outcomes: list[SavedBetOutcome]) -> str:
    """One line per bet, under its batch's name when the batch holds several."""
    lines: list[str] = []
    for outcome in outcomes:
        state = results.saved_outcome_line(outcome)
        if len(outcome.saved.bets) == 1:
            lines.append(f"{outcome.saved.name}: {state}")
            continue
        if outcome.position == 0:
            lines.append(outcome.saved.name)
        heading = strings.BET_NUMBER.format(number=outcome.position + 1)
        lines.append(f"    {heading}: {state}")
    return "\n".join(lines)


class Lobby(QWidget):
    """The way in: one button per game, and everything at once."""

    def __init__(self, palette: Palette, service: Service) -> None:
        super().__init__()
        self.palette_tokens = palette
        self.service = service
        self.chosen: str = ""

        self.count = label("", "muted")
        grid = QGridLayout()
        grid.setSpacing(10)
        self.buttons: dict[str, QPushButton] = {}
        for index, (key, rules) in enumerate(GAMES.items()):
            grid.addWidget(self._tile(key, rules), index // LOBBY_COLUMNS, index % LOBBY_COLUMNS)

        self.check_all = QPushButton(strings.CHECK_ALL)
        self.about = QPushButton(strings.ABOUT)
        self.settings = QPushButton(strings.SETTINGS)

        box = QVBoxLayout(self)
        box.setContentsMargins(20, 18, 20, 18)
        box.setSpacing(12)
        box.addWidget(label(strings.APP_NAME, "h1"))
        box.addWidget(label(strings.LOBBY_PROMPT, "muted"))
        box.addWidget(rule(palette))
        box.addLayout(grid)
        box.addWidget(rule(palette))
        box.addLayout(row(self.check_all, self.count, spacing=12))
        box.addLayout(row(self.settings, self.about, spacing=8))
        box.addStretch(1)
        self.refresh()

    def _tile(self, key: str, rules: GameRules) -> QPushButton:
        button = QPushButton()
        button.setObjectName("game")
        button.setAccessibleName(rules.name)
        inner = QHBoxLayout(button)
        inner.setContentsMargins(14, 10, 14, 10)
        inner.setSpacing(10)
        inner.addWidget(Dot(game_colour(key, self.palette_tokens)))
        name = label(rules.name)
        name.setStyleSheet("font-size:15px; font-weight:600; background:transparent;")
        inner.addWidget(name)
        inner.addStretch(1)
        self.buttons[key] = button
        return button

    def refresh(self) -> None:
        total = sum(len(saved.bets) for saved in self.service.store.saved_batches())
        self.count.setText(strings.saved_count(total))


class BetLine(QWidget):
    """One bet of several: its heading, its own volante, and what it says about itself.

    The line holds widgets and nothing else. Adding, removing and complaining
    are the screen's business, because only the screen knows the other lines.
    """

    changed = Signal()

    def __init__(self, rules: GameRules, palette: Palette) -> None:
        super().__init__()
        self.rules = rules
        self.heading = label("", "h2")
        self.picker = picker_for(rules, palette)
        self.picker.changed.connect(self._bet_changed)
        self.status = label("", "muted")

        self.clear_button = QPushButton(strings.CLEAR)
        self.clear_button.clicked.connect(self.picker.clear)
        self.mirror = QPushButton(strings.MIRROR_BET)
        self.mirror.setVisible(rules.has_mirror)
        # Icons alone are not enough to say what a button does, so both carry
        # their action in words for screen readers and as a tooltip.
        self.remove = QPushButton()
        self.remove.setIcon(icon("trash", palette.text))
        self.remove.setAccessibleName(strings.REMOVE_BET)
        self.remove.setToolTip(strings.REMOVE_BET)
        self.add = QPushButton("+")
        self.add.setAccessibleName(strings.ADD_BET)
        self.add.setToolTip(strings.ADD_BET)

        frame, box = pane()
        top = row(self.heading, self.clear_button, self.mirror, spacing=8)
        top.addWidget(self.remove)
        top.addWidget(self.add)
        box.addLayout(top)
        box.addWidget(self.picker)
        box.addWidget(self.status)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        self._bet_changed()

    def number(self, position: int) -> None:
        self.heading.setText(strings.BET_NUMBER.format(number=position + 1))

    def bet(self) -> Bet:
        return self.picker.bet()

    def playable(self) -> bool:
        try:
            validate_bet(self.bet())
        except LotoConfereError:
            return False
        return True

    def _bet_changed(self) -> None:
        bet = self.bet()
        try:
            validate_bet(bet)
        except LotoConfereError as error:
            # An empty picker is a volante nobody has touched yet, not a mistake.
            # Greeting someone with a validation error is a poor way to start.
            self.status.setText(
                strings.CHOSEN_COUNT.format(chosen=bet.size, needed=self.rules.minimum_bet_size)
                if bet.size == 0
                else str(error)
            )
        else:
            self.status.setText(
                strings.CHOSEN_COUNT.format(chosen=bet.size, needed=self.rules.minimum_bet_size)
            )
        self.changed.emit()


class GameScreen(QWidget):
    """One game: fill in one or more bets, choose a contest, read what happened."""

    def __init__(self, rules: GameRules, palette: Palette, service: Service) -> None:
        super().__init__()
        self.rules = rules
        self.palette_tokens = palette
        self.service = service
        self.job: Job | None = None
        self.lines: list[BetLine] = []

        self._build_controls()
        self._build_layout()
        self.reload_saved()
        self._set_line_count(1)
        # Focus starts where the work starts, not on the way out.
        self.lines[0].picker.setFocus()

    def _build_controls(self) -> None:
        """Every widget on the screen, before anything is arranged."""
        self.back = QPushButton(strings.BACK)
        self.saved = QComboBox()
        self.saved.setMinimumWidth(220)
        self.saved.currentIndexChanged.connect(self._saved_chosen)
        self.status = label("", "muted")

        self.contest = QLineEdit()
        self.contest.setFixedWidth(90)
        self.contest.setPlaceholderText(strings.LATEST_CONTEST)
        # The spin box's own arrows are hidden: under the Windows 11 style the up
        # arrow sat over the number, where the text field took most of its clicks.
        self.count = QSpinBox()
        self.count.setRange(1, 100)
        self.count.setFixedWidth(64)
        self.count.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.fewer = QPushButton()
        self.fewer.setIcon(icon("step-down", self.palette_tokens.text))
        self.fewer.setAccessibleName(strings.FEWER_CONTESTS)
        self.fewer.setToolTip(strings.FEWER_CONTESTS)
        self.fewer.clicked.connect(self.count.stepDown)
        self.more = QPushButton()
        self.more.setIcon(icon("step-up", self.palette_tokens.text))
        self.more.setAccessibleName(strings.MORE_CONTESTS)
        self.more.setToolTip(strings.MORE_CONTESTS)
        self.more.clicked.connect(self.count.stepUp)
        self.count.valueChanged.connect(self._count_limits)
        self._count_limits()
        self.go = QPushButton(strings.CHECK)
        self.go.setObjectName("go")
        self.go.clicked.connect(self.start)
        self.stop = QPushButton(strings.CANCEL)
        self.stop.clicked.connect(self.cancel)
        self.stop.setVisible(False)

        self.save = QPushButton(strings.SAVE_BET)
        self.save.clicked.connect(self._save)
        self.delete = QPushButton(strings.DELETE_BET)
        self.delete.clicked.connect(self._delete)

    def _build_layout(self) -> None:
        """The bets and their results scroll together; the actions stay put."""
        self.lines_box = QVBoxLayout()
        self.lines_box.setSpacing(10)
        self.results_box = QVBoxLayout()
        self.results_box.setSpacing(10)
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(10)
        # Without this the scroll area squeezes the volantes to fit the window
        # instead of scrolling; a ball grid pressed flat is unreadable.
        content.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        content.addLayout(self.lines_box)
        content.addLayout(self.results_box)
        content.addStretch(1)
        holder = QWidget()
        holder.setLayout(content)
        self.scroller = QScrollArea()
        self.scroller.setWidgetResizable(True)
        self.scroller.setWidget(holder)

        box = QVBoxLayout(self)
        box.setContentsMargins(20, 18, 20, 18)
        box.setSpacing(10)
        box.addLayout(row(label(self.rules.name, "h1"), self.back, spacing=10))
        box.addLayout(row(label(strings.SAVED_BET, "label"), self.saved, spacing=8))
        box.addWidget(self.scroller, stretch=1)
        box.addLayout(row(self.save, self.delete, self.status, spacing=8))
        box.addLayout(
            row(
                label(strings.CONTEST, "label"),
                self.contest,
                label(strings.TEIMOSINHA, "label"),
                self.count,
                self.fewer,
                self.more,
                label(strings.CONTESTS_WORD, "muted"),
                self.go,
                self.stop,
                spacing=8,
            )
        )

    # --- the bets on screen ------------------------------------------------------

    def bets(self) -> list[Bet]:
        return [line.bet() for line in self.lines]

    def add_line(self) -> BetLine:
        line = BetLine(self.rules, self.palette_tokens)
        line.changed.connect(self._bets_changed)
        line.add.clicked.connect(self.add_line)
        line.remove.clicked.connect(lambda _=False, gone=line: self.remove_line(gone))
        line.mirror.clicked.connect(lambda _=False, which=line: self._mirror(which))
        self.lines.append(line)
        self.lines_box.addWidget(line)
        self._renumber()
        return line

    def remove_line(self, line: BetLine) -> None:
        if len(self.lines) == 1:
            return
        self.lines.remove(line)
        self.lines_box.removeWidget(line)
        line.deleteLater()
        self._renumber()

    def _set_line_count(self, wanted: int) -> None:
        while len(self.lines) > wanted:
            self.remove_line(self.lines[-1])
        while len(self.lines) < wanted:
            self.add_line()
        for line in self.lines:
            line.picker.clear()

    def _renumber(self) -> None:
        """Headings follow position, and + sits on the last line only."""
        for position, line in enumerate(self.lines):
            line.number(position)
            line.remove.setVisible(len(self.lines) > 1)
            line.add.setVisible(line is self.lines[-1])
        self._bets_changed()

    def _count_limits(self) -> None:
        self.fewer.setEnabled(self.count.value() > self.count.minimum())
        self.more.setEnabled(self.count.value() < self.count.maximum())

    def _bets_changed(self) -> None:
        self.go.setEnabled(all(line.playable() for line in self.lines))

    def _first_unplayable(self) -> str | None:
        """Why the bets cannot be used, naming the line, or None when all can."""
        for position, line in enumerate(self.lines):
            try:
                validate_bet(line.bet())
            except LotoConfereError as error:
                heading = strings.BET_NUMBER.format(number=position + 1)
                return strings.INVALID_BET.format(reason=f"{heading}: {error}")
        return None

    # --- saved bets ------------------------------------------------------------

    def reload_saved(self, select: int | None = None) -> None:
        self.saved.blockSignals(True)
        self.saved.clear()
        self.saved.addItem(strings.NEW_BET, None)
        self.mine: list[SavedBatch] = [
            s for s in self.service.store.saved_batches() if s.game == self.rules.key
        ]
        for entry in self.mine:
            self.saved.addItem(entry.name, entry.id)
        if select is not None:
            self.saved.setCurrentIndex(max(self.saved.findData(select), 0))
        self.saved.blockSignals(False)

    def current_saved(self) -> SavedBatch | None:
        wanted = self.saved.currentData()
        return next((s for s in self.mine if s.id == wanted), None)

    def _saved_chosen(self) -> None:
        entry = self.current_saved()
        if entry is None:
            self._set_line_count(1)
            return
        self._set_line_count(len(entry.bets))
        for line, bet in zip(self.lines, entry.bets, strict=True):
            line.picker.load(bet)
        if entry.run_start is not None and entry.run_count is not None:
            self.contest.setText(str(entry.run_start))
            self.count.setValue(entry.run_count)

    def _save(self) -> None:
        problem = self._first_unplayable()
        if problem is not None:
            self._complain(problem)
            return
        existing = self.current_saved()
        suggestion = existing.name if existing else ""
        name, agreed = QInputDialog.getText(
            self, strings.SAVE_BET, strings.BET_NAME, QLineEdit.EchoMode.Normal, suggestion
        )
        if not agreed:
            return
        if not name.strip():
            self._complain(strings.NAME_REQUIRED)
            return
        start, count = self._run_wanted()
        # The same name updates what was opened; a new name saves a new batch
        # and leaves the old one as it was, which is how "save as" works here.
        if existing is not None and existing.name == name.strip():
            self.service.store.update_batch(existing.id, name.strip(), self.bets(), start, count)
            saved_id = existing.id
        else:
            saved_id = self.service.store.save_batch(name.strip(), self.bets(), start, count)
        self.reload_saved(select=saved_id)
        self.status.setText(strings.BET_SAVED)

    def _delete(self) -> None:
        entry = self.current_saved()
        if entry is None:
            return
        self.service.store.delete_batch(entry.id)
        self.reload_saved()
        self._set_line_count(1)
        self.status.setText(strings.BET_DELETED)

    def _mirror(self, line: BetLine) -> None:
        try:
            line.picker.load(mirror_bet(line.bet()))
        except LotoConfereError as error:
            self._complain(strings.INVALID_BET.format(reason=error))

    # --- checking ----------------------------------------------------------------

    def _run_wanted(self) -> tuple[int | None, int | None]:
        text = self.contest.text().strip()
        if not text.isdigit():
            return None, None
        count = self.count.value()
        return int(text), (count if count > 1 else None)

    def start(self) -> None:
        problem = self._first_unplayable()
        if problem is not None:
            self._complain(problem)
            return

        bets = self.bets()
        clear(self.results_box)
        self.checked: list[BetAnswer] = []
        self.go.setVisible(False)
        self.stop.setVisible(True)
        self.status.setText(strings.CHECKING)

        start, count = self._run_wanted()
        self.job = Job(lambda cancel: self._produce(bets, start, count, cancel))
        self.job.worker.found.connect(self._one_result)
        self.job.worker.failed.connect(self._complain)
        self.job.worker.finished.connect(self._done)
        self.job.start()

    def _produce(
        self, bets: list[Bet], start: int | None, count: int | None, cancel: threading.Event
    ) -> Iterator[BetAnswer]:
        """Each bet in turn. The second bet onwards reads its draws from the cache."""
        for position, bet in enumerate(bets):
            if cancel.is_set():
                return
            for answer in self._produce_one(bet, start, count, cancel):
                yield BetAnswer(position=position, answer=answer)

    def _produce_one(
        self, bet: Bet, start: int | None, count: int | None, cancel: threading.Event
    ) -> Iterator[ContestResult]:
        if start is not None and count is not None:
            yield from self.service.iter_run(bet, start, count, cancel)
            return
        contest = start if start is not None else self.service.latest_contest(bet.game)
        if contest is None:
            yield ContestResult(
                contest=0,
                outcome=self.service.check_one(bet, 0).outcome,
                reason=strings.NEVER_UPDATED,
            )
            return
        yield self.service.check_one(bet, contest)

    def _one_result(self, found: BetAnswer) -> None:
        first_of_bet = not self.checked or self.checked[-1].position != found.position
        self.checked.append(found)
        heading = None
        if first_of_bet and len(self.lines) > 1:
            heading = label(strings.BET_NUMBER.format(number=found.position + 1), "h2")
            self.results_box.addWidget(heading)
        block = results.contest_block(found.answer, self.palette_tokens)
        self.results_box.addWidget(block)
        if len(self.checked) == 1:
            # Several volantes push the results out of sight, so the first one
            # is brought to the top rather than left for the person to find.
            # Deferred, because the new widget has no position until the layout
            # has run.
            top = heading or block
            QTimer.singleShot(0, lambda: self._scroll_to(top))

    def _scroll_to(self, widget: QWidget) -> None:
        self.scroller.verticalScrollBar().setValue(widget.y())

    def _done(self) -> None:
        self.go.setVisible(True)
        self.stop.setVisible(False)
        last = self.service.store.last_updated(self.rules.key)
        self.status.setText(
            strings.OFFLINE_NOTICE.format(when=strings.moment(last))
            if last
            else strings.NEVER_UPDATED
        )
        self._bets_changed()

    def cancel(self) -> None:
        if self.job is not None:
            self.job.stop()
        self.status.setText(strings.RUN_CANCELLED)
        self._done()

    def _complain(self, message: str) -> None:
        QMessageBox.warning(self, strings.ERROR_TITLE, message)


class AboutBox(QDialog):
    """Who made it, what it is not, and the licences it ships."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(strings.ABOUT)
        box = QVBoxLayout(self)
        box.setSpacing(10)
        box.addWidget(label(strings.APP_NAME, "h1"))
        box.addWidget(label(strings.ABOUT_VERSION.format(version=__version__), "muted"))
        box.addWidget(label(strings.ABOUT_DISCLAIMER))
        box.addWidget(label(strings.ABOUT_RELEASES, "muted"))
        box.addWidget(label(strings.ABOUT_LICENCE, "muted"))
        box.addWidget(label(strings.ABOUT_COMPONENTS, "label"))

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            "\n\n".join(f"{n.component} — {n.licence}\n{n.path.name}" for n in notices.NOTICES)
        )
        box.addWidget(text)
        close = QPushButton("Fechar")
        close.clicked.connect(self.accept)
        box.addLayout(row(close))


class SettingsBox(QDialog):
    """The few choices there are. Everything else is a decision, not an option."""

    def __init__(self, service: Service, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.setWindowTitle(strings.SETTINGS)
        self.mirror = QCheckBox(strings.USE_MIRROR_LABEL)
        self.mirror.setChecked(service.store.flag(USE_MIRROR))
        self.mirror.toggled.connect(lambda on: service.store.set_flag(USE_MIRROR, on))

        box = QVBoxLayout(self)
        box.setSpacing(10)
        box.addWidget(self.mirror)
        box.addWidget(label(strings.USE_MIRROR_HELP, "muted"))
        close = QPushButton("Fechar")
        close.clicked.connect(self.accept)
        box.addLayout(row(close))


class MainWindow(QMainWindow):
    """Holds the lobby and whichever game screen is open."""

    def __init__(self, service: Service, palette: Palette) -> None:
        super().__init__()
        self.service = service
        self.palette_tokens = palette
        self.setWindowTitle(strings.APP_NAME)
        self.resize(820, 780)

        self.stack = QStackedWidget()
        self.lobby = Lobby(palette, service)
        self.stack.addWidget(self.lobby)
        self.setCentralWidget(self.stack)

        for key, button in self.lobby.buttons.items():
            button.clicked.connect(lambda _=False, k=key: self.open_game(k))
        self.lobby.about.clicked.connect(lambda: AboutBox(self).exec())
        self.lobby.settings.clicked.connect(lambda: SettingsBox(self.service, self).exec())
        self.lobby.check_all.clicked.connect(self.check_everything)

        self.screens: dict[str, GameScreen] = {}

    def open_game(self, key: str) -> None:
        screen = self.screens.get(key)
        if screen is None:
            screen = GameScreen(rules_for(key), self.palette_tokens, self.service)
            screen.back.clicked.connect(self.show_lobby)
            self.screens[key] = screen
            self.stack.addWidget(screen)
        screen.reload_saved()
        self.stack.setCurrentWidget(screen)

    def show_lobby(self) -> None:
        self.lobby.refresh()
        self.stack.setCurrentWidget(self.lobby)

    def check_everything(self) -> None:
        """Every saved bet at once, reported in one dialog."""
        outcomes = self.service.check_all()
        if not outcomes:
            QMessageBox.information(self, strings.CHECK_ALL, strings.SAVED_COUNT_NONE)
            return
        QMessageBox.information(self, strings.CHECK_ALL, check_all_report(outcomes))

    # --- import and export ---------------------------------------------------------

    def export_saved(self, path: str) -> None:
        try:
            text = export_bets(self.service.store.saved_batches())
            with open(path, "w", encoding="utf-8") as handle:  # noqa: PTH123
                handle.write(text)
        except OSError as error:
            QMessageBox.warning(
                self, strings.ERROR_TITLE, strings.EXPORT_FAILED.format(reason=error)
            )

    def import_saved(self, path: str) -> int:
        try:
            with open(path, "rb") as handle:  # noqa: PTH123
                imported = import_bets(handle.read())
        except (OSError, BetFileError) as error:
            QMessageBox.warning(
                self, strings.ERROR_TITLE, strings.IMPORT_FAILED.format(reason=error)
            )
            return 0
        for entry in imported:
            self.service.store.save_batch(entry.name, entry.bets, entry.run_start, entry.run_count)
        self.lobby.refresh()
        return len(imported)

    def ask_to_export(self) -> None:  # pragma: no cover - opens a native dialog
        path, _ = QFileDialog.getSaveFileName(
            self, strings.EXPORT_BETS, "apostas.json", "JSON (*.json)"
        )
        if path:
            self.export_saved(path)

    def ask_to_import(self) -> None:  # pragma: no cover - opens a native dialog
        path, _ = QFileDialog.getOpenFileName(self, strings.IMPORT_BETS, "", "JSON (*.json)")
        if path:
            self.import_saved(path)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802 (Qt's name)
        """Escape goes back to the lobby, which is where people expect it."""
        key = getattr(event, "key", lambda: None)()
        if key == Qt.Key.Key_Escape and self.stack.currentWidget() is not self.lobby:
            self.show_lobby()
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]
