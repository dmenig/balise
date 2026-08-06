"""`balise-mbfs` — validator + reference client, the tool we hand to a harbour-software vendor."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from balise_ingest.mbfs.client import MbfsClient, poll_feed
from balise_ingest.mbfs.validator import validate_document

app = typer.Typer(add_completion=False, help="MBFS v0.1 — Mooring & Berth Feed Specification")


@app.command()
def validate(
    target: Annotated[str, typer.Argument(help="URL ou fichier station_status.json")],
) -> None:
    findings = validate_document(target)
    errors = [finding for finding in findings if finding.severity == "error"]
    for finding in findings:
        typer.echo(str(finding))
    if errors:
        typer.echo(f"\n{len(errors)} erreur(s) — le flux serait rejeté.")
        raise typer.Exit(1)
    typer.echo("\nOK — flux conforme MBFS v0.1.")


@app.command()
def poll(url: Annotated[str, typer.Argument()]) -> None:
    result = poll_feed(url)
    typer.echo(
        json.dumps(
            {
                "fetched_at": result.fetched_at.isoformat(),
                "last_updated": result.snapshot.last_updated.isoformat(),
                "ttl": result.snapshot.ttl,
                "stale": result.stale,
                "harbours": len(result.snapshot.data.harbours),
            },
            ensure_ascii=False,
        )
    )


@app.command()
def push(
    base_url: Annotated[str, typer.Option(envvar="BALISE_API_URL")],
    feed_id: Annotated[str, typer.Option()],
    token: Annotated[str, typer.Option(envvar="BALISE_FEED_TOKEN")],
    spot_id: Annotated[str, typer.Option()],
    state: Annotated[str, typer.Option()] = "free",
) -> None:
    """Smoke-test a partner integration with a single observation."""
    client = MbfsClient(base_url=base_url, feed_id=feed_id, token=token)
    typer.echo(json.dumps(client.push_observations([{"spot_id": spot_id, "state": state}])))


@app.command()
def health(
    base_url: Annotated[str, typer.Option(envvar="BALISE_API_URL")],
    feed_id: Annotated[str, typer.Option()],
    token: Annotated[str, typer.Option(envvar="BALISE_FEED_TOKEN")],
) -> None:
    client = MbfsClient(base_url=base_url, feed_id=feed_id, token=token)
    typer.echo(json.dumps(client.health(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":  # pragma: no cover
    app()
