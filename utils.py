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
