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
