from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from database import Listing, get_matches
from enums import ListingType, Sport


@dataclass
class MatchResult:
    new_poster_user_id: int
    matched_poster_user_id: int
    listing_id: int
    listing_type: ListingType
    sport: Sport
    game_datetime: Optional[datetime]
    quantity: Optional[int]
    notes: Optional[str]


def find_matches(db_path, listing: Listing) -> list[MatchResult]:
    rows = []
    # Never match someone with their own listing: it pinged the poster about
    # themselves and flipped their other listing to MATCHED.
    if listing.listing_type == ListingType.HAVE:
        rows = get_matches(
            db=db_path,
            type=ListingType.WANT,
            sport=listing.sport,
            game_datetime=listing.game_datetime,
            exclude_user_id=listing.user_id,
        )
    else:  # WANT
        rows = get_matches(
            db=db_path,
            type=ListingType.HAVE,
            sport=listing.sport,
            game_datetime=listing.game_datetime,
            exclude_user_id=listing.user_id,
        )
    return [
        MatchResult(
            new_poster_user_id=listing.user_id,
            matched_poster_user_id=row["user_id"],
            listing_id=row["id"],
            listing_type=row["listing_type"],
            sport=row["sport"],
            game_datetime=Listing.game_datetime_from_str(row["game_datetime"]),
            quantity=row["quantity"],
            notes=row["notes"],
        )
        for row in rows
    ]
