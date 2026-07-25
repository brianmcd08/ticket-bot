import logging
from datetime import datetime
from typing import Optional, Union

import discord

from database import close_all_listings, update_listing_status
from enums import ListingStatus, ListingType

log = logging.getLogger("ticketbot")

# Discord's hard cap on select menu options.
MAX_SELECT_OPTIONS = 25


def _format_game_day(game_datetime: Optional[str]) -> str:
    """Readable date for a select option, not a raw isoformat timestamp."""
    if not game_datetime:
        return "Any game"
    return datetime.fromisoformat(game_datetime).strftime("%b %d, %Y")


async def mark_message_closed(channel, message_id, listing_id) -> bool:
    """Grey out a listing's channel post. Returns whether it was updated.

    Editing our own message needs no Manage Messages permission, so closed
    listings can be struck through rather than deleted.
    """
    # message_id is 0 when the channel post failed at creation time.
    if channel is None or not message_id:
        return False
    try:
        message = await channel.fetch_message(message_id)
        if not message.embeds:
            return False
        embed = message.embeds[0]
        embed.color = discord.Color.light_grey()
        title = embed.title or ""
        # Titles are "🎟️ HAVE — Football"; fall back rather than IndexError if
        # that shape ever changes.
        suffix = title.split("—", 1)[1].strip() if "—" in title else title
        embed.title = f"❌ CLOSED — {suffix}"
        await message.edit(embed=embed)
        return True
    except discord.NotFound:
        return False
    except discord.HTTPException:
        log.exception(
            "Could not mark message %s closed for listing %s", message_id, listing_id
        )
        return False


class CloseSelect(discord.ui.Select[discord.ui.View]):
    def __init__(self, listings, db_path, channel):
        self.db_path = db_path
        self.channel = channel

        options = [
            discord.SelectOption(
                label=f"{'HAVE' if row['listing_type'] == ListingType.HAVE else 'WANT'} — {row['sport'].replace('_', ' ').title()}",
                description=_format_game_day(row["game_datetime"]),
                value=f"{row['id']},{row['message_id']}",
            )
            for row in listings[:MAX_SELECT_OPTIONS]
        ]
        super().__init__(placeholder="Choose a listing to close...", options=options)

    async def callback(self, interaction: discord.Interaction):
        listing_id, message_id = self.values[0].split(",")
        listing_id = int(listing_id)
        message_id = int(message_id)

        update_listing_status(self.db_path, listing_id, ListingStatus.CLOSED)
        await mark_message_closed(self.channel, message_id, listing_id)

        await interaction.response.send_message("Listing closed!", ephemeral=True)


class CloseView(discord.ui.View):
    def __init__(self, listings, db_path, channel):
        # The default 180s left people who stepped away with a dropdown that
        # only answered "This interaction failed".
        super().__init__(timeout=900)
        # Set by the /close command so on_timeout can grey out the dropdown.
        self.message: Optional[Union[discord.Message, discord.WebhookMessage]] = None
        self.add_item(CloseSelect(listings, db_path, channel))

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(
                    content="This menu expired. Run /close again.", view=self
                )
            except discord.HTTPException:
                pass


class ConfirmClearView(discord.ui.View):
    """Confirmation step for the admin-only /clear command."""

    def __init__(self, db_path, channel, count):
        super().__init__(timeout=120)
        self.db_path = db_path
        self.channel = channel
        self.count = count
        self.message: Optional[Union[discord.Message, discord.WebhookMessage]] = None

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(
                    content="Confirmation expired. Nothing was cleared.", view=self
                )
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Yes, clear everything", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ):
        await interaction.response.defer(ephemeral=True)

        rows = close_all_listings(self.db_path)
        await interaction.followup.send(
            f"Cleared {len(rows)} listing(s). Updating the channel posts now.",
            ephemeral=True,
        )

        # After the reply, so a long run of edits cannot stall the interaction.
        updated = 0
        for row in rows:
            if await mark_message_closed(self.channel, row["message_id"], row["id"]):
                updated += 1
        log.info("/clear closed %s listings, marked %s posts", len(rows), updated)

        if self.channel is not None:
            try:
                await self.channel.send(
                    "🧹 An admin cleared all open listings. "
                    "Post again with `/have` or `/want` if you still need tickets."
                )
            except discord.HTTPException:
                log.exception("Could not announce /clear in the channel")

        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ):
        await interaction.response.send_message("Nothing was cleared.", ephemeral=True)
        self.stop()


class CloseMatchedListingsView(discord.ui.View):
    def __init__(self, db_path, listing_id):
        # Sent by DM once a day; stay usable until the next reminder replaces it.
        super().__init__(timeout=86400)
        self.db_path = db_path
        self.listing_id = listing_id

    @discord.ui.button(label="Yes, close it", style=discord.ButtonStyle.green)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ):
        update_listing_status(self.db_path, self.listing_id, ListingStatus.CLOSED)
        await interaction.response.send_message("Listing closed!", ephemeral=True)

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.grey)
    async def dismiss(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button[discord.ui.View],
    ):
        await interaction.response.send_message("Got it!", ephemeral=True)
