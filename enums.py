from enum import IntEnum, StrEnum


class ListingType(StrEnum):
    HAVE = "have"
    WANT = "want"


class Sport(StrEnum):
    FOOTBALL = "football"
    MENS_BASKETBALL = "mens_basketball"
    WOMENS_BASKETBALL = "womens_basketball"
    VOLLEYBALL = "volleyball"
    BASEBALL = "baseball"


class ListingStatus(IntEnum):
    CLOSED = 0
    OPEN = 1
    MATCHED = 2


# Display names, in the order sports are offered in menus.
SPORT_LABELS: dict[Sport, str] = {
    Sport.FOOTBALL: "Football",
    Sport.MENS_BASKETBALL: "Men's Basketball",
    Sport.VOLLEYBALL: "Volleyball",
    Sport.WOMENS_BASKETBALL: "Women's Basketball",
    Sport.BASEBALL: "Baseball",
}
