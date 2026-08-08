# 09 — Frontend & map

## Stack

| Concern | Choice | Why |
|---|---|---|
| Framework | React 18 + TypeScript (strict) | Team-standard, MapLibre bindings mature |
| Build | Vite 5 | Fast, simple PWA plugin |
| Map | **MapLibre GL JS 4** | Vector tiles, free, no Mapbox licence, good mobile perf |
| State | TanStack Query (server state) + Zustand (map/UI state) | No Redux ceremony |
| Styling | Tailwind + a small design-token layer | Marine palette, high-contrast outdoor mode |
| Offline | Workbox service worker + IndexedDB (idb) | Tile + API caching, report queue |
| i18n | `react-i18next`, `fr` default, `en` scaffolded | French product, foreign visiting crews |
| Charts | None in v1 (tide curve is a hand-drawn SVG, ~40 lines) | Avoid a chart lib for one sparkline |
| Prerender | `vite-plugin-ssg`-style prerender of harbour pages | SEO for ~1 500 `/port/{slug}` routes |

## Map layers (z-order, bottom to top)

| # | Layer | Source | Notes |
|---|---|---|---|
| 1 | Base map | OSM vector basemap (self-hosted PMTiles) or raster OSM | Muted "sea chart" style: land beige, sea pale blue |
| 2 | Bathymetry hint | (v2) SHOM depth contours | |
| 3 | Anchorage zones | `spots` MVT, polygons | Hatched fill, restriction icon when `restrn` present |
| 4 | Nav aids | `navaids` MVT | IALA-A symbology, visible from z12; labels z14+ |
| 5 | Harbour markers | `harbours` | Clustered below z11 |
| 6 | Spots | `spots` MVT (+ 🔌 status overlay in v2) | The core layer |
| 7 | Seamark reference overlay (optional toggle) | `tiles.openseamap.org` raster | For users who want the full chart look |
| 8 | User position | Geolocation API | Accuracy circle, heading when available |

### The UI seam (S5)

**v1 renders every spot in the neutral "unknown" style.** The paint expressions are nevertheless
written in their final v2 form, reading `feature-state` and falling back to neutral when unset — so
in v1 they are correct and simply always take the fallback branch
([06 §A/S5](06-availability-strategy.md)).

```ts
// v2 only: join the /status response onto tile features. Nothing calls this in v1.
export function applyStatus(map: Map, payload: StatusPayload): void {
  for (const [id, [state, confidence]] of Object.entries(payload.spots)) {
    map.setFeatureState({source: 'spots', sourceLayer: 'spots', id: Number(id)},
                        {state, confidence})
  }
}

// shipped in v1, unchanged in v2 — v1 always hits the final fallback
'circle-color': [
  'case',
  ['==', ['feature-state','state'], 'free'],     ['case', ['>=',['feature-state','confidence'],0.8], '#1F9D55', '#7BC08F'],
  ['==', ['feature-state','state'], 'occupied'], '#6B7280',
  '#9CA3AF'  // unknown — the only v1 state
]
```

Consequences that are **binding on v1 design work**:

- The pin, the legend, the cluster badge and the list row each need a neutral variant that looks
  intentional, not like a loading state. A map of grey pins must read as "the map", not "broken".
- Cluster badges show the **total** in v1 (`18`) and `free/total` in v2 (`5/18`) — same component,
  different props. Do not build a badge that cannot render a single number.
- No v1 layout may assume a status chip is absent: the spot sheet reserves its slot, so adding it in
  v2 does not reflow the sheet.
- The client data layer exposes `subscribe(bbox, onUpdate)`; the v1 implementation is a no-op
  ([08](08-api-contract.md)). No component knows whether updates are live.
- Keep `status === null` handling in the components from day 1 — it is also the correct v2 rendering
  for any spot nobody has reported, so the branch is never dead code.

## Symbology rules

- **Nav aids use official IALA region A symbology**, not invented icons. A sailor must recognise a
  cardinal mark instantly. Colours and topmark shapes are non-negotiable.
- **Spots use a shape that cannot be confused with a nav aid**: rounded square pins, never buoy
  shapes. Confusing an app pin with a chart symbol is a safety issue.
- **v1**: spots are differentiated by **kind** (buoy / berth / anchorage), not by state — that is the
  only meaningful axis when there is no state. Icon + shape carry the kind; the neutral fill carries
  "availability unknown".
- **v2**: free = filled green, probably-free = green outline on white, occupied = solid grey,
  unknown = hollow grey. Colour is **never** the only channel: the pin carries an icon (✓ / ● / ?)
  for colour-blind users and for glare.
- Cluster badges: total in v1, `free/total` in v2.

## Screens

| Route | Content |
|---|---|
| `/` | Map, geolocated, filter bar, bottom sheet list |
| `/carte?bbox=` | Shareable map state |
| `/port/{slug}` | Harbour page — prerendered, SEO, contacts, fields, live availability, tides |
| `/mouillage/{id}` | Spot sheet |
| `/balise/{id}` | Nav aid explainer (SEO gold: "que signifie une bouée cardinale sud") |
| `/mes-escales` | Local history of viewed/saved spots, offline (v2 adds check-ins) |
| `/contribuer` | How the data works, how to report a correction, how a port can claim its page |
| `/a-propos`, `/cgu`, `/donnees` | Legal, attribution, sources |

