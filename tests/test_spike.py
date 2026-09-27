"""The packaging spike: its probe classifies outcomes, and its window stays alive.

The spike is throwaway (PLAN.md step 2), but the thing it proves is not: a frozen
build that cannot verify a certificate must say so in those words, because that is
the failure this endpoint has actually produced.
"""

import ssl
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import httpx
import pytest

from lotoconfere import __version__
from lotoconfere.gui import spike


@dataclass
class FakeResponse:
    """Stands in for the streamed response httpx.stream() hands back."""

    status_code: int
    chunks: list[bytes]

    def iter_bytes(self) -> Iterator[bytes]:
        yield from self.chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def streaming(response: "FakeResponse") -> Callable[..., "FakeResponse"]:
    def fake_stream(*args, **kwargs):
        return response

    return fake_stream


def raising(error: Exception) -> Callable[..., object]:
    def fake_get(*args, **kwargs):
        raise error

    return fake_get


def test_a_good_response_reads_as_ok(monkeypatch):
    monkeypatch.setattr(httpx, "stream", streaming(FakeResponse(200, [b"x" * 740, b"y" * 1000])))
    result = spike.probe_caixa()
    assert result.ok
    assert "OK" in result.summary
    assert "1740" in result.detail


def test_a_non_200_is_not_ok(monkeypatch):
    monkeypatch.setattr(httpx, "stream", streaming(FakeResponse(403, [])))
    result = spike.probe_caixa()
    assert not result.ok
    assert "403" in result.detail


def test_a_timeout_says_the_caixa_did_not_answer(monkeypatch):
    monkeypatch.setattr(httpx, "stream", raising(httpx.ConnectTimeout("slow")))
    result = spike.probe_caixa()
    assert not result.ok
    assert "tempo" in result.summary.lower()


def test_a_rejected_certificate_names_the_certificate(monkeypatch):
    # How httpx actually reports it: a ConnectError wrapping the SSL failure.
    wrapped = httpx.ConnectError("handshake failed")
    wrapped.__cause__ = ssl.SSLCertVerificationError("unable to get local issuer certificate")
    monkeypatch.setattr(httpx, "stream", raising(wrapped))
    result = spike.probe_caixa()
    assert not result.ok
    assert "segura" in result.summary
    assert "certificado" in result.detail.lower()


def test_an_ordinary_network_failure_does_not_blame_the_certificate(monkeypatch):
    monkeypatch.setattr(httpx, "stream", raising(httpx.ConnectError("no route to host")))
    result = spike.probe_caixa()
    assert not result.ok
    assert "conectar" in result.summary
    assert "certificado" not in result.detail.lower()


def test_the_trust_store_is_not_empty():
    # Zero here in a frozen build means the CA bundle did not ship with it.
    assert spike.trusted_ca_count() > 0


def test_the_environment_report_names_the_version():
    assert any(__version__ in line for line in spike.environment_lines())


def test_the_window_reports_a_probe_that_succeeded(qtbot):
    ok = spike.ProbeResult(ok=True, summary="Conexao HTTPS com a Caixa: OK.", detail="tudo certo")
    window = spike.SpikeWindow(probe=lambda: ok)
    qtbot.addWidget(window)

    window.start_probe()
    qtbot.waitUntil(lambda: "tudo certo" in window._status.text(), timeout=5000)
    assert window._button.isEnabled()


def test_the_window_reports_a_probe_that_failed(qtbot):
    bad = spike.ProbeResult(ok=False, summary="Nao foi possivel conectar", detail="sem rede")
    window = spike.SpikeWindow(probe=lambda: bad)
    qtbot.addWidget(window)

    window.start_probe()
    qtbot.waitUntil(lambda: "sem rede" in window._status.text(), timeout=5000)


def test_run_opens_a_window_without_blocking(qtbot, monkeypatch):
    from PySide6.QtWidgets import QApplication

    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(spike, "probe_caixa", lambda: spike.ProbeResult(True, "ok", ""))
    assert spike.run() == 0


@pytest.mark.live
def test_the_real_endpoint_still_answers():
    """Drift check: run by hand with `pytest -m live`, never in CI."""
    result = spike.probe_caixa()
    assert result.ok, result.detail


def test_an_endless_response_is_abandoned_at_the_cap(monkeypatch):
    # A body that never ends must not be loaded whole and measured afterwards.
    oversized = [b"z" * 100_000] * 20
    monkeypatch.setattr(httpx, "stream", streaming(FakeResponse(200, oversized)))
    result = spike.probe_caixa()
    assert not result.ok
    assert "maior" in result.summary


def test_reading_stops_before_consuming_everything(monkeypatch):
    read = 0

    def counted():
        nonlocal read
        while True:
            read += 1
            yield b"z" * 100_000

    response = FakeResponse(200, [])
    monkeypatch.setattr(response, "iter_bytes", counted)
    monkeypatch.setattr(httpx, "stream", streaming(response))
    assert spike.probe_caixa().ok is False
    assert read < 15  # the cap is 1 MB, so ~11 chunks, not an unbounded read


def test_the_window_icon_ships_with_the_package():
    # A path that is right in the source tree and wrong in the frozen build is a
    # blank taskbar icon nobody notices until release day.
    assert spike.ICON.is_file()
    assert spike.ICON.parent.name == "icons"
