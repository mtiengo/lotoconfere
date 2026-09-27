"""The build tool pins have to be in the repository, not just on one machine.

A global gitignore with `*.env` in it -- a common thing for a person to have --
once kept this file out of the repository entirely. Nothing noticed until a
release build failed on two runners at once, because `git status` does not show
an ignored file. This test runs from the checkout, so CI fails the moment the
file is missing rather than the next time someone tags.
"""

import re
from pathlib import Path

import pytest

PINS = Path(__file__).parent.parent / "packaging" / "tool-pins.conf"
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def values() -> dict[str, str]:
    found = {}
    for line in PINS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$", line)
        if match:
            found[match.group(1)] = match.group(2)
    return found


def test_the_pins_file_is_in_the_repository():
    assert PINS.is_file(), f"{PINS.name} is missing -- check it is not caught by a gitignore"


def test_it_is_not_named_env():
    # The extension is load-bearing. See the comment at the top of the file.
    assert PINS.suffix != ".env"


@pytest.mark.parametrize("key", ["APPIMAGETOOL_SHA256", "INNOSETUP_SHA256"])
def test_every_build_tool_is_pinned_to_a_real_digest(key):
    value = values().get(key, "")
    assert DIGEST.match(value), f"{key} is not a SHA-256 digest: {value!r}"


def test_the_inno_setup_url_names_a_tagged_release():
    # Never a "latest" or "continuous" asset: those are re-uploaded in place and
    # the digest drifts out from under the pin.
    url = values().get("INNOSETUP_URL", "")
    assert url.startswith("https://")
    assert "latest" not in url