## Deck-usable UX rules (non-negotiable)

1. **Touch targets ≥ 56 px.** Wet fingers, gloves, a moving boat.
2. **One-hand reachable.** Primary actions in the bottom third of the screen.
3. **High-contrast outdoor theme by default in daylight**, plus a **red night mode** that never
   emits white light (preserves night vision — real requirement at sea).
4. **Every action must work offline or fail loudly.** No silent spinner over dead 4G: show
   « hors ligne — données du 06/08 à 14:12 » with the cache age.
5. **No modal that can trap a user with no signal.** Everything dismissible.
6. **Distances in nautical miles, depths in metres, wind in knots.** Never km/h. The list row leads
   with the distance from the boat, computed **in the browser** from the tile/API geometry — the
   position is never sent to the server ([04](04-licensing-and-legal.md)). Without it, the row falls
   back to what the referential knows.
7. The disclaimer strip ([04 §3](04-licensing-and-legal.md)) is part of the map chrome, always
   visible, not a dismissible toast. **This applies to the PWA.** The Streamlit shop window puts
   it behind an ⓘ instead — a divergence recorded in [04 §3](04-licensing-and-legal.md).

## Offline strategy

| Asset | Policy |
|---|---|
| App shell | Precache, `StaleWhileRevalidate` |
| Base + nav aid tiles | `CacheFirst`, 30-day expiry, LRU cap 400 MB, **explicit "télécharger cette zone"** button for a 20 NM radius, tapering to 10 NM at z13 and 5 NM at z14 so a pack stays ~350 tiles |
| Spot geometry tiles | `CacheFirst`, 7 days |
| `/status` | `NetworkOnly`; if offline, show last known with a visible age |
| Harbour sheets viewed | `StaleWhileRevalidate`, keep 90 days |
| Corrections created offline | IndexedDB queue → `POST /issues` on reconnect |
| 🔌 Reports created offline (v2) | Same queue, → `POST /reports/batch`, original timestamps preserved |

The offline **queue** ships in v1 for `/issues`, so v2 reuses it rather than inventing it — one more
seam that costs nothing because v1 needs the mechanism anyway.

Test the offline path in CI with a Playwright run under forced `offline` context — the "download
this area then go offline" journey is a first-class test, not a manual check.

## Performance budget

| Metric | Budget |
|---|---|
| JS on first load (gzip) | ≤ 220 kB excluding MapLibre; MapLibre lazy-loaded after shell paint |
| LCP on 4G mid-range Android | ≤ 2.5 s |
| Map interaction FPS with 5 000 visible spots | ≥ 45 fps (clustering below z13) |
| `/status` payload for a 0.5° bbox | ≤ 30 kB gzip |

## Accessibility

WCAG 2.2 AA: contrast ≥ 4.5:1 (verified in both day and night themes), full keyboard navigation of
the list view (the map itself has a list equivalent — the map is never the only way to reach data),
screen-reader labels in French, respects `prefers-reduced-motion`.


---

## The Streamlit shop window

A second, deliberately smaller front end (`streamlit_app.py`, `app/`) over the checked-in Bretagne
extract: read-only, zero backend, deployable on Community Cloud. It is not a second
implementation of the product and it shares no code with `web/`.

What it borrows from this document: the map is the screen, the chrome floats, marks carry their
own S-57 colour, night mode is a first-class control. What it does differently, because Streamlit
re-runs the whole script on every interaction:

| Concern | How |
|---|---|
| Layout | CSS pins each `st.container(key=…)` over a 100dvh deck.gl canvas; only the controls themselves take the pointer, so a panel never puts a dead zone over the map |
| Chrome | One dock at the bottom — search, filter chips that double as the legend, the credits in small print, and the detail card in their place while something is selected — plus ⌖ and day/night. The top of the screen is never covered |
| Detail | Kicker and name, up to three facts as chips, the rest as rows, and the position. An unnamed mark is titled by what it is ("Tourelle bâbord"), never "Sans nom"; no source ids, and lights read `Fl(2)R 6s 2 M` rather than the raw S-57 record |
| Camera | Held in session state; only a search result or ⌖ moves it, so a rerun never snaps the view back |
| Selection | deck.gl returns the picked row's index; only a *change* of pick is an event. There is no close button: the same pick comes back on every rerun, so a sheet closed by a button could not be reopened by tapping the same object. Tapping the map — a pick of nothing — is the close |
| Zones | Filled, never stroked: `PolygonLayer(stroked=True)` adds a PathLayer sublayer that, past a few hundred polygons, silently kills click picking for the whole scene |
| Cost of a tap | ~1 s, of which most is Streamlit re-sending the 0.87 MB spec. Any *change* to the spec adds another ~0.7 s, so the search ring is pinned to the destination rather than following the selection |
| Search | Places and harbours only, never individual marks; a pick moves the camera and leaves the chips alone |
| Screenshots | `shot.py` drives the running app with Playwright and writes `shots/<state>-{desktop,phone}.png` |
