from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.rest import router as rest_router
from backend.api.websocket import WebSocketManager, router as websocket_router
from backend.fleet.state import FleetState
from backend.models import RobotRosterEntry
from backend.mqtt.client import FleetMqttClient

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def _load_robot_roster(data_dir: Path) -> dict[str, RobotRosterEntry]:
    with (data_dir / "robots.json").open(encoding="utf-8") as roster_file:
        robots = [RobotRosterEntry.model_validate(robot) for robot in json.load(roster_file)]
    return {robot.robot_id: robot for robot in robots}


def create_app(*, start_mqtt: bool = True) -> FastAPI:
    """Create the backend application and wire its shared state components."""
    project_root = Path(__file__).resolve().parent.parent
    data_dir = Path(os.getenv("DATA_DIR", project_root / "data"))
    robot_roster = _load_robot_roster(data_dir)
    known_robot_ids = set(robot_roster)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if start_mqtt:
            event_loop = asyncio.get_running_loop()
            mqtt_client = FleetMqttClient(
                host=os.getenv("MQTT_HOST", "mqtt"),
                port=int(os.getenv("MQTT_PORT", "1883")),
                fleet_state=app.state.fleet_state,
                event_loop=event_loop,
                on_telemetry=app.state.websocket_manager.broadcast,
            )
            app.state.mqtt_client = mqtt_client
            mqtt_client.start()
            logger.info("Backend started with %d known robots", len(known_robot_ids))
        try:
            yield
        finally:
            mqtt_client = app.state.mqtt_client
            if mqtt_client is not None:
                mqtt_client.stop()
            await app.state.websocket_manager.close_all()
            logger.info("Backend shutdown complete")

    app = FastAPI(title="Robot Fleet API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.state.fleet_state = FleetState(known_robot_ids)
    app.state.robot_roster = robot_roster
    app.state.websocket_manager = WebSocketManager()
    app.state.mqtt_client = None

    app.include_router(rest_router)
    app.include_router(websocket_router)

    return app


app = create_app()
