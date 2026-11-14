import pytest

from database import (
    get_scoreboard,
    init_db,
    mark_final_posted,
    mark_start_posted,
    save_scoreboard_message,
)


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


def test_unknown_match_has_no_record(db):
    assert get_scoreboard(db, "401883963") is None


def test_saved_message_comes_back_with_nothing_posted(db):
    save_scoreboard_message(db, "401883963", channel_id=10, message_id=20)
    record = get_scoreboard(db, "401883963")
    assert record is not None
    assert (record.channel_id, record.message_id) == (10, 20)
    assert not record.start_posted and not record.final_posted


def test_resaving_replaces_message_and_keeps_flags(db):
    save_scoreboard_message(db, "1", 10, 20)
    mark_start_posted(db, "1")
    save_scoreboard_message(db, "1", 10, 99)  # scoreboard re-posted after a delete
    record = get_scoreboard(db, "1")
    assert record.message_id == 99
    assert record.start_posted


def test_marks_are_independent_and_idempotent(db):
    save_scoreboard_message(db, "1", 10, 20)
    mark_start_posted(db, "1")
    mark_start_posted(db, "1")
    record = get_scoreboard(db, "1")
    assert record.start_posted and not record.final_posted
    mark_final_posted(db, "1")
    assert get_scoreboard(db, "1").final_posted


def test_mark_without_a_saved_message_creates_the_row(db):
    mark_final_posted(db, "2")
    record = get_scoreboard(db, "2")
    assert record.final_posted and record.message_id == 0


def test_init_db_is_safe_to_rerun(db):
    save_scoreboard_message(db, "1", 10, 20)
    init_db(db)  # bot restart
    assert get_scoreboard(db, "1").message_id == 20
