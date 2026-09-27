# PyInstaller spec, one build per OS and architecture -- it cannot cross-compile.
#
#   pyinstaller packaging/lotoconfere.spec --noconfirm
#
# Onedir, not onefile: faster start, fewer antivirus false positives, and Qt ships
# as replaceable shared libraries, unmodified, with its notices -- which is what
# LGPL asks for. UPX is off for the same antivirus reason.
#
# BUNDLE is a no-op off macOS, so this one spec serves all three systems.

from pathlib import Path

PROJECT_ROOT = Path(SPECPATH).parent  # noqa: F821  (SPECPATH is injected by PyInstaller)
APP_NAME = "LotoConfere"
ICONS = PROJECT_ROOT / "packaging" / "icons"

a = Analysis(  # noqa: F821
    [str(PROJECT_ROOT / "src" / "lotoconfere" / "__main__.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    # certifi's CA bundle is collected by PyInstaller's own hook. Do not add it
    # here as well: two copies is how a stale bundle survives an upgrade. The
    # `--probe` run in the release workflow is what proves it arrived.
    #
    # The fonts and the window icon are package data the GUI reads at run time,
    # so they are collected under the same path they have in the source tree --
    # that is what lets one `Path(__file__).parent` work frozen and unfrozen.
    datas=[
        (str(PROJECT_ROOT / "src" / "lotoconfere" / "gui" / "fonts"), "lotoconfere/gui/fonts"),
        (str(PROJECT_ROOT / "src" / "lotoconfere" / "gui" / "icons"), "lotoconfere/gui/icons"),
        # Qt is used under the LGPL, which asks that the licence ship with the
        # program. Nothing else puts it in the build.
        (str(PROJECT_ROOT / "src" / "lotoconfere" / "licenses"), "lotoconfere/licenses"),
    ],
    hiddenimports=[],
    hookspath=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    # Windows reads the .ico; macOS takes its own from BUNDLE below.
    icon=str(ICONS / "lotoconfere.ico"),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # the runner's own architecture; macOS builds one per arch
    codesign_identity=None,  # macOS is ad-hoc signed in CI, after the build
    entitlements_file=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

app = BUNDLE(  # noqa: F821
    coll,
    name=f"{APP_NAME}.app",
    icon=str(ICONS / "lotoconfere.icns"),
    bundle_identifier="com.github.mtiengo.lotoconfere",
)
