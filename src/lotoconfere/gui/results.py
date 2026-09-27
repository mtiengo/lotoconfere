"""Drawing a result, which is where the honesty rules become pixels.

Three outcomes, three different things on screen, and none of them is "0
acertos":

* **checked** shows the draw with the hits marked, the count in words, and the
  tiers underneath.
* **pending** says the contest has not been drawn. No balls, no count.
* **unavailable** says it could not be consulted, and why.

A tier Caixa recorded no winner for says so in words instead of printing
R$ 0,00, and a result that came from the mirror says so where it is read.
"""

from PySide6.QtWidgets import QVBoxLayout, QWidget

from lotoconfere.core.models import CheckResult, Draw, Source
from lotoconfere.core.rules import Shape, rules_for
from lotoconfere.gui import strings
from lotoconfere.gui.theme import Palette
from lotoconfere.gui.widgets import Ball, BallState, Chip, label, pane, row
from lotoconfere.service import ContestResult, Outcome, RunSummary


def source_name(source: Source) -> str:
    return strings.FROM_CAIXA if source is Source.CAIXA else strings.FROM_MIRROR


def draw_row(
    numbers: tuple[int, ...],
    hits: set[int],
    palette: Palette,
    caption: str = "",
    *,
    pad: bool = True,
) -> QWidget:
    """One line of drawn numbers, the matched ones marked."""
    holder = QWidget()
    box = row(spacing=5)
    if caption:
        tag = label(caption, "label")
        tag.setFixedWidth(86)
        box.insertWidget(0, tag)
    for index, number in enumerate(numbers):
        state = BallState.HIT if index in hits else BallState.DRAWN
        text = f"{number:02d}" if pad else str(number)
        box.insertWidget(box.count() - 1, Ball(text, palette, state))
    holder.setLayout(box)
    return holder


def hit_positions(result: CheckResult, which: int) -> set[int]:
    """Which positions of a drawn row were matched.

    By position rather than by value, because Super Sete draws the same digit in
    more than one column and only one of them may be the person's hit.
    """
    rules = rules_for(result.bet.game)
    drawn = result.draw.numbers if which == 0 else (result.draw.second_numbers or ())
    if rules.shape is Shape.COLUMNS:
        return {index for index, hit in enumerate(result.column_hits) if hit}
    matched = set(result.matches[which].matched) if which < len(result.matches) else set()
    return {index for index, number in enumerate(drawn) if number in matched}


def header(draw: Draw) -> QWidget:
    """Contest number, date, and where the result came from."""
    holder = QWidget()
    box = row(
        label(str(draw.contest), "h2"),
        label(strings.day(draw.drawn_on), "muted"),
        spacing=8,
    )
    box.addWidget(label(source_name(draw.source), "muted"))
    holder.setLayout(box)
    return holder


def tiers_block(result: CheckResult, box: QVBoxLayout) -> None:
    """One line per tier reached, with the published prize or why there is none."""
    for tier in result.tiers:
        amount = (
            label(strings.PRIZE_NOT_PUBLISHED, "muted")
            if tier.prize is None
            else label(strings.money(tier.prize), "money")
        )
        if tier.prize is not None and tier.prize == 0:
            # Caixa published a zero because nobody won it. Saying "R$ 0,00" to
            # someone who just matched that tier reads as a cruel joke.
            amount = label(strings.NO_WINNER_IN_TIER, "muted")
        name = label(tier.label)
        name.setFixedWidth(220)
        times = label(strings.TIMES.format(count=tier.combinations), "muted")
        times.setFixedWidth(48)
        box.addLayout(row(name, times, amount))


def checked_block(answer: ContestResult, palette: Palette) -> QWidget:
    """A contest that was actually compared."""
    result = answer.result
    frame, box = pane()
    if result is None:  # pragma: no cover - a checked result always carries one
        return frame

    box.addWidget(header(result.draw))
    if result.draw.source is Source.MIRROR:
        box.addWidget(label(strings.MIRROR_WARNING, "warn"))

    rules = rules_for(result.bet.game)
    padded = rules.shape is not Shape.COLUMNS
    if rules.shape is Shape.DOUBLE:
        box.addWidget(
            draw_row(result.draw.numbers, hit_positions(result, 0), palette, strings.FIRST_DRAW)
        )
        box.addWidget(
            draw_row(
                result.draw.second_numbers or (),
                hit_positions(result, 1),
                palette,
                strings.SECOND_DRAW,
            )
        )
    else:
        box.addWidget(draw_row(result.draw.numbers, hit_positions(result, 0), palette, pad=padded))

    if result.draw.clovers:
        box.addWidget(
            draw_row(
                result.draw.clovers,
                {i for i, c in enumerate(result.draw.clovers) if c in set(result.bet.clovers)},
                palette,
                strings.CLOVERS,
                pad=False,
            )
        )
    if result.draw.extra:
        marked = " " + strings.PRIZED.lower() if result.extra_matched else ""
        box.addWidget(label(f"{rules.extra_label}: {result.draw.extra}{marked}", "label"))

    counts = " · ".join(strings.hits(n) for n in result.hit_counts)
    headline = row(label(counts, "h2"), spacing=8)
    if result.won:
        # Lotomania pays for matching nothing, so a win can show no green at all.
        # The chip is what carries it then.
        headline.insertWidget(1, Chip(strings.PRIZED, palette))
    box.addLayout(headline)
    tiers_block(result, box)
    return frame


def contest_block(answer: ContestResult, palette: Palette) -> QWidget:
    """Whatever happened for one contest, drawn as itself."""
    if answer.outcome is Outcome.CHECKED:
        return checked_block(answer, palette)

    frame, box = pane()
    box.addLayout(row(label(str(answer.contest), "h2"), spacing=8))
    if answer.outcome is Outcome.PENDING:
        box.addWidget(label(strings.NOT_DRAWN, "muted"))
    else:
        box.addWidget(label(strings.UNAVAILABLE, "warn"))
        if answer.reason:
            box.addWidget(label(answer.reason, "muted"))
    return frame


def run_summary_line(summary: RunSummary) -> str:
    """Counted honestly: only what was compared counts as checked."""
    parts = [
        strings.RUN_SUMMARY.format(checked=len(summary.checked), total=summary.total),
    ]
    if summary.winning:
        parts.append(strings.RUN_PRIZED.format(count=len(summary.winning)))
    if summary.pending:
        parts.append(strings.RUN_PENDING.format(count=len(summary.pending)))
    if summary.unavailable:
        parts.append(strings.RUN_UNAVAILABLE.format(count=len(summary.unavailable)))
    return " · ".join(parts)
