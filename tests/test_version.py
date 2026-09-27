"""The version has one home, and the entry point does its two jobs."""

import sys
from importlib.metadata import version

import lotoconfere
from lotoconfere import __main__
from lotoconfere.probe import ProbeResult


def test_version_matches_the_installed_distribution():
    assert version("lotoconfere") == lotoconfere.__version__


def test_the_entry_point_starts_the_gui(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["lotoconfere"])
    monkeypatch.setattr(__main__, "run", lambda: 0)
    assert __main__.main() == 0


def test_the_probe_flag_skips_the_gui_and_reports(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["lotoconfere", "--probe"])
    monkeypatch.setattr(__main__, "probe_caixa", lambda: ProbeResult(True, "OK.", "1740 bytes"))
    assert __main__.main() == 0
    assert "1740 bytes" in capsys.readouterr().out


def test_the_probe_flag_fails_the_build_when_the_call_fails(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["lotoconfere", "--probe"])
    monkeypatch.setattr(__main__, "probe_caixa", lambda: ProbeResult(False, "sem rede", ""))
    assert __main__.main() == 1


def test_the_probe_flag_refuses_extra_arguments(monkeypatch, capsys):
    # A mistyped probe in CI must fail, not open a window nobody can close.
    monkeypatch.setattr(sys, "argv", ["lotoconfere", "--probe", "--verbose"])
    assert __main__.main() == 2
    assert "no arguments" in capsys.readouterr().err
