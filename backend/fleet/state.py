from __future__ import annotations

import threading
from collections.abc import Iterable

from backend.models import Telemetry


class FleetState:
    """Stores only the newest accepted telemetry event per known robot."""

    def __init__(self, known_robot_ids: Iterable[str]) -> None:
        self._known_robot_ids = frozenset(known_robot_ids)
        self._robots: dict[str, Telemetry] = {}
        self._lock = threading.Lock()

    @property
    def known_robot_ids(self) -> frozenset[str]:
        return self._known_robot_ids

    def is_known(self, robot_id: str) -> bool:
        return robot_id in self._known_robot_ids

    def update(self, telemetry: Telemetry) -> bool:
        """Accept telemetry unless it is unknown or older than the current event."""
        if telemetry.robot_id not in self._known_robot_ids:
            return False

        with self._lock:
            current = self._robots.get(telemetry.robot_id)
            if current is not None and telemetry.t < current.t:
                return False
            self._robots[telemetry.robot_id] = telemetry
            return True

    def get_robot(self, robot_id: str) -> Telemetry | None:
        with self._lock:
            return self._robots.get(robot_id)

    def get_all_robots(self) -> list[Telemetry]:
        with self._lock:
            return [self._robots[robot_id] for robot_id in sorted(self._robots)]
