"""Text for the live scoreboard and the start/final posts.

Pure functions of a Game, so every message can be tested without Discord.
"""

from typing import Optional

import discord

from espn import Game, GameState, Team

PITT_BLUE = discord.Color(0x003594)
SPORT_EMOJI = "🏐"


def _matchup(game: Game, team_id: str) -> str:
    """'Pitt vs Louisville' at home, 'Pitt at Virginia' away."""
    us, them = game.team(team_id), game.opponent(team_id)
    word = "vs" if game.is_home(team_id) else "at"
    return f"{us.name} {word} {them.name}"


def _mention(role_id: Optional[int]) -> str:
    return f"<@&{role_id}> " if role_id else ""


def score_table(game: Game) -> str:
    """Away on top, home below; column S is sets won, then points per set.

           S   1   2   3
    LOU    1  20  25  11
    PITT   2  25  22  14
    """
    rows = [game.away, game.home]
    sets = max(len(t.periods) for t in rows)
    name_width = max(len(t.abbreviation) for t in rows)

    def row(label: str, cells: list[str]) -> str:
        return label.ljust(name_width) + "".join(c.rjust(4) for c in cells)

    header = row("", ["S"] + [str(i) for i in range(1, sets + 1)])
    lines = [header]
    for t in rows:
        points = [str(p) for p in t.periods] + [""] * (sets - len(t.periods))
        sets_won = "" if t.score is None else str(t.score)
        lines.append(row(t.abbreviation, [sets_won] + points))
    return "\n".join(line.rstrip() for line in lines)


def scoreboard_embed(game: Game) -> discord.Embed:
    """The one message in #live-scores, edited as the match goes on."""
    status = "FINAL" if game.state == GameState.FINAL else game.detail
    if game.state == GameState.LIVE:
        status = f"🔴 LIVE · {status}"
    if game.broadcast:
        status += f" · {game.broadcast}"
    embed = discord.Embed(
        title=f"{SPORT_EMOJI} {game.away.name} at {game.home.name}",
        description=f"{status}\n```\n{score_table(game)}\n```",
        color=PITT_BLUE,
    )
    return embed


def start_message(
    game: Game, team_id: str, role_id: Optional[int], scoreboard_link: str
) -> str:
    broadcast = f" ({game.broadcast})" if game.broadcast else ""
    return (
        f"{_mention(role_id)}{SPORT_EMOJI} {_matchup(game, team_id)} is underway"
        f"{broadcast}. Live score: {scoreboard_link}"
    )


def _set_scores(winner: Team, loser: Team) -> str:
    """'25-20, 22-25, 25-18' from the winner's side."""
    return ", ".join(f"{w}-{lo}" for w, lo in zip(winner.periods, loser.periods))


def final_message(game: Game, team_id: str, role_id: Optional[int]) -> str:
    """'Final: Pitt def. Louisville 3-1 (25-20, 22-25, 25-18, 25-21)'."""
    us, them = game.team(team_id), game.opponent(team_id)
    winner, loser = (us, them) if (us.score or 0) >= (them.score or 0) else (them, us)
    sets = _set_scores(winner, loser)
    detail = f" ({sets})" if sets else ""
    return (
        f"{_mention(role_id)}{SPORT_EMOJI} Final: {winner.name} def. {loser.name} "
        f"{winner.score}-{loser.score}{detail}"
    )
