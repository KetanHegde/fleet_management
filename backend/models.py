from pydantic import BaseModel


class Telemetry(BaseModel):
    """The telemetry payload emitted by a robot."""

    t: int
    robot_id: str
    x: float
    y: float
    status: str
    battery: float


class StartPosition(BaseModel):
    """The fixed recorded starting position in the robot roster."""

    x: float
    y: float


class RobotRosterEntry(BaseModel):
    """Static robot metadata loaded from data/robots.json."""

    robot_id: str
    robot_type: str
    start: StartPosition
