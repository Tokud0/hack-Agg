"""Road network: complete graph over depot + fields, Euclidean edge lengths.

A blocked road removes one edge; travel then detours via shortest path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import World

INF = math.inf


@dataclass(frozen=True)
class RoadNetwork:
    dist: dict[str, dict[str, float]]
    next_hop: dict[str, dict[str, str | None]]

    def distance(self, a: str, b: str) -> float:
        return self.dist[a][b]

    def path(self, a: str, b: str) -> tuple[str, ...]:
        """Nodes to visit after `a` to reach `b` (excludes `a`)."""
        if a == b:
            return ()
        if self.next_hop[a][b] is None:
            return ()
        hops: list[str] = []
        current = a
        while current != b:
            current = self.next_hop[current][b]  # type: ignore[assignment]
            hops.append(current)
        return tuple(hops)


def build_network(world: World) -> RoadNetwork:
    nodes = world.node_ids()
    dist: dict[str, dict[str, float]] = {a: {} for a in nodes}
    next_hop: dict[str, dict[str, str | None]] = {a: {} for a in nodes}

    for a in nodes:
        ax, ay = world.node_position(a)
        for b in nodes:
            if a == b:
                dist[a][b], next_hop[a][b] = 0.0, b
                continue
            if frozenset((a, b)) in world.blocked_roads:
                dist[a][b], next_hop[a][b] = INF, None
                continue
            bx, by = world.node_position(b)
            dist[a][b], next_hop[a][b] = math.hypot(ax - bx, ay - by), b

    # Floyd-Warshall; node count is tiny (≈10), so O(n^3) is instant.
    for k in nodes:
        for i in nodes:
            dik = dist[i][k]
            if dik == INF:
                continue
            for j in nodes:
                candidate = dik + dist[k][j]
                if candidate < dist[i][j] - 1e-9:
                    dist[i][j] = candidate
                    next_hop[i][j] = next_hop[i][k]

    return RoadNetwork(dist=dist, next_hop=next_hop)
