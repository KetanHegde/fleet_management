from fastapi import APIRouter, HTTPException, Request


router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/robots")
def list_robots(request: Request) -> dict[str, list]:
    return {"robots": request.app.state.fleet_state.get_all_robots()}


@router.get("/robots/roster")
def get_robot_roster(request: Request) -> dict[str, list]:
    """Return immutable robot IDs, types, and recorded starting positions."""
    roster = request.app.state.robot_roster
    return {"robots": [roster[robot_id] for robot_id in sorted(roster)]}


@router.get("/robots/{robot_id}")
def get_robot(robot_id: str, request: Request):
    telemetry = request.app.state.fleet_state.get_robot(robot_id)
    if telemetry is None:
        raise HTTPException(status_code=404, detail="Robot telemetry not found")
    return telemetry
