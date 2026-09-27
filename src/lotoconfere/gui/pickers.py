"""Choosing numbers: one picker per shape, all answering the same two questions.

Every picker offers both ways in: the grid, shaped like the paper volante, and a
typed field for numbers read off a ticket or pasted from somewhere. They stay in
step -- typing ticks the grid, clicking rewrites the field -- because a person
who starts one way should not have to finish that way.

A picker never decides whether a bet is legal. It reports what was chosen and
`lotoconfere.core.rules` says yes or no, so there is one answer to that question
in the app rather than two that can drift apart.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from lotoconfere.core.models import Bet
from lotoconfere.core.rules import GameRules, Shape
from lotoconfere.gui import strings
from lotoconfere.gui.theme import Palette
from lotoconfere.gui.widgets import BallButton, label, row

# Ten to a line reads like the volante; Super Sete's columns are their own shape.
PER_LINE = 10
# Above this many numbers the volante needs the smaller ball to stay on screen.
BIG_VOLANTE = 60


def parse_typed(text: str) -> tuple[int, ...]:
    """Numbers out of whatever someone typed or pasted.

    Deliberately forgiving about separators -- spaces, commas, dashes, newlines
    all appear on tickets and in messages -- and completely unforgiving about
    anything that is not a number, which is dropped rather than guessed at.
    """
    cleaned = "".join(char if char.isdigit() else " " for char in text)
    return tuple(int(part) for part in cleaned.split())


class Picker(QWidget):
    """What every picker can do. The game screen talks only to this."""

    changed = Signal()

    def __init__(self, rules: GameRules, palette: Palette) -> None:
        super().__init__()
        self.rules = rules
        self.colours = palette

    def bet(self) -> Bet:
        """What is currently chosen, legal or not."""
        raise NotImplementedError

    def load(self, bet: Bet) -> None:
        """Show a saved bet."""
        raise NotImplementedError

    def clear(self) -> None:
        raise NotImplementedError


class GridPicker(Picker):
    """A volante: every number in the game's range, ten to a line.

    Serves Mega-Sena, Lotofacil, Quina, Lotomania and Dupla Sena -- the bet is a
    set of numbers in all five, and Dupla Sena's second draw changes the result,
    not the ticket.
    """

    def __init__(self, rules: GameRules, palette: Palette) -> None:
        super().__init__(rules, palette)
        self._buttons: dict[int, BallButton] = {}
        self._typing = False

        grid = QGridLayout()
        grid.setSpacing(4)
        numbers = range(rules.first_number, rules.last_number + 1)
        size = 30 if len(list(numbers)) > BIG_VOLANTE else 34
        for index, number in enumerate(range(rules.first_number, rules.last_number + 1)):
            button = BallButton(number, self.colours, size=size)
            button.toggled.connect(self._grid_changed)
            self._buttons[number] = button
            grid.addWidget(button, index // PER_LINE, index % PER_LINE)

        self.typed = QLineEdit()
        self.typed.setObjectName("typed")
        self.typed.setPlaceholderText(strings.TYPED_HINT)
        self.typed.textEdited.connect(self._typed_changed)

        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(8)
        self.box.addLayout(grid)
        self.box.addWidget(self.typed)

    def chosen(self) -> tuple[int, ...]:
        return tuple(sorted(n for n, b in self._buttons.items() if b.isChecked()))

    def bet(self) -> Bet:
        return Bet(game=self.rules.key, numbers=self.chosen())

    def load(self, bet: Bet) -> None:
        self._set_numbers(bet.numbers)

    def clear(self) -> None:
        self._set_numbers(())

    def _set_numbers(self, numbers: tuple[int, ...]) -> None:
        wanted = set(numbers)
        self._typing = True
        for number, button in self._buttons.items():
            button.setChecked(number in wanted)
        self._typing = False
        self._sync_typed()
        self.changed.emit()

    def _grid_changed(self) -> None:
        if self._typing:
            return
        self._sync_typed()
        self.changed.emit()

    def _sync_typed(self) -> None:
        self.typed.setText(" ".join(f"{n:02d}" for n in self.chosen()))

    def _typed_changed(self, text: str) -> None:
        wanted = set(parse_typed(text))
        self._typing = True
        for number, button in self._buttons.items():
            button.setChecked(number in wanted)
        self._typing = False
        self.changed.emit()


class ExtraPicker(GridPicker):
    """Numbers plus one more thing: Timemania's team, Dia de Sorte's month.

    The month is a closed list and so it is a dropdown. The team is typed,
    because the official list of clubs is not something this app can invent --
    a dropdown built from memory would quietly refuse somebody's real ticket.
    """

    def __init__(self, rules: GameRules, palette: Palette) -> None:
        super().__init__(rules, palette)
        # One control, chosen by whether the game's extra field is a closed
        # list. Keeping two optionals would mean two branches that cannot both
        # be reached, which is two branches nobody can honestly test.
        self.control: QComboBox | QLineEdit
        if rules.extra_options:
            self.control = QComboBox()
            self.control.addItems(rules.extra_options)
            self.control.currentIndexChanged.connect(lambda _: self.changed.emit())
        else:
            self.control = QLineEdit()
            self.control.setPlaceholderText(rules.extra_label)
            self.control.textEdited.connect(lambda _: self.changed.emit())

        self.box.addLayout(row(label(rules.extra_label, "label"), self.control))

    def extra(self) -> str | None:
        if isinstance(self.control, QComboBox):
            return self.control.currentText()
        return self.control.text().strip() or None

    def bet(self) -> Bet:
        return Bet(game=self.rules.key, numbers=self.chosen(), extra=self.extra())

    def load(self, bet: Bet) -> None:
        super().load(bet)
        if bet.extra is None:
            return
        if isinstance(self.control, QComboBox):
            # A month the list does not have is left as it was rather than
            # silently becoming January.
            index = self.control.findText(bet.extra, Qt.MatchFlag.MatchFixedString)
            if index >= 0:
                self.control.setCurrentIndex(index)
        else:
            self.control.setText(bet.extra)


class CloverPicker(GridPicker):
    """+Milionaria: numbers, and a second smaller row of trevos."""

    def __init__(self, rules: GameRules, palette: Palette) -> None:
        super().__init__(rules, palette)
        self._clovers: dict[int, BallButton] = {}

        strip = QGridLayout()
        strip.setSpacing(4)
        for index, number in enumerate(range(rules.clover_first, rules.clover_last + 1)):
            button = BallButton(number, self.colours, size=30, text=str(number))
            button.toggled.connect(lambda _: self.changed.emit())
            self._clovers[number] = button
            strip.addWidget(button, 0, index)

        self.box.addLayout(row(label(strings.CLOVERS, "label"), strip))

    def clovers(self) -> tuple[int, ...]:
        return tuple(sorted(n for n, b in self._clovers.items() if b.isChecked()))

    def bet(self) -> Bet:
        return Bet(game=self.rules.key, numbers=self.chosen(), clovers=self.clovers())

    def load(self, bet: Bet) -> None:
        super().load(bet)
        wanted = set(bet.clovers)
        for number, button in self._clovers.items():
            button.setChecked(number in wanted)

    def clear(self) -> None:
        for button in self._clovers.values():
            button.setChecked(False)
        super().clear()


class ColumnPicker(Picker):
    """Super Sete: seven columns of 0-9, where the column is half the answer.

    Not a grid with a different label on it. A digit means nothing without the
    column it sits in, so the layout says so and the typed field takes one
    column per group rather than a flat list of numbers.
    """

    def __init__(self, rules: GameRules, palette: Palette) -> None:
        super().__init__(rules, palette)
        self._columns: list[dict[int, BallButton]] = []

        grid = QGridLayout()
        grid.setSpacing(4)
        for column in range(rules.column_count):
            heading = label(strings.COLUMN_TITLE.format(number=column + 1), "label")
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(heading, 0, column)
            buttons: dict[int, BallButton] = {}
            for digit in range(rules.first_number, rules.last_number + 1):
                button = BallButton(digit, self.colours, size=30, text=str(digit))
                button.toggled.connect(lambda _: self.changed.emit())
                buttons[digit] = button
                grid.addWidget(button, digit + 1, column)
            self._columns.append(buttons)

        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(8)
        self.box.addWidget(label(strings.COLUMN_HINT, "muted"))
        self.box.addLayout(grid)

    def columns(self) -> tuple[tuple[int, ...], ...]:
        return tuple(
            tuple(sorted(d for d, b in column.items() if b.isChecked())) for column in self._columns
        )

    def bet(self) -> Bet:
        return Bet(game=self.rules.key, columns=self.columns())

    def load(self, bet: Bet) -> None:
        for index, column in enumerate(self._columns):
            wanted = set(bet.columns[index]) if index < len(bet.columns) else set()
            for digit, button in column.items():
                button.setChecked(digit in wanted)
        self.changed.emit()

    def clear(self) -> None:
        for column in self._columns:
            for button in column.values():
                button.setChecked(False)
        self.changed.emit()


def picker_for(rules: GameRules, palette: Palette) -> Picker:
    """The picker a game needs, chosen by its shape and nothing else."""
    if rules.shape is Shape.COLUMNS:
        return ColumnPicker(rules, palette)
    if rules.shape is Shape.CLOVERS:
        return CloverPicker(rules, palette)
    if rules.shape is Shape.EXTRA:
        return ExtraPicker(rules, palette)
    return GridPicker(rules, palette)
