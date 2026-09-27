"""The refusals. Every one of these means "I will not guess", never "close enough"."""


class LotoConfereError(Exception):
    """Base for everything this package raises."""


class UnknownGameError(LotoConfereError):
    """A game key that is not in the rule table."""


class InvalidBetError(LotoConfereError):
    """A bet that breaks its game's rules: wrong size, out of range, repeated number."""


class InvalidDrawError(LotoConfereError):
    """A draw that breaks its game's rules.

    This is what a response that failed validation raises. It is never repaired:
    a draw the app cannot trust is one it refuses to check a bet against.
    """


class SourceError(LotoConfereError):
    """A result could not be obtained. Never the same thing as "no prize"."""


class ContestNotFoundError(SourceError):
    """The source says it has no such contest.

    Not the same as "not drawn yet": no status code from either source
    distinguishes those, so pending is decided against the latest known contest
    rather than inferred from a failure. See internal_docs/ENDPOINT.md.
    """


class SourceUnavailableError(SourceError):
    """The source could not be reached, answered badly, or failed verification."""
