"""Routing from a sport to the channel its listings belong in."""

from typing import Optional

from enums import Sport


class SportChannels:
    """Maps a sport to a channel id, with a fallback for anything unmapped.

    Kept separate from Config so it can be built and tested without a .env.
    """

    def __init__(self, mapping: dict[Sport, int], default: int):
        self._mapping = mapping
        self._default = default

    @property
    def default(self) -> int:
        return self._default

    def channel_id_for(self, sport) -> int:
        """Never raises: an unknown sport falls back to the default channel."""
        try:
            return self._mapping.get(Sport(sport), self._default)
        except ValueError:
            return self._default

    def resolve(self, bot, sport):
        """The discord channel for a sport, or None if the bot cannot see it."""
        return bot.get_channel(self.channel_id_for(sport))

    def sports_for_channel(self, channel_id) -> list[Sport]:
        """Which sports a channel covers, for channel-aware commands.

        Empty means "no filter": either the general/default channel, or a
        channel the bot does not route any sport to. The basketball channel
        serves two sports, so this returns a list rather than one sport.
        """
        if channel_id is None or channel_id == self._default:
            return []
        return [
            sport
            for sport, mapped in self._mapping.items()
            if mapped == channel_id
        ]

    def describe(self) -> str:
        """One line per sport, for logging the routing at startup."""
        lines = [
            f"  {sport.value} -> {self.channel_id_for(sport)}" for sport in Sport
        ]
        lines.append(f"  (fallback) -> {self._default}")
        return "\n".join(lines)


def build(
    channel_id: int,
    football: Optional[str] = None,
    basketball: Optional[str] = None,
    volleyball: Optional[str] = None,
    baseball: Optional[str] = None,
    default: Optional[str] = None,
) -> SportChannels:
    """Build the routing table from raw (string) config values.

    Anything missing falls back rather than failing startup, so an incomplete
    .env degrades to the old single-channel behaviour instead of taking the bot
    down. The resolved table is logged at startup so a gap is still visible.
    """
    fallback = int(default) if default else channel_id
    raw = {
        Sport.FOOTBALL: football,
        # Both basketball listings share one channel.
        Sport.MENS_BASKETBALL: basketball,
        Sport.WOMENS_BASKETBALL: basketball,
        Sport.VOLLEYBALL: volleyball,
        Sport.BASEBALL: baseball,
    }
    mapping = {sport: int(value) if value else fallback for sport, value in raw.items()}
    return SportChannels(mapping, fallback)
