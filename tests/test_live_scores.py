import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import discord
import pytest

from cogs.scores import active_games, sync_game
from database import get_scoreboard, init_db
from espn import PITT_TEAM_ID, GameState
from tests.test_scores_format import make_game

ROLE = 555
START = datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)


class FakeMessage:
    def __init__(self, channel, message_id, content=None, embed=None):
        self.channel = channel
        self.id = message_id
        self.content = content
        self.embed = embed
        self.jump_url = f"https://discord.com/channels/1/{channel.id}/{message_id}"

    async def edit(self, embed=None):
        if self.id in self.channel.deleted:
            raise discord.NotFound(_Response(), "Unknown Message")  # type: ignore[arg-type]
        self.channel.edits.append(embed)
        self.embed = embed


class _Response:
    status = 404
    reason = "Not Found"


class FakeChannel:
    id = 42

    def __init__(self):
        self.sent: list[FakeMessage] = []
        self.edits = []
        self.deleted: set[int] = set()
        self.mentions = []

    async def send(self, content=None, embed=None, allowed_mentions=None):
        message = FakeMessage(self, 1000 + len(self.sent), content, embed)
        self.sent.append(message)
        self.mentions.append(allowed_mentions)
        return message

    def get_partial_message(self, message_id):
        return FakeMessage(self, message_id)

    @property
    def texts(self):
        return [m.content for m in self.sent if m.content]


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


def run(db, channel: Any, game, cache, role: int | None = ROLE):
    asyncio.run(sync_game(db, channel, game, PITT_TEAM_ID, role, cache))


def test_nothing_posted_before_the_match():
    channel, cache = FakeChannel(), {}
    run(":memory:", channel, make_game(state=GameState.PRE), cache)
    assert channel.sent == []


def test_going_live_posts_scoreboard_then_pinged_start_linking_it(db):
    channel, cache = FakeChannel(), {}
    run(db, channel, make_game(), cache)

    scoreboard, start = channel.sent
    assert scoreboard.embed is not None and scoreboard.content is None
    assert start.content and start.content.startswith(f"<@&{ROLE}> ")
    assert scoreboard.jump_url in start.content
    assert [r.id for r in channel.mentions[1].roles] == [ROLE]
    record = get_scoreboard(db, "1")
    assert record and record.message_id == scoreboard.id and record.start_posted


def test_later_updates_edit_the_same_scoreboard_and_skip_no_change(db):
    channel, cache = FakeChannel(), {}
    run(db, channel, make_game(), cache)
    run(db, channel, make_game(), cache)  # same score: no edit
    assert channel.edits == []

    run(db, channel, make_game(pitt=(2, (25, 22, 15))), cache)
    assert len(channel.sent) == 2  # no new messages
    assert len(channel.edits) == 1


def test_restart_mid_match_reuses_the_message_and_does_not_repost_start(db):
    channel = FakeChannel()
    run(db, channel, make_game(), {})
    run(db, channel, make_game(), {})  # fresh cache, as after a restart
    assert len(channel.sent) == 2
    assert len(channel.edits) == 1


def test_deleted_scoreboard_is_replaced(db):
    channel, cache = FakeChannel(), {}
    run(db, channel, make_game(), cache)
    channel.deleted.add(channel.sent[0].id)
    run(db, channel, make_game(pitt=(2, (25, 22, 15))), cache)

    assert len(channel.sent) == 3
    assert channel.sent[2].embed is not None
    record = get_scoreboard(db, "1")
    assert record and record.message_id == channel.sent[2].id


def test_final_posts_once_with_a_ping(db):
    channel, cache = FakeChannel(), {}
    run(db, channel, make_game(), cache)
    final = make_game(state=GameState.FINAL, pitt=(3, (25, 22, 25, 25)), opp=(1, (20, 25, 18, 21)))
    run(db, channel, final, cache)
    run(db, channel, final, cache)

    assert len(channel.sent) == 3
    assert channel.texts[-1] == (
        f"<@&{ROLE}> 🏐 Final: Pitt def. Louisville 3-1 (25-20, 22-25, 25-18, 25-21)"
    )
    assert len(channel.edits) == 1


def test_match_missed_entirely_gets_scoreboard_and_final_but_no_start(db):
    channel = FakeChannel()
    final = make_game(state=GameState.FINAL, pitt=(3, (25, 25, 25)), opp=(0, (20, 20, 20)))
    run(db, channel, final, {})
    assert len(channel.sent) == 2
    assert "Final" in channel.texts[0]
    assert "underway" not in " ".join(channel.texts)


def test_postponed_match_posts_nothing(db):
    channel = FakeChannel()
    game = make_game(state=GameState.FINAL, pitt=(None, ()), opp=(None, ()), detail="Postponed")
    run(db, channel, game, {})
    assert channel.sent == []
    record = get_scoreboard(db, "1")
    assert record and record.final_posted


def test_no_role_means_no_ping(db):
    channel = FakeChannel()
    run(db, channel, make_game(), {}, role=None)
    assert not channel.texts[0].startswith("<@&")
    assert channel.mentions[1].roles is False


def test_active_window():
    game = make_game()  # starts at START
    assert game.start == START
    assert active_games([game], START - timedelta(minutes=16)) == []
    assert active_games([game], START - timedelta(minutes=14)) == [game]
    assert active_games([game], START + timedelta(hours=4, minutes=59)) == [game]
    assert active_games([game], START + timedelta(hours=5, minutes=1)) == []


def test_football_gets_a_longer_window():
    from enums import Sport

    game = make_game(sport=Sport.FOOTBALL)
    assert active_games([game], START + timedelta(hours=7)) == [game]
    assert active_games([game], START + timedelta(hours=8, minutes=1)) == []


def test_cog_follows_pitt_per_sport_unless_overridden(db):
    from cogs.scores import ScoresCog
    from enums import Sport

    pitt = ScoresCog(bot=None, db_path=db, channel_id=1, team_id=None)
    assert pitt._team(Sport.FOOTBALL) == "221"
    assert pitt._team(Sport.MENS_SOCCER) == "5744"
    assert pitt.last_embeds == {} and pitt.schedules == {}

    test = ScoresCog(bot=None, db_path=db, channel_id=1, team_id="2006")
    assert test._team(Sport.MENS_SOCCER) == "2006"
