from __future__ import annotations

import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """`"Port du Crouesty"` → `"port-du-crouesty"`. Stable: it is the public SEO identifier."""
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii").lower()
    slug = _NON_ALNUM.sub("-", ascii_only).strip("-")
    return slug or "port"
