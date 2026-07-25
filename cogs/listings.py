import logging
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import (
    Listing,
    add_listing,
    get_open_listings,
    get_user_listings,
    update_listing_status,
    update_message_id,
)
from enums import ListingStatus, ListingType, Sport
from matching import find_matches
from utils import build_embed, build_help_embed, format_listing_line
from validators import (
    validate_calendar_date,
    validate_day,
    validate_month,
    validate_year,
)
from views import CloseView, ConfirmClearView

log = logging.getLogger("ticketbot")

SPORT_CHOICES = [
    app_commands.Choice(name="Football", value=Sport.FOOTBALL),
    app_commands.Choice(name="Men's Basketball", value=Sport.MENS_BASKETBALL),
    app_commands.Choice(name="Volleyball", value=Sport.VOLLEYBALL),
    app_commands.Choice(name="Women's Basketball", value=Sport.WOMENS_BASKETBALL),
]

# Listings are identified by game day only. Start time is not collected: matching
# is day-level, so an hour/minute changed nothing except adding two required
# fields for the poster to get wrong. Anyone who needs the tip-off time puts it
# in Notes.
DESCRIBE_KWARGS = {
    "sport": "The sport",
    "quantity": "Number of tickets",
    "notes": "Any additional info, e.g. game time, section, row, price",
    "month": "The month of the game (between 1 and 12)",
    "day": "The day of the game (between 1 and 31)",
    "year": "The year of the game",
}


