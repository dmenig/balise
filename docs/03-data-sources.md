# 03 — Data sources

Every endpoint marked ✅ was called successfully on 2026-08-06 from a plain shell, **no API key**.
Counts are real, taken from those calls.

---

## A. Navigation marks — SHOM (authoritative, national)

**Product:** *Balisage maritime* (BDML). Fixed and floating aids to navigation over the whole French
EEZ, metropolitan + overseas. Modelled on IHO **S-57** object/attribute catalogue.

- Service: `https://services.data.shom.fr/INSPIRE/wfs` ✅ (WFS 2.0.0, `outputFormat=application/json`,
  `srsName=EPSG:4326`)
- Also available: WMS/WMTS `https://services.data.shom.fr/INSPIRE/wmts`, and file downloads
  (Shapefile, GeoPackage, GML INSPIRE) from `diffusion.shom.fr`.
- Licence: **Etalab Open Licence v2.0**. Attribution string: `Shom, 2026`.

### Layers we ingest (`BALISAGE_BDD_WFS:*`)

| typeName | S-57 object | Meaning | Use |
|---|---|---|---|
| `bcnlat` | Beacon, lateral | Balise latérale | nav_aid |
| `bcncar` | Beacon, cardinal | Balise cardinale | nav_aid |
| `bcnisd` | Beacon, isolated danger | Danger isolé | nav_aid |
| `bcnspp` | Beacon, special purpose | Balise spéciale | nav_aid |
| `boylat` | Buoy, lateral | Bouée latérale | nav_aid |
| `boycar` | Buoy, cardinal | Bouée cardinale | nav_aid |
| `boyisd` | Buoy, isolated danger | — | nav_aid |
| `boysaw` | Buoy, safe water | Eaux saines | nav_aid |
| `boyspp` | Buoy, special purpose | Bouée spéciale | nav_aid |
| `boyinb` | Buoy, installation | — | nav_aid |
| `lights` | Light | Feux (attached to a mark by id) | nav_aid attribute |
| `topmar` | Topmark | Voyant | nav_aid attribute |
| `daymar` | Daymark | — | nav_aid attribute |
| `lndmrk` | Landmark | Amer | nav_aid |
| `fogsig` | Fog signal | — | nav_aid attribute |
| **`morfac`** | **Mooring/warping facility** | **Includes mooring buoys** | **spot candidate** |

Full layer list also contains `aisatn`, `radsta`, `rdosta`, `rtpbcn`, `pilpnt`, `forstc`, `pylons`,
`newobj`, `ofsplf`, `siltnk`, `sistat`, `sistaw`, `vegatn`.

### Verified sample — `morfac`

```bash
curl -s "https://services.data.shom.fr/INSPIRE/wfs?service=WFS&version=2.0.0\
&request=GetFeature&typeNames=BALISAGE_BDD_WFS:morfac&count=2\
&outputFormat=application/json&srsName=EPSG:4326"
```

```json
{"type":"Feature","id":"morfac.1",
 "geometry":{"type":"Point","coordinates":[-1.0353404,45.5319257]},
 "properties":{"inspireid":"FR000001090900001","posacc":0.4,"objnam":null,"numald":"3300241",
   "catmor":1,"colour":"2,1","colpat":"1","height":8,"convis":2,
   "lights":"FR000004855800001,FR000004855900001,..."}}
```

`numberMatched` = **1 394** nationally. `catmor` is the S-57 mooring category:
`1` dolphin, `2` deviation dolphin, `3` bollard, `4` tie-up wall, `5` post/pile, `6` chain/wire,
**`7` mooring buoy**. ⚠️ Only charted moorings are present — SHOM is *not* a mooring inventory.
It gives us the big `coffres` and port structures, not the 40 buoys of a small ZMEL.

### Other useful SHOM layers

| typeName | Content | Verified |
|---|---|---|
| `REGLEMENTATION_NAVIGATION_BDD_WFS:achare_point` / `achare_polygon` | **Anchorage areas** with `catach`, `restrn`, and bilingual `inform`/`ninfom` notes (e.g. protected biocenosis → anchor on sand only) | ✅ 790 points |
| `INFORMATIONS_PORTUAIRES_BDD_WFS:hrbfac_point` / `_polygon` | Harbour facilities (marina, fishing, ferry…) | ✅ |
| `INFORMATIONS_PORTUAIRES_BDD_WFS:berths_point` | Charted berths | ✅ |
| `INFORMATIONS_PORTUAIRES_BDD_WFS:hrbare_polygon` | Harbour areas | ✅ |
| `INFORMATIONS_PORTUAIRES_BDD_WFS:smcfac_point` | Small craft facilities (water, fuel, slip) | ✅ |
| `DAM_LIMIT_CAT_NAVIGATION_WFS:categorie*_lines_3857` | Navigation category limits (2/3/4/5 miles) — needed for regulatory equipment hints | ✅ |
| `SPM_PORTS_WFS:liste_ports_spm_h2m` | Tide reference ports list (join key for the tide API) | ✅ |
| `DELMAR_BDD_WFS:*` | Baselines, territorial sea, EEZ | ✅ |
| `CABLES_BDD_WFS:cblsub_lv` | Submarine cables — **anchoring prohibited zones**, safety-relevant | ✅ |

