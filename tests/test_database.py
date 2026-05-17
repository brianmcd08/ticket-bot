from datetime import datetime

import pytest

from database import (
    Listing,
    add_listing,
    get_matching_haves,
    get_matching_wants,
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
    return add_listing(db_path, listing)


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
    listing_id = make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=2)
    from database import deactivate_listing

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
    listing_id = make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2)
    from database import deactivate_listing

    deactivate_listing(db, listing_id)
    results = get_matching_haves(
        db, user_id=1, sport=Sport.FOOTBALL, game_datetime=None
    )
    assert len(results) == 0