class ListingsCog(commands.Cog):
    def __init__(self, bot, db_path, channel_id):
        self.bot = bot
        self.db_path = db_path
        self.channel_id = channel_id

    async def _post_listing(
        self,
        interaction: discord.Interaction,
        listing: Listing,
    ):
        """Persist a listing, announce it, and notify matches.

        The interaction is already deferred by the caller, so every reply here
        goes through followup and none of this work races the 3 second deadline.
        """
        channel = self.bot.get_channel(self.channel_id)
        if channel is None:
            log.error("Ticket channel %s not found or not visible", self.channel_id)
            await interaction.followup.send(
                "I can't reach the ticket exchange channel right now. "
                "Please let an admin know.",
                ephemeral=True,
            )
            return

        listing_id = add_listing(self.db_path, listing)

        try:
            message = await channel.send(
                embed=build_embed(listing, listing_id, interaction.user)
            )
            update_message_id(
                self.db_path, listing_id=listing_id, message_id=message.id
            )
        except discord.HTTPException:
            log.exception("Failed to post listing %s to the channel", listing_id)
            await interaction.followup.send(
                "Your listing was saved, but I couldn't post it to the channel.",
                ephemeral=True,
            )
            return

        await interaction.followup.send("Listing posted!", ephemeral=True)

        try:
            await self._notify_matches(listing, listing_id, channel)
        except discord.HTTPException:
            # The listing is already live; a failed match ping must not surface
            # as a command error to the poster.
            log.exception("Failed to notify matches for listing %s", listing_id)

    @app_commands.command(name="have", description="Post tickets you have available")
    @app_commands.describe(**DESCRIBE_KWARGS)
    @app_commands.choices(sport=SPORT_CHOICES)
    async def have(
        self,
        interaction: discord.Interaction,
        sport: app_commands.Choice[str],
        quantity: int,
        month: int,
        day: int,
        year: int,
        notes: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)

        errors = [
            validate_month(month),
            validate_day(day),
            validate_year(year),
        ]
        errors = [e for e in errors if e]
        if not errors:
            # Only meaningful once the individual fields are known sane.
            calendar_error = validate_calendar_date(year, month, day)
            if calendar_error:
                errors.append(calendar_error)
        if errors:
            await interaction.followup.send("\n".join(errors), ephemeral=True)
            return

        listing = Listing(
            user_id=interaction.user.id,
            listing_type=ListingType.HAVE,
            sport=Sport(sport.value),
            game_datetime=datetime(year, month, day),
            quantity=quantity,
            notes=notes,
            posted_at=datetime.now().isoformat(),
        )
        await self._post_listing(interaction, listing)

    @app_commands.command(name="want", description="Post what tickets you want")
    @app_commands.describe(**DESCRIBE_KWARGS)
    @app_commands.choices(sport=SPORT_CHOICES)
    async def want(
        self,
        interaction: discord.Interaction,
        sport: app_commands.Choice[str],
        quantity: Optional[int] = None,
        month: Optional[int] = None,
        day: Optional[int] = None,
        year: Optional[int] = None,
        notes: Optional[str] = None,
    ):
        await interaction.response.defer(ephemeral=True)

        errors = [
            validate_month(month) if month is not None else None,
            validate_day(day) if day is not None else None,
            validate_year(year) if year is not None else None,
        ]
        errors = [e for e in errors if e]
        if errors:
            await interaction.followup.send("\n".join(errors), ephemeral=True)
            return

        date_fields = [month, day, year]
        if any(f is not None for f in date_fields) and not all(
            f is not None for f in date_fields
        ):
            await interaction.followup.send(
                "Please provide month, day and year together, or none at all.",
                ephemeral=True,
            )
            return

        # Spelled out rather than all(...) so the type checker can narrow away
        # the Optional on each field.
        if year is not None and month is not None and day is not None:
            calendar_error = validate_calendar_date(year, month, day)
            if calendar_error:
                await interaction.followup.send(calendar_error, ephemeral=True)
                return
            game_datetime = datetime(year, month, day)
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
        await self._post_listing(interaction, listing)

    async def _notify_matches(self, listing: Listing, listing_id: int, channel):
        matches = find_matches(db_path=self.db_path, listing=listing)
        if not matches:
            return

        update_listing_status(
            db_path=self.db_path,
            listing_id=listing_id,
            listing_status=ListingStatus.MATCHED,
        )

        lines = []
        for match in matches:
            update_listing_status(
                db_path=self.db_path,
                listing_id=match.listing_id,
                listing_status=ListingStatus.MATCHED,
            )
            lines.append(
                f"- <@{match.matched_poster_user_id}> — "
                f"**{str(match.listing_type).upper()}** "
                f"{match.sport.replace('_', ' ').title()}, "
                f"{_format_game_datetime(match.game_datetime)}"
            )

        header = (
            f"🎟️ Possible match! <@{listing.user_id}> posted "
            f"**{str(listing.listing_type).upper()}** "
            f"{listing.sport.replace('_', ' ').title()}, "
            f"{_format_game_datetime(listing.game_datetime)}\n"
            f"This matches:\n"
        )
        # One message per posted listing rather than two per match: a burst of
        # sends drains the channel rate limit and stalls the next person's
        # command past its interaction deadline.
        await channel.send(_truncate(header + "\n".join(lines)))

    @app_commands.command(
        name="listings", description="See all open have and want listings"
    )
    @app_commands.describe(sport="Filter by sport")
    @app_commands.choices(sport=SPORT_CHOICES)
    async def listings(
        self,
        interaction: discord.Interaction,
        sport: Optional[app_commands.Choice[str]] = None,
    ):
        await interaction.response.defer(ephemeral=True)

        rows = get_open_listings(self.db_path)
        if sport:
            rows = [row for row in rows if row["sport"] == sport.value]

        haves = [row for row in rows if row["listing_type"] == ListingType.HAVE]
        wants = [row for row in rows if row["listing_type"] == ListingType.WANT]

        if not haves and not wants:
            await interaction.followup.send(
                "No open listings right now.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎟️ Open Ticket Listings", color=discord.Color.gold()
        )
        if haves:
            embed.add_field(
                name=f"Have ({len(haves)})",
                value="\n".join(format_listing_line(row) for row in haves)[:1024],
                inline=False,
            )
        if wants:
            embed.add_field(
                name=f"Want ({len(wants)})",
                value="\n".join(format_listing_line(row) for row in wants)[:1024],
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="mine", description="See your own open have and want listings"
    )
    async def mine(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        rows = get_user_listings(self.db_path, interaction.user.id)
        if not rows:
            await interaction.followup.send(
                "You have no active listings.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎟️ Your Open Listings", color=discord.Color.gold()
        )
        embed.description = "\n".join(format_listing_line(row) for row in rows)[:4096]

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(
        name="help", description="Get help on how to use the ticket exchange"
    )
    async def help(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=build_help_embed(), ephemeral=True
        )

    @app_commands.command(
        name="close", description="Close listings that you have created"
    )
    async def close(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        listings = get_user_listings(self.db_path, interaction.user.id)
        if not listings:
            await interaction.followup.send(
                "You have no active listings.", ephemeral=True
            )
            return

        channel = self.bot.get_channel(self.channel_id)
        view = CloseView(listings, self.db_path, channel)
        view.message = await interaction.followup.send(
            "Select a listing to close:", view=view, ephemeral=True, wait=True
        )

    # Deliberately absent from /help: this is an admin maintenance command, not
    # something the members of the server need to see.
    @app_commands.command(
        name="clear", description="Admin only: close every open listing"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def clear(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        # default_permissions only sets the server default, which an admin can
        # override in the Integrations panel, so re-check at call time.
        member = interaction.user
        if (
            not isinstance(member, discord.Member)
            or not member.guild_permissions.administrator
        ):
            log.warning("Non-admin %s attempted /clear", interaction.user.id)
            await interaction.followup.send(
                "Only server administrators can use this command.", ephemeral=True
            )
            return

        rows = get_open_listings(self.db_path)
        if not rows:
            await interaction.followup.send(
                "There are no active listings to clear.", ephemeral=True
            )
            return

        channel = self.bot.get_channel(self.channel_id)
        view = ConfirmClearView(self.db_path, channel, len(rows))
        view.message = await interaction.followup.send(
            f"This will close **all {len(rows)} active listing(s)** for everyone "
            f"in the server and mark their channel posts closed. Continue?",
            view=view,
            ephemeral=True,
            wait=True,
        )


def _format_game_datetime(game_datetime: Optional[datetime]) -> str:
    if not game_datetime:
        return "Any game"
    return game_datetime.strftime("%B %d, %Y")


def _truncate(text: str, limit: int = 1900) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…and more."


def setup(bot, db_path, channel_id):
    bot.add_cog(ListingsCog(bot, db_path, channel_id))
