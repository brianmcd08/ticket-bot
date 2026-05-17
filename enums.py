from enum import StrEnum


class ListingType(StrEnum):
    HAVE = "have"
    WANT = "want"


class Sport(StrEnum):
    FOOTBALL = "football"
    MENS_BASKETBALL = "mens_basketball"
    WOMENS_BASKETBALL = "womens_basketball"
    VOLLEYBALL = "volleyball"
