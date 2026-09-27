"""The small pieces every screen is built from.

The ball is the one that carries a rule rather than a look: a hit is a fill, a
ring and bold weight together, never the fill alone, so it still reads for
someone who cannot separate that green from grey and in a greyscale screenshot.
"""

from enum import Enum, auto

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from lotoconfere.gui.theme import NUMERIC, Palette

# Below this the digits need the smaller size to stay inside the circle.
SMALL_BALL = 32


class BallState(Enum):
    """What a number on screen is saying."""

    PLAIN = auto()
    CHOSEN = auto()
    DRAWN = auto()
    HIT = auto()


def ball_style(state: BallState, p: Palette, size: int) -> str:
    if state is BallState.HIT:
        body = (
            f"background:{p.hit}; color:{p.hit_text};"
            f"border:2px solid {p.hit_ring}; font-weight:800;"
        )
    elif state is BallState.CHOSEN:
        body = f"background:{p.chosen}; color:{p.chosen_text}; border:0; font-weight:800;"
    elif state is BallState.DRAWN:
        body = (
            f"background:{p.ball}; color:{p.ball_text}; border:1px solid {p.line}; font-weight:700;"
        )
    else:
        body = f"background:{p.ball}; color:{p.muted}; border:0; font-weight:500;"
    return (
        f"{body} border-radius:{size // 2}px; font-family:'{NUMERIC}';"
        f" font-size:{12 if size < SMALL_BALL else 13}px;"
    )


class Ball(QLabel):
    """One number, not clickable. Used in results."""

    def __init__(self, text: str, palette: Palette, state: BallState, size: int = 34) -> None:
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(size, size)
        self.setStyleSheet(f"QLabel{{{ball_style(state, palette, size)}}}")
        # Screen readers and tests both need the state in words, not in colour.
        self.setAccessibleName(text)
        self.setAccessibleDescription("acertou" if state is BallState.HIT else "")


class BallButton(QAbstractButton):
    """One number the person can pick. Used in the pickers.

    A checkable button rather than a styled label so that keyboard focus, space
    to toggle and the accessibility tree all work without being reimplemented.
    """

    def __init__(self, number: int, palette: Palette, size: int = 34, text: str = "") -> None:
        super().__init__()
        self.number = number
        self._palette = palette
        self._size = size
        self.setText(text or f"{number:02d}")
        self.setCheckable(True)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toggled.connect(self._restyle)
        self._restyle(False)

    def _restyle(self, checked: bool) -> None:
        state = BallState.CHOSEN if checked else BallState.PLAIN
        self.setStyleSheet(
            f"QAbstractButton{{{ball_style(state, self._palette, self._size)}}}"
            f"QAbstractButton:focus{{border:2px solid {self._palette.accent};}}"
        )
        self.setAccessibleDescription("escolhido" if checked else "")

    def paintEvent(self, event: object) -> None:  # noqa: ARG002, N802 (Qt's name)
        """Qt draws nothing for a bare QAbstractButton, so the stylesheet does it."""
        from PySide6.QtWidgets import QStyleOption, QStylePainter  # noqa: PLC0415

        painter = QStylePainter(self)
        option = QStyleOption()
        option.initFrom(self)
        painter.drawPrimitive(painter.style().PrimitiveElement.PE_Widget, option)
        painter.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self.text())


class Chip(QLabel):
    """A short solid marker, for a word that must not be missed."""

    def __init__(self, word: str, palette: Palette, colour: str | None = None) -> None:
        super().__init__(word)
        fill = colour or palette.hit
        self.setStyleSheet(
            f"QLabel{{background:{fill}; color:{palette.hit_text}; font-weight:800;"
            f" font-size:12px; padding:3px 9px;}}"
        )


class Dot(QLabel):
    """A game's colour, always beside its name."""

    def __init__(self, colour: str, size: int = 14) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        self.setStyleSheet(f"QLabel{{background:{colour}; border-radius:{size // 2}px;}}")


def rule(palette: Palette) -> QFrame:
    """A hairline. One pixel, and never text."""
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"QFrame{{background:{palette.line}; border:0;}}")
    line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return line


def label(text: str, kind: str = "") -> QLabel:
    """A piece of text, styled by the one stylesheet rather than inline."""
    made = QLabel(text)
    if kind:
        made.setObjectName(kind)
    made.setWordWrap(kind in {"muted", "warn", ""})
    return made


def pane() -> tuple[QFrame, QVBoxLayout]:
    """A docked pane: square corners, a hairline border, no shadow."""
    frame = QFrame()
    frame.setObjectName("pane")
    box = QVBoxLayout(frame)
    box.setContentsMargins(16, 14, 16, 14)
    box.setSpacing(9)
    return frame, box


def row(*widgets: QWidget | QLayout, spacing: int = 8) -> QHBoxLayout:
    """A horizontal strip, its contents pushed to the left."""
    box = QHBoxLayout()
    box.setSpacing(spacing)
    for item in widgets:
        if isinstance(item, QWidget):
            box.addWidget(item)
        else:
            box.addLayout(item)
    box.addStretch(1)
    return box
