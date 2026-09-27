"""The one seam where a Protocol earns its place: where results come from.

Two implementations, Caixa and the community mirror. Both answer in core types,
both validate against the rule table, and both say which of them spoke.
"""

from typing import Protocol

from lotoconfere.core.models import Draw, Source


class ResultsSource(Protocol):
    """Somewhere draws can be fetched from."""

    name: Source

    def latest(self, game: str) -> Draw:
        """The newest drawn contest for a game."""
        ...

    def contest(self, game: str, number: int) -> Draw:
        """One contest by number."""
        ...
