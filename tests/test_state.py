from backend.fleet.state import FleetState
from backend.models import Telemetry


def telemetry(robot_id: str = "r1", t: int = 5) -> Telemetry:
    return Telemetry(
        t=t,
        robot_id=robot_id,
        x=10.5,
        y=20.5,
        status="active",
        battery=82.4,
    )


def test_new_robot_event_updates_fleet_state() -> None:
    fleet = FleetState({"r1"})

    assert fleet.update(telemetry(t=5)) is True
    assert fleet.get_robot("r1").t == 5


def test_stale_events_are_ignored() -> None:
    fleet = FleetState({"r1"})
    fleet.update(telemetry(t=20))

    assert fleet.update(telemetry(t=15)) is False
    assert fleet.get_robot("r1").t == 20


def test_unknown_robot_ids_are_rejected() -> None:
    fleet = FleetState({"r1"})

    assert fleet.update(telemetry(robot_id="unknown")) is False
    assert fleet.get_robot("unknown") is None
