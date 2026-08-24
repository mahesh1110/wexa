from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import requests

from graphbench.core import EdgeRow, NodeRow


@dataclass
class ArangoConfig:
    name: str
    base_url: str
    user: str
    password: str
    database: str = "_system"
    users_collection: str = "benchmark_users"
    edges_collection: str = "benchmark_follows"


class ArangoAdapter:
    """Small REST/AQL adapter for Arango Managed Platform / ArangoDB."""

    def __init__(self, config: ArangoConfig):
        self.config = config
        self.session = requests.Session()
        self.session.auth = (config.user, config.password)
        self.session.headers.update({"content-type": "application/json"})
        self.base = config.base_url.rstrip("/") + f"/_db/{config.database}"

    @property
    def name(self) -> str:
        return self.config.name

    def close(self) -> None:
        self.session.close()

    def _request(self, method: str, path: str, **kwargs):
        response = self.session.request(method, self.base + path, timeout=60, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}

    def _aql(self, query: str, bind_vars: dict | None = None):
        cursor = self._request("POST", "/_api/cursor", json={"query": query, "bindVars": bind_vars or {}, "batchSize": 1000})
        rows = cursor.get("result", [])
        while cursor.get("hasMore"):
            cursor_id = cursor.get("id") or cursor.get("_id")
            if not cursor_id:
                raise RuntimeError(f"Arango cursor indicated more rows but returned no cursor id: {cursor!r}")
            cursor = self._request("PUT", f"/_api/cursor/{cursor_id}")
            rows.extend(cursor.get("result", []))
        return rows

    def ping(self) -> None:
        self._request("GET", "/_api/version")

    def _ensure_collection(self, name: str, edge: bool = False) -> None:
        try:
            self._request("GET", f"/_api/collection/{name}")
        except requests.HTTPError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise
            self._request("POST", "/_api/collection", json={"name": name, "type": 3 if edge else 2})

    def reset(self) -> None:
        self._ensure_collection(self.config.users_collection)
        self._ensure_collection(self.config.edges_collection, edge=True)
        self._aql(f"FOR d IN `{self.config.edges_collection}` REMOVE d IN `{self.config.edges_collection}`")
        self._aql(f"FOR d IN `{self.config.users_collection}` REMOVE d IN `{self.config.users_collection}`")

    def create_schema(self) -> None:
        self._ensure_collection(self.config.users_collection)
        self._ensure_collection(self.config.edges_collection, edge=True)
        for fields in (("user_id",), ("country",)):
            try:
                self._request("POST", f"/_api/index?collection={self.config.users_collection}", json={"type": "persistent", "fields": list(fields)})
            except requests.HTTPError as exc:
                if exc.response is None or exc.response.status_code not in (400, 409):
                    raise

    def load_batch(self, nodes: Iterable[NodeRow], edges: Iterable[EdgeRow]) -> None:
        node_docs = [{"_key": str(n.user_id), "user_id": n.user_id, "name": n.name, "country": n.country, "age": n.age} for n in nodes]
        edge_docs = [{"_from": f"{self.config.users_collection}/{e.src}", "_to": f"{self.config.users_collection}/{e.dst}", "weight": e.weight} for e in edges]
        if node_docs:
            self._request("POST", f"/_api/document?collection={self.config.users_collection}&overwrite=true", json=node_docs)
        if edge_docs:
            self._request("POST", f"/_api/document?collection={self.config.edges_collection}&overwrite=true", json=edge_docs)

    def counts(self) -> tuple[int, int]:
        result = self._aql(
            f"RETURN [LENGTH(`{self.config.users_collection}`), LENGTH(`{self.config.edges_collection}`)]"
        )
        return int(result[0][0]), int(result[0][1])

    def traversal(self, start_id: int, hops: int) -> int:
        result = self._aql(
            f"FOR v IN 1..{hops} OUTBOUND @start `{self.config.edges_collection}` COLLECT id = v.user_id WITH COUNT INTO c RETURN c",
            {"start": f"{self.config.users_collection}/{start_id}"},
        )
        return sum(int(x) for x in result)

    def point_lookup(self, user_id: int) -> int:
        return int(self._aql(f"FOR u IN `{self.config.users_collection}` FILTER u.user_id == @id COLLECT WITH COUNT INTO c RETURN c", {"id": user_id})[0])

    def indexed_lookup(self, country: str) -> int:
        return int(self._aql(f"FOR u IN `{self.config.users_collection}` FILTER u.country == @country COLLECT WITH COUNT INTO c RETURN c", {"country": country})[0])

    def aggregate(self) -> int:
        return len(self._aql(f"FOR u IN `{self.config.users_collection}` COLLECT country = u.country WITH COUNT INTO c SORT c DESC RETURN {{country, c}}"))

    def mixed_write(self, src: int, dst: int, seq: int) -> None:
        self._aql(
            f"INSERT {{_from: CONCAT(@users, '/', @src), _to: CONCAT(@users, '/', @dst), seq: @seq}} INTO `{self.config.edges_collection}`",
            {"users": self.config.users_collection, "src": src, "dst": dst, "seq": seq},
        )
