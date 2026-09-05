# System Design

## 1. Adding a feature later

The code is small, but the boundaries are in useful places: MQTT lives in `backend/mqtt/client.py`, current telemetry lives in `FleetState`, and the UI is in `frontend/src/App.jsx`. That means a straightforward feature does not need a rewrite. For example, a robot detail/debug view could build on the existing selected-marker sidebar and the `GET /robots/{robot_id}` route in `backend/api/rest.py:get_robot()`. A click on a map marker could fetch that route and show the recorded `t` value in a separate debug panel, while leaving the main map and hover card focused on ID, type, status, position, and battery. The MQTT topic and shared-state design could stay exactly as they are.

For a bigger feature, such as task assignment, I would not overload `Telemetry` in `backend/models.py`; it is the fixed message that a robot publishes. I would give tasks their own state component, create it in `backend/main.py:create_app()`, expose it through a small `backend/api/` router, and send task updates through `WebSocketManager`. The existing pattern—validate, update state, then broadcast—is reusable. Task state would also be the point where I would make a conscious decision about persistence instead of trying to squeeze it into the live telemetry dictionary.

## 2. Growing from eight to five hundred robots

The dictionary in `FleetState._robots` is not the first thing I would worry about at 500 robots; it holds one small latest value per robot and looks that up directly. Fanout is more likely to hurt first. Every accepted event in `FleetMqttClient._on_message()` schedules work, and `WebSocketManager.broadcast()` sends every event to every connected browser one at a time. With hundreds of busy robots and several dashboards open, that single backend event loop could spend most of its time serialising and sending updates. The 500 colored markers and their hover interaction in `frontend/src/App.jsx` would also become expensive to update and difficult for an operator to read on one fixed facility map.

I would start by batching outbound changes for a very short window and keeping only the latest update per `robot_id` in that batch. The `/robots` snapshot would still be there to recover from anything a client misses. On the frontend I would use pagination or virtualised cards, then add measurements for broker-to-browser delay. I would only move to multiple backend instances after deciding how WebSocket clients should get a consistent stream. A shared database or cache may eventually be needed, but it is not the first thing this local project needs.

## 3. Limited robot bandwidth

Right now `robots/simulator.py:_publish_event()` sends a full JSON object for every event. That repeats field names and carries more coordinate precision than the screen necessarily needs. With limited bandwidth, I would change the message at that point: send a position only after meaningful movement, round it to the precision the UI uses, and send battery or status less often than position. That would need a clear versioned change to `Telemetry` in `backend/models.py` and the parser in `FleetMqttClient._on_message()` so the backend can still build a reliable current state.

If the link were extremely constrained, I would measure first and then consider a compact schema or binary payload—MQTT itself does not require JSON. I would still keep a sequence number or recorded time because `FleetState.update()` needs an ordering signal to avoid moving a robot backwards. The tradeoff is less smooth movement and less exact information, so the UI should make it clear that it is showing the last reported position, not a continuous live track.

## 4. A robot stops responding mid-task

Today, if a robot goes quiet, the system keeps its last accepted event in `FleetState`. `frontend/src/App.jsx` continues to show the robot at that last map position, with the color from its last recorded status, and its “reporting” count is not a health check. That is an honest limitation of the current build. The source recording is telemetry, and inventing an `offline` event just because no message arrived would be misleading.

The next version would add a real liveness path. Each robot process in `robots/simulator.py` could set an MQTT Last Will on an availability topic and send a small heartbeat while it is running. A background watchdog started from `backend/main.py:create_app()` would track availability and last-seen time separately from recorded telemetry. A task controller could then stop giving work to an unavailable robot, alert an operator, and make reallocation a deliberate policy instead of assuming the robot will finish.

## 5. Slow, unreliable, or out-of-order links

There is already a basic recovery path for a slow or unreliable link. The robot process retries in `robots/simulator.py:_connect_with_retry()` with 1, 2, 4, 8, then 30-second capped backoff. `_publish_event()` waits up to five seconds for Paho to complete the current QoS 1 publish and checks `is_published()` before it moves on. That confirms MQTT broker-level publish completion, not end-to-end processing by FastAPI. The backend uses the same startup retry pattern in `backend/mqtt/client.py:_connect_with_retry()` and Paho reconnects after a drop. During the outage, REST and the frontend keep showing the last accepted value. At the moment there is no age indicator, so an operator cannot tell whether that value is fresh or old.

Once the connection is healthy again, the robot continues replaying events in order. `FleetState.update()` compares `t`, accepts newer or equal events, and ignores late older ones, so state does not go backwards. `_on_message()` only broadcasts the accepted values, and `mergeTelemetry()` in `frontend/src/App.jsx` follows the same timestamp rule. The browser WebSocket also reconnects with capped backoff and refreshes `/robots`, which brings it back to the authoritative snapshot if it missed a live message. Adding last-seen/liveness data later would make the stale period visible instead of leaving it hidden behind the last known value.
