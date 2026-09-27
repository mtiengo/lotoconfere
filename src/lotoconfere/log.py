"""A rotating log file next to the database. Nothing leaves the machine.

This is not telemetry and must never become it: the file is written locally, read
by whoever owns the computer, and sent nowhere. It exists so that "it said it
could not connect" can be turned into something a maintainer can act on.

What gets logged is what the app *did* -- which contest it asked for, which
source answered, what failed. Not what the person played: their numbers are
their business, and a log is the wrong place to learn them.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from platformdirs import user_log_dir

from lotoconfere.store.database import APP_AUTHOR, APP_NAME

LOG_NAME = "lotoconfere.log"
# Small on purpose: a desktop app that quietly eats a gigabyte of disk is a bug.
MAX_BYTES = 512 * 1024
KEEP = 3
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def default_path() -> Path:
    """Where the log lives on this operating system."""
    return Path(user_log_dir(APP_NAME, APP_AUTHOR)) / LOG_NAME


def configure(path: Path | None = None, level: int = logging.INFO) -> Path:
    """Send this package's logging to a rotating file. Returns the file it uses.

    Only the `lotoconfere` logger is touched. Configuring the root logger would
    capture every library in the process, which is how a log fills up with
    somebody else's debug output.
    """
    target = path or default_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("lotoconfere")
    logger.setLevel(level)
    # Calling this twice -- the GUI starting after a test, say -- must not double
    # every line, so an existing handler for the same file is left alone.
    for existing in logger.handlers:
        if isinstance(existing, RotatingFileHandler) and existing.baseFilename == str(
            target.resolve()
        ):
            return target

    handler = RotatingFileHandler(target, maxBytes=MAX_BYTES, backupCount=KEEP, encoding="utf-8")
    handler.setFormatter(logging.Formatter(FORMAT))
    logger.addHandler(handler)
    # The app has no console to fall back to; a stray print would go nowhere.
    logger.propagate = False
    return target
