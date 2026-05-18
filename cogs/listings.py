from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import (
    Listing,
    add_listing,
    get_user_listings,
    update_listing_status,
    update_message_id,
)
from enums import ListingStatus, ListingType, Sport
from matching import find_matches
from utils import build_embed
from validators import validate_day, validate_hour, validate_month, validate_year
from views import CloseView


class ListingsCog(commands.Cog):
    def __init__(self, bot, db_path, channel_id):
        self.bot = bot
        self.db_path = db_path
        self.channel_id = channel_id

    @app_commands.command(name="have", description="Post tickets you have available")
    @app_commands.describe(
        sport="The sport",
        quantity="Number of tickets",
        notes="Any additional info",
        month="The month of the game (between 1 and 12)",
        day="The day of the game (between 1 and 31)",
        year="The year of the game",
        hour="Game start hour (between 0 and 23)",
        minute="Game start minutes",
    )
    @app_commands.choices(
        sport=[
            app_commands.Choice(name="Football", value=Sport.FOOTBALL),
            app_commands.Choice(name="Men's Basketball", value=Sport.MENS_BASKETBALL),
            app_commands.Choice(name="Volleyball", value=Sport.VOLLEYBALL),
            app_commands.Choice(
                name="Women's Basketball", value=Sport.WOMENS_BASKETBALL
            ),
        ]
    )
    @app_commands.choices(
        minute=[
            app_commands.Choice(name="00", value=0),
            app_commands.Choice(name="15", value=15),
            app_commands.Choice(name="30", value=30),
            app_commands.Choice(name="45", value=45),
        ]
    )
    async def have(
        self,
        interaction: discord.Interaction,
        sport: app_commands.Choice[str],
        quantity: int,
        month: int,
        day: int,
        year: int,
        hour: int,
        minute: int,
        notes: Optional[str] = None,
    ):
        errors = [
            validate_month(month),
            validate_day(day),
            validate_hour(hour),
            validate_year(year),
        ]
        errors = [e for e in errors if e]
        if errors:
            await interaction.response.send_message("\n".join(errors), ephemeral=True)
            return

        game_datetime = datetime(year, month, day, hour, minute)
        listing = Listing(
            user_id=interaction.user.id,
            listing_type=ListingType.HAVE,
            sport=Sport(sport.value),
            game_datetime=game_datetime,
            quantity=quantity,
            notes=notes,
            posted_at=datetime.now().isoformat(),
        )
        listing_id = add_listing(
            self.db_path,
            listing,
        )
        channel = self.bot.get_channel(self.channel_id)
        message = await channel.send(
            embed=build_embed(listing, listing_id, interaction.user)
        )
        update_message_id(self.db_path, listing_id=listing_id, message_id=message.id)
        await interaction.response.send_message("Listing posted!", ephemeral=True)

        await self._notify_matches(listing, listing_id, channel)

    @app_commands.command(name="want", description="Post what tickets you want")
    @app_commands.describe(
        sport="The sport",
        quantity="Number of tickets",
        notes="Any additional info",
        month="The month of the game (between 1 and 12)",
        day="The day of the game (between 1 and 31)",
        year="The year of the game",
        hour="Game start hour (between 0 and 23)",
        minute="Game start minutes",
    )
    @app_commands.choices(
        sport=[
            app_commands.Choice(name="Football", value=Sport.FOOTBALL),
            app_commands.Choice(name="Men's Basketball", value=Sport.MENS_BASKETBALL),
            app_commands.Choice(name="Volleyball", value=Sport.VOLLEYBALL),
            app_commands.Choice(
                name="Women's Basketball", value=Sport.WOMENS_BASKETBALL
            ),
        ]
    )
    @app_commands.choices(
        minute=[
            app_commands.Choice(name="00", value=0),
            app_commands.Choice(name="15", value=15),
            app_commands.Choice(name="30", value=30),
            app_commands.Choice(name="45", value=45),
        ]
    )
    async def want(
        self,
        interaction: discord.Interaction,
        sport: app_commands.Choice[str],
        quantity: Optional[int] = None,
        month: Optional[int] = None,
        day: Optional[int] = None,
        year: Optional[int] = None,
        hour: Optional[int] = None,
        minute: Optional[int] = None,
        notes: Optional[str] = None,
    ):
        errors = [
            validate_month(month) if month else None,
            validate_day(day) if day else None,
            validate_hour(hour) if hour else None,
            validate_year(year) if year else None,
        ]
        errors = [e for e in errors if e]
        if errors:
            await interaction.response.send_message("\n".join(errors), ephemeral=True)
            return

        date_fields = [month, day, year, hour, minute]
        if any(f is not None for f in date_fields) and not all(
            f is not None for f in date_fields
        ):
            await interaction.response.send_message(
                "Please provide all date and time fields or none at all.",
                ephemeral=True,
            )
            return

        if (
            year is not None
            and month is not None
            and day is not None
            and hour is not None
            and minute is not None
        ):
            game_datetime = datetime(year, month, day, hour, minute)
        else:
            game_datetime = None

        listing = Listing(
            user_id=interaction.user.id,
            listing_type=ListingType.WANT,
            sport=Sport(sport.value),
            game_datetime=game_datetime,
            quantity=quantity,
            notes=notes,
            posted_at=datetime.now().isoformat(),
        )
        listing_id = add_listing(
            self.db_path,
            listing,
        )
        channel = self.bot.get_channel(self.channel_id)
        message = await channel.send(
            embed=build_embed(listing, listing_id, interaction.user)
        )
        update_message_id(self.db_path, listing_id=listing_id, message_id=message.id)
        await interaction.response.send_message("Listing posted!", ephemeral=True)
        await self._notify_matches(listing, listing_id, channel)

    async def _notify_matches(self, listing: Listing, listing_id: int, channel):
        matches = find_matches(db_path=self.db_path, listing=listing)
        if matches:
            update_listing_status(
                db_path=self.db_path,
                listing_id=listing_id,
                listing_status=ListingStatus.MATCHED,
            )

        for match in matches:
            update_listing_status(
                db_path=self.db_path,
                listing_id=match.listing_id,
                listing_status=ListingStatus.MATCHED,
            )

            listing_sport = listing.sport.replace("_", " ").title()
            match_sport = match.sport.replace("_", " ").title()
            listing_gamedatetime = (
                listing.game_datetime.strftime("%B %d, %Y %I:%M %p")
                if listing.game_datetime
                else "Any game"
            )
            match_gamedatetime = (
                match.game_datetime.strftime("%B %d, %Y %I:%M %p")
                if match.game_datetime
                else "Any game"
            )

            await channel.send(
                f"<@{match.matched_poster_user_id}> <@{match.new_poster_user_id}> has posted tickets that match your listing: {listing.listing_type}, {listing_sport}, {listing_gamedatetime}"
            )
            await channel.send(
                f"<@{match.new_poster_user_id}> <@{match.matched_poster_user_id}> has posted tickets that match your listing: {match.listing_type}, {match_sport}, {match_gamedatetime}"
            )

    @app_commands.command(
        name="close", description="Close listings that you have created"
    )
    async def close(self, interaction: discord.Interaction):
        listings = get_user_listings(self.db_path, interaction.user.id)
        if not listings:
            await interaction.response.send_message(
                "You have no active listings.", ephemeral=True
            )
            return
        channel = self.bot.get_channel(self.channel_id)
        view = CloseView(listings, self.db_path, channel)
        await interaction.response.send_message(
            "Select a listing to close:", view=view, ephemeral=True
        )


def setup(bot, db_path, channel_id):
    bot.add_cog(ListingsCog(bot, db_path, channel_id))
