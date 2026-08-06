"""`make tiles-bench` — guards the ADR-0002 budget: p95 MVT generation under 300 ms per tile.

Renders every tile covering a bbox at each zoom, straight from PostGIS, bypassing Redis and the
CDN so the number is the database's, not the cache's.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import statistics
import time

from balise_api.db import dispose_engine, session_scope
from balise_api.services.tiles import TileRequest, render_tile

BUDGET_MS = 300.0
DEFAULT_BBOX = (-3.2, 47.4, -2.6, 47.8)


def tiles_for(bbox: tuple[float, float, float, float], zoom: int) -> list[tuple[int, int]]:
    min_lon, min_lat, max_lon, max_lat = bbox
    n = 2**zoom

    def x_of(lon: float) -> int:
        return int((lon + 180.0) / 360.0 * n)

    def y_of(lat: float) -> int:
        radians = math.radians(lat)
        return int((1.0 - math.log(math.tan(radians) + 1 / math.cos(radians)) / math.pi) / 2.0 * n)

    return [
        (x, y)
        for x in range(x_of(min_lon), x_of(max_lon) + 1)
        for y in range(y_of(max_lat), y_of(min_lat) + 1)
    ]


async def bench(layer: str, zooms: list[int], bbox: tuple[float, float, float, float]) -> int:
    failures = 0
    async with session_scope() as session:
        for zoom in zooms:
            timings: list[float] = []
            total_bytes = 0
            for x, y in tiles_for(bbox, zoom):
                request = TileRequest(layer=layer, z=zoom, x=x, y=y)
                if not request.in_range():
                    continue
                started = time.perf_counter()
                tile = await render_tile(session, request)
                timings.append((time.perf_counter() - started) * 1000)
                total_bytes += len(tile)
            if not timings:
                print(f"{layer} z{zoom}: out of range")
                continue
            timings.sort()
            p95 = timings[min(int(len(timings) * 0.95), len(timings) - 1)]
            verdict = "OK" if p95 <= BUDGET_MS else "OVER BUDGET"
            print(
                f"{layer} z{zoom}: {len(timings)} tiles, "
                f"median {statistics.median(timings):6.1f} ms, p95 {p95:6.1f} ms, "
                f"{total_bytes / max(len(timings), 1) / 1024:5.1f} kB/tile  [{verdict}]"
            )
            failures += p95 > BUDGET_MS
    await dispose_engine()
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--layer", default="spots", choices=["spots", "navaids", "anchorages"])
    parser.add_argument("--zooms", default="11,12,13,14,15")
    parser.add_argument("--bbox", default=",".join(str(value) for value in DEFAULT_BBOX))
    arguments = parser.parse_args()
    bbox = tuple(float(value) for value in arguments.bbox.split(","))
    zooms = [int(value) for value in arguments.zooms.split(",")]
    failures = asyncio.run(bench(arguments.layer, zooms, bbox))  # type: ignore[arg-type]
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
