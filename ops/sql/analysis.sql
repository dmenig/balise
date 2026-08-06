-- Ad-hoc analysis queries (docs/11 `ops/sql/`). Read-only, safe to paste into psql.

-- 1. Referential coverage per source and per family — the docs/00 success criteria.
SELECT s.id AS source,
       s.licence,
       (SELECT count(*) FROM nav_aid n WHERE n.source_id = s.id AND n.active) AS nav_aids,
       (SELECT count(*) FROM spot sp WHERE sp.source_id = s.id AND sp.active) AS spots,
       (SELECT count(*) FROM harbour h WHERE h.source_id = s.id) AS harbours,
       s.last_sync_at
FROM source s
ORDER BY s.id;

-- 2. Spots per kind, and how many carry any availability at all.
SELECT sp.kind,
       count(*) AS total,
       count(st.spot_id) AS with_status,
       count(*) FILTER (WHERE st.state = 'free' AND st.confidence >= 0.4) AS shown_free
FROM spot sp
LEFT JOIN spot_status st ON st.spot_id = sp.id
WHERE sp.active
GROUP BY sp.kind
ORDER BY total DESC;

-- 3. Conflation pressure: which sources are being merged into which.
SELECT left_source_id, right_source_id, count(*), round(avg(distance_m), 1) AS avg_distance_m
FROM conflation_log
WHERE right_source_id IS NOT NULL
GROUP BY 1, 2
ORDER BY 3 DESC;

-- 4. "Why did my buoy move" for one object (same as `balise-ingest conflate --explain`).
SELECT created_at, run_id, rule, left_source_id, left_external_id, distance_m, detail
FROM conflation_log
WHERE target_table = 'spot' AND target_id = :spot_id
ORDER BY created_at;

-- 5. Contribution funnel per week: how many devices, how many reports, how many corrections.
SELECT date_trunc('week', received_at) AS week,
       count(DISTINCT contributor_id) AS contributors,
       count(*) AS observations,
       count(*) FILTER (WHERE payload ->> 'report_kind' = 'check_in') AS check_ins,
       count(*) FILTER (WHERE payload ->> 'report_kind' = 'check_out') AS check_outs,
       count(*) FILTER (WHERE payload ->> 'report_kind' = 'correction') AS corrections,
       count(*) FILTER (WHERE (payload ->> 'remote')::boolean) AS remote
FROM observation
WHERE source_kind = 'community' AND NOT suppressed
GROUP BY 1
ORDER BY 1 DESC;

-- 6. Precision proxy for "free": how often a shown-free spot was corrected within the hour.
WITH shown_free AS (
  SELECT o.spot_id, o.observed_at
  FROM observation o
  WHERE o.state = 'free' AND NOT o.suppressed AND o.confidence >= 0.4
)
SELECT count(*) AS shown_free,
       count(*) FILTER (
         WHERE EXISTS (
           SELECT 1 FROM observation c
           WHERE c.spot_id = shown_free.spot_id
             AND c.state = 'occupied'
             AND c.observed_at BETWEEN shown_free.observed_at
                                  AND shown_free.observed_at + interval '1 hour'
         )
       ) AS contradicted_within_the_hour
FROM shown_free;

-- 7. Reputation distribution — is the community self-correcting?
SELECT width_bucket(reputation, 0.2, 1.5, 13) AS bucket,
       min(reputation) AS from_reputation,
       max(reputation) AS to_reputation,
       count(*)
FROM contributor
GROUP BY 1
ORDER BY 1;

-- 8. Harbours we know least about — the business-development worklist.
SELECT h.slug,
       h.name,
       (SELECT count(*) FROM spot sp WHERE sp.harbour_id = h.id AND sp.active) AS spots,
       h.phone IS NOT NULL AS has_phone,
       h.vhf_channel IS NOT NULL AS has_vhf,
       EXISTS (SELECT 1 FROM feed f WHERE f.harbour_id = h.id AND f.active) AS has_feed
FROM harbour h
ORDER BY spots DESC
LIMIT 50;
