"""Opt-in sport roles: one button per sport, tap to get or drop its pings.

A sport's role is pinged for its new ticket listings (and, later, its scores).
Members pick roles themselves from a panel an admin posts with /rolepanel.
"""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from database import get_sport_role, get_sport_roles, save_sport_role
from enums import SPORT_EMOJI, SPORT_LABELS, Sport

log = logging.getLogger("ticketbot")

# Stable across restarts, so buttons on an old panel keep working.
CUSTOM_ID_PREFIX = "sportrole:"

PERMISSION_HELP = (
    "I don't have permission to manage that role. An admin needs to give my "
    "role **Manage Roles** and drag it above the sport roles in Server "
    "Settings → Roles."
)


def panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔔 Sport notifications",
        description=(
            "Tap a sport to get pinged when someone posts tickets for it, and "
            "for live scores. Tap it again to stop.\n\n"
            "Only you see the confirmation, and you can change your mind any time."
        ),
        color=discord.Color.gold(),
    )
    return embed


class SportRoleButton(discord.ui.Button["RolePanelView"]):
    def __init__(self, sport: Sport, db_path):
        super().__init__(
            label=SPORT_LABELS[sport],
            emoji=SPORT_EMOJI.get(sport),
            style=discord.ButtonStyle.secondary,
            custom_id=f"{CUSTOM_ID_PREFIX}{sport.value}",
        )
        self.sport = sport
        self.db_path = db_path

    async def callback(self, interaction: discord.Interaction):
        member = interaction.user
        guild = interaction.guild
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "This only works inside the server.", ephemeral=True
            )
            return

        role_id = get_sport_role(self.db_path, self.sport)
        role = guild.get_role(role_id) if role_id else None
        label = SPORT_LABELS[self.sport]
        if role is None:
            await interaction.response.send_message(
                f"The {label} role is missing. Please ask an admin to run "
                f"/rolepanel again.",
                ephemeral=True,
            )
            return

        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Sport notifications panel")
                reply = f"🔕 You won't be pinged for {label} any more."
            else:
                await member.add_roles(role, reason="Sport notifications panel")
                reply = f"🔔 You'll now be pinged for {label}."
        except discord.Forbidden:
            log.warning("Missing permission to toggle role %s", role.id)
            await interaction.response.send_message(PERMISSION_HELP, ephemeral=True)
            return

        await interaction.response.send_message(reply, ephemeral=True)


class RolePanelView(discord.ui.View):
    """Persistent: no timeout, registered at startup with bot.add_view."""

    def __init__(self, db_path):
        super().__init__(timeout=None)
        for sport in SPORT_LABELS:
            self.add_item(SportRoleButton(sport, db_path))


class RolesCog(commands.Cog):
    def __init__(self, bot, db_path):
        self.bot = bot
        self.db_path = db_path

    async def _ensure_roles(self, guild: discord.Guild) -> list[str]:
        """Create any sport role that is missing. Returns the names created.

        Raises discord.Forbidden if the bot lacks Manage Roles.
        """
        existing = get_sport_roles(self.db_path)
        created = []
        for sport, label in SPORT_LABELS.items():
            role_id = existing.get(sport.value)
            if role_id and guild.get_role(role_id):
                continue
            # mentionable so a listing's ping actually notifies people.
            role = await guild.create_role(
                name=label, mentionable=True, reason="Sport notification role"
            )
            save_sport_role(self.db_path, sport, role.id)
            created.append(label)
        return created

    # Deliberately absent from /help, like the other admin commands.
    @app_commands.command(
        name="rolepanel",
        description="Admin only: post the sport notification buttons in this channel",
    )
    @app_commands.default_permissions(administrator=True)
    @app_commands.guild_only()
    async def rolepanel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        member = interaction.user
        if (
            not isinstance(member, discord.Member)
            or not member.guild_permissions.administrator
        ):
            await interaction.followup.send(
                "Only server administrators can use this command.", ephemeral=True
            )
            return
        guild = interaction.guild
        channel = interaction.channel
        if guild is None or not isinstance(channel, discord.abc.Messageable):
            await interaction.followup.send(
                "Run this in a server text channel.", ephemeral=True
            )
            return

        try:
            created = await self._ensure_roles(guild)
        except discord.Forbidden:
            await interaction.followup.send(
                "I couldn't create the sport roles. Give my role **Manage Roles** "
                "in Server Settings → Roles, then run this again.",
                ephemeral=True,
            )
            return

        try:
            await channel.send(embed=panel_embed(), view=RolePanelView(self.db_path))
        except discord.HTTPException:
            log.exception("Could not post the role panel")
            await interaction.followup.send(
                "I couldn't post in this channel. Check that I can send messages "
                "here.",
                ephemeral=True,
            )
            return

        note = f" Created roles: {', '.join(created)}." if created else ""
        await interaction.followup.send(f"Panel posted.{note}", ephemeral=True)