### Paging

WFS 2.0 paging with `count` + `startIndex`. Ingest job pages 1 000 features at a time and stops when
`numberReturned < count`. See [10](10-ingestion-pipelines.md).

---

## B. Moorings, marinas, pontoons — OpenStreetMap / OpenSeaMap

The only source with real *mooring buoy* density. Tagging follows the OpenSeaMap seamark scheme.

- Query API: `https://overpass-api.de/api/interpreter` ✅ (be polite: use a self-hosted Overpass or
  the `.osm.pbf` extracts for bulk, Overpass only for deltas)
- Bulk: Geofabrik `europe/france-latest.osm.pbf`, daily.
- Rendered overlay tiles: `https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png` (raster, transparent).
- Licence: **ODbL 1.0** — see [04](04-licensing-and-legal.md), it constrains what we may publish.

### Counts over the France bbox `(41.0,-5.5,51.5,10.0)` ✅ 2026-08-06

| Overpass filter | Count |
|---|---|
| `node["seamark:type"="mooring"]` | **14 754** |
| `node["seamark:type"~"^buoy_"]` | 8 707 |
| `node["seamark:type"~"^beacon_"]` | 7 493 |

(The bbox spills into neighbouring waters; clip to the French EEZ polygon from `DELMAR_BDD_WFS`.)

### Tags we map

| OSM tag | Maps to |
|---|---|
| `seamark:type=mooring` + `seamark:mooring:category=buoy` | `spot.kind=mooring_buoy` |
| `seamark:mooring:category=pile|bollard|dolphin` | `spot.kind` accordingly |
| `leisure=marina` (+ `name`, `phone`, `website`, `seamark:harbour:category=marina`) | `harbour` |
| `man_made=pier` / `floating=yes` / `seamark:type=berth` | `field` (pontoon) |
| `seamark:type=anchorage` / `seamark:anchorage:category` | `spot.kind=anchorage` |
| `seamark:buoy_lateral:*`, `seamark:beacon_cardinal:*`, `seamark:light:*` | `nav_aid` (fallback where SHOM is absent, e.g. inland waters) |
| `capacity`, `maxdraft`, `maxlength`, `fee`, `operator`, `vhf_channel` | `spot`/`harbour` attributes |

**Rule:** where SHOM and OSM describe the same nav aid, SHOM wins. Where they describe the same
mooring, OSM usually has it and SHOM does not — keep both linked (see conflation, [10](10-ingestion-pipelines.md)).

---

## C. Ports, ZMEL, administrative data — data.gouv.fr / IGN

| Dataset | Publisher | Content | Licence |
|---|---|---|---|
| *Ports — Espace maritime français* | IFREMER / SHOM / SANDRE | National reference of maritime and fluvio-maritime ports | Etalab |
| *Zones de mouillage et d'équipements légers (ZMEL)* — per département (Morbihan, Charente-Maritime, Manche, Vendée…) | DDTM / DREAL | **The authorised organised mooring fields — polygons + often buoy counts** | Etalab |
| *Aires de carénage dans les ports de plaisance, zones de mouillages…* | CEREMA/DDTM | Site inventory with facilities | Etalab |
| *Tracés géométriques des ports du système ERS* | DPMA | Port geometries | Etalab |
| IGN BD TOPO / Admin Express | IGN | Communes, coastline, for geocoding & SEO pages | Etalab |
| BAN (Base Adresse Nationale) | — | Address geocoding of capitaineries | Etalab |

⚠️ ZMEL datasets are **departmental and heterogeneous** (some polygons, some points, varying
attributes, varying vintage). Budget real effort for a per-département adapter. This is the main
source of *how many buoys exist in a field* — a v1 referential attribute (`field.capacity`), and
later the denominator for availability.

---

## D. Tides

| Source | What | Notes |
|---|---|---|
| **SHOM API (SPM / SAPM)** — `diffusion.shom.fr/api-shom.html` | Tide predictions per port (SPM) and at any point (SAPM), heights, HW/LW times, coefficients, 4-day free tier | ⚠️ registration + terms to confirm before relying on it; join key = `SPM_PORTS_WFS:liste_ports_spm_h2m` |
| maree.shom.fr | Free 10-day predictions, human portal | Not an API; do not scrape |
| Third-party REST wrappers (`api-maree.fr`, `tide-data.com`) | SHOM-derived REST | Fallback only; verify their right to redistribute |
| Harmonic computation in-house (`pytides`-style, constituents from SHOM/IHO) | Full control, offline-capable | Constituent data licensing to check |

