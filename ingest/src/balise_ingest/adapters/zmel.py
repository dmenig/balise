"""ZMEL adapters, one per département (docs/10).

Reality check from docs/03 §C: some datasets give polygons with a buoy count (→ one `field` with
`capacity`), some give one point per buoy (→ `spot` rows), some give only a site name (→ a field
with unknown capacity). All three are supported; nothing is invented — a field of 60 buoys we
cannot enumerate stays one field, never 60 fake spots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from balise_api.domain.enums import SpotKind

from balise_ingest.records import FieldRecord, RawFeature, SpotRecord
from balise_ingest.slugs import slugify

_NAME_KEYS = ("nom", "name", "libelle", "lib_zmel", "site", "nom_site", "zone", "denomination")
_CAPACITY_KEYS = (
    "nb_bouees",
    "nb_bouee",
    "nb_mouillages",
    "nb_postes",
    "capacite",
    "nombre",
    "nb_places",
    "nb_anneaux",
)
_VISITOR_KEYS = ("nb_visiteurs", "nb_passage", "places_visiteurs", "nb_escale")
_OPERATOR_KEYS = ("gestionnaire", "operateur", "commune", "beneficiaire", "titulaire")
_DEPTH_KEYS = ("profondeur", "prof_min", "sonde")


class ZmelAdapter(Protocol):
    dept: str
    dataset_slug: str

    def to_fields(self, raw: RawFeature) -> list[FieldRecord]: ...

    def to_spots(self, raw: RawFeature) -> list[SpotRecord]: ...


def _first(properties: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    lowered = {str(key).lower(): value for key, value in properties.items()}
    for key in keys:
        value = lowered.get(key)
        if value not in (None, "", "NULL"):
            return value
    return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "")
    return int(float(text)) if text.replace(".", "", 1).isdigit() else None


@dataclass(frozen=True, slots=True)
class GenericZmelAdapter:
    """Attribute-alias driven. A département with an exotic schema gets extra aliases here."""

    dept: str
    dataset_slug: str
    name_keys: tuple[str, ...] = _NAME_KEYS
    capacity_keys: tuple[str, ...] = _CAPACITY_KEYS
    extra_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def source_id(self) -> str:
        return f"zmel.{self.dept}"

    def _keys(self, logical: str, default: tuple[str, ...]) -> tuple[str, ...]:
        return self.extra_aliases.get(logical, ()) + default

    def to_fields(self, raw: RawFeature) -> list[FieldRecord]:
        properties = raw.properties
        geometry = raw.geometry
        if geometry is not None and geometry["type"] == "Point":
            return []
        name = _first(properties, self._keys("name", self.name_keys))
        return [
            FieldRecord(
                external_id=raw.external_id,
                source_id=self.source_id,
                kind=SpotKind.MOORING_BUOY,
                name=str(name) if name else f"ZMEL {self.dept} {raw.external_id}",
                capacity=_as_int(_first(properties, self._keys("capacity", self.capacity_keys))),
                visitor_capacity=_as_int(_first(properties, self._keys("visitor", _VISITOR_KEYS))),
                operator=str(_first(properties, self._keys("operator", _OPERATOR_KEYS)) or "")
                or None,
                area_geojson=geometry,
            )
        ]

    def to_spots(self, raw: RawFeature) -> list[SpotRecord]:
        geometry = raw.geometry
        if geometry is None or geometry["type"] != "Point":
            return []
        properties = raw.properties
        lon, lat = (float(value) for value in geometry["coordinates"][:2])
        code = _first(properties, ("num", "numero", "num_bouee", "code", "ref", *self.name_keys))
        depth = _first(properties, self._keys("depth", _DEPTH_KEYS))
        return [
            SpotRecord(
                external_id=raw.external_id,
                source_id=self.source_id,
                kind=SpotKind.MOORING_BUOY,
                lon=lon,
                lat=lat,
                code=str(code) if code else None,
                depth_m=None if depth is None else _decimal(depth),
                visitor=bool(_first(properties, _VISITOR_KEYS)),
                attrs_provenance={"position": self.source_id, "kind": self.source_id},
            )
        ]

    def slug_for(self, name: str) -> str:
        return slugify(f"zmel-{self.dept}-{name}")


def _decimal(value: Any) -> Any:
    from decimal import Decimal, InvalidOperation

    try:
        return Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        return None


#: The five densest départements first (docs/14 M1).
REGISTRY: dict[str, GenericZmelAdapter] = {
    "56": GenericZmelAdapter(
        dept="56",
        dataset_slug="zones-de-mouillage-et-dequipements-legers-zmel-departement-du-morbihan-1",
    ),
    "29": GenericZmelAdapter(
        dept="29",
        dataset_slug="zones-de-mouillages-et-dequipements-legers-zmel-du-finistere",
    ),
    "22": GenericZmelAdapter(
        dept="22",
        dataset_slug="zones-de-mouillages-et-dequipements-legers-zmel-des-cotes-darmor",
    ),
    "17": GenericZmelAdapter(
        dept="17",
        dataset_slug="zones-de-mouillages-et-dequipements-legers-zmel-en-charente-maritime",
    ),
    "83": GenericZmelAdapter(
        dept="83",
        dataset_slug="zones-de-mouillages-et-dequipements-legers-zmel-du-var",
    ),
}


def adapter_for(dept: str) -> GenericZmelAdapter:
    adapter = REGISTRY.get(dept)
    if adapter is None:
        raise KeyError(
            f"aucun adaptateur ZMEL pour le département {dept}; "
            f"disponibles: {', '.join(sorted(REGISTRY))}"
        )
    return adapter
