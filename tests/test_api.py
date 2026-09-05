from fastapi.testclient import TestClient

from backend.main import create_app
from backend.models import Telemetry


def test_health_and_robots_api_returns_current_state() -> None:
    app = create_app(start_mqtt=False)
    app.state.fleet_state.update(
        Telemetry(
            t=20,
            robot_id="r1",
            x=580.9,
            y=29.4,
            status="maintenance",
            battery=83.6,
        )
    )

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.get("/robots")

    assert response.status_code == 200
    assert response.json() == {
        "robots": [
            {
                "t": 20,
                "robot_id": "r1",
                "x": 580.9,
                "y": 29.4,
                "status": "maintenance",
                "battery": 83.6,
            }
        ]
    }


def test_individual_robot_returns_404_when_no_telemetry_exists() -> None:
    app = create_app(start_mqtt=False)

    with TestClient(app) as client:
        response = client.get("/robots/r1")

    assert response.status_code == 404


def test_roster_returns_recorded_start_positions() -> None:
    app = create_app(start_mqtt=False)

    with TestClient(app) as client:
        response = client.get("/robots/roster")

    assert response.status_code == 200
    assert response.json()["robots"][0] == {
        "robot_id": "r1",
        "robot_type": "picker",
        "start": {"x": 569.9, "y": 33.0},
    }
