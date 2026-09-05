# Local Robot Fleet System

## Overview

This local prototype demonstrates the complete flow:

```text
Robot processes -> MQTT Broker -> Backend -> REST/WebSocket -> Frontend
```

The eight robot processes replay the supplied recording. The React screen is deliberately small and is only intended to verify the live system.

## Architecture

```text
 r1 process ─┐
 r2 process ─┤
     ...     ├── MQTT QoS 1 ──> Mosquitto ──> FastAPI backend ──> REST / WebSocket ──> React frontend
 r8 process ─┘                              │
                                             └── thread-safe latest fleet state
```

The `robots` service starts exactly eight separate operating-system processes using `multiprocessing.Process`: one for `r1` through `r8`. Each process publishes only to `robots/{robot_id}/telemetry`.

## Requirements

- Docker
- Docker Compose

No other infrastructure needs to be installed manually.

## Run

```bash
docker compose up --build
```

## URLs

- Frontend: http://localhost:5173
- Backend: http://localhost:8000
- Swagger: http://localhost:8000/docs
- MQTT: localhost:1883

## Robot simulation

`data/events.jsonl` is the source of truth. Events are grouped by robot and replayed in the order each robot's events appear in that file. The simulator does not generate random telemetry.

The default `REPLAY_SPEED=10`, so a five-second recording gap is replayed in 0.5 seconds. Set `REPLAY_SPEED` in the `robots` service environment to change this. Equal event timestamps have no artificial delay.

## MQTT

Telemetry is sent on:

```text
robots/{robot_id}/telemetry
```

Publishing and the backend subscription use QoS 1 with non-retained messages. The included Mosquitto configuration allows anonymous access solely for local development. It is not production-safe and must not be used as a production security configuration.

QoS 1 is at-least-once delivery, so duplicate deliveries are possible. The backend validates every payload and uses its recorded `t` value to prevent an older delivery from moving a robot's state backwards. Equal timestamps remain accepted, as required by the replay ordering rule.

## Backend

The FastAPI backend consumes `robots/+/telemetry`, validates every payload with Pydantic, rejects unknown robots, and keeps only the latest telemetry event for each known robot. Its lock-protected fleet state rejects an incoming event if its `t` value is older than the current event.

Fleet state is intentionally in memory and contains no historical event store. A backend restart therefore starts with an empty telemetry snapshot until robots publish again; this keeps the prototype focused on live current state rather than durable telemetry storage.

- `GET /health` returns service health.
- `GET /robots` returns the deterministic robot-ID-sorted current snapshot.
- `GET /robots/roster` returns the robot type and recorded `start` position from `robots.json`.
- `GET /robots/{robot_id}` returns a robot's current telemetry or `404` before it has telemetry.
- `GET /ws` is the WebSocket endpoint. Every accepted event is broadcast to connected clients.

REST and WebSocket share the same fleet state; no second WebSocket-specific state exists.

## Design decisions

- `FleetState` is an in-memory, lock-protected latest-event dictionary. This keeps REST snapshots and WebSocket broadcasts consistent without retaining unneeded event history.
- MQTT QoS 1 is used for at-least-once robot telemetry. The backend validates messages and rejects events older than the state held for that robot; exact duplicate delivery can still produce a harmless equal-timestamp update.
- The supplied recording is replayed exactly and no connectivity or telemetry values are fabricated. In particular, “reporting” in the frontend is not claimed to be a robot health check.

## Reconnection

Robot clients and the backend use MQTT retries/reconnect delays of 1, 2, 4, 8 seconds, capped at 30 seconds. The browser WebSocket reconnects with the same sequence and refreshes `GET /robots` after reconnecting.

## Testing

Install the backend test dependencies, then run:

```bash
pytest
```

The unit/API tests do not require a running MQTT broker.

The MQTT consumer test in `tests/test_mqtt_client.py` covers the trickiest boundary: invalid JSON, unknown robot IDs, and stale events must not change the state or reach WebSocket fanout. State and API tests live in `tests/test_state.py` and `tests/test_api.py`.

## What is next

The next production-oriented addition would be an explicit robot liveness signal (heartbeat and MQTT Last Will), followed by durable storage where historical telemetry or task recovery is required. See [ANSWERS.md](ANSWERS.md) and [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for the code-specific rationale and scaling plan.

## AI delegation notes

The implementation was developed interactively with Codex from the supplied requirements and data. No subagents or external services were delegated implementation work. Changes were verified locally with the pytest suite; a full Docker run remains dependent on Docker Desktop's Linux engine being available on the host.
