from datetime import datetime
from typing import Optional, cast

import discord
import pytest

from database import Listing
from enums import ListingType, Sport
from utils import (
    HAVE_HINT_NAME,
    MATCH_HINT_NAMES,
    WANT_HINT_NAME,
    build_embed,
    build_help_embed,
    format_listing_line,
)

GAME_DT = datetime(2026, 11, 15, 19, 0)


class FakeUser:
    """build_embed only reads display_name."""

    display_name = "brianmcd"


def make_listing(
    listing_type: ListingType = ListingType.HAVE,
    sport: Sport = Sport.FOOTBALL,
    game_datetime: Optional[datetime] = GAME_DT,
    quantity: Optional[int] = 2,
    notes: Optional[str] = None,
) -> Listing:
    return Listing(
        user_id=42,
        listing_type=listing_type,
        sport=sport,
        game_datetime=game_datetime,
        quantity=quantity,
        notes=notes,
        posted_at=datetime.now().isoformat(),
    )


def embed_for(listing: Listing, listing_id: int = 7) -> discord.Embed:
    return build_embed(listing, listing_id, cast(discord.abc.User, FakeUser()))


def title_of(embed: discord.Embed) -> str:
    return embed.title or ""


def footer_of(embed: discord.Embed) -> str:
    return embed.footer.text or ""


def field_names(embed: discord.Embed) -> list[str]:
    return [f.name or "" for f in embed.fields]


def field_value(embed: discord.Embed, name: str) -> str:
    return next(f.value or "" for f in embed.fields if f.name == name)


# --- build_embed ---------------------------------------------------------


def test_have_embed_title_and_color():
    embed = embed_for(make_listing())
    assert "HAVE" in title_of(embed)
    assert "Football" in title_of(embed)
    assert embed.color == discord.Color.green()


def test_want_embed_title_and_color():
    embed = embed_for(make_listing(listing_type=ListingType.WANT))
    assert "WANT" in title_of(embed)
    assert embed.color == discord.Color.blue()


def test_sport_name_is_humanized():
    embed = embed_for(make_listing(sport=Sport.MENS_BASKETBALL))
    assert "Mens Basketball" in title_of(embed)


def test_embed_shows_date_without_time():
    """Start time is no longer collected; the embed must not imply one."""
    embed = embed_for(make_listing())
    assert field_value(embed, "Date") == "November 15, 2026"
    assert "Time" not in field_names(embed)


def test_embed_without_date_says_any_game():
    embed = embed_for(make_listing(game_datetime=None))
    assert field_value(embed, "Date") == "Any game"


def test_quantity_field_omitted_when_absent():
    assert "Tickets" not in field_names(embed_for(make_listing(quantity=None)))
    assert "Tickets" in field_names(embed_for(make_listing()))


def test_notes_field_omitted_when_absent():
    assert "Notes" not in field_names(embed_for(make_listing()))
    embed = embed_for(make_listing(notes="Section 12, $40"))
    assert field_value(embed, "Notes") == "Section 12, $40"


def test_have_card_tells_readers_to_post_a_want():
    embed = embed_for(make_listing())
    hint = field_value(embed, HAVE_HINT_NAME)
    assert "/want" in hint
    assert "November 15, 2026" in hint
    # The opposite command would send people to post a duplicate have.
    assert "/have" not in hint


def test_want_card_tells_readers_to_post_a_have():
    embed = embed_for(make_listing(listing_type=ListingType.WANT))
    hint = field_value(embed, WANT_HINT_NAME)
    assert "/have" in hint
    assert "November 15, 2026" in hint
    assert "/want" not in hint


def test_undated_want_card_says_any_game_for_the_sport():
    """A dateless want matches every open have for its sport, so don't name a day."""
    embed = embed_for(
        make_listing(listing_type=ListingType.WANT, game_datetime=None)
    )
    hint = field_value(embed, WANT_HINT_NAME)
    assert "any Football game" in hint
    assert "2026" not in hint


