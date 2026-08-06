from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from balise_api import attribution
from balise_api.repositories.protocols import NavAidNotFound
from balise_api.s57 import navaid_label
from balise_api.s57.labels import describe_light
from balise_api.schemas.navaids import LightOut, NavAidDetail

#: SEO gold and the P5 persona's whole use case: "what is this red thing in the water?"
_EXPLAINERS: dict[str, str] = {
    "boylat:bâbord": (
        "Bouée latérale de bâbord (balisage IALA région A) : rouge, forme cylindrique. "
        "En entrant dans le chenal, laissez-la sur votre bâbord."
    ),
    "boylat:tribord": (
        "Bouée latérale de tribord (IALA A) : verte, forme conique. En entrant dans le chenal, "
        "laissez-la sur votre tribord."
    ),
    "bcnlat:bâbord": "Balise latérale de bâbord (IALA A), fixe sur le fond : laissez-la à bâbord "
    "en entrant.",
    "bcnlat:tribord": "Balise latérale de tribord (IALA A), fixe sur le fond : laissez-la à "
    "tribord en entrant.",
    "boycar:nord": "Marque cardinale Nord : passez au nord de la marque. Voyant : deux cônes "
    "pointes en haut.",
    "boycar:est": "Marque cardinale Est : passez à l'est de la marque. Voyant : deux cônes bases "
    "opposées.",
    "boycar:sud": "Marque cardinale Sud : passez au sud de la marque. Voyant : deux cônes pointes "
    "en bas.",
    "boycar:ouest": "Marque cardinale Ouest : passez à l'ouest de la marque. Voyant : deux cônes "
    "pointes opposées.",
    "boyisd": "Marque de danger isolé : un danger de petite étendue, eaux saines autour. "
    "Ne passez pas dessus.",
    "boysaw": "Marque d'eaux saines : eau navigable tout autour, souvent l'atterrissage d'un "
    "chenal.",
    "boyspp": "Marque spéciale : signale une zone ou une activité particulière, pas un danger "
    "de navigation.",
    "morfac": "Installation d'amarrage. Une bouée de mouillage (corps-mort) peut être occupable ; "
    "vérifiez toujours l'amarrage avant de vous y fier.",
    "lndmrk": "Amer : point remarquable à terre, utile pour un relèvement ou un alignement.",
}

_DETAIL_SQL = """
SELECT n.id, n.inspire_id, n.s57_class, n.name, n.colour, n.colour_pattern, n.shape, n.topmark,
       n.category, n.light, n.height_m, ST_X(n.geom) AS lon, ST_Y(n.geom) AS lat,
       s.attribution AS source_attribution
FROM nav_aid n
JOIN source s ON s.id = n.source_id
WHERE n.id = :nav_aid_id AND n.active
"""


def explainer(s57_class: str, category: str | None) -> str:
    if category:
        keyed = _EXPLAINERS.get(f"{s57_class}:{category}")
        if keyed:
            return keyed
    generic = _EXPLAINERS.get(s57_class)
    if generic:
        return generic
    return (
        f"{navaid_label(s57_class, category)} — marque du référentiel de balisage. "
        "Reportez-vous aux cartes marines officielles pour son usage."
    )


def _light_out(raw: dict[str, Any] | None) -> LightOut | None:
    described = describe_light(raw)
    if described is None:
        return None
    return LightOut(
        text=described.text,
        character=described.character,
        period_s=described.period_s,
        colour=described.colour,
        range_nm=described.range_nm,
        group=described.group,
        sectors=described.sectors,
    )


async def get_navaid(session: AsyncSession, nav_aid_id: int) -> NavAidDetail:
    row = (await session.execute(text(_DETAIL_SQL), {"nav_aid_id": nav_aid_id})).one_or_none()
    if row is None:
        raise NavAidNotFound(f"nav_aid {nav_aid_id}")
    return NavAidDetail(
        id=f"navaid_{row.id}",
        s57_class=row.s57_class,
        label=navaid_label(row.s57_class, row.category),
        name=row.name,
        colour=row.colour,
        colour_pattern=row.colour_pattern,
        shape=row.shape,
        topmark=row.topmark,
        category=row.category,
        height_m=float(row.height_m) if row.height_m is not None else None,
        light=_light_out(row.light),
        position=[row.lon, row.lat],
        explainer=explainer(row.s57_class, row.category),
        source=row.source_attribution or attribution.SHOM,
        disclaimer=attribution.DISCLAIMER,
    )


async def navaid_ids(session: AsyncSession, limit: int = 5000) -> list[int]:
    rows = await session.execute(
        text("SELECT id FROM nav_aid WHERE active AND name IS NOT NULL ORDER BY id LIMIT :limit"),
        {"limit": limit},
    )
    return [int(value) for value in rows.scalars().all()]
