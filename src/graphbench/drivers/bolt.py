from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from neo4j import GraphDatabase

from graphbench.core import EdgeRow, NodeRow


@dataclass
class BoltConfig:
    name: str
    uri: str
    user: str | None
    password: str | None
    database: str | None = None
    encrypted: bool = True


class BoltAdapter:
    """Adapter for Neo4j-compatible Bolt + Cypher services.

    CognoDB, Neo4j Aura, and Memgraph can use this path, but the README records
    each product's protocol and feature caveats separately.
    """

    def __init__(self, config: BoltConfig):
        self.config = config
        driver_kwargs = {}
        if config.user is not None and config.password is not None:
            driver_kwargs["auth"] = (config.user, config.password)
        # Neo4j's Python driver infers TLS from bolt+s/neo4j+s URI schemes;
        # passing encrypted=True alongside those schemes is invalid.
        if config.uri.startswith(("bolt://", "neo4j://")):
            driver_kwargs["encrypted"] = config.encrypted
        self.driver = GraphDatabase.driver(config.uri, **driver_kwargs)

    @property
    def name(self) -> str:
        return self.config.name

    def close(self) -> None:
        self.driver.close()

    def _session(self):
        kwargs: dict[str, Any] = {}
        if self.config.database:
            kwargs["database"] = self.config.database
        return self.driver.session(**kwargs)

    def ping(self) -> None:
        with self._session() as s:
            s.run("RETURN 1 AS ok").consume()

    def reset(self) -> None:
        with self._session() as s:
            s.run("MATCH (n) DETACH DELETE n").consume()

    def create_schema(self) -> None:
        with self._session() as s:
            if self.config.name in {"memgraph", "memgraph_docker"}:
                # Memgraph does not implement Neo4j's constraint syntax. The
                # dataset has unique IDs by construction, so a property index
                # is sufficient for lookup performance on this benchmark.
                queries = (
                    "CREATE INDEX ON :User(user_id)",
                    "CREATE INDEX ON :User(country)",
                )
                for query in queries:
                    try:
                        s.run(query).consume()
                    except Exception as exc:
                        # Re-runs retain schema objects; duplicate-index errors
                        # are safe to ignore, while other errors must surface.
                        if "already exists" not in str(exc).lower() and "exists" not in str(exc).lower():
                            raise
            else:
                for query in (
                    "CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE",
                    "CREATE INDEX user_country IF NOT EXISTS FOR (u:User) ON (u.country)",
                ):
                    try:
                        s.run(query).consume()
                    except Exception:
                        # Some compatible services accept the older index syntax.
                        if "user_country" in query:
                            s.run("CREATE INDEX ON :User(country)").consume()
                        else:
                            raise

    def load_batch(self, nodes: Iterable[NodeRow], edges: Iterable[EdgeRow]) -> None:
        node_rows = [{"user_id": n.user_id, "name": n.name, "country": n.country, "age": n.age} for n in nodes]
        edge_rows = [{"src": e.src, "dst": e.dst, "weight": e.weight} for e in edges]
        with self._session() as s:
            if node_rows:
                s.run(
                    "UNWIND $rows AS row CREATE (:User {user_id: row.user_id, "
                    "name: row.name, country: row.country, age: row.age})",
                    rows=node_rows,
                ).consume()
            if edge_rows:
                s.run(
                    "UNWIND $rows AS row MATCH (a:User {user_id: row.src}), "
                    "(b:User {user_id: row.dst}) CREATE (a)-[r:FOLLOWS]->(b) "
                    "SET r.weight = row.weight",
                    rows=edge_rows,
                ).consume()

    def counts(self) -> tuple[int, int]:
        with self._session() as s:
            n = s.run("MATCH (u:User) RETURN count(u) AS c").single()["c"]
            r = s.run("MATCH (:User)-[x:FOLLOWS]->(:User) RETURN count(x) AS c").single()["c"]
            return int(n), int(r)

    def traversal(self, start_id: int, hops: int) -> int:
        query = (
            f"MATCH (s:User {{user_id: $user_id}})-[:FOLLOWS*1..{hops}]->(x) "
            "RETURN count(DISTINCT x) AS c"
        )
        with self._session() as s:
            return int(s.run(query, user_id=start_id).single()["c"])

    def point_lookup(self, user_id: int) -> int:
        with self._session() as s:
            return int(s.run(
                "MATCH (u:User) WHERE u.user_id = $user_id RETURN count(u) AS c",
                user_id=user_id,
            ).single()["c"])

    def indexed_lookup(self, country: str) -> int:
        with self._session() as s:
            return int(s.run(
                "MATCH (u:User) WHERE u.country = $country RETURN count(u) AS c",
                country=country,
            ).single()["c"])

    def aggregate(self) -> int:
        with self._session() as s:
            return sum(1 for _ in s.run(
                "MATCH (u:User) RETURN u.country AS country, count(*) AS c ORDER BY c DESC"
            ))

    def mixed_write(self, src: int, dst: int, seq: int) -> None:
        with self._session() as s:
            s.run(
                "MATCH (a:User {user_id: $src}), (b:User {user_id: $dst}) "
                "MERGE (a)-[r:BENCHMARK_WRITE {seq: $seq}]->(b)",
                src=src,
                dst=dst,
                seq=seq,
            ).consume()
