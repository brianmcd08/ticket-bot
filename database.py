import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from enums import ListingStatus, ListingType, Sport


@dataclass
class Listing:
    user_id: int
    listing_type: ListingType
    sport: Sport
    game_datetime: Optional[datetime]
    quantity: Optional[int]
    notes: Optional[str]
    posted_at: str
    status: ListingStatus = ListingStatus.OPEN
    message_id: int = 0

    # helper methods for datetime conversion
    def game_datetime_to_str(self) -> Optional[str]:
        return self.game_datetime.isoformat() if self.game_datetime else None

    @classmethod
    def game_datetime_from_str(cls, datetime_str: str) -> Optional[datetime]:
        if not datetime_str:
            return None
        return datetime.fromisoformat(datetime_str)

    def posted_at_to_datetime(self) -> datetime:
        return datetime.fromisoformat(self.posted_at)

    @classmethod
    def from_row(cls, row) -> "Listing":
        """Rebuild a Listing from a database row, e.g. to re-render its embed."""
        return cls(
            user_id=row["user_id"],
            listing_type=ListingType(row["listing_type"]),
            sport=Sport(row["sport"]),
            game_datetime=cls.game_datetime_from_str(row["game_datetime"]),
            quantity=row["quantity"],
            notes=row["notes"],
            posted_at=row["posted_at"],
            status=ListingStatus(row["status"]),
            message_id=row["message_id"],
        )


def init_db(db_path):
    with closing(sqlite3.connect(database=db_path)) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    listing_type TEXT NOT NULL,
                    sport TEXT NOT NULL,
                    game_datetime TEXT,
                    quantity INTEGER,
                    notes TEXT,
                    message_id INTEGER NOT NULL DEFAULT 0,
                    posted_at TEXT NOT NULL,
                    status INTEGER NOT NULL DEFAULT 1
                )
            """)


def add_listing(db_path, listing: Listing):
    with closing(sqlite3.connect(database=db_path)) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO listings
                (
                    user_id,
                    listing_type,
                    sport,
                    game_datetime,
                    quantity,
                    notes,
                    posted_at                
                )
                VALUES
                (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    listing.user_id,
                    listing.listing_type,
                    listing.sport,
                    listing.game_datetime_to_str(),
                    listing.quantity,
                    listing.notes,
                    listing.posted_at,
                ),
            )

            row_id = cursor.lastrowid
            if not row_id:
                raise RuntimeError("Failed to insert listing into database")
            return row_id


def update_message_id(db_path, listing_id, message_id):
    with closing(sqlite3.connect(database=db_path)) as conn:
        with conn:
            conn.execute(
                """
                UPDATE listings
                SET message_id = ?
                WHERE id = ?
                """,
                (message_id, listing_id),
            )


# A match is a notification, not a closure: a MATCHED listing is still live and
# must stay visible in /listings, /mine and /close until its owner closes it.
ACTIVE_STATUSES = (ListingStatus.OPEN, ListingStatus.MATCHED)


def get_user_listings(db_path, user_id):
    with closing(sqlite3.connect(database=db_path)) as conn:
        conn.row_factory = sqlite3.Row
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM listings
                WHERE user_id = ?
                AND status IN (?, ?)
                ORDER BY listing_type, sport, posted_at
                """,
                (user_id, *ACTIVE_STATUSES),
            )
            rows = cursor.fetchall()
    return rows


def get_listing(db_path, listing_id):
    """One listing by id, whatever its status, or None."""
    with closing(sqlite3.connect(database=db_path)) as conn:
        conn.row_factory = sqlite3.Row
        with conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM listings WHERE id = ?", (listing_id,))
            return cursor.fetchone()


def get_open_listings(db_path):
    with closing(sqlite3.connect(database=db_path)) as conn:
        conn.row_factory = sqlite3.Row
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM listings
                WHERE status IN (?, ?)
                ORDER BY listing_type, sport, posted_at
                """,
                ACTIVE_STATUSES,
            )
            rows = cursor.fetchall()
    return rows


def get_matches(
    db,
    sport,
    type,
    game_datetime,  # pass as isoformat
    exclude_user_id=None,
):
    with closing(sqlite3.connect(database=db)) as conn:
        query = """
        SELECT *
        FROM listings
        WHERE listing_type = ?
        AND status IN (?, ?)
        AND sport = ?
        """
        params = [ListingType(type), *ACTIVE_STATUSES, sport]
        if exclude_user_id is not None:
            query += " AND user_id != ?"
            params.append(exclude_user_id)
        if game_datetime:
            dt_str = (
                game_datetime.isoformat()
                if isinstance(game_datetime, datetime)
                else game_datetime
            )
            # Match on the calendar day, not the exact timestamp. Two people
            # describing the same game reliably agree on the date and almost
            # never on the minute (or even AM/PM), so exact equality here meant
            # real pairs silently never matched.
            day = dt_str[:10]
            if type == ListingType.HAVE:
                query += " AND substr(game_datetime, 1, 10) = ?"
            elif type == ListingType.WANT:
                query += (
                    " AND (game_datetime IS NULL OR substr(game_datetime, 1, 10) = ?)"
                )
            params.append(day)

        conn.row_factory = sqlite3.Row
        with conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
    return rows


def expire_old_listings(db_path):
    now = datetime.now()
    with closing(sqlite3.connect(database=db_path)) as conn:
        with conn:
            conn.execute(
                """
                UPDATE listings SET status = ? WHERE status IN (?, ?) AND (
                    (listing_type = ? AND substr(game_datetime, 1, 10) < ?)
                    OR
                    (listing_type = ? AND posted_at < ?)
                )
                """,
                (
                    ListingStatus.CLOSED,
                    *ACTIVE_STATUSES,
                    ListingType.HAVE,
                    # Compare day-to-day with a plain string. Passing a datetime
                    # object relied on sqlite3's implicit adapter, which is
                    # deprecated in 3.12 and renders "YYYY-MM-DD HH:MM:SS" with a
                    # space, so it never compared correctly against our stored
                    # isoformat values with a "T".
                    now.date().isoformat(),
                    ListingType.WANT,
                    (now - timedelta(days=182)).isoformat(),
                ),
            )


def close_all_listings(db_path):
    """Close every active listing. Returns the rows as they were before closing.

    The caller needs the returned message_ids to mark the channel posts closed,
    so the select and the update happen in one transaction.
    """
    with closing(sqlite3.connect(database=db_path)) as conn:
        conn.row_factory = sqlite3.Row
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM listings WHERE status IN (?, ?)", ACTIVE_STATUSES
            )
            rows = cursor.fetchall()
            cursor.execute(
                "UPDATE listings SET status = ? WHERE status IN (?, ?)",
                (ListingStatus.CLOSED, *ACTIVE_STATUSES),
            )
    return rows


def update_listing_status(db_path, listing_id, listing_status):
    with closing(sqlite3.connect(database=db_path)) as conn:
        with conn:
            conn.execute(
                """
                UPDATE listings SET status = ? 
                WHERE id = ?
                """,
                (listing_status, listing_id),
            )


def find_listings_in_matched_status(db_path):
    with closing(sqlite3.connect(database=db_path)) as conn:
        conn.row_factory = sqlite3.Row
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * 
                FROM listings
                WHERE status = ?
                """,
                (ListingStatus.MATCHED,),
            )
            rows = cursor.fetchall()
    return rows
