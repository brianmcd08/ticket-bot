from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from config import ListingType, Sport
from database import Listing, get_matching_haves, get_matching_wants


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
    if listing.listing_type == ListingType.HAVE:
        rows = get_matching_wants(
            db_path=db_path,
            user_id=listing.user_id,
            sport=listing.sport,
            game_datetime_str=listing.game_datetime_to_str(),
        )
    else:  # WANT
        rows = get_matching_haves(
            db_path=db_path,
            user_id=listing.user_id,
            sport=listing.sport,
            game_datetime=listing.game_datetime,
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
