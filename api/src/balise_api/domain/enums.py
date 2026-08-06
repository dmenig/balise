from __future__ import annotations

from enum import StrEnum


class SpotKind(StrEnum):
    MOORING_BUOY = "mooring_buoy"
    BERTH = "berth"
    ANCHORAGE = "anchorage"
    PILE = "pile"
    QUAY = "quay"


class SpotState(StrEnum):
    FREE = "free"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    OUT_OF_SERVICE = "out_of_service"
    UNKNOWN = "unknown"


class SourceKind(StrEnum):
    PORT_FEED = "port_feed"
    SENSOR = "sensor"
    COMMUNITY = "community"
    AIS = "ais"
    MANUAL = "manual"
    IMPORT = "import"


class ReportKind(StrEnum):
    """What a community/machine observation actually claims — drives decay half-life."""

    CHECK_IN = "check_in"
    CHECK_OUT = "check_out"
    CORRECTION = "correction"
    IMPLICIT_CHECKOUT = "implicit_checkout"
    FEED_SNAPSHOT = "feed_snapshot"
    FEED_DELTA = "feed_delta"
    AIS_AT_REST = "ais_at_rest"
    IMPORT = "import"


class ConfidenceBucket(StrEnum):
    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    UNCERTAIN = "uncertain"
    UNKNOWN = "unknown"


TIER_BY_SOURCE: dict[SourceKind, int] = {
    SourceKind.PORT_FEED: 1,
    SourceKind.SENSOR: 1,
    SourceKind.MANUAL: 1,
    SourceKind.COMMUNITY: 2,
    SourceKind.AIS: 3,
    SourceKind.IMPORT: 4,
}
