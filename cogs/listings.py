from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import Listing, add_listing, update_message_id
from enums import ListingType, Sport
from matching import find_matches
from utils import build_embed
from validators import validate_day, validate_hour, validate_month, validate_year


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
        matches = find_matches(db_path=self.db_path, listing=listing)

    @app_commands.command()
    async def want(self, interaction: discord.Interaction):
        await interaction.response.send_message("want received!")

    @app_commands.command()
    async def close(self, interaction: discord.Interaction):
        await interaction.response.send_message("close received!")


def setup(bot, db_path, channel_id):
    bot.add_cog(ListingsCog(bot, db_path, channel_id))
