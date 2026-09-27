"""One SQLite file in the user's data directory: the result cache and saved bets.

Parameterised queries only, everywhere, without exception.

Caching rule: a drawn contest whose prize table has been published never changes,
so it is kept permanently and read offline. One whose table is not out yet is
kept too -- the numbers are already useful -- but marked incomplete, so the next
run fetches it again instead of showing an old blank where a prize belongs.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from platformdirs import user_data_dir

from lotoconfere.core.errors import LotoConfereError
from lotoconfere.core.models import Bet, Draw, PrizeTier, Source

APP_NAME = "LotoConfere"
APP_AUTHOR = "mtiengo"
DATABASE_NAME = "lotoconfere.sqlite3"

# Bumped only when the schema changes in a way older files cannot be read as.
# A file from the future is refused rather than opened hopefully.
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS cached_draw (
    game        TEXT    NOT NULL,
    contest     INTEGER NOT NULL,
    drawn_on    TEXT    NOT NULL,
    numbers     TEXT    NOT NULL,
    second_numbers TEXT,
    extra       TEXT,
    clovers     TEXT    NOT NULL DEFAULT '[]',
    prizes      TEXT,
    source      TEXT    NOT NULL,
    complete    INTEGER NOT NULL,
    PRIMARY KEY (game, contest)
);

CREATE TABLE IF NOT EXISTS saved_bet (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    game         TEXT    NOT NULL,
    numbers      TEXT    NOT NULL,
    run_start    INTEGER,
    run_count    INTEGER
);
"""


class StoreError(LotoConfereError):
    """The local database could not be used."""


def default_path() -> Path:
    """Where the database lives on this operating system."""
    return Path(user_data_dir(APP_NAME, APP_AUTHOR)) / DATABASE_NAME


def encode_prizes(prizes: tuple[PrizeTier, ...] | None) -> str | None:
    """The prize table as JSON, or NULL when it has not been published.

    NULL and "[]" would look alike in a hurry, so the unpublished case is the
    absent column rather than an empty list.
    """
    if prizes is None:
        return None
    return json.dumps(
        [
            {"faixa": t.faixa, "label": t.label, "winners": t.winners, "amount": str(t.amount)}
            for t in prizes
        ]
    )


def decode_prizes(raw: str | None) -> tuple[PrizeTier, ...] | None:
    if raw is None:
        return None
    return tuple(
        PrizeTier(
            faixa=int(row["faixa"]),
            label=str(row["label"]),
            winners=int(row["winners"]),
            amount=Decimal(str(row["amount"])),
        )
        for row in json.loads(raw)
    )


@dataclass(frozen=True)
class SavedBet:
    """A bet someone named and kept, with its teimosinha run if it has one."""

    id: int
    name: str
    bet: Bet
    run_start: int | None = None
    run_count: int | None = None

    @property
    def has_run(self) -> bool:
        return self.run_start is not None and self.run_count is not None