**Decision:** start with the SHOM API for the ~150 reference ports; cache predictions 7 days ahead in
our DB so the frontend never calls SHOM directly and offline works. Depth-at-low-water is computed
as `charted_depth + predicted_height - chart_datum_offset`, and displayed as an estimate only.

## E. Weather & sea state

| Source | Use | Licence/cost |
|---|---|---|
| **Open-Meteo Marine API** (`marine-api.open-meteo.com`) | Wave height/period/direction, hourly, free, no key | CC-BY-4.0, generous free tier |
| **Open-Meteo Forecast API** | Wind speed/direction/gusts | idem |
| Météo-France open data (AROME/ARPEGE via `meteo.data.gouv.fr`) | Higher-fidelity national model | Etalab, heavier to operate (GRIB) |
| Windy / Meteoblue widgets | Embeddable maps | Commercial ToS, avoid in v1 |

**Decision:** Open-Meteo in v1 (one call per harbour, cached 1 h). Météo-France GRIB is a v2
optimisation, not a v1 dependency.

## F. Availability (Layer B) — there is no public source · **not used in v1**

> This section is why availability is out of v1 ([ADR-0005](adr/0005-availability-as-a-plugin.md)).
> Kept here because it is the research that justifies the decision, and the shopping list for M3.

| Candidate | Reality |
|---|---|
| **Harbour management software / IoT berth sensors** (e.g. **Nauticspot** ShellSpot pontoon sensors, OceanSpot connected mooring buoy; several ports equipped incl. Ajaccio Charles-Ornano ~1 007 berths) | Occupancy exists **inside the capitainerie's software**. No public API found. → **partnership + a feed spec we publish**, see [06](06-availability-strategy.md) |
| Navily / port booking platforms | Competitors, closed |
| Port websites | A handful publish live "places disponibles" widgets — scrapable per-port, brittle, needs written consent |
| **AIS** — `aisstream.io` (free WebSocket, global, API key by registration), AISHub, local RTL-SDR receivers | Gives vessel-at-rest positions → occupancy *hints* only. Most pleasure boats < 15 m carry no AIS, or class B at best |
| **Community check-in/out** | The only source we fully control. Cold-start problem, solvable in high-density spots |

This table is the evidence behind the v1 scope cut: **every row is a months-long partnership or a
weak proxy, and none of it can be fetched.** See [06](06-availability-strategy.md) for the seams that
keep it addable, and [15 R1](15-risks-and-open-questions.md) for the residual risk.

## G. Assets

| Need | Source |
|---|---|
| Base map tiles | OSM raster via a tile provider, or self-hosted vector (Protomaps/OpenMapTiles basemap in PMTiles) |
| Seamark symbols | OpenSeaMap icon set (CC-BY-SA), or redraw from IALA region A spec |
| Bathymetry / depth contours | SHOM `MNT` products (licence varies, some non-free) — v2 |
| Photos | Community uploads only (rights cleared at upload) |

## Attribution block (must appear in the UI)

```
Fonds de carte © OpenStreetMap contributors (ODbL) — Amers et balisage : Shom, 2026 (Licence
Ouverte Etalab 2.0) — Mouillages : OpenStreetMap/OpenSeaMap (ODbL) — Marées : Shom —
Météo : Open-Meteo (CC-BY 4.0). Ne pas utiliser pour la navigation.
```

## Sources

- [Balisage maritime — SHOM](https://diffusion.shom.fr/donnees/base-de-donnees-maritimes-et-littorales/balisage_maritime.html)
- [SHOM WFS help](https://services.data.shom.fr/support/en/geoservices/wfs) · [WMTS GetCapabilities](https://services.data.shom.fr/INSPIRE/wmts?request=GetCapabilities&service=WMTS)
- [API Shom (marées)](https://diffusion.shom.fr/api-shom.html) · [maree.shom.fr](https://maree.shom.fr/)
- [OpenSeaMap/Buoys — OSM wiki](https://wiki.openstreetmap.org/wiki/OpenSeaMap/Buoys) · [Seamarks](https://wiki.openstreetmap.org/wiki/Seamarks) · [Marine navigation](https://wiki.openstreetmap.org/wiki/Marine_navigation)
- [Ports — Espace maritime français (data.gouv.fr)](https://www.data.gouv.fr/datasets/ports-espace-maritime-francais) · [ZMEL Morbihan](https://www.data.gouv.fr/datasets/zones-de-mouillage-et-dequipements-legers-zmel-departement-du-morbihan-1) · [ZMEL Charente-Maritime](https://www.data.gouv.fr/datasets/zones-de-mouillages-et-dequipements-legers-zmel-en-charente-maritime)
- [Nauticspot ShellSpot](https://www.nauticspot.com/fr/produits/shellspot) · [OceanSpot](https://www.nauticspot.com/fr/produits/oceanspot) · [Port d'Ajaccio](https://www.nauticspot.com/fr/portfolio/port-ajaccio)
- [aisstream.io documentation](https://aisstream.io/documentation)
- [Navily (App Store)](https://apps.apple.com/fr/app/navily/id881103205)
