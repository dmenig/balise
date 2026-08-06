# 02 — Personas & user stories

## Personas

**P1 — Le plaisancier en escale (primary).** Coastal cruiser, 8–12 m sailboat, 2–6 h legs, decides
tonight's stop around 15:00 while underway. Phone on deck, gloves, glare, one hand. Cares about:
free spot, depth at low tide, shelter tonight, price, how late the capitainerie answers.

**P2 — Le local au corps-mort.** Has a permanent mooring in a ZMEL, knows everyone. Cares about:
is someone on my buoy, is the buoy in good condition, when is the field inspected. **He is our best
data contributor** — high-frequency, high-accuracy reports for a small area.

**P3 — Le maître de port / agent de capitainerie.** Manages 200–1500 berths. Cares about: filling
visitor berths, not being called 40 times a day, not entering data twice. **Will only adopt if we
consume his existing software, never if we ask him to type into ours.**

**P4 — Le loueur / skipper pro.** Charter base, plans 12 itineraries a week. Cares about: bulk view,
reliability, export.

**P5 — Le navigateur occasionnel / kayak-paddle-annexe.** Uses the app as "what is this red thing in
the water?" — pure referential reading. Cheap to serve, drives SEO and top-of-funnel.

## User stories

Priority: **M** must (v1), **S** should (v1), **C** could (v1), **V2** deferred with availability
([06](06-availability-strategy.md), [14](14-roadmap.md) M3).

### Discovery & map

- **M** As P1, I open the app and see my position and every stopping place within 10 NM, so I can
  pick one without knowing the area.
- **M** As P5, I tap any mark on the map and read what it means in plain French ("bouée latérale
  bâbord, feu rouge à éclats 4 s"), so I understand the chart.
- **V2** As P1, I filter to "places libres uniquement" and the map keeps only spots whose status is
  free with confidence ≥ medium.
- **M** As P1, I filter by "tirant d'eau ≥ 1.8 m" and "longueur ≤ 11 m" so I only see spots my boat
  fits.
- **S** As P1, I filter "abrité de vent de secteur NW" and get spots whose exposure excludes NW.
- **S** As P4, I search a port by name and get its sheet directly.

### Spot detail

- **M** As P1, I see for a mooring field: number of buoys, operator, price/night, VHF channel, phone,
  and **a one-tap call button to the capitainerie** — in v1 that call *is* the availability check.
- **M** As P1, I see the depth at the spot and the depth at tonight's low water (computed from the
  tide prediction), so I do not run aground at 03:00.
- **M** As P1, I see max LOA / draught / beam and the exposed wind sectors.
- **C** As P1, I see a 48 h wind/swell strip for that spot.
- **V2** As P1, I see how many buoys are free right now, with source and age.
- **V2** As P1, I see the last 3 community comments and photos.

### Contribution — v1 corrects the *referential*, not the state

- **M** As P2, I report that a buoy is in the wrong place, has been removed, or that the price is
  wrong; it reaches a moderation queue and becomes a reviewable change ([10](10-ingestion-pipelines.md)).
- **S** As P2, I report a defect on a buoy (mooring line worn, buoy adrift) and the operator sees it.
- **V2** As P1/P2, I press **"J'occupe cette bouée"** on arrival and **"Je libère"** on departure;
  one tap, works offline (queued).
- **V2** As P1, I press "C'était occupé" when I find a spot taken, correcting a wrong "free".
- **V2** As P2, I "adopt" a mooring field and get a weekly digest of its reported state.

### Harbour side

- **M** As P3, I claim my harbour page and correct prices, contacts, opening hours. **This is the v1
  relationship with capitaineries** — and the one that later makes a feed possible.
- **V2** As P3, my berth-management software pushes occupancy through one HTTP endpoint and my
  visitor berths appear as free with the "port" source badge.
- **V2** As P3, I see a dashboard of arrivals inferred by check-ins.

### Trust & safety

- **M** As any user, I see a permanent, non-dismissable notice that the app is not a navigation aid.
- **M** As any user, I can see for each object where the data came from and when it was last updated.
- **S** As a moderator, I can accept/reject a data correction and see it land in `overrides.yml`.
- **V2** As any user, every status shows *who said so* and *when* ("Port — il y a 4 min").
- **V2** As a moderator, I can suppress a user's reports and recompute affected statuses.

## Key UX flow: the 15-second escale decision

**v1**
```
Open app → geolocated map, "18 mouillages à moins de 5 NM"
        → tap cluster → list sorted by (distance, fits my boat, price)
        → tap spot → depth at LW tonight, shelter, price, "Appeler la capitainerie" (VHF 9 / tel)
        → "Y aller" (opens external nav app with waypoint)
```

**v2, once availability is wired** — same flow, two words change:
```
… "12 places libres à moins de 5 NM"
        → list sorted by (distance, confidence, price)
        → … → on arrival "J'occupe"
```

Everything else in the product is subordinate to this flow. Note that the v1 and v2 flows are the
*same screens* — that is the UI seam ([06 §A/S5](06-availability-strategy.md)) stated as a user
journey.
