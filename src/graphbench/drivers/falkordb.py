from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import redis

from graphbench.core import EdgeRow, NodeRow


@dataclass
class FalkorConfig:
    name: str
    host: str
    port: int
    password: str
    graph: str = "benchmark"
    ssl: bool = True


class FalkorAdapter:
    """Adapter for FalkorDB Cloud's Redis protocol and OpenCypher commands."""

    def __init__(self, config: FalkorConfig):
        self.config = config
        self.client = redis.Redis(
            host=config.host,
            port=config.port,
            password=config.password,
            ssl=config.ssl,
            decode_responses=True,
            socket_timeout=30,
        )

    @property
    def name(self) -> str:
        return self.config.name

    def close(self) -> None:
        self.client.close()

    def _query(self, cypher: str, params: dict | None = None):
        # FalkorDB Cloud uses GRAPH.QUERY with OpenCypher. Parameters are
        # represented as literals by the adapter because the Redis command
        # interface does not share Bolt's parameter binding shape.
        if params:
            for key, value in params.items():
                literal = f"'{value}'" if isinstance(value, str) else str(value)
                cypher = cypher.replace(f"${key}", literal)
        return self.client.execute_command("GRAPH.QUERY", self.config.graph, cypher, "--compact")

    def ping(self) -> None:
        self.client.ping()

    def reset(self) -> None:
        self._query("MATCH (n) DETACH DELETE n")

    def create_schema(self) -> None:
        # FalkorDB's index syntax is different from Neo4j's and is explicitly
        # kept in this adapter to make syntax differences visible in the report.
        try:
            self._query("CREATE INDEX FOR (u:User) ON (u.user_id)")
        except Exception:
            pass
        try:
            self._query("CREATE INDEX FOR (u:User) ON (u.country)")
        except Exception:
            pass

    def load_batch(self, nodes: Iterable[NodeRow], edges: Iterable[EdgeRow]) -> None:
        node_rows = list(nodes)
        edge_rows = list(edges)
        for n in node_rows:
            self._query(
                "CREATE (:User {user_id: $user_id, name: $name, country: $country, age: $age})",
                {"user_id": n.user_id, "name": n.name, "country": n.country, "age": n.age},
            )
        for e in edge_rows:
            self._query(
                "MATCH (a:User {user_id: $src}), (b:User {user_id: $dst}) "
                "CREATE (a)-[:FOLLOWS {weight: $weight}]->(b)",
                {"src": e.src, "dst": e.dst, "weight": e.weight},
            )

    def counts(self) -> tuple[int, int]:
        nodes = self._query("MATCH (u:User) RETURN count(u)")
        rels = self._query("MATCH (:User)-[r:FOLLOWS]->(:User) RETURN count(r)")
        return int(nodes[1][0][0]), int(rels[1][0][0])

    def traversal(self, start_id: int, hops: int) -> int:
        result = self._query(
            f"MATCH (s:User {{user_id: $user_id}})-[:FOLLOWS*1..{hops}]->(x) "
            "RETURN count(DISTINCT x)",
            {"user_id": start_id},
        )
        return int(result[1][0][0])

    def point_lookup(self, user_id: int) -> int:
        result = self._query(
            "MATCH (u:User) WHERE u.user_id = $user_id RETURN count(u)",
            {"user_id": user_id},
        )
        return int(result[1][0][0])

    def indexed_lookup(self, country: str) -> int:
        result = self._query(
            "MATCH (u:User) WHERE u.country = $country RETURN count(u)",
            {"country": country},
        )
        return int(result[1][0][0])

    def aggregate(self) -> int:
        result = self._query("MATCH (u:User) RETURN u.country, count(*) ORDER BY count(*) DESC")
        return len(result[1]) if len(result) > 1 else 0

    def mixed_write(self, src: int, dst: int, seq: int) -> None:
        self._query(
            "MATCH (a:User {user_id: $src}), (b:User {user_id: $dst}) "
            "CREATE (a)-[:BENCHMARK_WRITE {seq: $seq}]->(b)",
            {"src": src, "dst": dst, "seq": seq},
        )
