"""Text for the live scoreboard and the start/final posts.

Pure functions of a Game, so every message can be tested without Discord.

Volleyball counts sets won, so its table leads with S (sets) and its final
lists each set. Other sports end the table with a total, the box-score
convention: T for points, R H E (runs, hits, errors) for baseball. Soccer
has no per-half scores from ESPN, so its table is just the goals, plus PK for
a shootout, and its final can be a draw.
"""

from typing import Optional

import discord

from enums import SPORT_EMOJI, Sport
from espn import Game, GameState, Team

PITT_BLUE = discord.Color(0x003594)

# Periods in regulation; anything past this is overtime. Men's college
# basketball plays halves; women's basketball and football play quarters.
REGULATION_PERIODS: dict[Sport, int] = {
    Sport.MENS_BASKETBALL: 2,
    Sport.WOMENS_BASKETBALL: 4,
    Sport.FOOTBALL: 4,
    Sport.MENS_SOCCER: 2,
    Sport.WOMENS_SOCCER: 2,
}
SOCCER = (Sport.MENS_SOCCER, Sport.WOMENS_SOCCER)
BASEBALL_INNINGS = 9


def _emoji(game: Game) -> str:
    return SPORT_EMOJI.get(game.sport, "🏆")


def _counts_sets(game: Game) -> bool:
    return game.sport == Sport.VOLLEYBALL


def _matchup(game: Game, team_id: str) -> str:
    """'Pitt vs Louisville' at home or a neutral site, 'Pitt at Virginia' away."""
    us, them = game.team(team_id), game.opponent(team_id)
    word = "vs" if game.is_home(team_id) or game.neutral else "at"
    return f"{us.name} {word} {them.name}"


def _mention(role_id: Optional[int]) -> str:
    return f"<@&{role_id}> " if role_id else ""


def _period_label(game: Game, number: int) -> str:
    """'1'..'4', then 'OT', '2OT' past regulation (not volleyball)."""
    regulation = REGULATION_PERIODS.get(game.sport)
    if regulation is None or number <= regulation:
        return str(number)
    extra = number - regulation
    return "OT" if extra == 1 else f"{extra}OT"


def score_table(game: Game) -> str:
    """Away on top, home below, as on a TV score bug.

    Volleyball, S = sets won then points per set:
           S   1   2   3
    LOU    1  20  25  11
    PITT   2  25  22  14

    Basketball and football, points per half/quarter then T = total:
            1   2   T
    VILL   30  31  61
    PITT   38  43  81

    Baseball, narrower columns so nine innings fit on a phone:
          1  2  3  4  5  6  7  8  9   R  H  E
    PITT  2  0  1  0  0  1  0  0  1   5 13  2
    UNC   3  3  0  0  2  4  0  1     13 22  0
    """
    rows = [game.away, game.home]
    periods = max(len(t.periods) for t in rows)
    name_width = max(len(t.abbreviation) for t in rows)
    labels = [_period_label(game, i) for i in range(1, periods + 1)]
    width = 3 if game.sport == Sport.BASEBALL else 4

    def row(label: str, cells: list[str]) -> str:
        return label.ljust(name_width) + "".join(c.rjust(width) for c in cells)

    def num(value: Optional[int]) -> str:
        return "" if value is None else str(value)

    def cells(t: Team) -> tuple[str, list[str]]:
        points = [str(p) for p in t.periods] + [""] * (periods - len(t.periods))
        return num(t.score), points

    lines = []
    if game.sport == Sport.BASEBALL:
        # A space before R sets the totals apart from the innings.
        lines.append(row("", labels) + " " + "".join(c.rjust(3) for c in "RHE"))
        for t in rows:
            total, points = cells(t)
            totals = "".join(c.rjust(3) for c in (total, num(t.hits), num(t.errors)))
            lines.append(row(t.abbreviation, points) + " " + totals)
    elif game.sport in SOCCER and any(t.shootout is not None for t in rows):
        lines.append(row("", labels + ["T", "PK"]))
        for t in rows:
            total, points = cells(t)
            lines.append(row(t.abbreviation, points + [total, num(t.shootout)]))
    elif _counts_sets(game):
        lines.append(row("", ["S"] + labels))
        for t in rows:
            total, points = cells(t)
            lines.append(row(t.abbreviation, [total] + points))
    else:
        lines.append(row("", labels + ["T"]))
        for t in rows:
            total, points = cells(t)
            lines.append(row(t.abbreviation, points + [total]))
    return "\n".join(line.rstrip() for line in lines)


