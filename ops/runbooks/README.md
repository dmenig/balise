# Runbooks

**v1 is the referential** ([docs/06](../../docs/06-availability-strategy.md)), so the situations that
actually happen are about data, not about state. **Data-quality alerts matter more than infra
alerts here**: a wrong buoy position that nobody notices is worse than a 500 that pages someone.

The 🔌 runbooks at the end only apply once availability is switched on (docs/14 M3).

---

## 1. An ingest job failed (SHOM or OSM schema change)

*Symptom:* the nightly job exited non-zero with `UnknownS57Code` or `CountMismatch`. **The previous
data is still live** — that is by design (docs/10 failure policy).

1. Read the offending payload from the log line: the exception carries the layer and the code.
2. Add the new code to `api/src/balise_api/s57/codes.py` with a real French label, or fix the tag
   mapping in `ingest/src/balise_ingest/normalisers/`. Never guess a label — an unlabelled mark is
   what the failure exists to prevent.
3. Add the payload to `ingest/tests/fixtures/` and a golden assertion, so it cannot regress.
4. Re-run the job. If counts moved more than 20 %, verify by hand, then re-run with `--force`.

```bash
uv run balise-ingest shom balisage --bbox=-3.2,47.4,-2.6,47.8   # a small bbox reproduces fast
uv run balise-ingest shom balisage --force                      # only after eyeballing the delta
```

## 2. Wrong data reported by a user (a buoy in the wrong place)

```bash
uv run balise-ingest conflate --explain spot_18421     # why this row looks like it does
```

1. Read the trace: which source won the position, at what distance, under which rule.
2. Add a `pin_position`, `force_split`, `force_merge` or `blacklist` entry to
   `ingest/src/balise_ingest/overrides.yml` **with a `reason`**.
3. Re-run the relevant source, then `--explain` again to confirm.
4. Open a PR: data corrections are reviewable in git, always.
5. If the source itself is wrong, fix it upstream too (an OSM edit, a mail to SHOM/DDTM). That is
   the loop that makes the referential better for everyone.

The moderation queue is the inbox for this:

```sql
SELECT id, category, body, payload, created_at FROM issue WHERE NOT resolved ORDER BY created_at;
```

## 3. Empty map, 200 responses

`ref_version` did not move after an ingest, so the CDN and Redis are serving stale tile ETags.

```bash
uv run balise-admin tiles-flush
curl -s localhost:8000/ready         # ref_version must be present and recent
```

## 4. Traffic spike

```bash
docker compose -f ops/docker-compose.prod.yml up -d --scale api=4
```

1. Check the CDN hit ratio on `/v1/tiles/*` — v1 should sit above 95 %; everything it serves changes
   weekly at most (docs/07).
2. `GET /v1/health/data` to confirm an ingest is not competing for the database.
3. v1 has no websocket, so there is no connection cap to worry about.

## 5. A data-quality alert fired

```bash
uv run balise-audit list-checks
uv run balise-audit run
```

- `harbours_without_phone_and_vhf > 0` → **fix it**: in v1 the phone *is* the availability feature
  (docs/13). Source it from the port's website, or ask them; it is also the opening line of the
  business-development conversation.
- `duplicate_spots_within_10m` above tolerance → conflation tolerance or an upstream duplicate; use
  runbook 2.
- `spots_far_from_field` → a ZMEL polygon or a buoy position is wrong; use runbook 2.

Failures open an issue. They do not page anyone at 3 a.m.

## 6. GDPR erasure request

```bash
uv run balise-admin gdpr erase --email skipper@example.test
```

Deletes the account, anonymises what the contributor sent (the correction survives for the audit
trail, no longer identifiable), and prints the photo keys to purge. A user can do it themselves with
`DELETE /v1/me`. Keep the written trace with the request.

---

## 🔌 v2 runbooks (only once availability is on)

### A partner feed went stale

```bash
curl -s -H "Authorization: Bearer $TOKEN" https://api.balise.fr/v1/feeds/$FEED/health | jq
uv run balise-admin feed disable $FEED     # spots go `unknown`, never stale-green
```

The status worker already does this automatically every two minutes; the manual step is for a feed
that is *sending* but sending nonsense.

### Abuse or report poisoning

```bash
uv run balise-admin observations suppress --contributor 4212   # then recomputes every status
uv run balise-admin observations ban-device <device_hash>
```

Nothing is deleted: observations are tombstoned and the affected statuses are re-derived. The
append-only model (ADR-0003) is what makes this safe.

### Precision below the M3 gate

If the ground-truth audit puts "free" precision under 85 %, **roll back to the null provider**: set
`FEATURE_AVAILABILITY=false` and restart. One line, by design (docs/14 M3) — and shipping nothing
beats shipping a wrong green pin.

---

## Standing checks

| When | Command |
|---|---|
| Nightly | `uv run balise-audit run` — data-quality thresholds (docs/13) |
| After every ingest | `GET /v1/health/data` — per-source counts and last sync |
| Every build | `make seam` — the availability seam has not rotted |
| Weekly | `make tiles-bench` — MVT p95 under 300 ms (ADR-0002) |
| Monthly | Postgres restore drill, documented and timed (docs/12) |
| Once per season per region | **Position ground truth**: a volunteer GPS-tags 20 moorings in a bay; we measure the offset against what we display. Target ≥ 90 % within 25 m (docs/13). This is v1's headline quality metric, and no unit test substitutes for it. |