def test_have_card_mentions_the_dateless_want_shortcut():
    hint = field_value(embed_for(make_listing()), HAVE_HINT_NAME)
    assert "Leave the date off" in hint


def test_match_hint_is_the_last_field():
    """It's a call to action; it reads wrong above the listing's own details."""
    embed = embed_for(make_listing(notes="Section 12, $40"))
    assert field_names(embed)[-1] == HAVE_HINT_NAME


def test_each_card_carries_exactly_one_hint():
    for listing_type in (ListingType.HAVE, ListingType.WANT):
        names = field_names(embed_for(make_listing(listing_type=listing_type)))
        assert len([n for n in names if n in MATCH_HINT_NAMES]) == 1


def test_footer_carries_listing_id_and_poster():
    embed = embed_for(make_listing(), listing_id=99)
    assert "99" in footer_of(embed)
    assert "brianmcd" in footer_of(embed)


# --- format_listing_line -------------------------------------------------


def row(**overrides):
    base = {
        "id": 5,
        "user_id": 42,
        "listing_type": ListingType.HAVE,
        "sport": Sport.FOOTBALL,
        "game_datetime": GAME_DT.isoformat(),
        "quantity": 2,
    }
    base.update(overrides)
    return base


def test_line_has_type_sport_and_date():
    line = format_listing_line(row())
    assert "**HAVE**" in line
    assert "Football" in line
    assert "Nov 15, 2026" in line


def test_line_omits_time_of_day():
    line = format_listing_line(row())
    assert "07:00" not in line
    assert "PM" not in line


def test_line_without_date_says_any_game():
    assert "Any game" in format_listing_line(row(game_datetime=None))


def test_line_includes_quantity_only_when_set():
    assert "Qty: 2" in format_listing_line(row())
    assert "Qty" not in format_listing_line(row(quantity=None))


def test_line_mentions_user_and_listing_id():
    line = format_listing_line(row())
    assert "<@42>" in line
    assert "(#5)" in line


def test_want_line_labelled_want():
    assert "**WANT**" in format_listing_line(row(listing_type=ListingType.WANT))


def test_line_humanizes_sport_name():
    assert "Womens Basketball" in format_listing_line(
        row(sport=Sport.WOMENS_BASKETBALL)
    )


# --- build_help_embed ----------------------------------------------------


def test_help_lists_the_public_commands():
    """Command fields sit among explanatory sections, so check order not equality."""
    commands = [n for n in field_names(build_help_embed()) if n.startswith("/")]
    assert commands == ["/have", "/want", "/listings", "/mine", "/close", "/help"]


def test_help_explains_where_listings_are_posted():
    embed = build_help_embed()
    rendered = " ".join(f"{f.name} {f.value}" for f in embed.fields)
    assert "channel for its sport" in rendered
    assert "basketball" in rendered.lower()


def test_help_explains_the_channel_shortcut():
    rendered = " ".join(f.value or "" for f in build_help_embed().fields)
    assert "blank" in rendered and "sport" in rendered


def test_help_explains_day_level_matching():
    """People need to know start times aren't compared, since there's no time field."""
    rendered = " ".join(f.value or "" for f in build_help_embed().fields)
    assert "same game day" in rendered
    assert "Start times aren't compared" in rendered


def test_help_fields_are_within_discord_limits():
    embed = build_help_embed()
    assert len(embed.fields) <= 25
    for f in embed.fields:
        assert len(f.name or "") <= 256
        assert len(f.value or "") <= 1024
    assert len(embed) <= 6000


@pytest.mark.parametrize("admin_command", ["/clear", "/reopen", "/refresh"])
def test_help_does_not_expose_admin_commands(admin_command):
    embed = build_help_embed()
    rendered = " ".join(
        [title_of(embed), embed.description or "", footer_of(embed)]
        + [f"{f.name} {f.value}" for f in embed.fields]
    )
    assert admin_command not in rendered


@pytest.mark.parametrize("command", ["/have", "/want", "/close"])
def test_help_describes_each_command(command):
    assert field_value(build_help_embed(), command).strip()
