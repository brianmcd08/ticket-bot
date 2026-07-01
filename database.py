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
                AND status = ?
                """,
                (user_id, ListingStatus.OPEN),
            )
            rows = cursor.fetchall()
    return rows


def get_open_listings(db_path):
    with closing(sqlite3.connect(database=db_path)) as conn:
        conn.row_factory = sqlite3.Row
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM listings
                WHERE status = ?
                ORDER BY listing_type, sport, posted_at
                """,
                (ListingStatus.OPEN,),
            )
            rows = cursor.fetchall()
    return rows


def get_matches(
    db,
    sport,
    type,
    game_datetime,  # pass as isoformat
):
    with closing(sqlite3.connect(database=db)) as conn:
        query = """
        SELECT * 
        FROM listings
        WHERE listing_type = ?
        AND status IN (?, ?)
        AND sport = ?
        """
        params = [ListingType(type), ListingStatus.OPEN, ListingStatus.MATCHED, sport]
        if game_datetime:
            dt_str = (
                game_datetime.isoformat()
                if isinstance(game_datetime, datetime)
                else game_datetime
            )
            if type == ListingType.HAVE:
                query += " AND game_datetime = ?"
            elif type == ListingType.WANT:
                query += " AND (game_datetime IS NULL OR game_datetime = ?)"
            params.append(dt_str)

        conn.row_factory = sqlite3.Row
        with conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
    return rows


def expire_old_listings(db_path):
    with closing(sqlite3.connect(database=db_path)) as conn:
        with conn:
            conn.execute(
                """
                UPDATE listings SET status = ? WHERE status = ? AND (
                    (listing_type = ? AND game_datetime < ?)
                    OR
                    (listing_type = ? AND posted_at < ?)
                )
                """,
                (
                    ListingStatus.CLOSED,
                    ListingStatus.OPEN,
                    ListingType.HAVE,
                    datetime.now(),
                    ListingType.WANT,
                    (datetime.now() - timedelta(days=182)).isoformat(),
                ),
            )


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
