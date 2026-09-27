"""Record endpoint responses as test fixtures, once, by hand.

    python scripts/record_fixtures.py megasena 3062
    python scripts/record_fixtures.py megasena latest

A developer tool: never shipped, never run by the app, never run in CI. It saves
each response body byte for byte under tests/fixtures/ and records where it came
from in tests/fixtures/index.json, with a SHA-256 of the file.

That digest is the point. A fixture is evidence of what the endpoint actually
sent; editing one to make a parser pass is the one unforgivable move here, so the
digest is checked by the test suite and a hand-edited fixture fails loudly.

Be a good guest: one contest per request, sequential, with a pause between.
"""

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
INDEX = FIXTURES / "index.json"

CAIXA = "https://servicebus2.caixa.gov.br/portaldeloterias/api"
MIRROR = "https://loteriascaixa-api.herokuapp.com/api"

USER_AGENT = "LotoConfere/0.1.0.dev0 (+https://github.com/mtiengo/lotoconfere)"
TIMEOUT_SECONDS = 30.0
PAUSE_SECONDS = 2.0
EXPECTED_ARGUMENTS = 3  # the script, a game, a contest
MAX_RESPONSE_BYTES = 1_000_000


def url_for(source: str, game: str, contest: str) -> str:
    """The two hosts, spelled out. Nothing here is built from user configuration."""
    if source == "caixa":
        return f"{CAIXA}/{game}/" if contest == "latest" else f"{CAIXA}/{game}/{contest}"
    if source == "mirror":
        return f"{MIRROR}/{game}/latest" if contest == "latest" else f"{MIRROR}/{game}/{contest}"
    raise SystemExit(f"unknown source: {source}")


def fetch(url: str) -> bytes:
    """One request, capped, with verification on. Returns the body verbatim."""
    with httpx.stream(
        "GET",
        url,
        timeout=TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
    ) as response:
        response.raise_for_status()
        body = b""
        for chunk in response.iter_bytes():
            body += chunk
            if len(body) > MAX_RESPONSE_BYTES:
                raise SystemExit(f"response larger than {MAX_RESPONSE_BYTES} bytes: {url}")
    return body


def load_index() -> dict[str, Any]:
    if INDEX.exists():
        loaded: dict[str, Any] = json.loads(INDEX.read_text(encoding="utf-8"))
        return loaded
    return {}


def record(source: str, game: str, contest: str) -> str:
    """Fetch one response, save it, and note its provenance. Returns the filename."""
    url = url_for(source, game, contest)
    body = fetch(url)
    name = f"{source}_{game}_{contest}.json"
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / name).write_bytes(body)

    index = load_index()
    index[name] = {
        "source": source,
        "url": url,
        "fetched_on": time.strftime("%Y-%m-%d"),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    INDEX.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return name


def main() -> int:
    if len(sys.argv) != EXPECTED_ARGUMENTS:
        print(__doc__)
        return 2
    game, contest = sys.argv[1], sys.argv[2]
    for source in ("caixa", "mirror"):
        name = record(source, game, contest)
        print(f"recorded {name}")
        time.sleep(PAUSE_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
