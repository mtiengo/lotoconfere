"""Theme, wording and the number pickers.

The pickers are where a person's ticket becomes a Bet, so what is tested is that
what goes in comes out -- and that nothing here decides on its own whether a bet
is legal, which is `core.rules`' job alone.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from lotoconfere.core.models import Bet
from lotoconfere.core.rules import GAMES, validate_bet
from lotoconfere.gui import strings, theme
from lotoconfere.gui.pickers import (
    CloverPicker,
    ColumnPicker,
    ExtraPicker,
    GridPicker,
    parse_typed,
    picker_for,
)
from lotoconfere.gui.theme import DARK, LIGHT
from lotoconfere.gui.widgets import Ball, BallButton, BallState, Chip, Dot, ball_style

# --- wording ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("0"), "R$ 0,00"),
        (Decimal("3.5"), "R$ 3,50"),
        (Decimal("19736.75"), "R$ 19.736,75"),
        (Decimal("84512300.5"), "R$ 84.512.300,50"),
    ],
)
def test_money_is_written_the_brazilian_way(value, expected):
    assert strings.money(value) == expected


@pytest.mark.parametrize(
    ("count", "expected"), [(0, "Nenhum acerto"), (1, "1 acerto"), (6, "6 acertos")]
)
def test_the_singular_is_not_forgotten(count, expected):
    assert strings.hits(count) == expected


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "Nenhuma aposta salva"), (1, "1 aposta salva"), (3, "3 apostas salvas")],
)
def test_saved_bets_are_counted_in_words(count, expected):
    assert strings.saved_count(count) == expected


def test_dates_and_times_use_brazilian_order():
    assert strings.day(date(2026, 9, 24)) == "24/09/2026"
    assert strings.moment(datetime(2026, 9, 24, 21, 30, tzinfo=UTC)).startswith("24/09/2026")


@pytest.mark.parametrize(
    ("bet", "expected"),
    [
        (Bet(game="megasena", numbers=(5, 9, 11, 17, 18, 38)), "05 09 11 17 18 38"),
        (Bet(game="lotomania", numbers=(0, 1, 99)), "00 01 99"),
        (
            Bet(game="maismilionaria", numbers=(1, 2, 3, 4, 5, 6), clovers=(1, 6)),
            f"01 02 03 04 05 06 · {strings.CLOVERS} 1 6",
        ),
        (
            Bet(game="diadesorte", numbers=(1, 5, 9, 13, 17, 21, 25), extra="Janeiro"),
            "01 05 09 13 17 21 25 · Janeiro",
        ),
        (
            Bet(game="supersete", columns=((0,), (1, 2), (3,), (4,), (5,), (6,), (9,))),
            "0 | 1 2 | 3 | 4 | 5 | 6 | 9",
        ),
    ],
)
def test_a_bet_reads_the_way_it_was_marked(bet, expected):
    assert strings.bet_numbers(bet) == expected


def test_pending_and_unavailable_are_different_sentences():
    # The whole result-honesty rule, at the level of the words themselves.
    assert strings.NOT_DRAWN != strings.UNAVAILABLE
    assert "0" not in strings.NOT_DRAWN
    assert "0" not in strings.UNAVAILABLE


def test_a_tier_nobody_won_does_not_say_zero_reais():
    assert "R$" not in strings.NO_WINNER_IN_TIER


# --- theme -------------------------------------------------------------------------


def test_both_schemes_define_every_token():
    assert set(vars(DARK)) == set(vars(LIGHT))
    assert all(value.startswith("#") for value in vars(DARK).values())


def test_the_action_colour_is_never_the_prize_colour():
    # A green Conferir button reads as a win before anything has been checked.
    for palette in (DARK, LIGHT):
        assert palette.accent != palette.hit


@pytest.mark.parametrize("key", sorted(GAMES))
def test_every_game_has_a_dot_colour_in_both_schemes(key):
    assert theme.game_colour(key, LIGHT).startswith("#")
    assert theme.game_colour(key, DARK).startswith("#")


def test_an_unknown_game_falls_back_rather_than_crashing():
    assert theme.game_colour("lotogato", LIGHT) == LIGHT.accent


def test_the_stylesheet_is_built_from_the_tokens():
    sheet = theme.stylesheet(LIGHT)
    assert LIGHT.accent in sheet
    assert LIGHT.pane in sheet


def test_the_bundled_faces_load(qapp):
    assert theme.load_fonts() == 2


def test_the_scheme_follows_the_operating_system(qapp, monkeypatch):
    monkeypatch.setattr(theme, "prefers_dark", lambda: True)
    assert theme.palette_for_os() is DARK
    monkeypatch.setattr(theme, "prefers_dark", lambda: False)
    assert theme.palette_for_os() is LIGHT


def test_asking_the_os_does_not_raise(qapp):
    assert isinstance(theme.prefers_dark(), bool)


# --- widgets -----------------------------------------------------------------------


def test_a_hit_is_marked_by_more_than_colour(qapp):
    # Fill, ring and weight together, so it survives colour blindness and grey.
    style = ball_style(BallState.HIT, LIGHT, 34)
    assert LIGHT.hit in style
    assert "border:2px solid" in style
    assert "font-weight:800" in style


def test_a_hit_says_so_in_words_for_a_screen_reader(qapp):
    assert Ball("05", LIGHT, BallState.HIT).accessibleDescription() == "acertou"
    assert Ball("05", LIGHT, BallState.DRAWN).accessibleDescription() == ""


def test_a_picked_number_reports_itself(qapp):
    button = BallButton(7, LIGHT)
    assert button.text() == "07"
    assert button.accessibleDescription() == ""
    button.setChecked(True)
    assert button.accessibleDescription() == "escolhido"


def test_a_chip_and_a_dot_render(qapp):
    assert Chip("PREMIADO", LIGHT).text() == "PREMIADO"
    assert Dot("#209869").width() == 14


# --- typed entry ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("05 09 11 17 18 38", (5, 9, 11, 17, 18, 38)),
        ("5,9,11", (5, 9, 11)),
        ("05-09-11", (5, 9, 11)),
        ("  07   08  ", (7, 8)),
        ("", ()),
        ("nada aqui", ()),
    ],
)
def test_numbers_are_read_out_of_whatever_was_typed(typed, expected):
    assert parse_typed(typed) == expected


# --- the pickers -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("key", "kind"),
    [
        ("megasena", GridPicker),
        ("lotofacil", GridPicker),
        ("quina", GridPicker),
        ("lotomania", GridPicker),
        ("duplasena", GridPicker),
        ("timemania", ExtraPicker),
        ("diadesorte", ExtraPicker),
        ("maismilionaria", CloverPicker),
        ("supersete", ColumnPicker),
    ],
)
def test_each_game_gets_the_picker_its_shape_needs(qapp, key, kind):
    assert type(picker_for(GAMES[key], LIGHT)) is kind


def a_minimum_bet(key):
    rules = GAMES[key]
    if rules.column_count:
        return Bet(game=key, columns=tuple((d,) for d in (9, 2, 4, 7, 5, 5, 2)))
    return Bet(
        game=key,
        numbers=tuple(range(rules.first_number, rules.first_number + rules.minimum_bet_size)),
        extra=(rules.extra_options[0] if rules.extra_options else "CRB /AL")
        if rules.extra_label
        else None,
        clovers=(1, 2) if rules.clover_sizes else (),
    )


@pytest.mark.parametrize("key", sorted(GAMES))
def test_a_bet_loaded_into_a_picker_comes_back_out_of_it(qapp, key):
    picker = picker_for(GAMES[key], LIGHT)
    wanted = a_minimum_bet(key)
    picker.load(wanted)
    assert picker.bet() == wanted
    validate_bet(picker.bet())  # and it is playable


@pytest.mark.parametrize("key", sorted(GAMES))
def test_clearing_a_picker_empties_it(qapp, key):
    picker = picker_for(GAMES[key], LIGHT)
    picker.load(a_minimum_bet(key))
    picker.clear()
    assert picker.bet().size == 0


def test_typing_numbers_ticks_the_grid(qapp):
    picker = GridPicker(GAMES["megasena"], LIGHT)
    picker.typed.setText("05 09 11 17 18 38")
    picker._typed_changed("05 09 11 17 18 38")
    assert picker.chosen() == (5, 9, 11, 17, 18, 38)


def test_clicking_the_grid_rewrites_the_typed_field(qapp):
    picker = GridPicker(GAMES["megasena"], LIGHT)
    picker.load(Bet(game="megasena", numbers=(5, 9, 11, 17, 18, 38)))
    assert picker.typed.text() == "05 09 11 17 18 38"


def test_the_picker_reports_every_change(qapp):
    picker = GridPicker(GAMES["megasena"], LIGHT)
    seen = []
    picker.changed.connect(lambda: seen.append(1))
    picker.load(Bet(game="megasena", numbers=(5,)))
    picker._typed_changed("05 09")
    assert len(seen) >= 2


def test_a_month_is_chosen_from_the_closed_list(qapp):
    picker = picker_for(GAMES["diadesorte"], LIGHT)
    assert isinstance(picker, ExtraPicker)
    from PySide6.QtWidgets import QComboBox

    assert isinstance(picker.control, QComboBox)
    assert picker.control.count() == 12
    picker.load(Bet(game="diadesorte", numbers=tuple(range(1, 8)), extra="Janeiro"))
    assert picker.extra() == "Janeiro"


def test_a_team_is_typed_because_the_list_is_not_ours_to_invent(qapp):
    picker = picker_for(GAMES["timemania"], LIGHT)
    from PySide6.QtWidgets import QLineEdit

    assert isinstance(picker, ExtraPicker)
    assert isinstance(picker.control, QLineEdit)
    assert picker.extra() is None
    picker.load(Bet(game="timemania", numbers=tuple(range(1, 11)), extra="CRB /AL"))
    assert picker.extra() == "CRB /AL"


def test_a_month_that_is_not_in_the_list_is_left_alone(qapp):
    picker = picker_for(GAMES["diadesorte"], LIGHT)
    assert isinstance(picker, ExtraPicker)
    picker.load(Bet(game="diadesorte", numbers=tuple(range(1, 8)), extra="Smarch"))
    assert picker.extra() in GAMES["diadesorte"].extra_options


def test_a_column_picker_keeps_each_digit_in_its_own_column(qapp):
    picker = picker_for(GAMES["supersete"], LIGHT)
    picker.load(Bet(game="supersete", columns=tuple((d,) for d in (9, 2, 4, 7, 5, 5, 2))))
    assert picker.bet().columns == ((9,), (2,), (4,), (7,), (5,), (5,), (2,))


def test_a_short_column_bet_loads_without_complaint(qapp):
    # Loading is not validation: a half-filled ticket is shown, then refused.
    picker = picker_for(GAMES["supersete"], LIGHT)
    picker.load(Bet(game="supersete", columns=((1,), (2,))))
    assert picker.bet().columns[0] == (1,)
    assert picker.bet().columns[6] == ()


def test_the_base_picker_refuses_to_pretend(qapp):
    from lotoconfere.gui.pickers import Picker

    base = Picker(GAMES["megasena"], LIGHT)
    for call in (base.bet, base.clear):
        with pytest.raises(NotImplementedError):
            call()
    with pytest.raises(NotImplementedError):
        base.load(Bet(game="megasena"))
