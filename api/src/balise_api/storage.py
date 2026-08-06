from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from balise_api.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def _client() -> Any:
    import boto3

    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="fr-par",
    )


def put_object(key: str, body: bytes, content_type: str) -> str:
    settings = get_settings()
    _client().put_object(Bucket=settings.s3_bucket, Key=key, Body=body, ContentType=content_type)
    return key


def ensure_bucket() -> None:
    settings = get_settings()
    client = _client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        client.create_bucket(Bucket=settings.s3_bucket)
