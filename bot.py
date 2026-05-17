import discord
from discord.ext import commands

from cogs.listings import ListingsCog
from cogs.tasks import TasksCog
from config import settings
from database import init_db


class TicketBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        init_db(settings.db_path)
        await self.add_cog(ListingsCog(self, settings.db_path, settings.channel_id))
        await self.add_cog(TasksCog(self, settings.db_path, settings.channel_id))
        self.tree.copy_global_to(guild=discord.Object(id=settings.guild_id))
        self.synced = await self.tree.sync(guild=discord.Object(id=settings.guild_id))

    async def on_ready(self):
        print(f"Successfully connected! Logged in as {client.user}")
        print(
            f"Synced {len(self.synced)} commands: {[cmd.name for cmd in self.synced]}"
        )


client = TicketBot()
client.run(token=settings.token)
