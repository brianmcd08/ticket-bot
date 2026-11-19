"""Text for the live scoreboard and the start/final posts.

Pure functions of a Game, so every message can be tested without Discord.

Volleyball counts sets won, so its table leads with S (sets) and its final
lists each set. Basketball counts points, so its table ends with T (total),
the box-score convention, and its final is just the score.
"""

from typing import Optional

import discord

from enums import SPORT_EMOJI, Sport
from espn import Game, GameState, Team

PITT_BLUE = discord.Color(0x003594)

# Periods in regulation; anything past this is overtime. Men's college
# basketball plays halves, women's plays quarters.
REGULATION_PERIODS: dict[Sport, int] = {
    Sport.MENS_BASKETBALL: 2,
    Sport.WOMENS_BASKETBALL: 4,
}


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
    """'1'..'4', then 'OT', '2OT' past regulation (basketball only)."""
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

    Basketball, points per half/quarter then T = total:
            1   2   T
    VILL   30  31  61
    PITT   38  43  81
    """
    rows = [game.away, game.home]
    periods = max(len(t.periods) for t in rows)
    name_width = max(len(t.abbreviation) for t in rows)
    labels = [_period_label(game, i) for i in range(1, periods + 1)]

    def row(label: str, cells: list[str]) -> str:
        return label.ljust(name_width) + "".join(c.rjust(4) for c in cells)

    def cells(t: Team) -> tuple[str, list[str]]:
        points = [str(p) for p in t.periods] + [""] * (periods - len(t.periods))
        return ("" if t.score is None else str(t.score)), points

    lines = []
    if _counts_sets(game):
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


def final_message(game: Game, team_id: str, role_id: Optional[int]) -> str:
    """'Final: Pitt def. Louisville 3-1 (25-20, 22-25, 25-18, 25-21)' for
    volleyball, 'Final: Pitt def. Villanova 81-61' for basketball (with
    '(OT)' when it went to overtime)."""
    us, them = game.team(team_id), game.opponent(team_id)
    winner, loser = (us, them) if (us.score or 0) >= (them.score or 0) else (them, us)
    if _counts_sets(game):
        sets = _set_scores(winner, loser)
        detail = f" ({sets})" if sets else ""
    else:
        periods = max(len(winner.periods), len(loser.periods))
        last = _period_label(game, periods) if periods else ""
        detail = f" ({last})" if last.endswith("OT") else ""
    return (
        f"{_mention(role_id)}{_emoji(game)} Final: {winner.name} def. {loser.name} "
        f"{winner.score}-{loser.score}{detail}"
    )
