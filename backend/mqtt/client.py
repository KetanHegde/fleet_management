from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Awaitable, Callable

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from backend.fleet.state import FleetState
from backend.models import Telemetry

logger = logging.getLogger(__name__)


class FleetMqttClient:
    """MQTT consumer which validates telemetry and forwards accepted events."""

    def __init__(
        self,
        host: str,
        port: int,
        fleet_state: FleetState,
        event_loop: asyncio.AbstractEventLoop,
        on_telemetry: Callable[[Telemetry], Awaitable[None]],
    ) -> None:
        self.host = host
        self.port = port
        self.fleet_state = fleet_state
        self.event_loop = event_loop
        self.on_telemetry = on_telemetry
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id="fleet-backend",
        )
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self._stop_requested = threading.Event()
        self._connection_thread: threading.Thread | None = None
        self._loop_started = False

    def start(self) -> None:
        """Begin initial connection retries without blocking FastAPI's event loop."""
        self._connection_thread = threading.Thread(
            target=self._connect_with_retry,
            name="fleet-mqtt-connect",
            daemon=True,
        )
        self._connection_thread.start()

    def _connect_with_retry(self) -> None:
        delay = 1
        while not self._stop_requested.is_set():
            try:
                self.client.connect(self.host, self.port, keepalive=60)
                self.client.loop_start()
                self._loop_started = True
                return
            except Exception as exc:
                logger.warning(
                    "MQTT connection unavailable at %s:%s; retrying in %ss: %s",
                    self.host,
                    self.port,
                    delay,
                    exc,
                )
                self._stop_requested.wait(delay)
                delay = min(delay * 2, 30)

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code != 0:
            logger.warning("MQTT connection refused with result code %s", reason_code)
            return
        logger.info("MQTT connected to %s:%s", self.host, self.port)
        result, _ = client.subscribe("robots/+/telemetry", qos=1)
        if result == mqtt.MQTT_ERR_SUCCESS:
            logger.info("MQTT subscribed to robots/+/telemetry (QoS 1)")
        else:
            logger.warning("MQTT subscription failed with result code %s", result)

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties) -> None:
        if self._stop_requested.is_set():
            logger.info("MQTT disconnected")
        else:
            logger.warning("MQTT disconnected (result code %s); reconnecting", reason_code)

    def _on_message(self, client, userdata, message) -> None:
        try:
            payload = message.payload.decode("utf-8")
            telemetry = Telemetry.model_validate_json(payload)
        except (UnicodeDecodeError, ValidationError) as exc:
            logger.warning("Ignoring invalid MQTT telemetry on %s: %s", message.topic, exc)
            return
        except Exception as exc:
            logger.warning("Ignoring invalid JSON MQTT telemetry on %s: %s", message.topic, exc)
            return

        if not self.fleet_state.is_known(telemetry.robot_id):
            logger.warning("Ignoring telemetry for unknown robot ID %s", telemetry.robot_id)
            return

        if not self.fleet_state.update(telemetry):
            logger.info("Ignored stale event for %s at t=%s", telemetry.robot_id, telemetry.t)
            return

        logger.info("Received robot event: robot_id=%s t=%s", telemetry.robot_id, telemetry.t)
        future = asyncio.run_coroutine_threadsafe(self.on_telemetry(telemetry), self.event_loop)
        future.add_done_callback(self._log_broadcast_failure)

    @staticmethod
    def _log_broadcast_failure(future) -> None:
        try:
            future.result()
        except Exception as exc:
            logger.warning("WebSocket broadcast failed: %s", exc)

    def stop(self) -> None:
        self._stop_requested.set()
        try:
            self.client.disconnect()
        except Exception as exc:
            logger.debug("MQTT disconnect failed: %s", exc)
        if self._loop_started:
            self.client.loop_stop()
