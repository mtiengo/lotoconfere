"""The layering rules, enforced mechanically rather than by review.

A checker that quietly grew a network call, or a widget that reached past
service.py into the cache, would still pass every behavioural test. These scan
the source instead, so the seam is proven on every run and stays proven as the
package fills in.
"""

import ast
from pathlib import Path

import lotoconfere

PACKAGE_ROOT = Path(lotoconfere.__file__).parent

# Network, disk and Qt, by the names they are imported under. core/ is pure
# checking logic: it receives already-parsed types and returns results.
CORE_BANNED_MODULES = frozenset(
    {
        "httpx",
        "requests",
        "urllib",
        "http",
        "socket",
        "ssl",
        "sqlite3",
        "shutil",
        "tempfile",
        "platformdirs",
        "PySide6",
        "shiboken6",
    }
)
CORE_BANNED_CALLS = frozenset({"print", "open", "input"})

# The GUI calls service.py and nothing below it.
GUI_BANNED_MODULES = frozenset({"lotoconfere.source", "lotoconfere.store"})


def modules_in(package: str) -> list[Path]:
    """Every .py file under one subpackage."""
    return sorted((PACKAGE_ROOT / package).rglob("*.py"))


def imported_names(tree: ast.AST) -> set[str]:
    """Dotted module names an AST imports, each also yielding its top-level package."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
                names.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
            names.add(node.module.split(".", 1)[0])
    return names


def called_builtins(tree: ast.AST) -> set[str]:
    """Names called directly, e.g. `print(...)` -> {"print"}."""
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def test_core_does_no_io_and_knows_nothing_about_qt():
    for path in modules_in("core"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden = imported_names(tree) & CORE_BANNED_MODULES
        assert not forbidden, f"{path.name} imports {sorted(forbidden)}; core/ is pure"
        calls = called_builtins(tree) & CORE_BANNED_CALLS
        assert not calls, f"{path.name} calls {sorted(calls)}; core/ does no I/O"


def test_gui_reaches_the_app_only_through_the_service():
    for path in modules_in("gui"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden = imported_names(tree) & GUI_BANNED_MODULES
        assert not forbidden, f"{path.name} imports {sorted(forbidden)}; go through service.py"
