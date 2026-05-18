from datetime import datetime

import pytest

from database import Listing, add_listing, init_db, update_listing_status
from enums import ListingStatus, ListingType, Sport
from matching import find_matches

GAME_DT = datetime(2025, 11, 15, 14, 0)
OTHER_DT = datetime(2025, 12, 1, 18, 0)


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


def test_have_finds_want_no_date(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=2)
    have_listing, _ = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    matches = find_matches(db, have_listing)
    assert len(matches) == 1
    assert matches[0].matched_poster_user_id == 2
    assert matches[0].new_poster_user_id == 1


def test_have_finds_want_matching_date(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, GAME_DT, user_id=2)
    have_listing, _ = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    matches = find_matches(db, have_listing)
    assert len(matches) == 1
    assert matches[0].matched_poster_user_id == 2


def test_have_no_match_different_date(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, OTHER_DT, user_id=2)
    have_listing, _ = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    matches = find_matches(db, have_listing)
    assert len(matches) == 0


def test_have_no_match_different_sport(db):
    make_listing(db, ListingType.WANT, Sport.VOLLEYBALL, GAME_DT, user_id=2)
    have_listing, _ = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    matches = find_matches(db, have_listing)
    assert len(matches) == 0


def test_have_no_match_inactive_want(db):
    _, want_id = make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=2)
    have_listing, _ = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    update_listing_status(db, want_id, ListingStatus.CLOSED)
    # close_listing(db, want_id)
    matches = find_matches(db, have_listing)
    assert len(matches) == 0


def test_have_finds_multiple_wants(db):
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=2)
    make_listing(db, ListingType.WANT, Sport.FOOTBALL, GAME_DT, user_id=3)
    have_listing, _ = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    matches = find_matches(db, have_listing)
    assert len(matches) == 2


def test_want_finds_have_any_date(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2)
    want_listing, _ = make_listing(
        db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1
    )
    matches = find_matches(db, want_listing)
    assert len(matches) == 1
    assert matches[0].matched_poster_user_id == 2
    assert matches[0].new_poster_user_id == 1


def test_want_finds_have_matching_date(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2)
    want_listing, _ = make_listing(
        db, ListingType.WANT, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    matches = find_matches(db, want_listing)
    assert len(matches) == 1


def test_want_no_match_different_date(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, OTHER_DT, user_id=2)
    want_listing, _ = make_listing(
        db, ListingType.WANT, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    matches = find_matches(db, want_listing)
    assert len(matches) == 0


def test_want_no_match_different_sport(db):
    make_listing(db, ListingType.HAVE, Sport.VOLLEYBALL, GAME_DT, user_id=2)
    want_listing, _ = make_listing(
        db, ListingType.WANT, Sport.FOOTBALL, GAME_DT, user_id=1
    )
    matches = find_matches(db, want_listing)
    assert len(matches) == 0


def test_want_no_match_inactive_have(db):
    have_listing, _ = make_listing(
        db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2
    )
    _, want_id = make_listing(db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1)
    update_listing_status(db, want_id, ListingStatus.CLOSED)
    # close_listing(db, want_id)
    matches = find_matches(db, have_listing)
    assert len(matches) == 0


def test_want_finds_multiple_haves(db):
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=2)
    make_listing(db, ListingType.HAVE, Sport.FOOTBALL, GAME_DT, user_id=3)
    want_listing, _ = make_listing(
        db, ListingType.WANT, Sport.FOOTBALL, None, user_id=1
    )
    matches = find_matches(db, want_listing)
    assert len(matches) == 2
