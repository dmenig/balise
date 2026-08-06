from __future__ import annotations

import io
import secrets

from fastapi import APIRouter, File, UploadFile, status

from balise_api.auth.dependencies import ContributorDep
from balise_api.repositories.protocols import DomainError
from balise_api.schemas.common import Model
from balise_api.storage import put_object

router = APIRouter(tags=["contribution"])

MAX_BYTES = 8 * 1024 * 1024
ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class InvalidUpload(DomainError):
    status_code = 415
    title = "Fichier refusé"


class UploadOut(Model):
    key: str
    bytes: int
    note: str = "Métadonnées EXIF (dont GPS) supprimées au dépôt."


@router.post("/uploads", response_model=UploadOut, status_code=status.HTTP_201_CREATED)
async def upload_photo(contributor: ContributorDep, file: UploadFile = File(...)) -> UploadOut:
    if file.content_type not in ALLOWED:
        raise InvalidUpload(f"type {file.content_type!r} non accepté")
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise InvalidUpload("fichier trop volumineux (8 Mo max)")
    stripped, media_type = _strip_exif(raw)
    key = f"photos/{secrets.token_urlsafe(16)}{ALLOWED[media_type]}"
    put_object(key, stripped, media_type)
    return UploadOut(key=key, bytes=len(stripped))


def _strip_exif(raw: bytes) -> tuple[bytes, str]:
    """Re-encode through Pillow: sniffs the real type and drops every metadata block."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            fmt = (image.format or "").upper()
            if fmt not in {"JPEG", "PNG", "WEBP"}:
                raise InvalidUpload(f"format {fmt or 'inconnu'} non accepté")
            clean = Image.new(image.mode, image.size)
            clean.putdata(list(image.getdata()))
            buffer = io.BytesIO()
            clean.save(buffer, format=fmt)
    except UnidentifiedImageError as exc:
        raise InvalidUpload("fichier illisible") from exc
    media = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[fmt]
    return buffer.getvalue(), media
