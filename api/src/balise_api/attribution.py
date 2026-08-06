"""Attribution and safety strings. Both are legal obligations, not decoration (docs/04)."""

from __future__ import annotations

SHOM = "Shom, 2026 (Licence Ouverte Etalab 2.0)"
OSM = "© les contributeurs OpenStreetMap (ODbL 1.0)"
OPEN_METEO = "Météo : Open-Meteo (CC-BY 4.0)"
SHOM_TIDES = "Marées : Shom"
DATAGOUV = "data.gouv.fr — DDTM/DREAL (Licence Ouverte Etalab 2.0)"

REFERENTIAL = [SHOM, OSM]
ENVIRONMENT = [SHOM_TIDES, OPEN_METEO]

BLOCK = (
    "Fonds de carte © OpenStreetMap contributors (ODbL) — Amers et balisage : Shom, 2026 "
    "(Licence Ouverte Etalab 2.0) — Mouillages : OpenStreetMap/OpenSeaMap (ODbL) — "
    "Marées : Shom — Météo : Open-Meteo (CC-BY 4.0). Ne pas utiliser pour la navigation."
)

DISCLAIMER = (
    "Aide à la planification. Ne pas utiliser pour la navigation. Les cartes marines "
    "officielles à jour restent obligatoires (division 240)."
)

#: v1 has no availability, so the caveat is about the tackle, not about a report (docs/06 §A/S3).
MOORING_WARNING = (
    "Bouée recensée, pas un amarrage garanti : vérifiez toujours le corps-mort et sa ligne "
    "de mouillage."
)

#: 🔌 v2 wording, used only once a status is actually attached to the spot.
MOORING_STATUS_WARNING = (
    "Disponibilité rapportée, pas un état de l'amarrage : vérifiez toujours le corps-mort "
    "et sa ligne de mouillage."
)

DEPTH_WARNING = (
    "Profondeur dérivée de la sonde cartographiée et d'une prédiction de marée : estimation, "
    "jamais une garantie."
)
