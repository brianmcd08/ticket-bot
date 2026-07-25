import sqlite3
from contextlib import closing
from datetime import datetime

import pytest

from database import (
    Listing,
    add_listing,
    close_all_listings,
    expire_old_listings,
    find_listings_in_matched_status,
    get_matches,
    # get_matching_haves,
    # get_matching_wants,
    get_open_listings,
    get_user_listings,
    init_db,
    update_listing_status,
    update_message_id,
)
from enums import ListingStatus, ListingType, Sport

DB_PATH = ":memory:"


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


def make_listing(db_path, listing_type, sport, game_datetime=None, user_id=1):
    listing = Listing(
        user_id=user_id,
        listing_type=listing_type,
        sport=sport,
        game_datetime=game_datetime,
        quantity=2,
        notes=None,
        posted_at=datetime.now().isoformat(),
    )
    listing_id = add_listing(db_path, listing)
    return (listing, listing_id)


GAME_DT = datetime(2025, 11, 15, 14, 0)
OTHER_DT = datetime(2025, 12, 1, 18, 0)


def test_want_no_date_matches_have(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=2)
    results = get_matches(
        db,
        sport=Sport.FOOTBALL,
        type=ListingType.WANT,
        game_datetime=GAME_DT.isoformat(),
    )
    assert len(results) == 1


def test_want_matching_date_matches_have(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, GAME_DT, user_id=2)
    results = get_matches(
        db,
        sport=Sport.FOOTBALL,
        type=ListingType.WANT,
        game_datetime=GAME_DT.isoformat(),
    )
    assert len(results) == 1


def test_want_different_date_no_match(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, OTHER_DT, user_id=2)
    results = get_matches(
        db,
        sport=Sport.FOOTBALL,
        type=ListingType.WANT,
        game_datetime=GAME_DT.isoformat(),
    )
    assert len(results) == 0


def test_inactive_want_no_match(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    _, listing_id = make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=2)

    update_listing_status(db, listing_id, ListingStatus.CLOSED)
    results = get_matches(
        db,
        sport=Sport.FOOTBALL,
        type=ListingType.WANT,
        game_datetime=GAME_DT.isoformat(),
    )
    assert len(results) == 0


def test_have_matches_want_no_date(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2)
    results = get_matches(
        db,
        sport=Sport.FOOTBALL,
        type=ListingType.WANT,
        game_datetime=None,
    )
    assert len(results) == 1


def test_have_matches_want_with_date(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, GAME_DT, user_id=1)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2)
    results = get_matches(
        db,
        sport=Sport.FOOTBALL,
        type=ListingType.WANT,
        game_datetime=GAME_DT.isoformat(),
    )
    assert len(results) == 1


def test_have_different_date_no_match(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, GAME_DT, user_id=1)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, OTHER_DT, user_id=2)
    results = get_matches(
        db,
        type=ListingType.HAVE,
        sport=Sport.FOOTBALL,
        game_datetime=GAME_DT.isoformat(),
    )
    assert len(results) == 0


def test_inactive_have_no_match(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2
    )
    update_listing_status(db, listing_id, ListingStatus.CLOSED)
    results = get_matches(
        db, type=ListingType.HAVE, sport=Sport.FOOTBALL, game_datetime=None
    )
    assert len(results) == 0


def test_deactivate_already_inactive_listing(db):
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    update_listing_status(db, listing_id, ListingStatus.CLOSED)
    update_listing_status(db, listing_id, ListingStatus.CLOSED)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 0


def test_deactivated_listing_not_in_user_listings(db):
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    update_listing_status(db, listing_id, ListingStatus.CLOSED)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 1


def test_expire_old_haves(db):
    # game_datetime in the past
    past_dt = datetime(2020, 1, 1, 12, 0)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, past_dt, user_id=1)
    expire_old_listings(db)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 0


def test_future_have_not_expired(db):
    future_dt = datetime(2099, 1, 1, 12, 0)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, future_dt, user_id=1)
    expire_old_listings(db)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 1


def test_expire_old_wants(db):
    _, listing_id = make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    # manually backdate posted_at
    with closing(sqlite3.connect(db)) as conn:
        with conn:
            conn.execute(
                "UPDATE listings SET posted_at = ? WHERE id = ?",
                (datetime(2020, 1, 1).isoformat(), listing_id),
            )
    expire_old_listings(db)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 0


def test_recent_want_not_expired(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    expire_old_listings(db)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 1


def test_matched_want_still_matches_have(db):
    """A WANT in MATCHED status should still appear as a match for a new HAVE."""
    _, want_id = make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=2)
    update_listing_status(db, want_id, ListingStatus.MATCHED)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    results = get_matches(
        db,
        type=ListingType.WANT,
        sport=Sport.FOOTBALL,
        game_datetime=GAME_DT.isoformat(),
    )
    assert len(results) == 1


