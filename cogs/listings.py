import discord
from discord import app_commands
from discord.ext import commands


class ListingsCog(commands.Cog):
    def __init__(self, bot, db_path, channel_id):
        self.bot = bot
        self.db_path = db_path
        self.channel_id = channel_id

    @app_commands.command()
    async def have(self, interaction: discord.Interaction):
        await interaction.response.send_message("have received!")

    @app_commands.command()
    async def want(self, interaction: discord.Interaction):
        await interaction.response.send_message("want received!")

    @app_commands.command()
    async def close(self, interaction: discord.Interaction):
        await interaction.response.send_message("close received!")


def setup(bot, db_path, channel_id):
    bot.add_cog(ListingsCog(bot, db_path, channel_id))
