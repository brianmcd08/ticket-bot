"""ESPN's public scoreboard feeds: fetch, and parse into Game objects.

The feeds are undocumented and need no key, so they can change without notice.
The team-schedule and scoreboard endpoints describe the same match in slightly
different shapes (a score is a dict in one and a string in the other, and the
broadcast lives in different fields), so the parser accepts both.

Parsing is kept separate from fetching so it can be tested against saved JSON.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Optional
from zoneinfo import ZoneInfo

import aiohttp

from enums import Sport

BASE_URL = "https://site.api.espn.com/apis/site/v2/sports"
PITT_TEAM_ID = "221"
EASTERN = ZoneInfo("America/New_York")

# Adding a sport is one entry here (and a channel/role in config).
SPORT_PATHS: dict[Sport, str] = {
    Sport.VOLLEYBALL: "volleyball/womens-college-volleyball",
}

TIMEOUT = aiohttp.ClientTimeout(total=15)


class GameState(StrEnum):
    PRE = "pre"
    LIVE = "in"
    FINAL = "post"


@dataclass(frozen=True)
class Team:
    id: str
    name: str  # short display name, e.g. "Pitt"
    abbreviation: str
    score: Optional[int]  # sets won in volleyball; None before the match
    periods: tuple[int, ...]  # points per set (or per quarter/half)


@dataclass(frozen=True)
class Game:
    event_id: str
    start: datetime  # timezone-aware, UTC
    state: GameState
    detail: str  # ESPN's status text: "3rd Set", "Final", a start time
    period: int
    broadcast: Optional[str]
    home: Team
    away: Team

    def has_team(self, team_id: str) -> bool:
        return team_id in (self.home.id, self.away.id)

    def team(self, team_id: str) -> Team:
        return self.home if self.home.id == team_id else self.away

    def opponent(self, team_id: str) -> Team:
        return self.away if self.home.id == team_id else self.home

    def is_home(self, team_id: str) -> bool:
        return self.home.id == team_id


# ---------- parsing (pure) ----------


def _parse_score(raw: Any) -> Optional[int]:
    """Scoreboard gives "2", schedule gives {"value": 2.0, ...}, upcoming gives None."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("value", raw.get("displayValue"))
        if raw is None:
            return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _parse_periods(raw: Any) -> tuple[int, ...]:
    if not raw:
        return ()
    return tuple(int(float(p.get("value", 0))) for p in raw)


def _parse_team(competitor: dict) -> Team:
    team = competitor["team"]
    return Team(
        id=str(team["id"]),
        name=team.get("shortDisplayName") or team.get("displayName", "?"),
        abbreviation=team.get("abbreviation", "?"),
        score=_parse_score(competitor.get("score")),
        periods=_parse_periods(competitor.get("linescores")),
    )


def _parse_broadcast(competition: dict) -> Optional[str]:
    # Scoreboard: "broadcast": "ACCNX" and broadcasts[].names
    if competition.get("broadcast"):
        return competition["broadcast"]
    for b in competition.get("broadcasts") or []:
        # Schedule: broadcasts[].media.shortName
        name = (b.get("media") or {}).get("shortName")
        if name:
            return name
        names = b.get("names")
        if names:
            return names[0]
    return None


def parse_start(raw: str) -> datetime:
    """ESPN dates look like "2026-11-16T01:00Z"."""
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def parse_event(event: dict) -> Game:
    competition = event["competitions"][0]
    status = competition.get("status") or event.get("status") or {}
    status_type = status.get("type", {})
    competitors = competition["competitors"]
    home_raw = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
    away_raw = next((c for c in competitors if c is not home_raw), competitors[-1])
    home, away = _parse_team(home_raw), _parse_team(away_raw)
    return Game(
        event_id=str(event["id"]),
        start=parse_start(event.get("date") or competition["date"]),
        state=GameState(status_type.get("state", "pre")),
        detail=status_type.get("shortDetail") or status_type.get("detail", ""),
        period=int(status.get("period") or 0),
        broadcast=_parse_broadcast(competition),
        home=home,
        away=away,
    )


def parse_events(payload: dict) -> list[Game]:
    return [parse_event(e) for e in payload.get("events", [])]


# ---------- fetching ----------


def schedule_url(sport: Sport, team_id: str) -> str:
    return f"{BASE_URL}/{SPORT_PATHS[sport]}/teams/{team_id}/schedule"


def scoreboard_url(sport: Sport, day: datetime) -> str:
    """ESPN files a match under its US Eastern date."""
    date = day.astimezone(EASTERN).strftime("%Y%m%d")
    return f"{BASE_URL}/{SPORT_PATHS[sport]}/scoreboard?dates={date}&limit=500"


async def _get_json(session: aiohttp.ClientSession, url: str) -> dict:
    async with session.get(url, timeout=TIMEOUT) as response:
        response.raise_for_status()
        return await response.json()


async def fetch_schedule(
    session: aiohttp.ClientSession, sport: Sport, team_id: str
) -> list[Game]:
    return parse_events(await _get_json(session, schedule_url(sport, team_id)))


async def fetch_game(
    session: aiohttp.ClientSession, sport: Sport, event_id: str, start: datetime
) -> Optional[Game]:
    """Live state of one match, from the scoreboard for its date."""
    games = parse_events(await _get_json(session, scoreboard_url(sport, start)))
    return next((g for g in games if g.event_id == event_id), None)
