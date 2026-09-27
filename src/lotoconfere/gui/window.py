"""The window: a lobby of games, and one screen per game.

Thin by design. Every question it asks goes to `service.py`, and every value it
shows comes back from there; nothing here decides what a bet is worth, whether
one is legal, or what a contest did. What this module owns is arrangement,
wording lookups and keeping the network off the UI thread.
"""

import threading
from collections.abc import Iterator

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
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
from lotoconfere.gui.pickers import Picker, picker_for
from lotoconfere.gui.theme import Palette, game_colour
from lotoconfere.gui.widgets import Dot, label, pane, row, rule
from lotoconfere.gui.worker import Job
from lotoconfere.service import ContestResult, Service
from lotoconfere.store.database import USE_MIRROR, SavedBet
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
        self.count.setText(strings.saved_count(len(list(self.service.store.saved_bets()))))


class GameScreen(QWidget):
    """One game: pick numbers, choose a contest, read what happened."""

    def __init__(self, rules: GameRules, palette: Palette, service: Service) -> None:
        super().__init__()
        self.rules = rules
        self.palette_tokens = palette
        self.service = service
        self.job: Job | None = None

        self._build_controls()
        self._build_layout()
        self.reload_saved()
        self._bet_changed()
        # Focus starts where the work starts, not on the way out.
        self.picker.setFocus()

    def _build_controls(self) -> None:
        """Every widget on the screen, before anything is arranged."""
        self.back = QPushButton(strings.BACK)
        self.saved = QComboBox()
        self.saved.setMinimumWidth(220)
        self.saved.currentIndexChanged.connect(self._saved_chosen)

        self.picker: Picker = picker_for(self.rules, self.palette_tokens)
        self.picker.changed.connect(self._bet_changed)
        self.status = label("", "muted")

        self.contest = QLineEdit()
        self.contest.setFixedWidth(90)
        self.contest.setPlaceholderText(strings.LATEST_CONTEST)
        self.count = QSpinBox()
        self.count.setRange(1, 100)
        self.count.setFixedWidth(70)
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
        self.clear_button = QPushButton(strings.CLEAR)
        self.clear_button.clicked.connect(self.picker.clear)
        self.mirror = QPushButton(strings.MIRROR_BET)
        self.mirror.clicked.connect(self._mirror)
        self.mirror.setVisible(self.rules.has_mirror)

    def _build_layout(self) -> None:
        """Where each control sits. Picker on top, results underneath."""
        picker_pane, picker_box = pane()
        picker_box.addWidget(self.picker)
        picker_box.addWidget(self.status)

        self.results_box = QVBoxLayout()
        self.results_box.setSpacing(10)
        holder = QWidget()
        holder.setLayout(self.results_box)
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setWidget(holder)

        box = QVBoxLayout(self)
        box.setContentsMargins(20, 18, 20, 18)
        box.setSpacing(10)
        box.addLayout(row(label(self.rules.name, "h1"), self.back, spacing=10))
        box.addLayout(row(label(strings.SAVED_BET, "label"), self.saved, spacing=8))
        box.addWidget(picker_pane)
        box.addLayout(row(self.clear_button, self.mirror, self.save, self.delete, spacing=8))
        box.addLayout(
            row(
                label(strings.CONTEST, "label"),
                self.contest,
                label(strings.TEIMOSINHA, "label"),
                self.count,
                label(strings.CONTESTS_WORD, "muted"),
                self.go,
                self.stop,
                spacing=8,
            )
        )
        box.addWidget(scroller, stretch=1)

    # --- saved bets ------------------------------------------------------------

    def reload_saved(self) -> None:
        self.saved.blockSignals(True)
        self.saved.clear()
        self.saved.addItem(strings.NEW_BET, None)
        self.mine: list[SavedBet] = [
            s for s in self.service.store.saved_bets() if s.bet.game == self.rules.key
        ]
        for entry in self.mine:
            self.saved.addItem(entry.name, entry.id)
        self.saved.blockSignals(False)

    def current_saved(self) -> SavedBet | None:
        wanted = self.saved.currentData()
        return next((s for s in self.mine if s.id == wanted), None)

    def _saved_chosen(self) -> None:
        entry = self.current_saved()
        if entry is None:
            self.picker.clear()
            return
        self.picker.load(entry.bet)
        if entry.run_start is not None and entry.run_count is not None:
            self.contest.setText(str(entry.run_start))
            self.count.setValue(entry.run_count)

    def _save(self) -> None:
        try:
            validate_bet(self.picker.bet())
        except LotoConfereError as error:
            self._complain(strings.INVALID_BET.format(reason=error))
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
        if existing is not None and existing.name == name.strip():
            self.service.store.update_bet(
                existing.id, name.strip(), self.picker.bet(), start, count
            )
        else:
            self.service.store.save_bet(name.strip(), self.picker.bet(), start, count)
        self.reload_saved()
        self.status.setText(strings.BET_SAVED)

    def _delete(self) -> None:
        entry = self.current_saved()
        if entry is None:
            return
        self.service.store.delete_bet(entry.id)
        self.reload_saved()
        self.picker.clear()
        self.status.setText(strings.BET_DELETED)

    def _mirror(self) -> None:
        try:
            self.picker.load(mirror_bet(self.picker.bet()))
        except LotoConfereError as error:
            self._complain(strings.INVALID_BET.format(reason=error))

    # --- checking ----------------------------------------------------------------

    def _bet_changed(self) -> None:
        bet = self.picker.bet()
        try:
            validate_bet(bet)
        except LotoConfereError as error:
            # An empty picker is a screen nobody has touched yet, not a mistake.
            # Greeting someone with a validation error is a poor way to start.
            self.status.setText(
                strings.CHOSEN_COUNT.format(chosen=bet.size, needed=self.rules.minimum_bet_size)
                if bet.size == 0
                else str(error)
            )
            self.go.setEnabled(False)
            return
        self.status.setText(
            strings.CHOSEN_COUNT.format(chosen=bet.size, needed=self.rules.minimum_bet_size)
        )
        self.go.setEnabled(True)

    def _run_wanted(self) -> tuple[int | None, int | None]:
        text = self.contest.text().strip()
        if not text.isdigit():
            return None, None
        count = self.count.value()
        return int(text), (count if count > 1 else None)

    def start(self) -> None:
        bet = self.picker.bet()
        try:
            validate_bet(bet)
        except LotoConfereError as error:
            self._complain(strings.INVALID_BET.format(reason=error))
            return

        clear(self.results_box)
        self.checked: list[ContestResult] = []
        self.go.setVisible(False)
        self.stop.setVisible(True)
        self.status.setText(strings.CHECKING)

        start, count = self._run_wanted()
        self.job = Job(lambda cancel: self._produce(bet, start, count, cancel))
        self.job.worker.found.connect(self._one_result)
        self.job.worker.failed.connect(self._complain)
        self.job.worker.finished.connect(self._done)
        self.job.start()

    def _produce(
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

    def _one_result(self, answer: ContestResult) -> None:
        self.checked.append(answer)
        self.results_box.addWidget(results.contest_block(answer, self.palette_tokens))

    def _done(self) -> None:
        self.go.setVisible(True)
        self.stop.setVisible(False)
        last = self.service.store.last_updated(self.rules.key)
        self.status.setText(
            strings.OFFLINE_NOTICE.format(when=strings.moment(last))
            if last
            else strings.NEVER_UPDATED
        )
        self._bet_changed()

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
        lines = []
        for outcome in outcomes:
            won = len(outcome.winning)
            state = strings.RUN_PRIZED.format(count=won) if won else strings.NO_HITS
            lines.append(f"{outcome.saved.name}: {state}")
        QMessageBox.information(self, strings.CHECK_ALL, "\n".join(lines))

    # --- import and export ---------------------------------------------------------

    def export_saved(self, path: str) -> None:
        try:
            text = export_bets(self.service.store.saved_bets())
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
            self.service.store.save_bet(entry.name, entry.bet, entry.run_start, entry.run_count)
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
