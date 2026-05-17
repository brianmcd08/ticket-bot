import sqlite3
from contextlib import closing
from datetime import datetime

import pytest

from database import (
    Listing,
    add_listing,
    deactivate_listing,
    expire_old_listings,
    get_matching_haves,
    get_matching_wants,
    get_user_listings,
    init_db,
)
from enums import ListingType, Sport

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

# get_matching_wants tests


def test_want_no_date_matches_have(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=2)
    results = get_matching_wants(
        db, user_id=1, sport=Sport.FOOTBALL, game_datetime_str=GAME_DT.isoformat()
    )
    assert len(results) == 1


def test_want_matching_date_matches_have(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, GAME_DT, user_id=2)
    results = get_matching_wants(
        db, user_id=1, sport=Sport.FOOTBALL, game_datetime_str=GAME_DT.isoformat()
    )
    assert len(results) == 1


def test_want_different_date_no_match(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, OTHER_DT, user_id=2)
    results = get_matching_wants(
        db, user_id=1, sport=Sport.FOOTBALL, game_datetime_str=GAME_DT.isoformat()
    )
    assert len(results) == 0


def test_want_same_user_no_match(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    results = get_matching_wants(
        db, user_id=1, sport=Sport.FOOTBALL, game_datetime_str=GAME_DT.isoformat()
    )
    assert len(results) == 0


def test_inactive_want_no_match(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    _, listing_id = make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=2)

    deactivate_listing(db, listing_id)
    results = get_matching_wants(
        db, user_id=1, sport=Sport.FOOTBALL, game_datetime_str=GAME_DT.isoformat()
    )
    assert len(results) == 0


# get_matching_haves tests


def test_have_matches_want_no_date(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2)
    results = get_matching_haves(
        db, user_id=1, sport=Sport.FOOTBALL, game_datetime=None
    )
    assert len(results) == 1


def test_have_matches_want_with_date(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, GAME_DT, user_id=1)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2)
    results = get_matching_haves(
        db, user_id=1, sport=Sport.FOOTBALL, game_datetime=GAME_DT
    )
    assert len(results) == 1


def test_have_different_date_no_match(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, GAME_DT, user_id=1)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, OTHER_DT, user_id=2)
    results = get_matching_haves(
        db, user_id=1, sport=Sport.FOOTBALL, game_datetime=GAME_DT
    )
    assert len(results) == 0


def test_have_same_user_no_match(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1)
    results = get_matching_haves(
        db, user_id=1, sport=Sport.FOOTBALL, game_datetime=None
    )
    assert len(results) == 0


def test_inactive_have_no_match(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2
    )

    deactivate_listing(db, listing_id)
    results = get_matching_haves(
        db, user_id=1, sport=Sport.FOOTBALL, game_datetime=None
    )
    assert len(results) == 0


def test_user_can_deactivate_own_listing(db):
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    deactivate_listing(db, listing_id, user_id=1)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 0


def test_user_cannot_deactivate_others_listing(db):
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    deactivate_listing(db, listing_id, user_id=2)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 1


def test_deactivate_already_inactive_listing(db):
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    deactivate_listing(db, listing_id, user_id=1)
    deactivate_listing(db, listing_id, user_id=1)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 0


def test_deactivated_listing_not_in_user_listings(db):
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    deactivate_listing(db, listing_id, user_id=1)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 1


def test_expire_old_haves(db):
    # game_datetime in the past
    past_dt = datetime(2020, 1, 1, 12, 0)
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, past_dt, user_id=1
    )
    expire_old_listings(db)
    listings = get_user_listings(db, user_id=1)
    assert len(listings) == 0


def test_future_have_not_expired(db):
    future_dt = datetime(2099, 1, 1, 12, 0)
    _, listing_id = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, future_dt, user_id=1
    )
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
