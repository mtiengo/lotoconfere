"""Orchestration: check this bet over one contest, or over a run of them.

The only place that combines source, store and core. The GUI calls this and
nothing below it.

Result honesty lives here, because this is the layer that knows the difference
between the three outcomes:

* **checked**     -- a draw was obtained and the bet was compared against it.
* **pending**     -- the contest has not been drawn yet. Decided by comparing it
  against the latest known contest, never inferred from a failed request: Caixa
  answers 500 for an undrawn contest, for an impossible one, and presumably for
  a broken server (internal_docs/ENDPOINT.md).
* **unavailable** -- it should exist, and it could not be obtained.

Pending and unavailable are never counted as zero hits and never quietly fold
into a summary.
"""

import threading
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

from lotoconfere.core.check import check_bet
from lotoconfere.core.errors import LotoConfereError, SourceError
from lotoconfere.core.models import Bet, CheckResult, Draw
from lotoconfere.core.rules import validate_bet
from lotoconfere.source.base import ResultsSource
from lotoconfere.source.caixa import CaixaSource
from lotoconfere.store.database import Store


class Outcome(StrEnum):
    """What happened for one contest. Exactly one of these, always."""

    CHECKED = "checked"
    PENDING = "pending"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ContestResult:
    """One contest's answer, whatever kind of answer it turned out to be."""

    contest: int
    outcome: Outcome
    result: CheckResult | None = None
    reason: str | None = None

    @property
    def draw(self) -> Draw | None:
        return None if self.result is None else self.result.draw


@dataclass(frozen=True)
class RunSummary:
    """A teimosinha run, counted honestly.

    `checked` counts contests that were actually compared, so "5 de 8" means five
    were checked and three were not. Nothing here averages over a contest that
    produced no answer.

    A cancelled run keeps what it already found and says it stopped. The contests
    it never reached are absent rather than listed as unavailable: nobody tried
    them, which is not the same as trying and failing.
    """

    results: tuple[ContestResult, ...]
    requested: int = 0
    cancelled: bool = False

    @property
    def checked(self) -> tuple[ContestResult, ...]:
        return tuple(r for r in self.results if r.outcome is Outcome.CHECKED)

    @property
    def pending(self) -> tuple[ContestResult, ...]:
        return tuple(r for r in self.results if r.outcome is Outcome.PENDING)

    @property
    def unavailable(self) -> tuple[ContestResult, ...]:
        return tuple(r for r in self.results if r.outcome is Outcome.UNAVAILABLE)

    @property
    def total(self) -> int:
        """How many contests were asked for, which a cancelled run still knows."""
        return self.requested or len(self.results)

    @property
    def attempted(self) -> int:
        return len(self.results)

    @property
    def best_hits(self) -> int | None:
        """The best hit count among contests that were actually checked."""
        counts = [r.result.hit_count for r in self.checked if r.result is not None]
        return max(counts) if counts else None

    @property
    def winning(self) -> tuple[ContestResult, ...]:
        return tuple(r for r in self.checked if r.result is not None and r.result.won)


class Service:
    """What the GUI talks to."""

    def __init__(
        self,
        store: Store,
        source: ResultsSource | None = None,
        fallback: ResultsSource | None = None,
    ) -> None:
        self.store = store
        self.source = source or CaixaSource()
        # Off unless the caller passes one: the mirror is never consulted by
        # default, and a result from it is labelled wherever it is shown.
        self.fallback = fallback

    # --- getting a draw --------------------------------------------------------

    def latest_contest(self, game: str) -> int | None:
        """The newest drawn contest, from the source if reachable, else from the cache."""
        try:
            draw = self.source.latest(game)
        except SourceError:
            return self.store.latest_cached(game)
        self.store.remember(draw)
        return draw.contest

    def draw_for(self, game: str, contest: int) -> Draw:
        """A draw, from the cache when it is complete, otherwise fetched.

        A cached draw whose prize table was not published yet is refetched, and
        only used as it stands if the fetch fails -- old numbers beat no numbers,
        but a blank prize that could be filled in should be.
        """
        cached = self.store.recall(game, contest)
        if cached is not None and cached.prize_table_published:
            return cached
        try:
            draw = self._fetch(game, contest)
        except SourceError:
            if cached is not None:
                return cached
            raise
        self.store.remember(draw)
        return draw

    def _fetch(self, game: str, contest: int) -> Draw:
        """Caixa first. The mirror only if one was supplied, and only after Caixa fails."""
        try:
            return self.source.contest(game, contest)
        except SourceError:
            if self.fallback is None:
                raise
            return self.fallback.contest(game, contest)

    # --- checking --------------------------------------------------------------

    def check_one(self, bet: Bet, contest: int, latest: int | None = None) -> ContestResult:
        """Check a bet against one contest, or say why it could not be checked."""
        validate_bet(bet)
        horizon = latest if latest is not None else self.latest_contest(bet.game)
        if horizon is not None and contest > horizon:
            return ContestResult(contest=contest, outcome=Outcome.PENDING)
        try:
            draw = self.draw_for(bet.game, contest)
        except LotoConfereError as error:
            return ContestResult(
                contest=contest,
                outcome=Outcome.UNAVAILABLE,
                reason=str(error),
            )
        return ContestResult(
            contest=contest,
            outcome=Outcome.CHECKED,
            result=check_bet(bet, draw),
        )

    def check_run(
        self,
        bet: Bet,
        start: int,
        count: int,
        cancel: threading.Event | None = None,
    ) -> RunSummary:
        """Check a bet over `count` consecutive contests from `start`."""
        results = tuple(self.iter_run(bet, start, count, cancel))
        stopped = cancel is not None and cancel.is_set()
        return RunSummary(results=results, requested=count, cancelled=stopped)

    def iter_run(
        self,
        bet: Bet,
        start: int,
        count: int,
        cancel: threading.Event | None = None,
    ) -> Iterator[ContestResult]:
        """The same run, one contest at a time, so a slow fetch can report progress.

        The horizon is read once: asking the endpoint for the latest contest
        before every row of a teimosinha would be rude and no more accurate.

        `cancel` is checked between contests, never in the middle of one. A run of
        24 contests is 24 requests with a pause between them, and someone who
        started it by mistake must be able to stop it without killing the window
        or leaving a half-written row on screen.
        """
        if count < 1:
            raise ValueError("uma teimosinha tem pelo menos um concurso")
        validate_bet(bet)
        horizon = self.latest_contest(bet.game)
        for contest in range(start, start + count):
            if cancel is not None and cancel.is_set():
                return
            yield self.check_one(bet, contest, latest=horizon)
