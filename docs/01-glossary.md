# 01 — Glossary

Read this before anything else: the word **balise** is ambiguous in the original brief, and the
ambiguity decides the product.

## The disambiguation that matters

| Term (fr) | English | Can it be "free/occupied"? | Source |
|---|---|---|---|
| **Balise** | Beacon — fixed mark on a rock/seabed (`bcnlat`, `bcncar`…) | **No.** It marks a danger. | SHOM |
| **Bouée** | Buoy — floating navigation mark (`boylat`, `boycar`…) | **No.** | SHOM |
| **Bouée de mouillage / corps-mort** | Mooring buoy, attached to a dead-weight | **Yes** — this is the "city bike" object | OSM + ports |
| **Anneau / place de port** | Berth / ring in a marina | **Yes** | Capitaineries |
| **Place visiteur / escale** | Visitor berth, rented by the night | **Yes** | Capitaineries |
| **Mouillage forain** | Free-form anchoring on your own anchor | Not a discrete object — capacity of a zone | SHOM `achare` |
| **ZMEL** | *Zone de Mouillage et d'Équipements Légers* — authorised organised mooring field | Zone containing N mooring buoys | DDTM / data.gouv |
| **Amer** | Landmark used for bearings (`lndmrk`) | No | SHOM |
| **Capitainerie** | Harbour master's office | — | — |
| **Ponton** | Pontoon / floating dock | Contains berths | OSM |
| **Panne** | A single pontoon finger/row in a marina | Groups berths | Capitaineries |
| **Coffre** | Heavy mooring buoy (often for large yachts) | Yes | Ports |
| **Perche** | Withy / pole mark | No | SHOM |
| **Cardinale / latérale / danger isolé / eaux saines / spéciale** | Cardinal / lateral / isolated danger / safe water / special mark | No | SHOM |
| **Feu** | Light (a separate S-57 object attached to a mark) | No | SHOM `lights` |
| **Tirant d'eau** | Draught | — | — |
| **Marnage** | Tidal range | — | — |
| **Coefficient de marée** | French tidal coefficient (20–120) | — | SHOM |
| **Instructions Nautiques** | Official sailing directions | — | SHOM |

## Product consequence

The app therefore has **two object families**, deliberately kept separate everywhere in the code:

- `nav_aid` — the *référentiel de balisage*: beacons, buoys, lights, landmarks. **Read-only,
  authoritative, never has a status.** It is the "map".
- `spot` — a bookable/occupiable place: mooring buoy, visitor berth, anchorage zone. **This is what
  would carry availability.** It is the "bikes". In v1 a spot has no state — `status` is always
  `null` ([06](06-availability-strategy.md)) — but the distinction from `nav_aid` still holds,
  because it is what makes the spot filterable by boat size, priced, and operated by someone.

Never merge these two tables. A user asking "where is a free balise?" means "where is a free
*corps-mort*". The UI must use the sailor's word (`bouée de mouillage`, `place visiteur`) and never
the schema word.

## Internal vocabulary (code)

| Code term | Meaning |
|---|---|
| `spot` | Any occupiable unit (buoy, berth, or a slot in an anchorage zone) |
| `field` | A group of spots under one operator (a ZMEL, a pontoon, a marina) |
| `harbour` | A port / marina entity, groups fields |
| `observation` | One raw signal about a spot's state, from any source |
| `status` | The current derived state of a spot + confidence |
| `feed` | A partner-operated source of observations |
| `S-57` | IHO vector chart standard; SHOM attribute names come from it (`catmor`, `boyshp`…) |
