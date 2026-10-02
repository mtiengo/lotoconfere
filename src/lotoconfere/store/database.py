"""One SQLite file in the user's data directory: the result cache and saved bets.

Saved bets are kept in batches: a name, a game and an optional teimosinha run,
holding one or more bets that are each edited, removed or re-saved on their own.

Parameterised queries only, everywhere, without exception.

Caching rule: a drawn contest whose prize table has been published never changes,
so it is kept permanently and read offline. One whose table is not out yet is
kept too -- the numbers are already useful -- but marked incomplete, so the next
run fetches it again instead of showing an old blank where a prize belongs.
"""

import json
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from platformdirs import user_data_dir

from lotoconfere.core.errors import LotoConfereError
from lotoconfere.core.models import Bet, Draw, PrizeTier, Source

APP_NAME = "LotoConfere"
APP_AUTHOR = "mtiengo"
DATABASE_NAME = "lotoconfere.sqlite3"

# Stored preferences, by name. The mirror is off unless someone turns it on.
USE_MIRROR = "usar_espelho"
YES = "sim"
NO = "nao"

# Bumped only when the schema changes in a way older files cannot be read as.
# A file from the future is refused rather than opened hopefully; an older one
# is migrated in _prepare.
#   2: cached_draw.fetched_at, so the app can say when its offline copy is from.
#   3: saved_bet.extra, .clovers and .columns. Before this a saved bet kept only
#      its numbers, so a month, team, trevos or Super Sete columns were lost.
#   4: saved_batch and batch_bet replace saved_bet; each old bet becomes a
#      batch of one, keeping its id.
SCHEMA_VERSION = 4
VERSION_WITH_FETCH_TIME = 2
VERSION_WITH_FULL_BETS = 3
VERSION_WITH_BATCHES = 4

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
    -- Nullable: rows written by a version 1 file predate this column, and an
    -- unknown fetch time must read as unknown rather than as "just now".
    fetched_at  TEXT,
    PRIMARY KEY (game, contest)
);

