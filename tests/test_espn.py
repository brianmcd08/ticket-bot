import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from enums import Sport
from espn import (
    PITT_TEAM_ID,
    GameState,
    parse_event,
    parse_events,
    scoreboard_url,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def schedule():
    return {g.event_id: g for g in parse_events(load("schedule.json"))}


@pytest.fixture
def scoreboard():
    return {g.state: g for g in parse_events(load("scoreboard.json"))}


def test_schedule_final_reads_dict_scores(schedule):
    game = schedule["401884336"]  # Notre Dame at Pitt, Pitt won 3-0
    assert game.state == GameState.FINAL
    assert game.team(PITT_TEAM_ID).score == 3
    assert game.opponent(PITT_TEAM_ID).score == 0
    assert game.opponent(PITT_TEAM_ID).abbreviation == "ND"
    assert game.is_home(PITT_TEAM_ID)


def test_schedule_upcoming_has_no_score_and_a_broadcast(schedule):
    game = schedule["401883963"]  # Louisville at Pitt
    assert game.state == GameState.PRE
    assert game.team(PITT_TEAM_ID).score is None
    assert game.opponent(PITT_TEAM_ID).name == "Louisville"
    assert game.broadcast == "ESPN"
    assert game.start == datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)


def test_schedule_event_without_broadcast(schedule):
    assert schedule["401884275"].broadcast is None


def test_live_match_reads_string_scores_and_set_points(scoreboard):
    game = scoreboard[GameState.LIVE]
    assert game.home.score is not None and game.away.score is not None
    # One entry per set played so far, for both teams
    assert len(game.home.periods) == len(game.away.periods) >= 1
    assert game.period >= 1
    assert game.broadcast == "ACCNX"


def test_final_match_has_a_winner_by_sets(scoreboard):
    game = scoreboard[GameState.FINAL]
    assert game.detail == "Final"
    assert max(game.home.score, game.away.score) == 3


def test_home_and_away_follow_home_away_field():
    event = load("schedule.json")["events"][0]
    competitors = event["competitions"][0]["competitors"]
    competitors.reverse()  # order in the list must not matter
    game = parse_event(event)
    assert game.home.id == PITT_TEAM_ID


def test_scoreboard_url_uses_eastern_date():
    # 01:00 UTC on the 16th is 8 PM Eastern on the 15th
    start = datetime(2026, 11, 16, 1, 0, tzinfo=timezone.utc)
    assert "dates=20261115" in scoreboard_url(Sport.VOLLEYBALL, start)


def test_basketball_scoreboard_asks_for_all_of_division_one():
    from espn import scoreboard_url

    day = datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)  # 7pm Eastern on the 17th
    assert scoreboard_url(Sport.MENS_BASKETBALL, day).endswith(
        "scoreboard?dates=20261117&limit=500&groups=50"
    )
    assert scoreboard_url(Sport.VOLLEYBALL, day).endswith("dates=20261117&limit=500")


def test_pitt_team_ids_differ_for_soccer_and_baseball():
    from espn import pitt_team_id

    assert pitt_team_id(Sport.FOOTBALL) == "221"
    assert pitt_team_id(Sport.BASEBALL) == "115"
    assert pitt_team_id(Sport.MENS_SOCCER) == "5744"
    assert pitt_team_id(Sport.WOMENS_SOCCER) == "20468"


def test_every_sport_has_a_score_feed():
    from espn import SPORT_PATHS

    assert set(SPORT_PATHS) == set(Sport)
