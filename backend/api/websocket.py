from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.models import Telemetry

logger = logging.getLogger(__name__)
router = APIRouter()


class WebSocketManager:
    """Tracks clients and safely broadcasts accepted telemetry to them."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        logger.info("WebSocket connection established; clients=%d", len(self._clients))

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)
        logger.info("WebSocket disconnected; clients=%d", len(self._clients))

    async def broadcast(self, telemetry: Telemetry) -> None:
        disconnected: list[WebSocket] = []
        payload = telemetry.model_dump(mode="json")
        for websocket in tuple(self._clients):
            try:
                await websocket.send_json(payload)
            except Exception:  # A disconnected peer must not stop the broadcast.
                disconnected.append(websocket)
        for websocket in disconnected:
            self.disconnect(websocket)

    async def close_all(self) -> None:
        for websocket in tuple(self._clients):
            try:
                await websocket.close()
            except Exception:
                pass
            self.disconnect(websocket)


@router.websocket("/ws")
async def fleet_websocket(websocket: WebSocket) -> None:
    manager: WebSocketManager = websocket.app.state.websocket_manager
    await manager.connect(websocket)
    try:
        while True:
            # Keeping the receive loop active lets FastAPI surface disconnects promptly.
            await websocket.receive()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
