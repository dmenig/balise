from __future__ import annotations

from dataclasses import dataclass, replace
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

import yaml

from balise_ingest.records import NormalisedBatch, SpotRecord

DEFAULT_PATH = Path(__file__).with_name("overrides.yml")


@dataclass(frozen=True, slots=True)
class Ref:
    source_id: str
    external_id: str

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Ref:
        return cls(source_id=str(raw["source_id"]), external_id=str(raw["external_id"]))


@dataclass(frozen=True, slots=True)
class Overrides:
    blacklist: frozenset[Ref] = frozenset()
    pins: dict[Ref, tuple[float, float]] = dataclass_field(default_factory=dict)
    merges: dict[Ref, Ref] = dataclass_field(default_factory=dict)
    splits: frozenset[tuple[Ref, Ref]] = frozenset()

    @classmethod
    def load(cls, path: Path | None = None) -> Overrides:
        document = yaml.safe_load((path or DEFAULT_PATH).read_text(encoding="utf-8")) or {}
        pins = {
            Ref.parse(entry): (float(entry["lon"]), float(entry["lat"]))
            for entry in document.get("pin_position") or []
        }
        merges = {
            Ref.parse(entry["absorb"]): Ref.parse(entry["keep"])
            for entry in document.get("force_merge") or []
        }
        splits = {
            (Ref.parse(entry["left"]), Ref.parse(entry["right"]))
            for entry in document.get("force_split") or []
        }
        return cls(
            blacklist=frozenset(Ref.parse(entry) for entry in document.get("blacklist") or []),
            pins=pins,
            merges=merges,
            splits=frozenset(splits) | frozenset((right, left) for left, right in splits),
        )

    def is_blacklisted(self, source_id: str, external_id: str) -> bool:
        return Ref(source_id, external_id) in self.blacklist

    def forced_merge_target(self, source_id: str, external_id: str) -> Ref | None:
        return self.merges.get(Ref(source_id, external_id))

    def is_forced_split(self, left: Ref, right: Ref) -> bool:
        return (left, right) in self.splits

    def apply(self, batch: NormalisedBatch) -> NormalisedBatch:
        spots: list[SpotRecord] = []
        for spot in batch.spots:
            if self.is_blacklisted(spot.source_id, spot.external_id):
                continue
            pin = self.pins.get(Ref(spot.source_id, spot.external_id))
            spots.append(replace(spot, lon=pin[0], lat=pin[1]) if pin else spot)
        nav_aids = tuple(
            nav_aid
            for nav_aid in batch.nav_aids
            if not self.is_blacklisted(nav_aid.source_id, nav_aid.external_id)
        )
        return replace(batch, spots=tuple(spots), nav_aids=nav_aids)
