import logging

import discord
from discord import app_commands
from discord.ext import commands

from cogs.listings import ListingsCog
from cogs.tasks import TasksCog
from config import settings
from database import init_db

log = logging.getLogger("ticketbot")


class TicketBot(commands.Bot):
    synced: list[discord.app_commands.AppCommand]

    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        # Populated by setup_hook; initialized so on_ready can't AttributeError
        # if the sync call fails.
        self.synced = []

    async def setup_hook(self):
        init_db(settings.db_path)
        await self.add_cog(
            ListingsCog(
                self, settings.db_path, settings.channel_id, settings.sport_channels
            )
        )
        await self.add_cog(
            TasksCog(
                self, settings.db_path, settings.channel_id, settings.sport_channels
            )
        )
        self.tree.on_error = on_app_command_error
        self.tree.copy_global_to(guild=discord.Object(id=settings.guild_id))
        self.synced = await self.tree.sync(guild=discord.Object(id=settings.guild_id))

    async def on_ready(self):
        print(f"Successfully connected! Logged in as {client.user}")
        print(
            f"Synced {len(self.synced)} commands: {[cmd.name for cmd in self.synced]}"
        )
        # Config gaps fall back silently rather than failing startup, so print
        # the resolved routing to make a missing .env entry visible.
        print("Sport channel routing:")
        print(settings.sport_channels.describe())


async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    """Log every command failure and always tell the user something went wrong.

    Without this, an unhandled exception means no interaction response at all,
    and the user just sees Discord's generic "The application did not respond".
    """
    command_name = interaction.command.name if interaction.command else "unknown"
    log.exception(
        "Error in /%s (user=%s, channel=%s)",
        command_name,
        interaction.user.id,
        interaction.channel_id,
        exc_info=error,
    )

    message = (
        "Something went wrong running that command. "
        "It has been logged, please try again."
    )
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        # Interaction token already expired; nothing more we can do.
        log.warning("Could not deliver error message for /%s", command_name)


client = TicketBot()
# root_logger=True so our own "ticketbot" logger reaches the same handler
# discord.py installs, i.e. stderr -> journalctl -u ticket-bot.
client.run(token=settings.token, root_logger=True)
