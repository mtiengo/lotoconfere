"""The connection self-check: what it says when the call does not work.

A frozen build that cannot verify a certificate must say so in those words,
because that is a failure this endpoint has actually produced.
"""

import ssl
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import httpx

from lotoconfere import __version__
from lotoconfere import probe as spike


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
