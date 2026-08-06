# 04 — Licensing, legal & safety

Not legal advice; this is the engineering-facing summary of constraints that shape the code.
Have a lawyer review before public launch (item in [14](14-roadmap.md) M3).

## 1. Incoming data licences

| Source | Licence | Obligation on us |
|---|---|---|
| SHOM (balisage, ports, réglementation, marées) | **Licence Ouverte / Etalab 2.0** | Mention source + date: `Shom, 2026`. Free reuse, including commercial, including derivatives. |
| OpenStreetMap / OpenSeaMap | **ODbL 1.0** | Attribution *and* **share-alike on Derivative Databases**. See §2. |
| data.gouv.fr datasets (ZMEL, ports, carénage) | Etalab 2.0 (verify per dataset — a few are ODbL) | Attribution |
| Open-Meteo | CC-BY 4.0 | Attribution |
| SHOM tide API | Specific ToS ⚠️ | **Confirm redistribution/caching rights before shipping.** If caching predictions server-side is not allowed, call per-request and degrade offline. |
| OpenSeaMap icons | CC-BY-SA | Attribution + share-alike on the icon set |

## 2. The ODbL question (design-forcing)

ODbL share-alike applies to a **Derivative Database**, not to a "Collective Database" that merely
sits next to OSM data. Our architecture must make the distinction structural, not accidental.

**Rules for the codebase:**

1. Every row carries `source_id` and `source_licence`. No exceptions.
2. Tables are physically partitioned by provenance: OSM-derived rows in `osm_*` staging, SHOM-derived
   in `shom_*`, our own observations in `obs_*`. The public `spot` table is a *view/conflation* that
   records, per attribute, which source it came from (`attrs_provenance jsonb`).
3. **Availability observations (Layer B) are our own data, produced independently.** They must never
   be stored inside an OSM-derived table, or we risk having to publish them under ODbL.
4. We publish, quarterly, an ODbL extract of the OSM-derived part of the referential
   (`/opendata/referential-osm.geojson`), which discharges share-alike cleanly and buys goodwill.
5. Never import Navily, port websites' content, or any scraped commercial guide. Copy-paste of a
   competitor's mooring descriptions is both a licence breach and a lawsuit.
6. Contributions we receive from users are licensed to us under CC-BY-SA 4.0 + a licence to
   sublicense (stated in the Terms), so we can push corrections back to OSM.

## 3. Safety and liability — the biggest legal exposure

We display depths, moorings and "free" statuses. A sailor who runs aground or picks up a broken
mooring will look for someone to blame.

**Mandatory product measures:**

- Permanent, always-visible banner: **« Aide à la planification. Ne pas utiliser pour la
  navigation. Les cartes marines officielles à jour restent obligatoires (division 240). »**
- One-time blocking acceptance of the disclaimer at first use, versioned and logged.
- Never display a depth without saying it is derived and approximate; never display "safe".
- Never state that a mooring is *sound* — only that it is *reported free/occupied*. Mooring
  condition is the operator's responsibility; add "vérifiez toujours l'amarrage" on every mooring
  sheet.
- Statuses always carry source + age. No naked green dot.
- Do not reproduce official SHOM raster charts unless we buy the licence.
- CGU with a liability limitation clause; professional liability insurance (RC pro) before launch.

## 4. GDPR / RGPD

We process **geolocation of individuals** — sensitive by nature under CNIL guidance.

| Data | Basis | Retention | Measure |
|---|---|---|---|
| Device position (map centring) | Consent, browser prompt | **Never stored server-side** | Computed client-side only |
| Check-in / check-out | Legitimate interest + consent | 12 months, then aggregated | Position snapped to the spot; raw GPS discarded |
| Account (email) | Contract | Until deletion + 30 d | Magic-link auth, no password |
| Device id (anonymous contributors) | Legitimate interest (anti-abuse) | 6 months rolling | Salted hash, salt rotated |
| Photos | Consent | Until deletion | EXIF (incl. GPS) stripped on upload |
| Logs | Legitimate interest | 30 days | IP truncated to /24 |

- Register of processing activities, privacy policy in French, DPO contact.
- Data hosted in the EU ([12](12-deployment-and-ops.md)).
- Self-service export + deletion endpoints from day one; cheaper than retrofitting.
- Never publish a trace of an identifiable boat's movements — a public "who is moored where" is both
  a GDPR problem and a burglary tool. Publish only aggregate occupancy.

## 5. Contracts with harbours

For every partner feed ([06](06-availability-strategy.md)), a one-page agreement covering: what data
they send, that they own it and may share it, our licence to display it, no warranty of accuracy on
either side, termination, and logo/attribution use. Template to draft in M2.

## 6. Naming & trademark

Check **Balise** availability at INPI (classes 9, 39, 42) and the `.fr` domain before any public
communication. Avoid names that imply official status (`Shom-*`, `Marine-*`, `Port-*officiel`) —
SHOM's marks are protected and implying official endorsement is a real risk.
