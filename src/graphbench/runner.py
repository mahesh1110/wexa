from __future__ import annotations

import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from graphbench.core import (
    BenchmarkRun,
    EdgeRow,
    NodeRow,
    Sample,
    choose_start_ids,
    host_fingerprint,
    timed_call,
    utc_now,
)
from graphbench.drivers.bolt import BoltAdapter, BoltConfig
from graphbench.drivers.falkordb import FalkorAdapter, FalkorConfig
from graphbench.drivers.arango import ArangoAdapter, ArangoConfig


COUNTRIES = ("IN", "US", "DE", "GB", "BR", "JP", "CA", "AU")


def progress(message: str) -> None:
    print(f"[graphbench] {message}", file=sys.stderr, flush=True)


def load_dataset(path: str | Path) -> tuple[list[NodeRow], list[EdgeRow]]:
    path = Path(path)
    nodes: list[NodeRow] = []
    edges: list[EdgeRow] = []
    with (path / "nodes.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            nodes.append(NodeRow(int(row["user_id"]), row["name"], row["country"], int(row["age"])))
    with (path / "edges.csv").open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            edges.append(EdgeRow(int(row["src"]), int(row["dst"]), float(row["weight"])))
    return nodes, edges


def make_adapter(name: str):
    load_dotenv(".env")
    load_dotenv(".env.docker", override=False)
    key = name.upper().replace("-", "_")
    if name in {"cognodb", "neo4j_aura", "memgraph", "neo4j_docker", "memgraph_docker"}:
        if name == "neo4j_aura":
            uri = os.environ.get("NEO4J_AURA_URI") or os.environ["NEO4J_URI"]
            user = os.environ.get("NEO4J_AURA_USER") or os.environ.get("NEO4J_USERNAME", "neo4j")
            password = os.environ.get("NEO4J_AURA_PASSWORD") or os.environ["NEO4J_PASSWORD"]
            database = os.environ.get("NEO4J_AURA_DATABASE") or os.environ.get("NEO4J_DATABASE")
        elif name == "neo4j_docker":
            uri = os.environ.get("NEO4J_DOCKER_URI", "bolt://localhost:17687")
            user = os.environ.get("LOCAL_NEO4J_USER", "neo4j")
            password = os.environ.get("LOCAL_NEO4J_PASSWORD", "graphbench_neo4j")
            database = os.environ.get("NEO4J_DOCKER_DATABASE")
        elif name == "memgraph_docker":
            uri = os.environ.get("MEMGRAPH_DOCKER_URI", "bolt://localhost:27687")
            user = None
            password = None
            database = None
        else:
            uri = os.environ[f"{key}_URI"]
            user = os.environ.get(f"{key}_USER", "cognodb" if name == "cognodb" else "neo4j")
            password = os.environ[f"{key}_PASSWORD"]
            database = os.environ.get(f"{key}_DATABASE")
        encrypted = not name.endswith("_docker")
        return BoltAdapter(BoltConfig(name, uri, user, password, database, encrypted=encrypted))
    if name == "arango_docker":
        return ArangoAdapter(ArangoConfig(
            name=name,
            base_url=os.environ.get("ARANGO_DOCKER_URL", "http://localhost:18529"),
            user="root",
            password=os.environ.get("LOCAL_ARANGO_PASSWORD", "graphbench_arango"),
            database=os.environ.get("ARANGO_DOCKER_DATABASE", "_system"),
        ))
    if name == "arango":
        return ArangoAdapter(ArangoConfig(
            name=name,
            base_url=os.environ["ARANGO_URL"],
            user=os.environ.get("ARANGO_USER") or os.environ.get("ARANGO_USERNAME", "root"),
            password=os.environ["ARANGO_PASSWORD"],
            database=os.environ.get("ARANGO_DATABASE", "_system"),
            users_collection=os.environ.get("ARANGO_USERS_COLLECTION", "benchmark_users"),
            edges_collection=os.environ.get("ARANGO_EDGES_COLLECTION", "benchmark_follows"),
        ))
    if name == "falkordb_docker":
        return FalkorAdapter(FalkorConfig(
            name=name,
            host="localhost",
            port=int(os.environ.get("FALKORDB_DOCKER_PORT", "36379")),
            password=os.environ.get("LOCAL_FALKORDB_PASSWORD", "graphbench_falkordb"),
            graph=os.environ.get("FALKORDB_DOCKER_GRAPH", "benchmark"),
            ssl=False,
        ))
    if name == "falkordb":
        return FalkorAdapter(FalkorConfig(
            name=name,
            host=os.environ["FALKORDB_HOST"],
            port=int(os.environ.get("FALKORDB_PORT", "6379")),
            password=os.environ["FALKORDB_PASSWORD"],
            graph=os.environ.get("FALKORDB_GRAPH", "benchmark"),
            ssl=os.environ.get("FALKORDB_SSL", "true").lower() == "true",
        ))
    raise ValueError(f"Unsupported database: {name}")


def timed_samples(database: str, workload: str, fn: Callable[[], Any], iterations: int, concurrency: int | None = None) -> list[Sample]:
    samples: list[Sample] = []
    progress(f"{database}: {workload} — {iterations} measured iterations")
    for index in range(iterations):
        started = utc_now()
        try:
            _, duration_ms = timed_call(fn)
            samples.append(Sample(workload, database, started, duration_ms, True, concurrency=concurrency))
        except Exception as exc:
            samples.append(Sample(workload, database, started, 0.0, False, repr(exc), concurrency))
        if (index + 1) % 10 == 0 or index + 1 == iterations:
            progress(f"{database}: {workload} — completed {index + 1}/{iterations}")
    return samples


def cycling(values: list[Any]) -> Callable[[], Any]:
    index = 0

    def next_value() -> Any:
        nonlocal index
        value = values[index % len(values)]
        index += 1
        return value

    return next_value


def run_benchmark(database: str, data_dir: str, out_path: str, warmup: int = 10, iterations: int = 100, clients: int = 10) -> None:
    nodes, edges = load_dataset(data_dir)
    adapter = make_adapter(database)
    started_at = utc_now()
    samples: list[Sample] = []
    notes: list[str] = []
    try:
        progress(f"{database}: ping")
        adapter.ping()
        progress(f"{database}: reset")
        adapter.reset()
        # Build lookup structures before relationship ingestion; otherwise each
        # edge batch may scan all loaded users on small cloud tiers.
        progress(f"{database}: create schema")
        adapter.create_schema()
        load_start = time.perf_counter()
        batch_size = int(os.environ.get("GRAPHBENCH_BATCH_SIZE", "1000"))
        progress(f"{database}: loading {len(nodes)} nodes and {len(edges)} relationships with batch_size={batch_size}")
        for i in range(0, len(nodes), batch_size):
            adapter.load_batch(nodes[i:i + batch_size], [])
            if (i // batch_size + 1) % 5 == 0 or i + batch_size >= len(nodes):
                progress(f"{database}: nodes {min(i + batch_size, len(nodes))}/{len(nodes)}")
        for i in range(0, len(edges), batch_size):
            adapter.load_batch([], edges[i:i + batch_size])
            if (i // batch_size + 1) % 5 == 0 or i + batch_size >= len(edges):
                progress(f"{database}: relationships {min(i + batch_size, len(edges))}/{len(edges)}")
        load_ms = (time.perf_counter() - load_start) * 1000
        progress(f"{database}: counting loaded graph")
        n_count, r_count = adapter.counts()
        progress(f"{database}: loaded counts nodes={n_count}, relationships={r_count}")
        notes.append(json.dumps({"load_wall_ms": load_ms, "loaded_nodes": n_count, "loaded_relationships": r_count}))
        start_ids = choose_start_ids(nodes, min(iterations, 100), seed=20260824)
        countries = [COUNTRIES[i % len(COUNTRIES)] for i in range(iterations)]
        for hops in (1, 2, 3):
            for j in range(warmup):
                adapter.traversal(start_ids[j % len(start_ids)], hops)
            next_id = cycling(start_ids)
            samples.extend(timed_samples(database, f"traversal_{hops}hop", lambda h=hops: adapter.traversal(next_id(), h), iterations))

        for j in range(warmup):
            adapter.point_lookup(start_ids[j % len(start_ids)])
        next_id = cycling(start_ids)
        samples.extend(timed_samples(database, "point_lookup", lambda: adapter.point_lookup(next_id()), iterations))

        for j in range(warmup):
            adapter.indexed_lookup(countries[j % len(countries)])
        next_country = cycling(countries)
        samples.extend(timed_samples(database, "indexed_lookup", lambda: adapter.indexed_lookup(next_country()), iterations))

        for _ in range(warmup):
            adapter.aggregate()
        samples.extend(timed_samples(database, "aggregation", adapter.aggregate, iterations))

        def mixed_operation(index: int) -> None:
            if index % 2 == 0:
                adapter.point_lookup(start_ids[index % len(start_ids)])
            else:
                adapter.mixed_write(start_ids[index % len(start_ids)], start_ids[(index + 1) % len(start_ids)], index)

        progress(f"{database}: mixed_read_write — {iterations} concurrent operations, clients={clients}")
        mixed_start = time.perf_counter()
        mixed_ok = 0
        with ThreadPoolExecutor(max_workers=clients) as pool:
            submitted = {pool.submit(mixed_operation, i): (utc_now(), time.perf_counter()) for i in range(iterations)}
            for index, future in enumerate(as_completed(submitted)):
                seq_started, operation_start = submitted[future]
                duration_ms = (time.perf_counter() - operation_start) * 1000
                try:
                    future.result()
                    mixed_ok += 1
                    samples.append(Sample("mixed_read_write", database, seq_started, duration_ms, True, concurrency=clients))
                except Exception as exc:
                    samples.append(Sample("mixed_read_write", database, seq_started, duration_ms, False, error=repr(exc), concurrency=clients))
                if (index + 1) % 10 == 0 or index + 1 == iterations:
                    progress(f"{database}: mixed_read_write — completed {index + 1}/{iterations}")
        mixed_seconds = time.perf_counter() - mixed_start
        notes.append(json.dumps({"mixed_clients": clients, "mixed_ok": mixed_ok, "mixed_qps": mixed_ok / mixed_seconds if mixed_seconds else 0.0, "read_fraction": 0.5, "write_fraction": 0.5}))
    finally:
        adapter.close()

    run = BenchmarkRun(
        database=database,
        started_at=started_at,
        finished_at=utc_now(),
        host=host_fingerprint(),
        platform={"name": database, "resource_specs": os.environ.get(f"{database.upper()}_SPECS", "not recorded")},
        dataset={"directory": str(data_dir), "nodes": len(nodes), "relationships": len(edges)},
        settings={"warmup": warmup, "iterations": iterations, "mixed_clients": clients},
        samples=samples,
        notes=notes,
    )
    run.write_json(out_path)


def summarize_results(results_dir: str, output_path: str) -> None:
    from graphbench.report import summarize_directory
    summary = summarize_directory(results_dir)
    Path(output_path).write_text(json.dumps(summary, indent=2), encoding="utf-8")
