from discord.ext import commands, tasks

from database import expire_old_listings


class TasksCog(commands.Cog):
    def __init__(self, bot, db_path):
        self.bot = bot
        self.db_path = db_path
        self.expire_listings_task.start()

    def cog_unload(self):
        # Cancel the loop when the Cog is unloaded to prevent memory leaks
        self.expire_listings_task.cancel()

    @tasks.loop(hours=24.0)
    async def expire_listings_task(self):
        expire_old_listings(self.db_path)

    @expire_listings_task.before_loop
    async def before_my_background_task(self):
        # Wait until the bot is logged in before starting the loop
        await self.bot.wait_until_ready()


def setup(bot, db_path):
    bot.add_cog(TasksCog(bot, db_path))
