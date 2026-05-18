from datetime import datetime

from discord.ext import commands, tasks

from database import expire_old_listings, find_listings_in_matched_status
from views import CloseMatchedListingsView


class TasksCog(commands.Cog):
    def __init__(self, bot, db_path, channel_id):
        self.bot = bot
        self.db_path = db_path
        self.channel_id = channel_id
        self.expire_listings_task.start()
        self.close_matched_listings_task.start()

    def cog_unload(self):
        # Cancel the loop when the Cog is unloaded to prevent memory leaks
        self.expire_listings_task.cancel()
        self.close_matched_listings_task.cancel()

    @tasks.loop(hours=24.0)
    async def expire_listings_task(self):
        expire_old_listings(self.db_path)

    @tasks.loop(hours=24.0)
    async def close_matched_listings_task(self):
        rows = find_listings_in_matched_status(self.db_path)
        for row in rows:
            user = await self.bot.fetch_user(row["user_id"])
            listing_type = row["listing_type"].title()
            sport = row["sport"].replace("_", " ").title()

            game_datetime = (
                datetime.fromisoformat(row["game_datetime"]).strftime(
                    "%B %d, %Y %I:%M %p"
                )
                if row["game_datetime"]
                else "Any game"
            )

            await user.send(
                f"A match was previously identified for this listing: {listing_type}, {sport}, {game_datetime}\nWould you like to close your listing?",
                view=CloseMatchedListingsView(self.db_path, row["id"]),
            )

    @close_matched_listings_task.before_loop
    async def before_closed_match_listings_task(self):
        # Wait until the bot is logged in before starting the loop
        await self.bot.wait_until_ready()

    @expire_listings_task.before_loop
    async def before_expire_listings_task(self):
        # Wait until the bot is logged in before starting the loop
        await self.bot.wait_until_ready()


def setup(bot, db_path, channel_id):
    bot.add_cog(TasksCog(bot, db_path, channel_id))
