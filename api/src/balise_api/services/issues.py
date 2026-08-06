"""v1's contribution loop: corrections to the *referential* (docs/08, docs/14 M2).

It improves *what the object is* — position, existence, price, contact — never its *state*.
An accepted correction ends up as a reviewed entry in `overrides.yml`, which is why the moderation
queue stores the proposed geometry verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from balise_api.repositories.protocols import DomainError

TargetType = Literal["spot", "harbour", "navaid"]
IssueKind = Literal[
    "wrong_position", "removed", "wrong_price", "wrong_contact", "wrong_name", "other"
]

_TABLE_BY_TARGET: dict[str, str] = {
    "spot": "spot",
    "harbour": "harbour",
    "navaid": "nav_aid",
}
_COLUMN_BY_TARGET: dict[str, str] = {
    "spot": "spot_id",
    "harbour": "harbour_id",
    "navaid": "nav_aid_id",
}


class UnknownTarget(DomainError):
    status_code = 404
    title = "Objet inconnu"


@dataclass(frozen=True, slots=True)
class Correction:
    target_type: TargetType
    target_id: int
    kind: IssueKind
    note: str
    position: tuple[float, float] | None = None


async def submit(
    session: AsyncSession, correction: Correction, contributor_id: int | None
) -> dict[str, Any]:
    table = _TABLE_BY_TARGET[correction.target_type]
    exists = await session.execute(
        text(f"SELECT 1 FROM {table} WHERE id = :id"),
        {"id": correction.target_id},
    )
    if exists.scalar_one_or_none() is None:
        raise UnknownTarget(f"{correction.target_type} {correction.target_id}")

    payload: dict[str, Any] = {"target_type": correction.target_type}
    if correction.position is not None:
        payload["proposed_position"] = list(correction.position)

    column = _COLUMN_BY_TARGET[correction.target_type]
    row = await session.execute(
        text(
            f"""
            INSERT INTO issue ({column}, contributor_id, category, body, payload)
            VALUES (:target_id, :contributor_id, :category, :body, CAST(:payload AS jsonb))
            RETURNING id, created_at
            """
        ),
        {
            "target_id": correction.target_id,
            "contributor_id": contributor_id,
            "category": correction.kind,
            "body": correction.note,
            "payload": _json(payload),
        },
    )
    created = row.one()
    return {"id": f"issue_{created.id}", "created_at": created.created_at}


def _json(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False)
