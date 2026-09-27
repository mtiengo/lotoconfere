"""Entry point: `python -m lotoconfere`, and the `lotoconfere` gui-script."""

import contextlib
import io
import sys
from typing import cast

from lotoconfere.gui.app import run
from lotoconfere.probe import environment_lines, probe_caixa

# Not a CLI, and not a step toward one: verifying HTTPS *inside the frozen app*
# is a release blocker (PLAN.md section 10), and a blocker CI cannot run is not a
# blocker. The packaged binary is launched with this flag on every OS, and its
# exit code is what the release workflow checks.
PROBE_FLAG = "--probe"


def report_probe() -> int:
    """Run the connection check with no GUI; 0 if the call succeeded, 1 if not."""
    # The report is Portuguese and the Windows console is not UTF-8 by default,
    # which turns every accent into mojibake in a CI log. Asked for rather than
    # checked for: whether stdout can be reconfigured depends on what replaced
    # it, and a hasattr branch is taken on one machine and not on another.
    # sys.stdout is typed as TextIO, which does not promise reconfigure; the real
    # object usually is a TextIOWrapper, and when it is not, suppress covers it.
    with contextlib.suppress(AttributeError):
        cast(io.TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8", errors="replace")
    result = probe_caixa()
    for line in (*environment_lines(), result.summary, result.detail):
        print(line)
    return 0 if result.ok else 1


def main() -> int:
    """Start the GUI and return a process exit code."""
    arguments = sys.argv[1:]
    if PROBE_FLAG in arguments:
        if arguments != [PROBE_FLAG]:
            # Refuse rather than open a window: in CI a mistyped probe would hang
            # the job on a GUI nobody is there to close. Developer-facing, so it
            # is English -- it is not part of the product's pt-BR surface.
            print(f"{PROBE_FLAG} takes no arguments", file=sys.stderr)
            return 2
        return report_probe()
    # Anything else goes to Qt, which reads its own flags (-platform, -style).
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
