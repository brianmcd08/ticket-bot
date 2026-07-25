from datetime import datetime

import discord

from database import Listing
from enums import ListingType


def build_embed(
    listing: Listing, listing_id: int, user: discord.abc.User
) -> discord.Embed:
    is_have = listing.listing_type == ListingType.HAVE

    embed = discord.Embed(
        title=f"🎟️ {'HAVE' if is_have else 'WANT'} — {listing.sport.replace('_', ' ').title()}",
        color=discord.Color.green() if is_have else discord.Color.blue(),
    )

    embed.add_field(
        name="Date",
        value=listing.game_datetime.strftime("%B %d, %Y")
        if listing.game_datetime
        else "Any game",
        inline=True,
    )

    if listing.quantity:
        embed.add_field(name="Tickets", value=str(listing.quantity), inline=True)

    if listing.notes:
        embed.add_field(name="Notes", value=listing.notes, inline=False)

    embed.set_footer(text=f"Listing ID: {listing_id} | Posted by {user.display_name}")

    return embed


def format_listing_line(row) -> str:
    is_have = row["listing_type"] == ListingType.HAVE
    sport = row["sport"].replace("_", " ").title()

    if row["game_datetime"]:
        game_datetime = datetime.fromisoformat(row["game_datetime"]).strftime(
            "%b %d, %Y"
        )
    else:
        game_datetime = "Any game"

    qty = f" | Qty: {row['quantity']}" if row["quantity"] else ""

    return (
        f"🎟️ **{'HAVE' if is_have else 'WANT'}** — {sport} | {game_datetime}{qty} "
        f"| <@{row['user_id']}> (#{row['id']})"
    )


HELP_COMMAND_FIELDS = [
    (
        "/have",
        "Post tickets you have available.\n"
        "**Needed:** how many, and the month, day and year of the game.\n"
        "**Sport:** skip it in a sport's channel, otherwise pick one.\n"
        "**Notes:** put the game time, section, row or price here.",
    ),
    (
        "/want",
        "Post that you're looking for tickets.\n"
        "**Needed:** nothing, if you run it in a sport's channel.\n"
        "**Leave the date blank** to match any game for that sport, which is "
        "best if you're flexible. If you do give a date, give all three of "
        "month, day and year.",
    ),
    (
        "/listings",
        "See open haves and wants.\n"
        "Shows **the sport of the channel you run it in**. In the general "
        "channel, or anywhere else, it shows everything. Add the sport option "
        "to filter it yourself.",
    ),
    (
        "/mine",
        "See your own listings, including ones that have already matched. "
        "Each shows its **listing ID** in case you need it.",
    ),
    (
        "/close",
        "Close one of your listings once the tickets are sorted, or if you "
        "change your mind. Pick it from the dropdown; its post gets marked "
        "❌ CLOSED.",
    ),
    ("/help", "Show this message again."),
]


def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎟️ Ticket Exchange Bot",
        description=(
            "Post tickets you have, find tickets you need, and get pinged "
            "automatically when there's a match."
        ),
        color=discord.Color.gold(),
    )

    embed.add_field(
        name="📍 Where things show up",
        value=(
            "Your listing is posted to **the channel for its sport**. Men's and "
            "women's basketball share one channel.\n"
            "Match pings go to that same sport channel and tag both people.\n"
            "`/listings`, `/mine`, `/close` and `/help` reply **privately**, "
            "visible only to you, in whatever channel you ran them."
        ),
        inline=False,
    )
    embed.add_field(
        name="🎯 Running commands in a sport channel",
        value=(
            "In a sport's channel you can leave the **sport** option blank on "
            "`/have` and `/want`; it's taken from the channel.\n"
            "The basketball channel covers two sports, so there you'll be asked "
            "which one you mean.\n"
            "You can run any command from anywhere. Picking a sport explicitly "
            "always wins, and the listing still goes to that sport's channel."
        ),
        inline=False,
    )
    embed.add_field(
        name="🔔 How matching works",
        value=(
            "A have and a want match when they're the **same sport on the same "
            "game day**. Start times aren't compared, so you don't need to "
            "agree on the exact tip-off.\n"
            "A want with no date matches any game for that sport.\n"
            "You'll never match your own listing. When there's a match the bot "
            "tags you both; take it from there and run `/close` when done."
        ),
        inline=False,
    )

    for name, value in HELP_COMMAND_FIELDS:
        embed.add_field(name=name, value=value, inline=False)

    embed.add_field(
        name="⏳ Listings expire on their own",
        value=(
            "Haves disappear the day after the game. Wants last six months. "
            "Closing yours early still helps, so people know it's gone."
        ),
        inline=False,
    )
    # /clear and /reopen are intentionally not listed: admin-only commands.
    embed.set_footer(text="Only visible to you — run /help anytime to see this again.")
    return embed