def test_closed_want_does_not_match_have(db):
    """A WANT in CLOSED status should not appear as a match."""
    _, want_id = make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=2)
    update_listing_status(db, want_id, ListingStatus.CLOSED)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    results = get_matches(
        db,
        type=ListingType.WANT,
        sport=Sport.FOOTBALL,
        game_datetime=GAME_DT.isoformat(),
    )
    assert len(results) == 0


def test_matched_have_still_matches_want(db):
    """A HAVE in MATCHED status should still appear as a match for a new WANT."""
    _, have_id = make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2)
    update_listing_status(db, have_id, ListingStatus.MATCHED)
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    results = get_matches(
        db, type=ListingType.HAVE, sport=Sport.FOOTBALL, game_datetime=None
    )
    assert len(results) == 1


def test_closed_have_does_not_match_want(db):
    """A HAVE in CLOSED status should not appear as a match."""
    _, have_id = make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2)
    update_listing_status(db, have_id, ListingStatus.CLOSED)
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    results = get_matches(
        db, type=ListingType.HAVE, sport=Sport.FOOTBALL, game_datetime=None
    )
    assert len(results) == 0


def test_set_listing_status_to_matched(db):
    """set_listing_status should correctly update a listing's status."""
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    update_listing_status(db, listing_id, ListingStatus.MATCHED)
    with closing(sqlite3.connect(db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM listings WHERE id = ?", (listing_id,)
        ).fetchone()
    assert row["status"] == ListingStatus.MATCHED


def test_get_matched_listings(db):
    """Get all listings in the db that have a MATCHED status"""
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.VOLLEYBALL, GAME_DT, user_id=1
    )
    update_listing_status(db, listing_id, ListingStatus.MATCHED)
    _, listing_id = make_listing(
        db, ListingType.WANT, Sport.MENS_BASKETBALL, GAME_DT, user_id=2
    )
    update_listing_status(db, listing_id, ListingStatus.MATCHED)
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.MENS_BASKETBALL, GAME_DT, user_id=2
    )

    listings = find_listings_in_matched_status(db)
    assert len(listings) == 2


def test_get_open_listings_excludes_closed(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    _, closed_id = make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=2)
    update_listing_status(db, closed_id, ListingStatus.CLOSED)

    listings = get_open_listings(db)
    assert len(listings) == 1
    assert listings[0]["listing_type"] == ListingType.HAVE


def test_get_open_listings_includes_matched(db):
    """A match is a notification, not a closure: the listing stays visible."""
    _, matched_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    update_listing_status(db, matched_id, ListingStatus.MATCHED)

    listings = get_open_listings(db)
    assert len(listings) == 1


def test_get_user_listings_includes_matched(db):
    """/mine and /close must still show a listing after it has matched."""
    _, matched_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    update_listing_status(db, matched_id, ListingStatus.MATCHED)

    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 1


def test_matches_ignore_time_of_day(db):
    """Same game day, different start time entered, still a match."""
    make_listing(
        db, ListingType.WANT, Sport.FOOTBALL, datetime(2025, 11, 15, 19, 30), user_id=1
    )
    results = get_matches(
        db,
        type=ListingType.WANT,
        sport=Sport.FOOTBALL,
        game_datetime=datetime(2025, 11, 15, 7, 0).isoformat(),
    )
    assert len(results) == 1


def test_matches_exclude_own_listings(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, GAME_DT, user_id=1)
    results = get_matches(
        db,
        type=ListingType.WANT,
        sport=Sport.FOOTBALL,
        game_datetime=GAME_DT.isoformat(),
        exclude_user_id=1,
    )
    assert len(results) == 0


def test_expire_leaves_game_earlier_today(db):
    """A game today has not passed just because its start time has."""
    earlier_today = datetime.now().replace(hour=0, minute=1)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, earlier_today, user_id=1)
    expire_old_listings(db)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 1


def test_close_all_listings_closes_open_and_matched(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    _, matched_id = make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=2)
    update_listing_status(db, matched_id, ListingStatus.MATCHED)

    rows = close_all_listings(db)

    assert len(rows) == 2
    assert get_open_listings(db) == []
    assert get_user_listings(db, user_id=1) == []
    assert get_user_listings(db, user_id=2) == []


def test_close_all_listings_returns_message_ids(db):
    """The caller needs message_ids to grey out the channel posts."""
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    update_message_id(db, listing_id=listing_id, message_id=4242)

    rows = close_all_listings(db)

    assert [row["message_id"] for row in rows] == [4242]


def test_close_all_listings_on_empty_db(db):
    assert close_all_listings(db) == []


def test_close_all_listings_leaves_already_closed_alone(db):
    _, closed_id = make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    update_listing_status(db, closed_id, ListingStatus.CLOSED)

    rows = close_all_listings(db)

    assert rows == []


def test_expire_closes_matched_listings_too(db):
    past_dt = datetime(2020, 1, 1, 12, 0)
    _, listing_id = make_listing(db, ListingType.HAVE, Sport.FOOTBALL, past_dt, user_id=1)
    update_listing_status(db, listing_id, ListingStatus.MATCHED)
    expire_old_listings(db)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 0
