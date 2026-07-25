import asyncio
from datetime import datetime
from typing import cast

import discord

from database import Listing
from enums import ListingType, Sport
from utils import MATCH_HINT_NAMES, build_embed
from views import mark_message_closed


class FakeUser:
    display_name = "brianmcd"


class FakeMessage:
    def __init__(self, embed):
        self.embeds = [embed]
        self.edited_with = None

    async def edit(self, embed=None):
        self.edited_with = embed


class FakeChannel:
    def __init__(self, message):
        self.message = message

    async def fetch_message(self, message_id):
        return self.message


def closed_embed(listing_type=ListingType.HAVE):
    listing = Listing(
        user_id=42,
        listing_type=listing_type,
        sport=Sport.FOOTBALL,
        game_datetime=datetime(2026, 11, 15),
        quantity=2,
        notes="Section 12",
        posted_at=datetime.now().isoformat(),
    )
    message = FakeMessage(build_embed(listing, 7, cast(discord.abc.User, FakeUser())))
    channel = FakeChannel(message)
    updated = asyncio.run(mark_message_closed(channel, 123, 7))
    return updated, message.edited_with


def test_closing_marks_the_title():
    updated, embed = closed_embed()
    assert updated
    assert embed is not None
    assert embed.title is not None and embed.title.startswith("❌ CLOSED")


def test_closing_strips_the_match_hint():
    """A closed listing can't match, so it must stop telling people to post."""
    _, embed = closed_embed()
    assert embed is not None
    assert [f.name for f in embed.fields if f.name in MATCH_HINT_NAMES] == []


def test_closing_keeps_the_listing_details():
    _, embed = closed_embed()
    assert embed is not None
    assert [f.name for f in embed.fields] == ["Date", "Tickets", "Notes"]


def test_closing_strips_the_hint_on_wants_too():
    _, embed = closed_embed(ListingType.WANT)
    assert embed is not None
    assert [f.name for f in embed.fields if f.name in MATCH_HINT_NAMES] == []
