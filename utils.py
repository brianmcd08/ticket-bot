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

    if listing.game_datetime:
        embed.add_field(
            name="Date",
            value=listing.game_datetime.strftime("%B %d, %Y"),
            inline=True,
        )
        embed.add_field(
            name="Time",
            value=listing.game_datetime.strftime("%I:%M %p"),
            inline=True,
        )
    else:
        embed.add_field(name="Date", value="Any game", inline=True)

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
            "%b %d, %Y %I:%M %p"
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
        value="See all open have and want listings, optionally filtered by sport.",
        inline=False,
    )
    embed.add_field(name="/mine", value="See your own open listings.", inline=False)
    embed.add_field(
        name="/close",
        value="Close one of your listings once it's been exchanged or if you change your mind.",
        inline=False,
    )
    embed.set_footer(text="Run /help again to refresh this message.")
    return embed
