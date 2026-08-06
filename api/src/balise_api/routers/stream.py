from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from balise_api.config import get_settings
from balise_api.services.availability.realtime import Bbox, heartbeat, hub

router = APIRouter()

IDLE_TIMEOUT_S = 120
HEARTBEAT_S = 25
MAX_CONNECTIONS = 20_000


@router.websocket("/stream")
async def stream(socket: WebSocket) -> None:
    settings = get_settings()
    await socket.accept()
    if not settings.feature_websocket or hub.connections >= MAX_CONNECTIONS:
        await socket.send_json({"type": "unavailable", "fallback": "poll /v1/status every 20s"})
        await socket.close(code=1013)
        return
    try:
        request = await asyncio.wait_for(socket.receive_json(), timeout=IDLE_TIMEOUT_S)
        bbox = Bbox.parse(list(request["subscribe"]["bbox"]))
    except (TimeoutError, KeyError, TypeError, ValueError):
        await socket.send_json({"type": "error", "detail": "premier message: {subscribe:{bbox}}"})
        await socket.close(code=1003)
        return
    if bbox.too_large:
        await socket.send_json({"type": "error", "detail": "bbox > 1°"})
        await socket.close(code=1009)
        return

    await hub.start()
    queue = hub.subscribe(bbox)
    reader = asyncio.create_task(_drain(socket))
    try:
        await socket.send_json({"type": "subscribed", "bbox": list(request["subscribe"]["bbox"])})
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_S)
            except TimeoutError:
                await socket.send_json(heartbeat())
                continue
            await socket.send_json(message)
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(queue)
        reader.cancel()
        with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
            await reader


async def _drain(socket: WebSocket) -> None:
    """Consume pongs/keepalives so a client that talks does not fill the receive buffer."""
    while True:
        await socket.receive_text()
