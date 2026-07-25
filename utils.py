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


def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎟️ Ticket Exchange Bot — Commands",
        description="Post tickets you have, find tickets you need, and get pinged automatically when there's a match.",
        color=discord.Color.gold(),
    )
    embed.add_field(name="/have", value="Post tickets you have available.", inline=False)
    embed.add_field(
        name="/want", value="Post that you're looking for tickets.", inline=False
    )
    embed.add_field(
        name="/listings",
        value="See all open have and want listings, optionally filtered by sport. "
        "Only visible to you, in whatever channel you run it.",
        inline=False,
    )
    embed.add_field(
        name="/mine",
        value="See your own open listings. Only visible to you, in whatever channel you run it.",
        inline=False,
    )
    embed.add_field(
        name="/close",
        value="Close one of your listings once it's been exchanged or if you change your mind.",
        inline=False,
    )
    embed.add_field(
        name="/help",
        value="Show this list of commands. Only visible to you, in whatever channel you run it.",
        inline=False,
    )
    # /clear is intentionally not listed: admin-only maintenance command.
    embed.set_footer(text="Only visible to you — run /help anytime to see this again.")
    return embed
