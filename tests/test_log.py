"""The log file: local, bounded, and never wired to the outside."""

import logging
from logging.handlers import RotatingFileHandler

from lotoconfere import log


def clean(logger):
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def test_it_writes_to_the_file_it_was_given(tmp_path):
    logger = logging.getLogger("lotoconfere")
    clean(logger)
    path = log.configure(tmp_path / "logs" / "test.log")
    try:
        logging.getLogger("lotoconfere.teste").info("concurso 3062 consultado")
        assert path.exists()
        assert "concurso 3062 consultado" in path.read_text(encoding="utf-8")
    finally:
        clean(logger)


def test_it_creates_the_directory(tmp_path):
    logger = logging.getLogger("lotoconfere")
    clean(logger)
    try:
        path = log.configure(tmp_path / "a" / "b" / "c.log")
        assert path.parent.is_dir()
    finally:
        clean(logger)


def test_configuring_twice_does_not_double_every_line(tmp_path):
    logger = logging.getLogger("lotoconfere")
    clean(logger)
    try:
        target = tmp_path / "twice.log"
        log.configure(target)
        log.configure(target)
        logging.getLogger("lotoconfere.teste").info("uma vez")
        assert target.read_text(encoding="utf-8").count("uma vez") == 1
    finally:
        clean(logger)


def test_it_only_captures_this_package(tmp_path):
    # Configuring the root logger would swallow every library in the process.
    logger = logging.getLogger("lotoconfere")
    clean(logger)
    try:
        path = log.configure(tmp_path / "scoped.log")
        logging.getLogger("httpx").warning("outra biblioteca")
        assert "outra biblioteca" not in path.read_text(encoding="utf-8")
    finally:
        clean(logger)


def test_the_file_is_bounded(tmp_path):
    logger = logging.getLogger("lotoconfere")
    clean(logger)
    try:
        log.configure(tmp_path / "bounded.log")
        handler = logger.handlers[0]
        assert isinstance(handler, RotatingFileHandler)
        assert handler.maxBytes == log.MAX_BYTES
        assert handler.backupCount == log.KEEP
    finally:
        clean(logger)


def test_the_default_path_is_a_log_file_in_the_user_directory():
    assert log.default_path().name == "lotoconfere.log"


def test_pointing_it_at_a_second_file_adds_a_handler(tmp_path):
    # The guard against double-configuring must only match the same file.
    logger = logging.getLogger("lotoconfere")
    clean(logger)
    try:
        log.configure(tmp_path / "first.log")
        second = log.configure(tmp_path / "second.log")
        logging.getLogger("lotoconfere.teste").info("nos dois")
        assert len(logger.handlers) == 2
        assert "nos dois" in second.read_text(encoding="utf-8")
    finally:
        clean(logger)
