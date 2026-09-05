# Written Answers

## 1. Current fleet state

The backend keeps one latest telemetry record per robot in `FleetState._robots` in `backend/fleet/state.py`. It is just a dictionary keyed by `robot_id`, so finding `r1` or replacing its current value is simple. `FleetState.update()` only lets a record replace the old one when its recorded `t` value is not older. `get_robot()` and `get_all_robots()` read from that same dictionary. Each operation uses the same `threading.Lock`, because MQTT writes on Paho's network thread while FastAPI can read the data for an API request at the same time.

I wanted REST and WebSocket to describe the same fleet, not two slightly different views of it. `backend/main.py:create_app()` creates one shared `FleetState`. `list_robots()` in `backend/api/rest.py` returns a snapshot from it, while `FleetMqttClient._on_message()` in `backend/mqtt/client.py` updates it first and then calls `WebSocketManager.broadcast()`. In other words, the frontend only gets a live event after that event has become part of the state that `/robots` would return. A dictionary is a good fit here because this dashboard needs the current answer, not a full event archive.

## 2. MQTT QoS 1 tradeoff

I used MQTT with QoS 1 between the robots and backend. `robots/simulator.py:_publish_event()` sends each event to `robots/{robot_id}/telemetry`, and `FleetMqttClient._on_connect()` in `backend/mqtt/client.py` subscribes to all of those topics. MQTT makes sense for robots because the clients are lightweight and both sides can reconnect after a flaky connection. QoS 1 means at-least-once delivery: an event is more likely to make it through a temporary connection problem than with QoS 0, but it can be delivered more than once.

The downside is that MQTT is not exactly once. In `_on_message()`, I validate the payload, reject robots that are not in the roster, and let `FleetState.update()` ignore anything older than the telemetry already stored. Only accepted events are sent out over the WebSocket, so live updates line up with the REST snapshot instead of being a raw copy of every broker delivery. Equal timestamps are still accepted because that is part of the replay rule; an exact QoS 1 retry can therefore result in a harmless repeat WebSocket message. `mergeTelemetry()` in `frontend/src/App.jsx` handles that safely by keeping the value for the robot and timestamp. The other tradeoff is that the state lives only in memory. Restarting the backend clears the snapshot until robots publish again, which was acceptable for a small live prototype but would not be enough for a production history or recovery system.

## 3. What is left out and next work

I left out the pieces that would turn this into a larger operational platform: durable storage, authentication, task orchestration, proper robot liveness checks, and deployment monitoring. The dashboard count in `frontend/src/App.jsx` says that a robot has reported telemetry since this backend started. It does not say the robot is currently healthy or connected, because the system has no heartbeat or broker availability signal to prove that. I would rather show that limitation than make the UI look more certain than it is.

With more time, I would add an explicit liveness signal first. I would keep telemetry separate and add last-seen/availability data next to `FleetState` in `backend/fleet/state.py`, expose it through `backend/api/rest.py`, and broadcast changes with `WebSocketManager`. The robot client in `robots/simulator.py` could publish a small heartbeat and set an MQTT Last Will. Then the UI could tell the difference between “this is the last location we heard” and “the robot has actually gone offline”, which is the information an operator needs before pausing or reassigning work.
