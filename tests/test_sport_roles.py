import asyncio
import sqlite3
from contextlib import closing
from datetime import datetime
from types import SimpleNamespace

import pytest

from cogs.roles import CUSTOM_ID_PREFIX, RolePanelView, SportRoleButton
from database import (
    Listing,
    add_listing,
    backfill_listing_channels,
    get_listing,
    get_sport_role,
    get_sport_roles,
    init_db,
    save_sport_role,
    update_message_id,
    update_message_location,
)
from enums import SPORT_LABELS, ListingType, Sport


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


def listing(sport=Sport.FOOTBALL, channel_id=0):
    return Listing(
        user_id=1,
        listing_type=ListingType.HAVE,
        sport=sport,
        game_datetime=datetime(2026, 11, 15),
        quantity=2,
        notes=None,
        posted_at=datetime.now().isoformat(),
        channel_id=channel_id,
    )


# --- listing channel ---------------------------------------------------------


def test_new_listing_records_its_channel(db):
    listing_id = add_listing(db, listing(channel_id=777))
    row = get_listing(db, listing_id)
    assert row["channel_id"] == 777
    assert Listing.from_row(row).channel_id == 777


def test_upgrade_adds_channel_column_to_an_existing_database(tmp_path):
    path = str(tmp_path / "old.db")
    with closing(sqlite3.connect(path)) as conn, conn:
        # The listings table as it was before channel_id existed.
        conn.execute("""
            CREATE TABLE listings (
                id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                listing_type TEXT NOT NULL, sport TEXT NOT NULL,
                game_datetime TEXT, quantity INTEGER, notes TEXT,
                message_id INTEGER NOT NULL DEFAULT 0,
                posted_at TEXT NOT NULL, status INTEGER NOT NULL DEFAULT 1)
        """)
        conn.execute(
            "INSERT INTO listings (user_id, listing_type, sport, message_id, "
            "posted_at) VALUES (1, 'have', 'football', 55, '2026-11-01')"
        )

    init_db(path)
    init_db(path)  # running again on startup must not fail

    row = get_listing(path, 1)
    assert row["channel_id"] == 0
    assert row["message_id"] == 55


def test_backfill_uses_the_old_sport_routing(db):
    football = add_listing(db, listing(Sport.FOOTBALL))
    volleyball = add_listing(db, listing(Sport.VOLLEYBALL))
    no_card = add_listing(db, listing(Sport.BASEBALL))
    already = add_listing(db, listing(Sport.FOOTBALL, channel_id=999))
    for listing_id in (football, volleyball, already):
        update_message_id(db, listing_id, 1000 + listing_id)

    routing = {"football": 10, "volleyball": 30, "baseball": 40}
    assert backfill_listing_channels(db, routing.__getitem__) == 2

    assert get_listing(db, football)["channel_id"] == 10
    assert get_listing(db, volleyball)["channel_id"] == 30
    assert get_listing(db, no_card)["channel_id"] == 0  # no card to find
    assert get_listing(db, already)["channel_id"] == 999  # left alone
    assert backfill_listing_channels(db, routing.__getitem__) == 0


def test_update_message_location_moves_the_card(db):
    listing_id = add_listing(db, listing(channel_id=10))
    update_message_location(db, listing_id, channel_id=20, message_id=5)
    row = get_listing(db, listing_id)
    assert (row["channel_id"], row["message_id"]) == (20, 5)


# --- sport roles -------------------------------------------------------------


def test_sport_roles_save_and_replace(db):
    assert get_sport_role(db, Sport.VOLLEYBALL) is None
    save_sport_role(db, Sport.VOLLEYBALL, 111)
    save_sport_role(db, Sport.VOLLEYBALL, 222)
    save_sport_role(db, Sport.FOOTBALL, 333)
    assert get_sport_role(db, Sport.VOLLEYBALL) == 222
    assert get_sport_roles(db) == {"volleyball": 222, "football": 333}


def test_panel_has_one_stable_button_per_sport(db):
    async def build():
        return RolePanelView(db)

    view = asyncio.run(build())
    assert view.timeout is None
    assert [b.custom_id for b in view.children] == [
        f"{CUSTOM_ID_PREFIX}{s.value}" for s in SPORT_LABELS
    ]


class FakeMember:
    def __init__(self, roles):
        self.roles = list(roles)

    async def add_roles(self, role, reason=None):
        self.roles.append(role)

    async def remove_roles(self, role, reason=None):
        self.roles.remove(role)


class FakeResponse:
    def __init__(self):
        self.sent = []

    async def send_message(self, content, ephemeral=False):
        self.sent.append(content)


def press(db, member, guild_roles):
    import discord

    async def go():
        button = SportRoleButton(Sport.VOLLEYBALL, db)
        guild = SimpleNamespace(get_role=lambda rid: guild_roles.get(rid))
        interaction = SimpleNamespace(
            user=member, guild=guild, response=FakeResponse()
        )
        # The callback only accepts real Members; let the fake through.
        original = discord.Member
        discord.Member = FakeMember  # type: ignore[misc]
        try:
            await button.callback(interaction)  # type: ignore[arg-type]
        finally:
            discord.Member = original  # type: ignore[misc]
        return interaction.response.sent[-1]

    return asyncio.run(go())


def test_button_toggles_the_role(db):
    role = SimpleNamespace(id=222)
    save_sport_role(db, Sport.VOLLEYBALL, 222)
    member = FakeMember([])

    assert "now be pinged" in press(db, member, {222: role})
    assert role in member.roles
    assert "won't be pinged" in press(db, member, {222: role})
    assert role not in member.roles


def test_button_explains_a_missing_role(db):
    member = FakeMember([])
    assert "/rolepanel" in press(db, member, {})
    assert member.roles == []
