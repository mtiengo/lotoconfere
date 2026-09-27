"""The connection self-check behind `--probe`.

Its job is to answer one question about a **packaged** build: can this binary, on
this machine, complete an HTTPS request to Caixa? A frozen app can lose its CA
bundle, and Caixa's certificate chain has broken before, so the release workflow
runs this on every operating system and refuses to ship a build that fails it.

No Qt here. Importing the app already proves the Qt libraries load; this proves
the network does.
"""

import platform
import ssl
import sys
from dataclasses import dataclass

import httpx

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
    frozen = "sim" if getattr(sys, "frozen", False) else "não"
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
            summary="A Caixa não respondeu a tempo.",
            detail=f"Tempo limite de {TIMEOUT_SECONDS:.0f} segundos.",
        )
    except httpx.HTTPError as error:
        if is_certificate_failure(error):
            return ProbeResult(
                ok=False,
                summary="Nao foi possível verificar a conexao segura com a Caixa.",
                detail=f"Falha de certificado: {error}",
            )
        return ProbeResult(
            ok=False,
            summary="Nao foi possível conectar ao site da Caixa.",
            detail=f"{type(error).__name__}: {error}",
        )

    if status != httpx.codes.OK:
        return ProbeResult(
            ok=False,
            summary="A Caixa respondeu, mas com um erro.",
            detail=f"Código HTTP {status}.",
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
        detail=f"Resposta de {size} bytes, código HTTP {status}.",
    )
