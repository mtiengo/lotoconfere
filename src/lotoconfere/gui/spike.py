"""Throwaway diagnostic window for the packaging spike (PLAN.md step 2).

It exists to surface Qt, PyInstaller, certificate and Gatekeeper problems on all
three operating systems before any real code depends on them, so it reports what
a frozen build gets wrong: whether Qt starts, whether a CA store is visible, and
whether one HTTPS call to Caixa completes.

This is the one widget that talks to the network directly. There is no `source/`
yet, and there is no point building one before the frozen app is known to reach
the endpoint at all. Step 8 deletes this module; nothing else may copy its shape.
"""

import platform
import ssl
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lotoconfere import __version__

# The spike calls the same host the app will, so a certificate problem shows up
# here rather than in step 4. One contest, one request.
PROBE_URL = "https://servicebus2.caixa.gov.br/portaldeloterias/api/megasena/"
USER_AGENT = f"LotoConfere/{__version__} (+https://github.com/mtiengo/lotoconfere)"
TIMEOUT_SECONDS = 20.0
# A real contest response is under 2 KB. The cap is generous enough to be no
# judgement about the endpoint's shape and small enough that a response which
# never ends cannot fill memory: the body is read in chunks and abandoned the
# moment it crosses this, rather than loaded whole and measured afterwards.
MAX_RESPONSE_BYTES = 1_000_000

# Package data, collected into the frozen build under this same relative path,
# so one expression finds it whether the app was installed or run from source.
ICON = Path(__file__).parent / "icons" / "lotoconfere.png"


@dataclass(frozen=True)
class ProbeResult:
    """What one HTTPS call to Caixa did, in words a non-developer can read."""

    ok: bool
    summary: str
    detail: str


def trusted_ca_count() -> int:
    """How many CA certificates the HTTPS client can see.

    Zero means a frozen build shipped without its trust store, which is the
    failure this spike exists to catch -- every request would fail verification.
    """
    context: ssl.SSLContext = httpx.create_ssl_context()
    return int(context.cert_store_stats()["x509_ca"])


def environment_lines() -> list[str]:
    """The facts worth knowing when a packaged build misbehaves."""
    frozen = "sim" if getattr(sys, "frozen", False) else "nao"
    return [
        f"Versao: {__version__}",
        f"Empacotado: {frozen}",
        f"Python: {platform.python_version()}",
        f"Sistema: {platform.system()} {platform.release()} ({platform.machine()})",
        f"Certificados confiaveis: {trusted_ca_count()}",
    ]


def is_certificate_failure(error: BaseException) -> bool:
    """Whether a failed request failed because the certificate chain did not verify.

    httpx reports a rejected chain as a ConnectError wrapping ssl.SSLError, so the
    cause has to be walked -- and a certificate problem deserves its own message:
    Caixa's chain has broken before, and "could not connect" would send the user
    looking at their internet connection instead.
    """
    cause: BaseException | None = error
    while cause is not None:
        if isinstance(cause, ssl.SSLError):
            return True
        cause = cause.__cause__
    return False


def read_capped(response: httpx.Response) -> int | None:
    """Read the body in chunks, returning its size, or None if it exceeded the cap."""
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            return None
    return size


def probe_caixa() -> ProbeResult:
    """Make one HTTPS request to Caixa and describe the outcome in pt-BR."""
    try:
        with httpx.stream(
            "GET",
            PROBE_URL,
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            # A redirect is how a hijacked or misconfigured host would move the
            # request somewhere else; the app talks to two hosts and no others.
            follow_redirects=False,
        ) as response:
            status = response.status_code
            size = read_capped(response) if status == httpx.codes.OK else 0
    except httpx.TimeoutException:
        return ProbeResult(
            ok=False,
            summary="A Caixa nao respondeu a tempo.",
            detail=f"Tempo limite de {TIMEOUT_SECONDS:.0f} segundos.",
        )
    except httpx.HTTPError as error:
        if is_certificate_failure(error):
            return ProbeResult(
                ok=False,
                summary="Nao foi possivel verificar a conexao segura com a Caixa.",
                detail=f"Falha de certificado: {error}",
            )
        return ProbeResult(
            ok=False,
            summary="Nao foi possivel conectar ao site da Caixa.",
            detail=f"{type(error).__name__}: {error}",
        )

    if status != httpx.codes.OK:
        return ProbeResult(
            ok=False,
            summary="A Caixa respondeu, mas com um erro.",
            detail=f"Codigo HTTP {status}.",
        )
    if size is None:
        return ProbeResult(
            ok=False,
            summary="A resposta da Caixa veio maior do que o esperado.",
            detail=f"Leitura interrompida acima de {MAX_RESPONSE_BYTES} bytes.",
        )
    return ProbeResult(
        ok=True,
        summary="Conexao HTTPS com a Caixa: OK.",
        detail=f"Resposta de {size} bytes, codigo HTTP {status}.",
    )


class ProbeWorker(QObject):
    """Runs one probe on a worker thread so the window never freezes."""

    finished = Signal(ProbeResult)

    def __init__(self, probe: Callable[[], ProbeResult]) -> None:
        super().__init__()
        self._probe = probe

    def run(self) -> None:
        self.finished.emit(self._probe())


class SpikeWindow(QWidget):
    """A button, a result line, and the environment facts behind them."""

    def __init__(self, probe: Callable[[], ProbeResult] = probe_caixa) -> None:
        super().__init__()
        self._probe = probe
        self._thread: QThread | None = None

        self.setWindowTitle("LotoConfere - teste de empacotamento")

        self._environment = QLabel("\n".join(environment_lines()))
        self._environment.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._button = QPushButton("Testar conexao com a Caixa")
        self._button.clicked.connect(self.start_probe)

        self._status = QLabel("Nenhum teste executado ainda.")
        self._status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._environment)
        layout.addWidget(self._button)
        layout.addWidget(self._status)

    def start_probe(self) -> None:
        """Run the probe off the UI thread and report when it lands."""
        self._button.setEnabled(False)
        self._status.setText("Consultando a Caixa...")

        thread = QThread(self)
        worker = ProbeWorker(self._probe)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self.show_result)
        worker.finished.connect(thread.quit)
        # The worker outlives the local name only because the thread owns its
        # lifetime; without this parent it is collected mid-run.
        worker.setParent(thread)
        self._thread = thread
        thread.start()

    def show_result(self, result: ProbeResult) -> None:
        """Put the probe's verdict on screen."""
        self._status.setText(f"{result.summary}\n{result.detail}")
        self._button.setEnabled(True)


def run() -> int:
    """Open the spike window and return a process exit code."""
    app = QApplication.instance() or QApplication(sys.argv)
    # The taskbar, the title bar, the alt-tab list and the macOS dock all read this.
    QApplication.setWindowIcon(QIcon(str(ICON)))
    window = SpikeWindow()
    window.resize(480, 260)
    window.show()
    return app.exec()
