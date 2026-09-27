"""The one place this app makes a request.

Both sources go through here, so the rules that make a request safe are written
once: two hardcoded hosts, verification on, no redirects, a size cap, an explicit
timeout, and a User-Agent that says who is calling.
"""

import json
import ssl

import httpx

from lotoconfere import __version__
from lotoconfere.core.errors import SourceUnavailableError

USER_AGENT = f"LotoConfere/{__version__} (+https://github.com/mtiengo/lotoconfere)"
TIMEOUT_SECONDS = 20.0
# A contest response is a couple of kilobytes. The cap is generous enough to say
# nothing about the endpoint's shape, and small enough that a response which
# never ends cannot fill memory.
MAX_RESPONSE_BYTES = 1_000_000

# The only two hosts this app talks to. Not configurable, not derived from a
# saved bet or anything else a user can influence.
ALLOWED_HOSTS = frozenset(
    {
        "servicebus2.caixa.gov.br",
        "loteriascaixa-api.herokuapp.com",
    }
)


def check_host(url: str) -> None:
    """Refuse any URL that is not one of the two hosts."""
    host = httpx.URL(url).host
    if host not in ALLOWED_HOSTS:
        raise SourceUnavailableError(f"host nao permitido: {host}")


def get_json(url: str, client: httpx.Client | None = None) -> object:
    """Fetch and decode one JSON response, or raise SourceUnavailableError.

    `follow_redirects` stays off: a redirect is how a request ends up somewhere
    other than the host it was checked against, so a 3xx is a failure here rather
    than a detour.
    """
    check_host(url)
    owned = client is None
    client = client or httpx.Client()
    try:
        with client.stream(
            "GET",
            url,
            timeout=TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
        ) as response:
            if response.status_code != httpx.codes.OK:
                raise SourceUnavailableError(
                    f"resposta {response.status_code} de {httpx.URL(url).host}"
                )
            body = b""
            for chunk in response.iter_bytes():
                body += chunk
                if len(body) > MAX_RESPONSE_BYTES:
                    raise SourceUnavailableError("resposta maior que o limite esperado")
    except httpx.HTTPError as error:
        raise SourceUnavailableError(describe(error)) from error
    finally:
        if owned:
            client.close()

    try:
        return json.loads(body)
    except json.JSONDecodeError as error:
        raise SourceUnavailableError("a resposta nao era JSON valido") from error


def describe(error: httpx.HTTPError) -> str:
    """A plain pt-BR reason. Never a stack trace, never a library name.

    A certificate failure gets its own sentence because Caixa's chain has broken
    before, and "could not connect" would send someone to check their wifi.
    """
    cause: BaseException | None = error
    while cause is not None:
        if isinstance(cause, ssl.SSLError):
            return "nao foi possivel verificar a conexao segura com o servidor"
        cause = cause.__cause__
    if isinstance(error, httpx.TimeoutException):
        return "o servidor nao respondeu a tempo"
    return "nao foi possivel conectar ao servidor"
