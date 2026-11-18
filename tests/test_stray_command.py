import asyncio
from types import SimpleNamespace
from typing import cast

import discord

from enums import SPORT_LABELS, Sport
from utils import stray_command, stray_command_hint
from views import SportPickView

NAMES = {"have", "want", "listings", "mine", "close", "help"}


def test_detects_command_sent_as_text():
    assert stray_command("/have", NAMES) == "have"


def test_detects_mobile_newline_and_trailing_text():
    assert stray_command("/have\n", NAMES) == "have"
    assert stray_command("  /Want 2 tickets sec 110", NAMES) == "want"


def test_ignores_unknown_commands_and_plain_text():
    assert stray_command("/shrug", NAMES) is None
    assert stray_command("I have 2 tickets", NAMES) is None
    assert stray_command("/", NAMES) is None
    assert stray_command("", NAMES) is None
    assert stray_command("and/or /have", NAMES) is None


def test_hint_names_the_command():
    assert "/have" in stray_command_hint("have")


class FakeResponse:
    def __init__(self):
        self.edits = []

    async def edit_message(self, **kwargs):
        self.edits.append(kwargs)


def run_pick(view: SportPickView, sport: Sport, interaction):
    select = view.children[0]
    select._values = [sport.value]  # what discord.py sets from the payload
    asyncio.run(select.callback(interaction))


def test_sport_pick_calls_back_once_and_removes_menu():
    picks = []

    async def on_pick(interaction, sport):
        picks.append(sport)

    async def build():
        return SportPickView(list(SPORT_LABELS), on_pick)

    view = asyncio.run(build())
    interaction = cast(discord.Interaction, SimpleNamespace(response=FakeResponse()))

    run_pick(view, Sport.VOLLEYBALL, interaction)
    run_pick(view, Sport.FOOTBALL, interaction)

    assert picks == [Sport.VOLLEYBALL]
    assert interaction.response.edits[0]["view"] is None


def test_sport_pick_offers_only_given_sports():
    async def build():
        return SportPickView(
            [Sport.MENS_BASKETBALL, Sport.WOMENS_BASKETBALL], lambda i, s: None
        )

    view = asyncio.run(build())
    labels = [o.label for o in view.children[0].options]
    assert labels == ["Men's Basketball", "Women's Basketball"]


def test_resolve_sport_offers_choices_instead_of_erroring():
    import channels
    from cogs.listings import ListingsCog

    routing = channels.build(
        channel_id=1, football="10", basketball="20", volleyball="30"
    )
    cog = ListingsCog(bot=None, db_path=":memory:", channel_id=1, sport_channels=routing)

    def where(channel_id):
        return cast(discord.Interaction, SimpleNamespace(channel_id=channel_id))

    assert cog.resolve_sport(where(30), None) == (Sport.VOLLEYBALL, [])
    assert cog.resolve_sport(where(20), None) == (
        None,
        [Sport.MENS_BASKETBALL, Sport.WOMENS_BASKETBALL],
    )
    assert cog.resolve_sport(where(1), None) == (None, list(SPORT_LABELS))
    explicit = SimpleNamespace(value="football")
    assert cog.resolve_sport(where(1), explicit) == (Sport.FOOTBALL, [])
