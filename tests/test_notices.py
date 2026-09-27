"""Shipping Qt without its licence is a breach, so the check is a test."""

from lotoconfere import notices


def test_every_bundled_licence_is_actually_there():
    assert notices.missing() == ()


def test_qt_travels_with_the_lgpl_and_the_gpl():
    # LGPLv3 is written as a supplement to GPLv3; one without the other is
    # incomplete.
    licences = {n.licence for n in notices.NOTICES if "PySide6" in n.component}
    assert licences == {"LGPL 3.0", "GPL 3.0"}


def test_both_bundled_typefaces_carry_their_licence():
    fonts = {n.component for n in notices.NOTICES if "Open Font" in n.licence}
    assert fonts == {"Inter", "JetBrains Mono"}


def test_a_notice_can_be_read_for_display():
    lgpl = next(n for n in notices.NOTICES if n.filename == "LGPL-3.0.txt")
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in lgpl.text()
