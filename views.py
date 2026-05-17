import discord

from database import set_listing_status
from enums import ListingStatus, ListingType


class CloseSelect(discord.ui.Select):
    def __init__(self, listings, db_path, channel):
        self.db_path = db_path
        self.channel = channel

        options = [
            discord.SelectOption(
                label=f"{'HAVE' if row['listing_type'] == ListingType.HAVE else 'WANT'} — {row['sport'].replace('_', ' ').title()}",
                description=row["game_datetime"]
                if row["game_datetime"]
                else "Any game",
                value=f"{row['id']},{row['message_id']}",
            )
            for row in listings
        ]
        super().__init__(placeholder="Choose a listing to close...", options=options)

    async def callback(self, interaction: discord.Interaction):
        listing_id, message_id = self.values[0].split(",")
        listing_id = int(listing_id)
        message_id = int(message_id)

        set_listing_status(self.db_path, listing_id, ListingStatus.CLOSED)
        # close_listing(self.db_path, listing_id, user_id=interaction.user.id)

        try:
            message = await self.channel.fetch_message(message_id)
            embed = message.embeds[0]
            embed.color = discord.Color.light_grey()
            embed.title = f"❌ CLOSED — {embed.title.split('—')[1].strip()}"
            await message.edit(embed=embed)
        except discord.NotFound:
            pass

        await interaction.response.send_message("Listing closed!", ephemeral=True)


class CloseView(discord.ui.View):
    def __init__(self, listings, db_path, channel):
        super().__init__()
        self.add_item(CloseSelect(listings, db_path, channel))


class CloseMatchedListingsView(discord.ui.View):
    def __init__(self, db_path, listing_id):
        super().__init__()
        self.db_path = db_path
        self.listing_id = listing_id

    @discord.ui.button(label="Yes, close it", style=discord.ButtonStyle.green)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        set_listing_status(self.db_path, self.listing_id, ListingStatus.CLOSED)
        # close_listing(self.db_path, self.listing_id)
        await interaction.response.send_message("Listing closed!", ephemeral=True)

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.grey)
    async def dismiss(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message("Got it!", ephemeral=True)
