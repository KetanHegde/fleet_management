import asyncio
import json

from backend.fleet.state import FleetState
from backend.mqtt import client as mqtt_client_module
from backend.mqtt.client import FleetMqttClient
from backend.models import Telemetry


class Message:
    def __init__(self, payload: bytes, topic: str = "robots/r1/telemetry") -> None:
        self.payload = payload
        self.topic = topic


class InlineFuture:
    """Minimal Future substitute for running a broadcast synchronously in a unit test."""

    def __init__(self, coroutine) -> None:
        self._exception: Exception | None = None
        try:
            asyncio.run(coroutine)
        except Exception as exc:  # pragma: no cover - exercised by the production callback
            self._exception = exc

    def add_done_callback(self, callback) -> None:
        callback(self)

    def result(self) -> None:
        if self._exception is not None:
            raise self._exception


def test_mqtt_only_broadcasts_valid_accepted_telemetry(monkeypatch) -> None:
    fleet = FleetState({"r1"})
    broadcasts: list[Telemetry] = []

    async def capture_broadcast(telemetry: Telemetry) -> None:
        broadcasts.append(telemetry)

    monkeypatch.setattr(
        mqtt_client_module.asyncio,
        "run_coroutine_threadsafe",
        lambda coroutine, loop: InlineFuture(coroutine),
    )
    mqtt_client = FleetMqttClient(
        host="mqtt",
        port=1883,
        fleet_state=fleet,
        event_loop=object(),
        on_telemetry=capture_broadcast,
    )

    valid_event = {
        "t": 20,
        "robot_id": "r1",
        "x": 580.9,
        "y": 29.4,
        "status": "active",
        "battery": 83.6,
    }
    mqtt_client._on_message(None, None, Message(json.dumps(valid_event).encode()))
    mqtt_client._on_message(None, None, Message(b"not-json"))
    mqtt_client._on_message(
        None,
        None,
        Message(json.dumps({**valid_event, "robot_id": "unknown", "t": 21}).encode()),
    )
    mqtt_client._on_message(
        None,
        None,
        Message(json.dumps({**valid_event, "t": 15}).encode()),
    )

    assert fleet.get_robot("r1").t == 20
    assert [event.t for event in broadcasts] == [20]
