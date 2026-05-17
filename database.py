import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from enums import ListingType, Sport


@dataclass
class Listing:
    user_id: int
    listing_type: ListingType
    sport: Sport
    game_datetime: Optional[datetime]
    quantity: Optional[int]
    notes: Optional[str]
    posted_at: str
    is_active: int = 1
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
                    is_active INTEGER NOT NULL DEFAULT 1
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


def deactivate_listing(db_path, listing_id, user_id=None):
    query = "UPDATE listings SET is_active = 0 WHERE id = ?"
    params = [listing_id]

    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)

    with closing(sqlite3.connect(database=db_path)) as conn:
        with conn:
            conn.execute(query, params)


def get_user_listings(db_path, user_id):
    with closing(sqlite3.connect(database=db_path)) as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * 
                FROM listings
                WHERE user_id = ?
                AND is_active = 1
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
    return rows


def get_matching_wants(
    db_path,
    user_id,
    sport,
    game_datetime_str,
):
    with closing(sqlite3.connect(database=db_path)) as conn:
        conn.row_factory = sqlite3.Row
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * 
                FROM listings
                WHERE listing_type = ?
                AND user_id != ?
                AND is_active = 1
                AND sport = ?
                AND (game_datetime IS NULL OR game_datetime = ?)
                """,
                (
                    ListingType.WANT,
                    user_id,
                    sport,
                    game_datetime_str,
                ),
            )
            rows = cursor.fetchall()
    return rows


def get_matching_haves(
    db_path,
    user_id,
    sport,
    game_datetime,
):

    with closing(sqlite3.connect(database=db_path)) as conn:
        query = """
                SELECT * 
                FROM listings
                WHERE listing_type = ?
                AND user_id != ?
                AND is_active = 1
                AND sport = ?
                """
        params = [ListingType.HAVE, user_id, sport]

        if game_datetime:
            query += " AND game_datetime = ?"
            params.append(game_datetime.isoformat())

        conn.row_factory = sqlite3.Row
        with conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
    return rows