CREATE TABLE IF NOT EXISTS setting (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_batch (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL,
    game         TEXT    NOT NULL,
    run_start    INTEGER,
    run_count    INTEGER
);

-- The game lives on the batch, so a batch cannot hold bets of two games.
CREATE TABLE IF NOT EXISTS batch_bet (
    batch_id     INTEGER NOT NULL,
    position     INTEGER NOT NULL,
    numbers      TEXT    NOT NULL,
    extra        TEXT,
    clovers      TEXT    NOT NULL DEFAULT '[]',
    columns      TEXT    NOT NULL DEFAULT '[]',
    PRIMARY KEY (batch_id, position)
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


def _encode_bet(bet: Bet) -> tuple[str, str | None, str, str]:
    """A bet's marks as the batch_bet columns hold them, in column order."""
    return (
        json.dumps(list(bet.numbers)),
        bet.extra,
        json.dumps(list(bet.clovers)),
        json.dumps([list(column) for column in bet.columns]),
    )


def _decode_bet(game: str, row: sqlite3.Row) -> Bet:
    return Bet(
        game=game,
        numbers=tuple(json.loads(row["numbers"])),
        extra=None if row["extra"] is None else str(row["extra"]),
        clovers=tuple(json.loads(row["clovers"])),
        columns=tuple(tuple(column) for column in json.loads(row["columns"])),
    )


def _game_of(bets: Sequence[Bet]) -> str:
    """The one game a batch is for. An empty or mixed batch is a caller's bug."""
    games = {bet.game for bet in bets}
    if len(games) != 1:
        raise ValueError("a batch holds at least one bet, all of the same game")
    return games.pop()


@dataclass(frozen=True)
class SavedBatch:
    """Bets someone named and kept together, with a shared teimosinha run if any."""

    id: int
    name: str
    game: str
    bets: tuple[Bet, ...]
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
        # The GUI fetches on a worker thread and the store is what it writes to,
        # so the connection has to be usable from more than the thread that
        # opened it. sqlite3 refuses that by default; the lock is what makes it
        # safe, by serialising every statement rather than hoping they do not
        # overlap.
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._prepare()

    def _prepare(self) -> None:
        with self._lock, closing(self._connection.cursor()) as cursor:
            found = int(cursor.execute("PRAGMA user_version").fetchone()[0])
            if found > SCHEMA_VERSION:
                raise StoreError(
                    f"o arquivo de dados foi criado por uma versão mais nova "
                    f"(formato {found}, esta versão entende {SCHEMA_VERSION})"
                )
            cursor.executescript(SCHEMA)
            self._migrate(cursor, found)
            # No parameter binding in a PRAGMA, so the value is an int constant
            # from this module and never anything a caller supplied.
            cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self._connection.commit()

    @staticmethod
    def _migrate(cursor: sqlite3.Cursor, found: int) -> None:
        """Bring an older file up to date. CREATE TABLE IF NOT EXISTS covers new ones."""
        if found and found < VERSION_WITH_FETCH_TIME:
            columns = {row["name"] for row in cursor.execute("PRAGMA table_info(cached_draw)")}
            if "fetched_at" not in columns:
                cursor.execute("ALTER TABLE cached_draw ADD COLUMN fetched_at TEXT")
        if found and found < VERSION_WITH_FULL_BETS:
            # Rows saved before this keep what they had. What was never stored
            # cannot be recovered, and such a bet fails validation when checked
            # rather than being checked without its month or trevos.
            columns = {row["name"] for row in cursor.execute("PRAGMA table_info(saved_bet)")}
            # A version 1 file may never have created the table at all.
            if columns and "extra" not in columns:
                cursor.execute("ALTER TABLE saved_bet ADD COLUMN extra TEXT")
            if columns and "clovers" not in columns:
                cursor.execute(
                    "ALTER TABLE saved_bet ADD COLUMN clovers TEXT NOT NULL DEFAULT '[]'"
                )
            if columns and "columns" not in columns:
                cursor.execute(
                    "ALTER TABLE saved_bet ADD COLUMN columns TEXT NOT NULL DEFAULT '[]'"
                )
        if found and found < VERSION_WITH_BATCHES:
            Store._move_bets_into_batches(cursor)

    @staticmethod
    def _move_bets_into_batches(cursor: sqlite3.Cursor) -> None:
        """Each old saved bet becomes a batch of one.

        INSERT OR IGNORE so that a file whose migration died before the version
        bump can run it again without duplicating anything.
        """
        if not list(cursor.execute("PRAGMA table_info(saved_bet)")):
            return
        cursor.execute(
            """
            INSERT OR IGNORE INTO saved_batch (id, name, game, run_start, run_count)
            SELECT id, name, game, run_start, run_count FROM saved_bet
            """
        )
        cursor.execute(
            """
            INSERT OR IGNORE INTO batch_bet (batch_id, position, numbers, extra, clovers, columns)
            SELECT id, 0, numbers, extra, clovers, columns FROM saved_bet
            """
        )
        cursor.execute("DROP TABLE saved_bet")

    def _read(self, sql: str, parameters: tuple[object, ...] = ()) -> sqlite3.Cursor:
        """One read, serialised like every other statement."""
        with self._lock:
            return self._connection.execute(sql, parameters)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- the result cache ------------------------------------------------------

    def remember(self, draw: Draw, fetched_at: datetime | None = None) -> None:
        """Cache a draw, replacing an incomplete copy of the same contest.

        The fetch time is what lets the app say "showing saved results from
        dd/mm/yyyy hh:mm" instead of implying the numbers are current.
        """
        with self._lock, self._connection as connection:
            connection.execute(
                """
                INSERT INTO cached_draw
                    (game, contest, drawn_on, numbers, second_numbers, extra, clovers,
                     prizes, source, complete, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (game, contest) DO UPDATE SET
                    drawn_on       = excluded.drawn_on,
                    numbers        = excluded.numbers,
                    second_numbers = excluded.second_numbers,
                    extra          = excluded.extra,
                    clovers        = excluded.clovers,
                    prizes         = excluded.prizes,
                    source         = excluded.source,
                    complete       = excluded.complete,
                    fetched_at     = excluded.fetched_at
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
                    (fetched_at or datetime.now(UTC)).isoformat(),
                ),
            )

    def recall(self, game: str, contest: int) -> Draw | None:
        """A cached draw, or None. The caller decides whether an incomplete one will do."""
        row = self._read(
            "SELECT * FROM cached_draw WHERE game = ? AND contest = ?",
            (game, contest),
        ).fetchone()
        return None if row is None else self._draw_from(row)

    def incomplete_contests(self, game: str) -> tuple[int, ...]:
        """Contests cached without a prize table, which are worth fetching again."""
        rows = self._read(
            "SELECT contest FROM cached_draw WHERE game = ? AND complete = 0 ORDER BY contest",
            (game,),
        ).fetchall()
        return tuple(int(row["contest"]) for row in rows)

    def fetched_at(self, game: str, contest: int) -> datetime | None:
        """When one cached contest was downloaded, or None if that is not recorded."""
        row = self._read(
            "SELECT fetched_at FROM cached_draw WHERE game = ? AND contest = ?",
            (game, contest),
        ).fetchone()
        if row is None or row["fetched_at"] is None:
            return None
        return datetime.fromisoformat(str(row["fetched_at"]))

    def last_updated(self, game: str | None = None) -> datetime | None:
        """The most recent download, for a game or across all of them.

        This is what the offline notice reads. None means nothing has been
        downloaded yet, which is a different sentence from an old timestamp.
        """
        if game is None:
            row = self._read("SELECT MAX(fetched_at) AS newest FROM cached_draw").fetchone()
        else:
            row = self._read(
                "SELECT MAX(fetched_at) AS newest FROM cached_draw WHERE game = ?", (game,)
            ).fetchone()
        return None if row["newest"] is None else datetime.fromisoformat(str(row["newest"]))

    def latest_cached(self, game: str) -> int | None:
        """The newest contest held for a game, which is the offline horizon."""
        row = self._read(
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

    # --- settings ----------------------------------------------------------------

    def setting(self, key: str, default: str = "") -> str:
        """One stored preference, or the default when it was never set."""
        row = self._read("SELECT value FROM setting WHERE key = ?", (key,)).fetchone()
        return default if row is None else str(row["value"])

    def set_setting(self, key: str, value: str) -> None:
        with self._lock, self._connection as connection:
            connection.execute(
                "INSERT INTO setting (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def flag(self, key: str, *, default: bool = False) -> bool:
        """A yes/no preference. Anything unrecognised reads as the default."""
        stored = self.setting(key, YES if default else NO)
        return stored == YES

    def set_flag(self, key: str, value: bool) -> None:
        self.set_setting(key, YES if value else NO)

    # --- saved bets ------------------------------------------------------------

    def save_batch(
        self,
        name: str,
        bets: Sequence[Bet],
        run_start: int | None = None,
        run_count: int | None = None,
    ) -> int:
        """Store named bets of one game, optionally with a shared teimosinha run."""
        game = _game_of(bets)
        with self._lock, self._connection as connection:
            cursor = connection.execute(
                "INSERT INTO saved_batch (name, game, run_start, run_count) VALUES (?, ?, ?, ?)",
                (name, game, run_start, run_count),
            )
            batch_id = int(cursor.lastrowid or 0)
            self._write_bets(connection, batch_id, bets)
        return batch_id

    def update_batch(
        self,
        batch_id: int,
        name: str,
        bets: Sequence[Bet],
        run_start: int | None = None,
        run_count: int | None = None,
    ) -> None:
        """Replace a batch's name, run and bets in one transaction."""
        game = _game_of(bets)
        with self._lock, self._connection as connection:
            connection.execute(
                """
                UPDATE saved_batch SET name = ?, game = ?, run_start = ?, run_count = ?
                 WHERE id = ?
                """,
                (name, game, run_start, run_count, batch_id),
            )
            connection.execute("DELETE FROM batch_bet WHERE batch_id = ?", (batch_id,))
            self._write_bets(connection, batch_id, bets)

    @staticmethod
    def _write_bets(connection: sqlite3.Connection, batch_id: int, bets: Sequence[Bet]) -> None:
        connection.executemany(
            """
            INSERT INTO batch_bet (batch_id, position, numbers, extra, clovers, columns)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [(batch_id, position, *_encode_bet(bet)) for position, bet in enumerate(bets)],
        )

    def delete_batch(self, batch_id: int) -> None:
        with self._lock, self._connection as connection:
            connection.execute("DELETE FROM batch_bet WHERE batch_id = ?", (batch_id,))
            connection.execute("DELETE FROM saved_batch WHERE id = ?", (batch_id,))

    def saved_batches(self) -> Iterator[SavedBatch]:
        """Every saved batch, oldest first, each with its bets in the order entered."""
        batches = self._read("SELECT * FROM saved_batch ORDER BY id").fetchall()
        rows = self._read("SELECT * FROM batch_bet ORDER BY batch_id, position").fetchall()
        bets: dict[int, list[sqlite3.Row]] = {}
        for row in rows:
            bets.setdefault(int(row["batch_id"]), []).append(row)
        for batch in batches:
            game = str(batch["game"])
            yield SavedBatch(
                id=int(batch["id"]),
                name=str(batch["name"]),
                game=game,
                bets=tuple(_decode_bet(game, row) for row in bets.get(int(batch["id"]), [])),
                run_start=None if batch["run_start"] is None else int(batch["run_start"]),
                run_count=None if batch["run_count"] is None else int(batch["run_count"]),
            )
