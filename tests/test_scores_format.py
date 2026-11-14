from datetime import datetime, timezone

from espn import PITT_TEAM_ID, Game, GameState, Team
from scores_format import (
    final_message,
    score_table,
    scoreboard_embed,
    start_message,
)

ROLE = 555


def make_game(
    state=GameState.LIVE,
    pitt_home=True,
    pitt=(2, (25, 22, 14)),
    opp=(1, (20, 25, 11)),
    broadcast="ESPN",
    detail="3rd Set",
):
    pitt_team = Team(PITT_TEAM_ID, "Pitt", "PITT", pitt[0], pitt[1])
    opp_team = Team("97", "Louisville", "LOU", opp[0], opp[1])
    home, away = (pitt_team, opp_team) if pitt_home else (opp_team, pitt_team)
    return Game(
        event_id="1",
        start=datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc),
        state=state,
        detail=detail,
        period=len(pitt[1]),
        broadcast=broadcast,
        home=home,
        away=away,
    )


def test_score_table_away_on_top_with_sets_and_points():
    assert score_table(make_game()) == (
        "       S   1   2   3\n"
        "LOU    1  20  25  11\n"
        "PITT   2  25  22  14"
    )


def test_score_table_before_first_serve_is_blank():
    game = make_game(state=GameState.PRE, pitt=(None, ()), opp=(None, ()))
    assert score_table(game) == "       S\nLOU\nPITT"


def test_embed_shows_live_status_and_broadcast():
    embed = scoreboard_embed(make_game())
    assert embed.title == "🏐 Louisville at Pitt"
    assert embed.description.startswith("🔴 LIVE · 3rd Set · ESPN")


def test_embed_final_drops_live_marker():
    embed = scoreboard_embed(make_game(state=GameState.FINAL, detail="Final"))
    assert embed.description.startswith("FINAL · ESPN")


def test_start_message_home():
    msg = start_message(make_game(), PITT_TEAM_ID, ROLE, "https://link")
    assert msg == (
        "<@&555> 🏐 Pitt vs Louisville is underway (ESPN). Live score: https://link"
    )


def test_start_message_away_without_role_or_broadcast():
    game = make_game(pitt_home=False, broadcast=None)
    msg = start_message(game, PITT_TEAM_ID, None, "https://link")
    assert msg == "🏐 Pitt at Louisville is underway. Live score: https://link"


def test_final_message_pitt_wins_sets_from_pitt_side():
    game = make_game(
        state=GameState.FINAL,
        pitt=(3, (25, 22, 25, 25)),
        opp=(1, (20, 25, 18, 21)),
    )
    assert final_message(game, PITT_TEAM_ID, ROLE) == (
        "<@&555> 🏐 Final: Pitt def. Louisville 3-1 (25-20, 22-25, 25-18, 25-21)"
    )


def test_final_message_pitt_loses_sets_from_winner_side():
    game = make_game(
        state=GameState.FINAL,
        pitt=(2, (25, 20, 25, 22, 13)),
        opp=(3, (21, 25, 23, 25, 15)),
    )
    assert final_message(game, PITT_TEAM_ID, None) == (
        "🏐 Final: Louisville def. Pitt 3-2 (21-25, 25-20, 23-25, 25-22, 15-13)"
    )
