"""Qt runs headless in tests, on every OS, before anything imports PySide6."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
