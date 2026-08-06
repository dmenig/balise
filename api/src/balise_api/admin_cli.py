"""`balise-admin` — the operations documented in the runbooks (docs/12).

The append-only observation model is what makes suppression and recomputation safe (ADR-0003).
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from sqlalchemy import text

from balise_api.auth.tokens import issue_feed_token
from balise_api.db import sync_session

app = typer.Typer(add_completion=False, help="Administration Balise")
feed_app = typer.Typer(help="Flux partenaires (MBFS)")
observations_app = typer.Typer(help="Observations")
gdpr_app = typer.Typer(help="RGPD")
app.add_typer(feed_app, name="feed")
app.add_typer(observations_app, name="observations")
app.add_typer(gdpr_app, name="gdpr")


def _echo(payload: dict[str, object]) -> None:
    typer.echo(json.dumps(payload, ensure_ascii=False, default=str))


@feed_app.command("create")
def feed_create(
    feed_id: Annotated[str, typer.Argument(help="ex. feed.port-crouesty")],
    harbour_slug: Annotated[str, typer.Option()],
    contact_email: Annotated[str, typer.Option()],
    ttl_seconds: Annotated[int, typer.Option()] = 60,
    trust: Annotated[float, typer.Option(help="≤ 0.95")] = 0.95,
) -> None:
    token, token_hash = issue_feed_token(feed_id)
    with sync_session() as session:
        harbour_id = session.execute(
            text("SELECT id FROM harbour WHERE slug = :slug"), {"slug": harbour_slug}
        ).scalar_one_or_none()
        if harbour_id is None:
            raise typer.BadParameter(f"port inconnu: {harbour_slug}")
        session.execute(
            text(
                """
                INSERT INTO feed (id, harbour_id, kind, contact_email, token_hash,
                                  ttl_seconds, trust)
                VALUES (:id, :harbour_id, 'port_feed', :email, :hash, :ttl, :trust)
                ON CONFLICT (id) DO UPDATE SET token_hash = EXCLUDED.token_hash,
                    contact_email = EXCLUDED.contact_email, ttl_seconds = EXCLUDED.ttl_seconds,
                    trust = EXCLUDED.trust, active = true
                """
            ),
            {
                "id": feed_id,
                "harbour_id": harbour_id,
                "email": contact_email,
                "hash": token_hash,
                "ttl": ttl_seconds,
                "trust": min(trust, 0.95),
            },
        )
        session.commit()
    _echo({"feed_id": feed_id, "token": token, "note": "jeton affiché une seule fois"})


@feed_app.command("disable")
def feed_disable(feed_id: Annotated[str, typer.Argument()]) -> None:
    """Runbook 1: a partner feed went stale → force it to `unknown` and notify."""
    with sync_session() as session:
        session.execute(text("UPDATE feed SET active = false WHERE id = :id"), {"id": feed_id})
        affected = session.execute(
            text(
                """
                UPDATE spot_status SET state = 'unknown', confidence = 0, as_of = now(),
                    updated_at = now()
                WHERE source_kind IN ('port_feed', 'sensor')
                  AND spot_id IN (SELECT id FROM spot WHERE harbour_id =
                        (SELECT harbour_id FROM feed WHERE id = :id))
                RETURNING spot_id
                """
            ),
            {"id": feed_id},
        )
        count = len(affected.scalars().all())
        session.commit()
    _echo({"feed_id": feed_id, "disabled": True, "spots_set_unknown": count})


@feed_app.command("rotate-token")
def feed_rotate(feed_id: Annotated[str, typer.Argument()]) -> None:
    token, token_hash = issue_feed_token(feed_id)
    with sync_session() as session:
        session.execute(
            text("UPDATE feed SET token_hash = :hash WHERE id = :id"),
            {"hash": token_hash, "id": feed_id},
        )
        session.commit()
    _echo({"feed_id": feed_id, "token": token})


@observations_app.command("suppress")
def observations_suppress(
    contributor: Annotated[int | None, typer.Option("--contributor")] = None,
    feed: Annotated[str | None, typer.Option("--feed")] = None,
) -> None:
    """Runbook 5: quarantine and recompute. Nothing is lost, no state is corrupted."""
    if contributor is None and feed is None:
        raise typer.BadParameter("--contributor ou --feed requis")
    with sync_session() as session:
        result = session.execute(
            text(
                """
                UPDATE observation SET suppressed = true
                WHERE (CAST(:contributor AS bigint) IS NULL OR contributor_id = :contributor)
                  AND (CAST(:feed AS text) IS NULL OR source_ref = :feed)
                  AND NOT suppressed
                RETURNING spot_id
                """
            ),
            {"contributor": contributor, "feed": feed},
        )
        spot_ids = sorted({value for value in result.scalars().all() if value is not None})
        session.commit()
    from balise_workers.status_worker import recompute_decay

    with sync_session() as session:
        report = recompute_decay(session)
        session.commit()
    _echo({"suppressed_spots": len(spot_ids), "recomputed": report.checked})


@observations_app.command("ban-device")
def ban_device(device_hash: Annotated[str, typer.Argument()]) -> None:
    with sync_session() as session:
        session.execute(
            text("UPDATE contributor SET banned = true WHERE device_hash = :hash"),
            {"hash": device_hash},
        )
        session.commit()
    _echo({"device_hash": device_hash, "banned": True})


@gdpr_app.command("erase")
def gdpr_erase(email: Annotated[str, typer.Option("--email")]) -> None:
    """Runbook 6: delete the account, anonymise observations, purge photos, keep a written trace."""
    with sync_session() as session:
        contributor_id = session.execute(
            text("SELECT id FROM contributor WHERE email = :email"), {"email": email}
        ).scalar_one_or_none()
        if contributor_id is None:
            raise typer.BadParameter(f"aucun compte pour {email}")
        photos = (
            session.execute(
                text("SELECT unnest(photo_keys) FROM comment WHERE contributor_id = :cid"),
                {"cid": contributor_id},
            )
            .scalars()
            .all()
        )
        session.execute(
            text(
                "UPDATE observation SET contributor_id = NULL, source_ref = NULL "
                "WHERE contributor_id = :cid"
            ),
            {"cid": contributor_id},
        )
        session.execute(
            text("DELETE FROM comment WHERE contributor_id = :cid"), {"cid": contributor_id}
        )
        session.execute(text("DELETE FROM contributor WHERE id = :cid"), {"cid": contributor_id})
        session.commit()
    _echo(
        {
            "email": email,
            "erased": True,
            "photos_to_purge": list(photos),
            "observations": "anonymised",
        }
    )


@app.command("tiles-flush")
def tiles_flush() -> None:
    """Common problem in docs/11: empty map with 200s → stale tile ETags."""
    import asyncio

    from balise_api.cache import close_redis, invalidate_tiles

    async def _run() -> int:
        removed = await invalidate_tiles()
        await close_redis()
        return removed

    _echo({"tiles_flushed": asyncio.run(_run())})


if __name__ == "__main__":  # pragma: no cover
    app()