def scoreboard_embed(game: Game) -> discord.Embed:
    """The one message in #live-scores, edited as the game goes on."""
    status = "FINAL" if game.state == GameState.FINAL else game.detail
    if game.state == GameState.LIVE:
        status = f"🔴 LIVE · {status}"
    if game.broadcast:
        status += f" · {game.broadcast}"
    word = "vs" if game.neutral else "at"
    embed = discord.Embed(
        title=f"{_emoji(game)} {game.away.name} {word} {game.home.name}",
        description=f"{status}\n```\n{score_table(game)}\n```",
        color=PITT_BLUE,
    )
    return embed


def start_message(
    game: Game, team_id: str, role_id: Optional[int], scoreboard_link: str
) -> str:
    broadcast = f" ({game.broadcast})" if game.broadcast else ""
    return (
        f"{_mention(role_id)}{_emoji(game)} {_matchup(game, team_id)} is underway"
        f"{broadcast}. Live score: {scoreboard_link}"
    )


def _set_scores(winner: Team, loser: Team) -> str:
    """'25-20, 22-25, 25-18' from the winner's side."""
    return ", ".join(f"{w}-{lo}" for w, lo in zip(winner.periods, loser.periods))


def _winner_first(us: Team, them: Team) -> tuple[Team, Team]:
    # ESPN's winner flag decides a soccer shootout, where goals are level.
    if them.winner and not us.winner:
        return them, us
    if us.winner and not them.winner:
        return us, them
    return (us, them) if (us.score or 0) >= (them.score or 0) else (them, us)


def final_message(game: Game, team_id: str, role_id: Optional[int]) -> str:
    """The result, from the winner's side:
    'Final: Pitt def. Louisville 3-1 (25-20, 22-25, 25-18, 25-21)' volleyball
    'Final: Pitt def. Villanova 81-61 (OT)' points, '(OT)' only if it went there
    'Final: UNC def. Pitt 13-5 (10 innings)' baseball, innings only if extra
    'Final: Syracuse def. Pitt 1-1 (7-6 on penalties)' soccer shootout
    'Final: Pitt 2, SMU 2 (draw)' soccer draw, Pitt first
    """
    us, them = game.team(team_id), game.opponent(team_id)
    prefix = f"{_mention(role_id)}{_emoji(game)} Final:"
    shootout = us.shootout is not None and them.shootout is not None
    if game.sport in SOCCER and us.score == them.score and not shootout:
        return f"{prefix} {us.name} {us.score}, {them.name} {them.score} (draw)"

    winner, loser = _winner_first(us, them)
    if _counts_sets(game):
        sets = _set_scores(winner, loser)
        detail = f" ({sets})" if sets else ""
    elif shootout:
        detail = f" ({winner.shootout}-{loser.shootout} on penalties)"
    elif game.sport == Sport.BASEBALL:
        innings = max(len(winner.periods), len(loser.periods))
        detail = f" ({innings} innings)" if innings > BASEBALL_INNINGS else ""
    else:
        periods = max(len(winner.periods), len(loser.periods))
        last = _period_label(game, periods) if periods else ""
        detail = f" ({last})" if last.endswith("OT") else ""
    return f"{prefix} {winner.name} def. {loser.name} {winner.score}-{loser.score}{detail}"
