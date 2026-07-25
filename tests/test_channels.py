import pytest

import channels
from enums import Sport

FOOTBALL_ID = 1217496779361222686
BASKETBALL_ID = 1217496733358100630
VOLLEYBALL_ID = 1217561679567650886
BASEBALL_ID = 1218975369554558996
DEFAULT_ID = 1222039441204314132
MAIN_ID = 1222385227381473311


@pytest.fixture
def routing():
    return channels.build(
        channel_id=MAIN_ID,
        football=str(FOOTBALL_ID),
        basketball=str(BASKETBALL_ID),
        volleyball=str(VOLLEYBALL_ID),
        baseball=str(BASEBALL_ID),
        default=str(DEFAULT_ID),
    )


@pytest.mark.parametrize(
    "sport,expected",
    [
        (Sport.FOOTBALL, FOOTBALL_ID),
        (Sport.MENS_BASKETBALL, BASKETBALL_ID),
        (Sport.WOMENS_BASKETBALL, BASKETBALL_ID),
        (Sport.VOLLEYBALL, VOLLEYBALL_ID),
        (Sport.BASEBALL, BASEBALL_ID),
    ],
)
def test_each_sport_routes_to_its_channel(routing, sport, expected):
    assert routing.channel_id_for(sport) == expected


def test_both_basketballs_share_one_channel(routing):
    assert routing.channel_id_for(Sport.MENS_BASKETBALL) == routing.channel_id_for(
        Sport.WOMENS_BASKETBALL
    )


def test_every_sport_in_the_enum_is_mapped(routing):
    """A new Sport member must not silently land in the fallback unnoticed."""
    unmapped = [s for s in Sport if routing.channel_id_for(s) == DEFAULT_ID]
    assert unmapped == []


def test_rows_from_the_database_route_by_string(routing):
    """get_open_listings returns plain strings, not Sport members."""
    assert routing.channel_id_for("volleyball") == VOLLEYBALL_ID


def test_unknown_sport_falls_back_instead_of_raising(routing):
    assert routing.channel_id_for("curling") == DEFAULT_ID


def test_missing_sport_entry_falls_back_to_default():
    routing = channels.build(channel_id=MAIN_ID, default=str(DEFAULT_ID))
    assert routing.channel_id_for(Sport.FOOTBALL) == DEFAULT_ID


def test_missing_default_falls_back_to_main_channel():
    """An empty .env degrades to the old single-channel behaviour."""
    routing = channels.build(channel_id=MAIN_ID)
    for sport in Sport:
        assert routing.channel_id_for(sport) == MAIN_ID


def test_partial_config_only_falls_back_for_the_gaps():
    routing = channels.build(
        channel_id=MAIN_ID, football=str(FOOTBALL_ID), default=str(DEFAULT_ID)
    )
    assert routing.channel_id_for(Sport.FOOTBALL) == FOOTBALL_ID
    assert routing.channel_id_for(Sport.VOLLEYBALL) == DEFAULT_ID


def test_resolve_uses_the_bots_channel_lookup(routing):
    seen = {}

    class FakeBot:
        def get_channel(self, cid):
            seen["id"] = cid
            return f"channel-{cid}"

    assert routing.resolve(FakeBot(), Sport.BASEBALL) == f"channel-{BASEBALL_ID}"
    assert seen["id"] == BASEBALL_ID


def test_sports_for_channel_single_sport(routing):
    assert routing.sports_for_channel(VOLLEYBALL_ID) == [Sport.VOLLEYBALL]
    assert routing.sports_for_channel(FOOTBALL_ID) == [Sport.FOOTBALL]
    assert routing.sports_for_channel(BASEBALL_ID) == [Sport.BASEBALL]


def test_sports_for_basketball_channel_returns_both(routing):
    """One channel serves two sports, so /have there cannot infer one."""
    assert set(routing.sports_for_channel(BASKETBALL_ID)) == {
        Sport.MENS_BASKETBALL,
        Sport.WOMENS_BASKETBALL,
    }


def test_default_channel_means_no_filter(routing):
    assert routing.sports_for_channel(DEFAULT_ID) == []


def test_unrelated_channel_means_no_filter(routing):
    assert routing.sports_for_channel(999999999999) == []
    assert routing.sports_for_channel(MAIN_ID) == []


def test_missing_channel_id_means_no_filter(routing):
    assert routing.sports_for_channel(None) == []


def test_no_filter_when_everything_falls_back_to_one_channel():
    """With an unconfigured .env every sport shares a channel; that channel is
    the default, so it must not filter to all five sports."""
    routing = channels.build(channel_id=MAIN_ID)
    assert routing.sports_for_channel(MAIN_ID) == []


def test_describe_lists_every_sport(routing):
    described = routing.describe()
    for sport in Sport:
        assert sport.value in described
