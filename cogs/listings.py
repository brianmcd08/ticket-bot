import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import (
    Listing,
    add_listing,
    get_listing,
    get_open_listings,
    get_sport_role,
    get_user_listings,
    update_listing_status,
    update_message_id,
    update_message_location,
)
from enums import SPORT_LABELS, ListingStatus, ListingType, Sport
from matching import find_matches
from utils import (
    build_embed,
    build_help_embed,
    format_listing_line,
    stray_command,
    stray_command_hint,
)
from validators import (
    validate_calendar_date,
    validate_day,
    validate_month,
    validate_year,
)
from views import CloseView, ConfirmClearView, SportPickView, replace_message_embed

log = logging.getLogger("ticketbot")

SPORT_CHOICES = [
    app_commands.Choice(name=label, value=sport.value)
    for sport, label in SPORT_LABELS.items()
]

# Listings are identified by game day only. Start time is not collected: matching
# is day-level, so an hour/minute changed nothing except adding two required
# fields for the poster to get wrong. Anyone who needs the tip-off time puts it
# in Notes.
DESCRIBE_KWARGS = {
    "sport": "The sport (optional in a sport's channel)",
    "quantity": "Number of tickets",
    "notes": "Any additional info, e.g. game time, section, row, price",
    "month": "The month of the game (between 1 and 12)",
    "day": "The day of the game (between 1 and 31)",
    "year": "The year of the game",
}


@dataclass
class RefreshResult:
    """Tally for /refresh, which reports counts rather than pinging anyone."""

    updated: int = 0
    missing_post: int = 0
    no_channel: int = 0
    unknown_poster: int = 0

    def summary(self) -> str:
        if not any(
            (self.updated, self.missing_post, self.no_channel, self.unknown_poster)
        ):
            return "There are no active listings to refresh."

        lines = [f"Re-rendered {self.updated} listing post(s)."]
        if self.missing_post:
            lines.append(
                f"{self.missing_post} listing(s) have no post in the channel "
                f"any more, so there was nothing to update."
            )
        if self.no_channel:
            lines.append(
                f"{self.no_channel} listing(s) have a post in a channel I "
                f"can't reach any more."
            )
        if self.unknown_poster:
            lines.append(
                f"{self.unknown_poster} listing(s) were left alone because I "
                f"couldn't look up who posted them."
            )
        return "\n".join(lines)


