from __future__ import annotations

import json
import logging
import multiprocessing
import os
import threading
import time
from collections import defaultdict
from pathlib import Path

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(processName)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _connect_with_retry(client: mqtt.Client, host: str, port: int, stopped: threading.Event) -> None:
    """Retry initial broker connection using 1, 2, 4, ... 30 second backoff."""
    delay = 1
    while not stopped.is_set():
        try:
            client.connect(host, port, keepalive=60)
            client.loop_start()
            return
        except Exception as exc:
            logger.warning("MQTT reconnect to %s:%s in %ss: %s", host, port, delay, exc)
            stopped.wait(delay)
            delay = min(delay * 2, 30)


def _publish_event(
    client: mqtt.Client,
    connected: threading.Event,
    stopped: threading.Event,
    robot_id: str,
    event: dict,
) -> bool:
    """Do not advance the replay until this event has been handed to MQTT at QoS 1."""
    topic = f"robots/{robot_id}/telemetry"
    payload = json.dumps(event, separators=(",", ":"))
    while not stopped.is_set():
        if not connected.wait(timeout=1):
            continue
        try:
            published = client.publish(topic, payload=payload, qos=1, retain=False)
            if published.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.warning("Publish unavailable for %s; waiting for MQTT reconnect", robot_id)
                connected.clear()
                continue
            published.wait_for_publish(timeout=5)
            if published.is_published():
                logger.info("event published robot_id=%s t=%s", robot_id, event["t"])
                return True
            logger.warning("Publish timed out for %s; retrying after reconnect", robot_id)
            connected.clear()
        except Exception as exc:
            logger.warning("Publish failed for %s; retrying after reconnect: %s", robot_id, exc)
            connected.clear()
    return False


def replay_robot(robot_id: str, events: list[dict], host: str, port: int, replay_speed: float) -> None:
    """The entry point for exactly one robot operating-system process."""
    logger.info("robot process started: %s", robot_id)
    connected = threading.Event()
    stopped = threading.Event()
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"robot-{robot_id}",
    )
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    def on_connect(mqtt_client, userdata, flags, reason_code, properties) -> None:
        if reason_code == 0:
            connected.set()
            logger.info("MQTT connection established for %s", robot_id)
        else:
            logger.warning("MQTT connection refused for %s with result code %s", robot_id, reason_code)

    def on_disconnect(mqtt_client, userdata, disconnect_flags, reason_code, properties) -> None:
        connected.clear()
        if not stopped.is_set():
            logger.warning("MQTT disconnected for %s; reconnecting", robot_id)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    try:
        _connect_with_retry(client, host, port, stopped)
        previous_t: int | None = None
        for event in events:
            event_t = event["t"]
            if previous_t is not None:
                delay = max(0, (event_t - previous_t) / replay_speed)
                if delay:
                    time.sleep(delay)
            if not _publish_event(client, connected, stopped, robot_id, event):
                return
            previous_t = event_t
        logger.info("robot process completed: %s", robot_id)
    finally:
        stopped.set()
        try:
            client.disconnect()
        except Exception:
            pass
        client.loop_stop()


def _load_recording(data_dir: Path) -> tuple[list[str], dict[str, list[dict]]]:
    with (data_dir / "robots.json").open(encoding="utf-8") as roster_file:
        robot_ids = [robot["robot_id"] for robot in json.load(roster_file)]
    if len(robot_ids) != 8 or len(set(robot_ids)) != 8:
        raise ValueError("robots.json must contain exactly eight unique robots")

    events_by_robot: dict[str, list[dict]] = defaultdict(list)
    with (data_dir / "events.jsonl").open(encoding="utf-8") as event_file:
        for line_number, line in enumerate(event_file, start=1):
            if not line.strip():
                continue
            event = json.loads(line)
            robot_id = event.get("robot_id")
            if robot_id not in robot_ids:
                raise ValueError(f"Unknown robot_id on events.jsonl line {line_number}: {robot_id}")
            events_by_robot[robot_id].append(event)
    return robot_ids, events_by_robot


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    data_dir = Path(os.getenv("DATA_DIR", project_root / "data"))
    host = os.getenv("MQTT_HOST", "mqtt")
    port = int(os.getenv("MQTT_PORT", "1883"))
    replay_speed = float(os.getenv("REPLAY_SPEED", "10"))
    if replay_speed <= 0:
        raise ValueError("REPLAY_SPEED must be greater than zero")

    robot_ids, events_by_robot = _load_recording(data_dir)
    processes = [
        multiprocessing.Process(
            target=replay_robot,
            name=f"robot-{robot_id}",
            args=(robot_id, events_by_robot[robot_id], host, port, replay_speed),
        )
        for robot_id in robot_ids
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join()

    failed = [process.name for process in processes if process.exitcode != 0]
    if failed:
        raise SystemExit(f"Robot processes failed: {', '.join(failed)}")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
