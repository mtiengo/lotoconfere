"""Starting the application: fonts, theme, store, service, window.

The order matters. Fonts register before any widget is built or Qt measures text
with a face that is about to change; the store opens before the service, because
the service reads its preferences; and the window is built last.
"""

import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from lotoconfere.gui import theme
from lotoconfere.gui.strings import APP_NAME
from lotoconfere.gui.window import MainWindow
from lotoconfere.log import configure
from lotoconfere.service import Service
from lotoconfere.store.database import Store

# Package data, collected into the frozen build at the same relative path, so one
# expression finds it whether the app was installed or run from source.
ICON = theme.FONTS.parent / "icons" / "lotoconfere.png"


def build(app: QApplication) -> MainWindow:
    """Everything between a bare QApplication and a window worth showing."""
    theme.load_fonts()
    palette = theme.palette_for_os()
    app.setStyleSheet(theme.stylesheet(palette))
    app.setApplicationName(APP_NAME)
    QApplication.setWindowIcon(QIcon(str(ICON)))

    store = Store()
    window = MainWindow(Service(store), palette)
    # The store outlives every screen, so the window owns closing it.
    app.aboutToQuit.connect(store.close)
    return window


def run() -> int:
    """Open the app and return a process exit code."""
    configure()
    app = QApplication.instance() or QApplication(sys.argv)
    if not isinstance(app, QApplication):  # pragma: no cover - only a GUI app gets here
        raise TypeError("esperava uma QApplication")
    window = build(app)
    window.show()
    return app.exec()