class ListingsCog(commands.Cog):
    def __init__(self, bot, db_path, channel_id, sport_channels):
        self.bot = bot
        self.db_path = db_path
        self.channel_id = channel_id
        self.sport_channels = sport_channels

    def listings_channel(self):
        """ticket-exchange: where every new listing card is posted."""
        return self.bot.get_channel(self.channel_id)

    def sports_in_channel(self, interaction: discord.Interaction) -> list[Sport]:
        """Sports implied by where the command was run. Empty means no filter."""
        return self.sport_channels.sports_for_channel(interaction.channel_id)

    def resolve_sport(
        self, interaction: discord.Interaction, sport
    ) -> tuple[Optional[Sport], list[Sport]]:
        """Sport from the explicit option, else inferred from the channel.

        Returns (sport, []) when it is known, or (None, sports to offer) when
        the member has to choose: the channel's sports if it covers several
        (basketball), otherwise all of them. An explicit choice always wins,
        so a football listing can still be posted from anywhere.
        """
        if sport is not None:
            return Sport(sport.value), []

        candidates = self.sports_in_channel(interaction)
        if len(candidates) == 1:
            return candidates[0], []
        return None, candidates or list(SPORT_LABELS)

    async def _post_with_sport(
        self,
        interaction: discord.Interaction,
        sport,
        make_listing: Callable[[Sport], Listing],
    ):
        """Post now if the sport is known, else ask for it with a dropdown.

        Called after every other field is validated, so picking a sport never
        leads to a date error.
        """
        resolved, choices = self.resolve_sport(interaction, sport)
        if resolved is not None:
            await self._post_listing(interaction, make_listing(resolved))
            return

        async def on_pick(pick_interaction: discord.Interaction, picked: Sport):
            await self._post_listing(pick_interaction, make_listing(picked))

        view = SportPickView(choices, on_pick)
        view.message = await interaction.followup.send(
            "Which sport is this for?", view=view, ephemeral=True, wait=True
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Point out a slash command that mobile sent as a plain message."""
        if message.author.bot or message.guild is None:
            return
        names = {command.name for command in self.get_app_commands()}
        name = stray_command(message.content, names)
        if name is None:
            return
        log.info("Stray /%s text from %s, sent hint", name, message.author.id)
        try:
            await message.reply(stray_command_hint(name), mention_author=True)
        except discord.HTTPException:
            log.exception("Could not reply to stray /%s message", name)

    async def _post_listing(
        self,
        interaction: discord.Interaction,
        listing: Listing,
    ):
        """Persist a listing, announce it, and notify matches.

        The interaction is already deferred by the caller, so every reply here
        goes through followup and none of this work races the 3 second deadline.
        """
        channel = self.listings_channel()
        if channel is None:
            log.error("Listings channel %s not found or not visible", self.channel_id)
            await interaction.followup.send(
                "I can't reach the ticket channel right now. "
                "Please let an admin know.",
                ephemeral=True,
            )
            return

        listing.channel_id = channel.id
        listing_id = add_listing(self.db_path, listing)

        # Ping the sport's opt-in role, if /rolepanel has created one.
        role_id = get_sport_role(self.db_path, listing.sport)
        try:
            message = await channel.send(
                content=f"<@&{role_id}>" if role_id else None,
                embed=build_embed(listing, listing_id, interaction.user),
                allowed_mentions=discord.AllowedMentions(
                    everyone=False,
                    users=False,
                    roles=[discord.Object(role_id)] if role_id else False,
                ),
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
        quantity: int,
        month: int,
        day: int,
        year: int,
        sport: Optional[app_commands.Choice[str]] = None,
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

        user_id = interaction.user.id
        await self._post_with_sport(
            interaction,
            sport,
            lambda resolved: Listing(
                user_id=user_id,
                listing_type=ListingType.HAVE,
                sport=resolved,
                game_datetime=datetime(year, month, day),
                quantity=quantity,
                notes=notes,
                posted_at=datetime.now().isoformat(),
            ),
        )

    @app_commands.command(name="want", description="Post what tickets you want")
    @app_commands.describe(**DESCRIBE_KWARGS)
    @app_commands.choices(sport=SPORT_CHOICES)
    async def want(
        self,
        interaction: discord.Interaction,
        sport: Optional[app_commands.Choice[str]] = None,
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

        user_id = interaction.user.id
        await self._post_with_sport(
            interaction,
            sport,
            lambda resolved: Listing(
                user_id=user_id,
                listing_type=ListingType.WANT,
                sport=resolved,
                game_datetime=game_datetime,
                quantity=quantity,
                notes=notes,
                posted_at=datetime.now().isoformat(),
            ),
        )

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

        # An explicit sport wins; otherwise the channel narrows it. The
        # basketball channel covers two sports, so this is a set, and an empty
        # set means show everything.
        if sport:
            wanted = {sport.value}
            scope = _sport_label(sport.value)
        else:
            candidates = self.sports_in_channel(interaction)
            wanted = {s.value for s in candidates}
            scope = " & ".join(_sport_label(s) for s in candidates)

        rows = get_open_listings(self.db_path)
        if wanted:
            rows = [row for row in rows if row["sport"] in wanted]

        haves = [row for row in rows if row["listing_type"] == ListingType.HAVE]
        wants = [row for row in rows if row["listing_type"] == ListingType.WANT]

        if not haves and not wants:
            await interaction.followup.send(
                f"No open {scope} listings right now." if scope
                else "No open listings right now.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"🎟️ Open {scope} Listings" if scope else "🎟️ Open Ticket Listings",
            color=discord.Color.gold(),
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

        view = CloseView(listings, self.db_path, self.bot.get_channel)
        view.message = await interaction.followup.send(
            "Select a listing to close:", view=view, ephemeral=True, wait=True
        )

    async def _require_admin(self, interaction: discord.Interaction) -> bool:
        """default_permissions only sets the server default, which an admin can
        override in the Integrations panel, so re-check at call time."""
        member = interaction.user
        if (
            not isinstance(member, discord.Member)
            or not member.guild_permissions.administrator
        ):
            log.warning(
                "Non-admin %s attempted /%s",
                interaction.user.id,
                interaction.command.name if interaction.command else "?",
            )
            await interaction.followup.send(
                "Only server administrators can use this command.", ephemeral=True
            )
            return False
        return True

    # Deliberately absent from /help: this is an admin maintenance command, not
    # something the members of the server need to see.
    @app_commands.command(
        name="reopen",
        description="Admin only: put a closed listing back, e.g. after /clear",
    )
    @app_commands.describe(
        listing_id="The listing's ID, shown as 'Listing ID: N' on its post"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def reopen(self, interaction: discord.Interaction, listing_id: int):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_admin(interaction):
            return

        row = get_listing(self.db_path, listing_id)
        if row is None:
            await interaction.followup.send(
                f"No listing with ID {listing_id}.", ephemeral=True
            )
            return
        if row["status"] != ListingStatus.CLOSED:
            await interaction.followup.send(
                f"Listing {listing_id} is already active.", ephemeral=True
            )
            return

        listing = Listing.from_row(row)
        # The card stays where it was posted; only a missing card is reposted,
        # and that goes to ticket-exchange like any new listing.
        card_channel = self.bot.get_channel(listing.channel_id)
        listings_channel = self.listings_channel()
        if card_channel is None and listings_channel is None:
            await interaction.followup.send(
                "I can't reach the ticket channel right now.", ephemeral=True
            )
            return

        update_listing_status(self.db_path, listing_id, ListingStatus.OPEN)

        # Re-render from the row rather than un-picking the "CLOSED" title, so
        # the restored post is identical to the original.
        try:
            poster = await self.bot.fetch_user(listing.user_id)
        except discord.HTTPException:
            poster = interaction.user
        embed = build_embed(listing, listing_id, poster)

        message = await replace_message_embed(card_channel, row["message_id"], embed)
        if message is None:
            # Original post is gone; post a fresh one and repoint the row.
            channel = listings_channel or card_channel
            # Both being None was ruled out above; this narrows the type.
            assert channel is not None
            message = await channel.send(embed=embed)
            update_message_location(self.db_path, listing_id, channel.id, message.id)
            listing.channel_id = channel.id
        channel = message.channel

        await interaction.followup.send(
            f"Listing {listing_id} reopened.", ephemeral=True
        )

        # A pointer, because the restored post may be far up the channel.
        try:
            await channel.send(
                f"🔄 <@{listing.user_id}> your listing (#{listing_id}) has been "
                f"reopened by an admin. {message.jump_url}"
            )
        except discord.HTTPException:
            log.exception("Could not announce reopen of listing %s", listing_id)

        try:
            await self._notify_matches(listing, listing_id, channel)
        except discord.HTTPException:
            log.exception("Failed to notify matches for reopened %s", listing_id)

    async def _resolve_poster(self, user_id: int, cache: dict[int, discord.abc.User]):
        """The poster, for the card's footer. None if they can't be looked up.

        Cached across the batch so one person's five listings cost one fetch,
        and skipped rather than substituted: a wrong name in the footer is worse
        than leaving a card alone.
        """
        if user_id in cache:
            return cache[user_id]
        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.HTTPException:
                log.warning("Could not resolve poster %s during /refresh", user_id)
                return None
        cache[user_id] = user
        return user

    # Deliberately absent from /help, like /clear and /reopen.
    @app_commands.command(
        name="refresh",
        description="Admin only: re-render active listing posts with the current card layout",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def refresh(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_admin(interaction):
            return

        rows = get_open_listings(self.db_path)
        result = RefreshResult()
        poster_cache: dict[int, discord.abc.User] = {}

        for row in rows:
            # 0 means the channel post failed at creation, so there is nothing
            # to re-render.
            if not row["message_id"]:
                result.missing_post += 1
                continue

            listing = Listing.from_row(row)
            channel = self.bot.get_channel(listing.channel_id)
            if channel is None:
                result.no_channel += 1
                continue

            poster = await self._resolve_poster(listing.user_id, poster_cache)
            if poster is None:
                result.unknown_poster += 1
                continue

            embed = build_embed(listing, row["id"], poster)
            # Edit in place only. Unlike /reopen this never reposts a missing
            # card and never announces anything: the point is to change the
            # rendering without pinging anyone.
            if await replace_message_embed(channel, row["message_id"], embed) is None:
                result.missing_post += 1
            else:
                result.updated += 1

        log.info(
            "/refresh updated %s of %s active listing(s)", result.updated, len(rows)
        )
        try:
            await interaction.followup.send(result.summary(), ephemeral=True)
        except discord.HTTPException:
            # A long batch can outlive the 15 minute followup window; the work
            # itself already happened.
            log.exception("Could not report /refresh results")

    @app_commands.command(
        name="clear", description="Admin only: close every open listing"
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def clear(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not await self._require_admin(interaction):
            return

        rows = get_open_listings(self.db_path)
        if not rows:
            await interaction.followup.send(
                "There are no active listings to clear.", ephemeral=True
            )
            return

        announce_channel = self.bot.get_channel(self.channel_id)
        view = ConfirmClearView(
            self.db_path, self.bot.get_channel, announce_channel, len(rows)
        )
        view.message = await interaction.followup.send(
            f"This will close **all {len(rows)} active listing(s)** for everyone "
            f"in the server and mark their channel posts closed. Continue?",
            view=view,
            ephemeral=True,
            wait=True,
        )


def _sport_label(sport) -> str:
    return str(sport).replace("_", " ").title()


def _format_game_datetime(game_datetime: Optional[datetime]) -> str:
    if not game_datetime:
        return "Any game"
    return game_datetime.strftime("%B %d, %Y")


def _truncate(text: str, limit: int = 1900) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…and more."


def setup(bot, db_path, channel_id, sport_channels):
    bot.add_cog(ListingsCog(bot, db_path, channel_id, sport_channels))
