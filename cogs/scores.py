"""Live scores: one scoreboard message per game in #live-scores, kept current.

Covers every sport in espn.SPORT_PATHS: football, volleyball, both
basketballs, baseball and both soccers.

Every minute the loop looks at the team's cached schedule. Only a match that
starts soon or started in the last few hours is fetched from ESPN, so on a
day without a match the bot makes no requests beyond the schedule refresh.

Per match, once it goes live:
  1. post the scoreboard embed (edited in place from then on),
  2. post a start message pinging the sport's role, linking the scoreboard,
  3. at the end, a final message pinging the role again.
What's been posted is stored in scoreboard_messages, so a restart mid-match
picks the same message back up and never sends the start or final twice.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Protocol

import aiohttp
import discord
from discord.ext import commands, tasks

import espn
from database import (
    get_scoreboard,
    get_sport_role,
    mark_final_posted,
    mark_start_posted,
    save_scoreboard_message,
)
from enums import Sport
from espn import Game, GameState
from scores_format import final_message, scoreboard_embed, start_message

log = logging.getLogger("ticketbot")

POLL_SECONDS = 60
SCHEDULE_REFRESH = timedelta(hours=3)
SCHEDULE_RETRY = timedelta(minutes=10)
# Start fetching a little before first serve, in case ESPN's clock runs early.
LEAD = timedelta(minutes=15)
# Stop fetching this long after the scheduled start. A five-set volleyball
# match or a multi-overtime basketball game fits comfortably; a game ESPN
# never marks final just drops out instead of being polled forever.
WINDOW = timedelta(hours=5)
# Football runs 3.5-4 hours before any weather delay, and baseball can add
# extra innings and rain delays, so they get longer.
SPORT_WINDOWS: dict[Sport, timedelta] = {
    Sport.FOOTBALL: timedelta(hours=8),
    Sport.BASEBALL: timedelta(hours=8),
}

SPORTS: tuple[Sport, ...] = tuple(espn.SPORT_PATHS)


def active_games(schedule: list[Game], now: datetime) -> list[Game]:
    """Games worth fetching right now."""
    return [
        g
        for g in schedule
        if g.start - LEAD <= now <= g.start + SPORT_WINDOWS.get(g.sport, WINDOW)
    ]


def _mentions(role_id: Optional[int]) -> discord.AllowedMentions:
    return discord.AllowedMentions(
        everyone=False,
        users=False,
        roles=[discord.Object(role_id)] if role_id else False,
    )


class ScoresChannel(Protocol):
    """The bits of a TextChannel used here; tests pass a fake."""

    async def send(self, *args, **kwargs) -> discord.Message: ...

    def get_partial_message(self, message_id: int, /) -> discord.PartialMessage: ...

    @property
    def id(self) -> int: ...


async def sync_game(
    db_path,
    channel: ScoresChannel,
    game: Game,
    team_id: str,
    role_id: Optional[int],
    last_embeds: dict[str, discord.Embed],
) -> None:
    """Bring #live-scores up to date with one match's current state."""
    if game.state == GameState.PRE:
        return
    record = get_scoreboard(db_path, game.event_id)
    if record and record.final_posted:
        return

    if game.state == GameState.FINAL and game.home.score is None and game.away.score is None:
        # Postponed or cancelled: ESPN reports these as "post" with no score.
        log.info("Match %s ended with no score (%s); skipping", game.event_id, game.detail)
        mark_final_posted(db_path, game.event_id)
        return

    embed = scoreboard_embed(game)
    message: Optional[discord.Message | discord.PartialMessage] = None

    if record and record.message_id and record.channel_id == channel.id:
        message = channel.get_partial_message(record.message_id)
        if last_embeds.get(game.event_id) != embed:
            try:
                await message.edit(embed=embed)
            except discord.NotFound:
                # Someone deleted the scoreboard; post a fresh one below.
                message = None
    if message is None:
        message = await channel.send(embed=embed)
        save_scoreboard_message(db_path, game.event_id, channel.id, message.id)
    last_embeds[game.event_id] = embed

    started = record.start_posted if record else False
    if game.state == GameState.LIVE and not started:
        await channel.send(
            start_message(game, team_id, role_id, message.jump_url),
            allowed_mentions=_mentions(role_id),
        )
        mark_start_posted(db_path, game.event_id)
    elif game.state == GameState.FINAL:
        # Also covers a match the bot was down for the whole of: no start
        # message (it's over), just the scoreboard and the result.
        await channel.send(
            final_message(game, team_id, role_id),
            allowed_mentions=_mentions(role_id),
        )
        mark_final_posted(db_path, game.event_id)
        last_embeds.pop(game.event_id, None)


class ScoresCog(commands.Cog):
    def __init__(self, bot, db_path, channel_id: Optional[int], team_id: Optional[str]):
        self.bot = bot
        self.db_path = db_path
        self.channel_id = channel_id
        # None follows Pitt; set only for testing (SCORES_TEAM_ID).
        self.team_id = team_id
        self.session: Optional[aiohttp.ClientSession] = None
        # sport -> (when to refresh next, games)
        self.schedules: dict[Sport, tuple[datetime, list[Game]]] = {}
        # event_id -> last embed sent, to skip edits when nothing changed
        self.last_embeds: dict[str, discord.Embed] = {}

    def _team(self, sport: Sport) -> str:
        return self.team_id or espn.pitt_team_id(sport)

    async def cog_load(self):
        if not self.channel_id:
            log.info("SCORES_CHANNEL_ID not set; live scores are off")
            return
        self.session = aiohttp.ClientSession()
        self.poll.start()

    async def cog_unload(self):
        self.poll.cancel()
        if self.session:
            await self.session.close()

    async def _schedule(self, sport: Sport, now: datetime) -> list[Game]:
        assert self.session is not None
        refresh_at, games = self.schedules.get(sport, (now, []))
        if now >= refresh_at:
            try:
                games = await espn.fetch_schedule(self.session, sport, self._team(sport))
                refresh_at = now + SCHEDULE_REFRESH
                log.info(
                    "Loaded %s %s game(s) for team %s", len(games), sport.value, self._team(sport)
                )
            except (aiohttp.ClientError, TimeoutError, ValueError, KeyError):
                log.warning("Could not load the %s schedule; retrying soon", sport.value, exc_info=True)
                refresh_at = now + SCHEDULE_RETRY
            self.schedules[sport] = (refresh_at, games)
        return games

    @tasks.loop(seconds=POLL_SECONDS)
    async def poll(self):
        # Any exception escaping a tasks.loop stops it for good, so every
        # step is guarded and logged instead.
        assert self.session is not None
        channel = self.bot.get_channel(self.channel_id)
        if not isinstance(channel, discord.TextChannel):
            log.warning("Scores channel %s not found or not a text channel", self.channel_id)
            return
        now = datetime.now(timezone.utc)
        for sport in SPORTS:
            for scheduled in active_games(await self._schedule(sport, now), now):
                try:
                    game = await espn.fetch_game(
                        self.session, sport, scheduled.event_id, scheduled.start
                    )
                    if game is None:
                        continue
                    await sync_game(
                        self.db_path,
                        channel,
                        game,
                        self._team(sport),
                        get_sport_role(self.db_path, sport),
                        self.last_embeds,
                    )
                except Exception:
                    log.exception("Live score update failed for %s", scheduled.event_id)

    @poll.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()
