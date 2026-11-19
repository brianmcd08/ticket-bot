from datetime import datetime, timezone

from enums import Sport
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
    broadcast: str | None = "ESPN",
    detail="3rd Set",
    sport=Sport.VOLLEYBALL,
    neutral=False,
    opp_name=("Louisville", "LOU"),
):
    pitt_team = Team(PITT_TEAM_ID, "Pitt", "PITT", pitt[0], pitt[1])
    opp_team = Team("97", opp_name[0], opp_name[1], opp[0], opp[1])
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
        sport=sport,
        neutral=neutral,
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


# ---------- basketball ----------


def hoops(sport=Sport.MENS_BASKETBALL, pitt=(81, (38, 43)), opp=(61, (30, 31)), **kw):
    kw.setdefault("state", GameState.FINAL)
    kw.setdefault("detail", "Final")
    return make_game(sport=sport, pitt=pitt, opp=opp, opp_name=("Villanova", "VILL"), **kw)


def test_mens_table_has_halves_then_total():
    assert score_table(hoops()) == (
        "       1   2   T\n"
        "VILL  30  31  61\n"
        "PITT  38  43  81"
    )


def test_womens_table_has_quarters_and_labels_overtime():
    game = hoops(
        Sport.WOMENS_BASKETBALL,
        pitt=(80, (20, 20, 15, 15, 10)),
        opp=(75, (15, 15, 20, 20, 5)),
    )
    assert score_table(game).splitlines()[0] == "       1   2   3   4  OT   T"


def test_double_overtime_label():
    game = hoops(pitt=(90, (35, 35, 10, 10)), opp=(85, (30, 40, 10, 5)))
    assert score_table(game).splitlines()[0] == "       1   2  OT 2OT   T"


def test_basketball_embed_uses_basketball_emoji():
    assert scoreboard_embed(hoops()).title == "🏀 Villanova at Pitt"


def test_basketball_final_is_just_the_score():
    assert final_message(hoops(), PITT_TEAM_ID, ROLE) == (
        "<@&555> 🏀 Final: Pitt def. Villanova 81-61"
    )


def test_basketball_final_notes_overtime():
    game = hoops(pitt=(70, (30, 30, 10)), opp=(72, (35, 25, 12)))
    assert final_message(game, PITT_TEAM_ID, None) == (
        "🏀 Final: Villanova def. Pitt 72-70 (OT)"
    )


def test_neutral_site_says_vs_even_when_listed_away():
    game = hoops(pitt_home=False, neutral=True, state=GameState.LIVE)
    assert start_message(game, PITT_TEAM_ID, None, "L").startswith(
        "🏀 Pitt vs Villanova is underway"
    )
    assert scoreboard_embed(game).title == "🏀 Pitt vs Villanova"


# ---------- football ----------


def test_football_table_quarters_and_final():
    game = make_game(
        sport=Sport.FOOTBALL,
        state=GameState.FINAL,
        detail="Final",
        pitt=(10, (0, 7, 3, 0)),
        opp=(16, (3, 3, 7, 3)),
        opp_name=("Florida St", "FSU"),
    )
    assert scoreboard_embed(game).title == "🏈 Florida St at Pitt"
    assert score_table(game) == (
        "       1   2   3   4   T\n"
        "FSU    3   3   7   3  16\n"
        "PITT   0   7   3   0  10"
    )
    assert final_message(game, PITT_TEAM_ID, None) == "🏈 Final: Florida St def. Pitt 16-10"


# ---------- baseball and soccer ----------


def other(sport, pitt, opp, opp_name, pitt_extra=None, opp_extra=None):
    game = make_game(
        sport=sport, state=GameState.FINAL, detail="Final",
        pitt=pitt, opp=opp, opp_name=opp_name,
    )
    from dataclasses import replace

    # make_game puts Pitt at home.
    return replace(
        game,
        home=replace(game.home, **(pitt_extra or {})),
        away=replace(game.away, **(opp_extra or {})),
    )


def test_baseball_line_score_with_runs_hits_errors():
    game = other(
        Sport.BASEBALL,
        pitt=(13, (3, 3, 0, 0, 2, 4, 0, 1)),
        opp=(5, (2, 0, 1, 0, 0, 1, 0, 0, 1)),
        opp_name=("Wake Forest", "WAKE"),
        pitt_extra={"hits": 22, "errors": 0},
        opp_extra={"hits": 13, "errors": 2},
    )
    assert score_table(game) == (
        "      1  2  3  4  5  6  7  8  9   R  H  E\n"
        "WAKE  2  0  1  0  0  1  0  0  1   5 13  2\n"
        "PITT  3  3  0  0  2  4  0  1     13 22  0"
    )
    assert final_message(game, PITT_TEAM_ID, None) == "⚾ Final: Pitt def. Wake Forest 13-5"


def test_baseball_extra_innings_noted():
    game = other(
        Sport.BASEBALL,
        pitt=(4, (0,) * 9 + (4,)),
        opp=(3, (0,) * 8 + (3, 0)),
        opp_name=("Wake Forest", "WAKE"),
    )
    assert final_message(game, PITT_TEAM_ID, None).endswith("4-3 (10 innings)")
    assert score_table(game).splitlines()[0].startswith("      1  2  3  4  5  6  7  8  9 10")


def test_soccer_draw_puts_pitt_first():
    game = other(Sport.WOMENS_SOCCER, pitt=(2, ()), opp=(2, ()), opp_name=("SMU", "SMU"))
    assert final_message(game, PITT_TEAM_ID, ROLE) == "<@&555> ⚽ Final: Pitt 2, SMU 2 (draw)"
    assert score_table(game) == "       T\nSMU    2\nPITT   2"


def test_soccer_shootout_uses_espn_winner():
    game = other(
        Sport.MENS_SOCCER,
        pitt=(1, ()),
        opp=(1, ()),
        opp_name=("Syracuse", "SYR"),
        pitt_extra={"shootout": 6, "winner": False},
        opp_extra={"shootout": 7, "winner": True},
    )
    assert final_message(game, PITT_TEAM_ID, None) == (
        "⚽ Final: Syracuse def. Pitt 1-1 (7-6 on penalties)"
    )
    assert score_table(game) == "       T  PK\nSYR    1   7\nPITT   1   6"


def test_soccer_win():
    game = other(Sport.MENS_SOCCER, pitt=(2, ()), opp=(0, ()), opp_name=("Boston College", "BC"))
    assert final_message(game, PITT_TEAM_ID, None) == "⚽ Final: Pitt def. Boston College 2-0"