class Store:
    """The local database. One per process; close it when done."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._prepare()

    def _prepare(self) -> None:
        with closing(self._connection.cursor()) as cursor:
            found = int(cursor.execute("PRAGMA user_version").fetchone()[0])
            if found > SCHEMA_VERSION:
                raise StoreError(
                    f"o arquivo de dados foi criado por uma versao mais nova "
                    f"(formato {found}, esta versao entende {SCHEMA_VERSION})"
                )
            cursor.executescript(SCHEMA)
            # No parameter binding in a PRAGMA, so the value is an int constant
            # from this module and never anything a caller supplied.
            cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- the result cache ------------------------------------------------------

    def remember(self, draw: Draw) -> None:
        """Cache a draw, replacing an incomplete copy of the same contest."""
        with self._connection as connection:
            connection.execute(
                """
                INSERT INTO cached_draw
                    (game, contest, drawn_on, numbers, second_numbers, extra, clovers,
                     prizes, source, complete)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (game, contest) DO UPDATE SET
                    drawn_on       = excluded.drawn_on,
                    numbers        = excluded.numbers,
                    second_numbers = excluded.second_numbers,
                    extra          = excluded.extra,
                    clovers        = excluded.clovers,
                    prizes         = excluded.prizes,
                    source         = excluded.source,
                    complete       = excluded.complete
                """,
                (
                    draw.game,
                    draw.contest,
                    draw.drawn_on.isoformat(),
                    json.dumps(list(draw.numbers)),
                    None if draw.second_numbers is None else json.dumps(list(draw.second_numbers)),
                    draw.extra,
                    json.dumps(list(draw.clovers)),
                    encode_prizes(draw.prizes),
                    str(draw.source),
                    int(draw.prize_table_published),
                ),
            )

    def recall(self, game: str, contest: int) -> Draw | None:
        """A cached draw, or None. The caller decides whether an incomplete one will do."""
        row = self._connection.execute(
            "SELECT * FROM cached_draw WHERE game = ? AND contest = ?",
            (game, contest),
        ).fetchone()
        return None if row is None else self._draw_from(row)

    def incomplete_contests(self, game: str) -> tuple[int, ...]:
        """Contests cached without a prize table, which are worth fetching again."""
        rows = self._connection.execute(
            "SELECT contest FROM cached_draw WHERE game = ? AND complete = 0 ORDER BY contest",
            (game,),
        ).fetchall()
        return tuple(int(row["contest"]) for row in rows)

    def latest_cached(self, game: str) -> int | None:
        """The newest contest held for a game, which is the offline horizon."""
        row = self._connection.execute(
            "SELECT MAX(contest) AS newest FROM cached_draw WHERE game = ?",
            (game,),
        ).fetchone()
        return None if row["newest"] is None else int(row["newest"])

    @staticmethod
    def _draw_from(row: sqlite3.Row) -> Draw:
        return Draw(
            game=str(row["game"]),
            contest=int(row["contest"]),
            drawn_on=date.fromisoformat(str(row["drawn_on"])),
            numbers=tuple(json.loads(row["numbers"])),
            source=Source(str(row["source"])),
            prizes=decode_prizes(row["prizes"]),
            second_numbers=(
                None if row["second_numbers"] is None else tuple(json.loads(row["second_numbers"]))
            ),
            extra=None if row["extra"] is None else str(row["extra"]),
            clovers=tuple(json.loads(row["clovers"])),
        )

    # --- saved bets ------------------------------------------------------------

    def save_bet(
        self,
        name: str,
        bet: Bet,
        run_start: int | None = None,
        run_count: int | None = None,
    ) -> int:
        """Store a named bet, optionally with an active teimosinha run."""
        with self._connection as connection:
            cursor = connection.execute(
                """
                INSERT INTO saved_bet (name, game, numbers, run_start, run_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, bet.game, json.dumps(list(bet.numbers)), run_start, run_count),
            )
        return int(cursor.lastrowid or 0)

    def update_bet(
        self,
        bet_id: int,
        name: str,
        bet: Bet,
        run_start: int | None = None,
        run_count: int | None = None,
    ) -> None:
        with self._connection as connection:
            connection.execute(
                """
                UPDATE saved_bet
                   SET name = ?, game = ?, numbers = ?, run_start = ?, run_count = ?
                 WHERE id = ?
                """,
                (name, bet.game, json.dumps(list(bet.numbers)), run_start, run_count, bet_id),
            )

    def delete_bet(self, bet_id: int) -> None:
        with self._connection as connection:
            connection.execute("DELETE FROM saved_bet WHERE id = ?", (bet_id,))

    def saved_bets(self) -> Iterator[SavedBet]:
        """Every saved bet, oldest first."""
        for row in self._connection.execute("SELECT * FROM saved_bet ORDER BY id").fetchall():
            yield SavedBet(
                id=int(row["id"]),
                name=str(row["name"]),
                bet=Bet(game=str(row["game"]), numbers=tuple(json.loads(row["numbers"]))),
                run_start=None if row["run_start"] is None else int(row["run_start"]),
                run_count=None if row["run_count"] is None else int(row["run_count"]),
            )
