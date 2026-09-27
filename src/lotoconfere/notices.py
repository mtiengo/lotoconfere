"""The third-party components this app ships, and their licence texts.

Qt is used under the LGPL, which asks that the licence travel with the program.
Neither PySide6's wheel nor a PyInstaller build carries it, so the texts are kept
here and bundled deliberately -- shipping Qt without them is a licence breach,
not a missing About box.

The About box reads this. It is also why the packaging spec collects
`licenses/` into the frozen build.
"""

from dataclasses import dataclass
from pathlib import Path

LICENSES = Path(__file__).parent / "licenses"


@dataclass(frozen=True)
class Notice:
    """One bundled component and the licence it is used under."""

    component: str
    licence: str
    filename: str

    @property
    def path(self) -> Path:
        return LICENSES / self.filename

    def text(self) -> str:
        """The licence itself, as shipped."""
        return self.path.read_text(encoding="utf-8")


# Qt ships as replaceable shared libraries, unmodified, which is what the LGPL
# asks of a program that links it. LGPLv3 builds on GPLv3, so both texts travel.
NOTICES = (
    Notice("Qt (via PySide6)", "LGPL 3.0", "LGPL-3.0.txt"),
    Notice("Qt (via PySide6)", "GPL 3.0", "GPL-3.0.txt"),
    Notice("Inter", "SIL Open Font License 1.1", "OFL-Inter.txt"),
    Notice("JetBrains Mono", "SIL Open Font License 1.1", "OFL-JetBrainsMono.txt"),
)


def missing() -> tuple[str, ...]:
    """Licence files that should be bundled and are not.

    A build that lost them still runs, so nothing else would notice; this is what
    the test and the release check ask.
    """
    return tuple(notice.filename for notice in NOTICES if not notice.path.is_file())
