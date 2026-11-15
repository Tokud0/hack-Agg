"""Immutable domain model for the fleet coordinator.

All times are simulated hours, distances are grid cells.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Implement(str, Enum):
    SPRAYER = "sprayer"
    MOWER = "mower"


JOB_TYPE_TO_IMPLEMENT = {
    "spray": Implement.SPRAYER,
    "mow": Implement.MOWER,
}


class JobStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    UNASSIGNABLE = "unassignable"


class TractorStatus(str, Enum):
    IDLE = "idle"
    TRAVELING = "traveling"
    WORKING = "working"
    BROKEN = "broken"


@dataclass(frozen=True)
class Field:
    id: str
    x: float
    y: float


@dataclass(frozen=True)
class Job:
    id: str
    type: str
    field_id: str
    priority: int
    deadline: float
    work_hours: float
    remaining_hours: float
    status: JobStatus = JobStatus.PENDING
    tractor_id: str | None = None
    reason: str | None = None
    completed_at: float | None = None
    # Start of the current work segment; closed segments are (tractor, start, end).
    started_at: float | None = None
    segments: tuple[tuple[str, float, float], ...] = ()

    @property
    def implement(self) -> Implement:
        return JOB_TYPE_TO_IMPLEMENT[self.type]

    @property
    def progress(self) -> float:
        if self.work_hours <= 0:
            return 1.0
        return 1.0 - self.remaining_hours / self.work_hours


@dataclass(frozen=True)
class Tractor:
    id: str
    implement: Implement
    fuel_capacity: float
    fuel: float
    speed: float
    fuel_per_travel_hour: float
    fuel_per_work_hour: float
    x: float
    y: float
    node: str
    status: TractorStatus = TractorStatus.IDLE
    # Remaining nodes to visit on the current leg; empty when not traveling.
    path: tuple[str, ...] = ()
    current_job: str | None = None
    queue: tuple[str, ...] = ()
    travel_time: float = 0.0
    idle_time: float = 0.0
    work_time: float = 0.0


@dataclass(frozen=True)
class Plan:
    """Coordinator output: ordered job queue per tractor plus unassignable reasons."""

    queues: dict[str, tuple[str, ...]]
    unassignable: dict[str, str] = field(default_factory=dict)
    score: float = 0.0


@dataclass(frozen=True)
class World:
    time: float
    fields: dict[str, Field]
    jobs: dict[str, Job]
    tractors: dict[str, Tractor]
    depot: Field
    blocked_roads: frozenset[frozenset[str]] = frozenset()

    def node_position(self, node: str) -> tuple[float, float]:
        if node == self.depot.id:
            return self.depot.x, self.depot.y
        f = self.fields[node]
        return f.x, f.y

    def node_ids(self) -> list[str]:
        return [self.depot.id, *sorted(self.fields)]
