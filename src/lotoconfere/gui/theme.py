"""Colour, type and the one stylesheet, following whatever the OS is set to.

The values here are the home for the look. They came from the spike the owner
approved, and the contrast floors below are the reason several of them are not
the obvious choice.

Rules this file exists to keep:

* **Colour is rationed and never used alone.** Green means "you hit this", and a
  hit also carries a ring and bold weight so it survives colour blindness and a
  greyscale screenshot.
* **The action colour is never the prize colour.** A green Conferir button would
  read as a win before the person has read anything.
* **Readable before stylish.** Text meets its contrast floor on the surface it
  sits on, in both schemes.
"""

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication

FONTS = Path(__file__).parent / "fonts"
BODY = "Inter"
NUMERIC = "JetBrains Mono"


@dataclass(frozen=True)
class Palette:
    """One colour scheme. Same token names in both, so nothing branches on theme."""

    app: str
    pane: str
    bar: str
    line: str
    text: str
    label: str
    muted: str
    ink: str
    accent: str
    hit: str
    hit_ring: str
    hit_text: str
    ball: str
    ball_text: str
    chosen: str
    chosen_text: str
    warn: str


DARK = Palette(
    app="#16181c",
    pane="#1d2025",
    bar="#24282e",
    line="#343a43",
    text="#f2f4f7",
    label="#b9c0cb",
    muted="#8f98a6",
    ink="#10141a",
    accent="#e07a28",
    hit="#2f7d4f",
    hit_ring="#5fd08d",
    hit_text="#f2fbf5",
    ball="#2a2f36",
    ball_text="#e6eaf0",
    chosen="#e8ecf2",
    chosen_text="#15181d",
    warn="#e0b62c",
)

LIGHT = Palette(
    app="#f4f5f7",
    pane="#ffffff",
    bar="#eceef1",
    line="#d3d8de",
    text="#14181d",
    label="#495159",
    muted="#6b7481",
    ink="#ffffff",
    accent="#b9560f",
    hit="#1f7a45",
    hit_ring="#0f5c30",
    hit_text="#ffffff",
    ball="#e7eaee",
    ball_text="#1b2026",
    chosen="#1b2026",
    chosen_text="#ffffff",
    warn="#8a6100",
)

# Each game's own colour, read from Caixa's stylesheet (h3.<game> in
# loterias.css, 2026-09-26). These are hues, not logos: no Caixa artwork ships
# with this app, and the game's name is always beside its dot.
#
# The dark column keeps the hue and lifts the lightness until the dot clears 3:1
# on the pane, because Quina and +Milionaria are near-black indigo and would
# otherwise be invisible.
GAME_COLOURS: dict[str, tuple[str, str]] = {
    "megasena": ("#209869", "#209869"),
    "lotofacil": ("#930089", "#c600b9"),
    "quina": ("#260085", "#753eff"),
    "lotomania": ("#f78100", "#f78100"),
    "duplasena": ("#a61324", "#d4182e"),
    "timemania": ("#049645", "#049645"),
    "diadesorte": ("#cb852b", "#cb852b"),
    "supersete": ("#a8cf45", "#a8cf45"),
    "maismilionaria": ("#2e3078", "#5f61c2"),
}


def load_fonts() -> int:
    """Register the bundled faces. Returns how many loaded.

    Zero is survivable -- Qt falls back to a system face and the app still reads
    -- so this never raises. It is reported so a build that lost its fonts can
    be spotted rather than silently looking wrong.
    """
    loaded = 0
    for face in ("Inter-Variable.ttf", "JetBrainsMono-Variable.ttf"):
        if QFontDatabase.addApplicationFont(str(FONTS / face)) != -1:
            loaded += 1
    return loaded


def prefers_dark() -> bool:
    """Whether the OS is set to a dark scheme right now."""
    hints = QGuiApplication.styleHints()
    return bool(hints) and hints.colorScheme() == Qt.ColorScheme.Dark


def palette_for_os() -> Palette:
    return DARK if prefers_dark() else LIGHT


def game_colour(game: str, palette: Palette) -> str:
    """A game's dot colour in the current scheme, or the accent if it is unknown."""
    pair = GAME_COLOURS.get(game)
    if pair is None:
        return palette.accent
    light, dark = pair
    return dark if palette is DARK else light


def stylesheet(p: Palette) -> str:
    """One stylesheet, driven by the tokens. Square corners, hairlines, no cards."""
    return f"""
    QWidget {{ background: {p.app}; color: {p.text}; font-family: "{BODY}"; font-size: 14px; }}
    QLabel {{ background: transparent; }}
    QLabel#h1 {{ font-size: 24px; font-weight: 700; }}
    QLabel#h2 {{ font-size: 17px; font-weight: 700; }}
    QLabel#label {{ color: {p.label}; font-size: 13px; font-weight: 600; }}
    QLabel#muted {{ color: {p.muted}; font-size: 13px; }}
    QLabel#warn {{ color: {p.warn}; font-size: 13px; font-weight: 600; }}
    QLabel#money {{ font-family: "{NUMERIC}"; font-size: 14px; }}

    QFrame#pane {{ background: {p.pane}; border: 1px solid {p.line}; }}
    QScrollArea {{ border: 0; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}

    QPushButton {{ background: {p.bar}; color: {p.text}; border: 1px solid {p.line};
                   padding: 8px 14px; font-size: 14px; font-weight: 600; }}
    QPushButton:hover {{ border-color: {p.accent}; }}
    QPushButton:focus {{ border: 2px solid {p.accent}; }}
    QPushButton:disabled {{ color: {p.muted}; }}
    QPushButton#go {{ background: {p.accent}; color: {p.ink}; border: 1px solid {p.accent};
                      padding: 10px 24px; font-size: 15px; font-weight: 700; }}
    QPushButton#go:disabled {{ background: {p.bar}; border-color: {p.line}; }}
    QPushButton#game {{ padding: 0px; min-height: 52px; text-align: left; }}

    QComboBox, QLineEdit, QSpinBox {{ background: {p.pane}; color: {p.text};
        border: 1px solid {p.line}; padding: 6px 9px; font-size: 14px; }}
    QComboBox:focus, QLineEdit:focus, QSpinBox:focus {{ border: 2px solid {p.accent}; }}
    QLineEdit#typed {{ font-family: "{NUMERIC}"; font-size: 15px; letter-spacing: 1px; }}
    QCheckBox {{ spacing: 8px; }}
    """
