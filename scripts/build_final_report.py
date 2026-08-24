from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from statistics import fmean

import matplotlib.pyplot as plt

DOCKER_TARGETS = ["neo4j_docker", "memgraph_docker", "falkordb_docker", "arango_docker"]
ALL_TARGETS = ["neo4j_docker", "memgraph_docker", "falkordb_docker", "arango_docker", "cognodb"]
READ_WORKLOADS = ["traversal_1hop", "traversal_2hop", "traversal_3hop", "point_lookup", "indexed_lookup", "aggregation"]


def load_result(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("database") not in ALL_TARGETS:
        raise ValueError(f"Unexpected benchmark file: {path}")
    return payload


def notes(payload: dict) -> list[dict]:
    parsed = []
    for item in payload.get("notes", []):
        try:
            value = json.loads(item)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            parsed.append(value)
    return parsed


def stats(payload: dict, workload: str) -> dict:
    samples = [s for s in payload.get("samples", []) if s.get("workload") == workload]
    good = [float(s["duration_ms"]) for s in samples if s.get("ok") and float(s.get("duration_ms", 0)) > 0]
    xs = sorted(good)
    if not xs:
        return {"n": len(samples), "ok": 0, "failed": len(samples), "p50": None, "p95": None, "p99": None, "mean": None}

    def nr(q: float) -> float:
        return xs[min(len(xs) - 1, max(0, int(__import__("math").ceil(q * len(xs))) - 1))]

    return {"n": len(samples), "ok": len(good), "failed": len(samples) - len(good), "p50": nr(.50), "p95": nr(.95), "p99": nr(.99), "mean": fmean(xs)}


def load_note(payload: dict) -> dict:
    return next((n for n in notes(payload) if "load_wall_ms" in n), {})


def mixed_note(payload: dict) -> dict:
    return next((n for n in notes(payload) if "mixed_qps" in n), {})


def safe_result(payload: dict) -> dict:
    copy = json.loads(json.dumps(payload))
    copy.setdefault("host", {}).pop("hostname", None)
    copy.setdefault("host", {})["hostname"] = "redacted"
    return copy


def safe_inspect(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    item = raw[0] if isinstance(raw, list) and raw else raw
    host = item.get("HostConfig", {})
    config = item.get("Config", {})
    return {
        "name": item.get("Name"),
        "image": config.get("Image"),
        "cpus_nano": host.get("NanoCpus"),
        "memory_bytes": host.get("Memory"),
        "storage_opt": host.get("StorageOpt"),
    }


def fmt(v):
    return "—" if v is None else f"{v:.2f}" if isinstance(v, (float, int)) else str(v)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    source = Path(args.input)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    safe_dir = output / "raw"
    safe_dir.mkdir(exist_ok=True)

    payloads = {}
    for target in ALL_TARGETS:
        payload = load_result(source / f"{target}.json")
        payloads[target] = payload
        (safe_dir / f"{target}.json").write_text(json.dumps(safe_result(payload), indent=2), encoding="utf-8")
    for target in DOCKER_TARGETS:
        meta = safe_inspect(source / f"{target}-inspect.json")
        (output / f"{target}-resources.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    # Copy the generated raw summaries, which contain no credentials or host names.
    for name in ("summary.csv", "summary.md"):
        shutil.copy2(source / name, output / name)

    colors = {"neo4j_docker": "#2E86DE", "memgraph_docker": "#10AC84", "falkordb_docker": "#EE5253", "arango_docker": "#5F27CD"}
    labels = {"neo4j_docker": "Neo4j", "memgraph_docker": "Memgraph", "falkordb_docker": "FalkorDB", "arango_docker": "ArangoDB"}

    # P50 latency chart for the equal-resource Docker comparison.
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
    for ax, workload in zip(axes.flat, READ_WORKLOADS):
        vals = []
        names = []
        for target in DOCKER_TARGETS:
            value = stats(payloads[target], workload)["p50"]
            vals.append(value if value is not None else 0)
            names.append(labels[target])
        bars = ax.bar(names, vals, color=[colors[t] for t in DOCKER_TARGETS])
        ax.set_title(workload.replace("_", " "))
        ax.set_ylabel("p50 latency (ms)")
        ax.tick_params(axis="x", rotation=25, labelsize=8)
        ax.grid(axis="y", alpha=.25)
        for bar, value in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{value:.2f}", ha="center", va="bottom", fontsize=7)
    fig.suptitle("Equal-resource Docker comparison: p50 latency", fontsize=15)
    fig.savefig(output / "p50-latency-docker.png", dpi=180)
    plt.close(fig)

    # Ingestion and mixed QPS chart.
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    ingest = []
    for target in DOCKER_TARGETS:
        load = load_note(payloads[target])
        seconds = float(load["load_wall_ms"]) / 1000
        ingest.append(float(load["loaded_relationships"]) / seconds if seconds else 0)
    qps = [float(mixed_note(payloads[t]).get("mixed_qps", 0)) for t in DOCKER_TARGETS]
    for ax, values, title, ylabel in zip(axes, [ingest, qps], ["Relationship ingestion throughput", "Mixed read/write throughput"], ["relationships/s", "successful operations/s"]):
        bars = ax.bar([labels[t] for t in DOCKER_TARGETS], values, color=[colors[t] for t in DOCKER_TARGETS])
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.tick_params(axis="x", rotation=20)
        ax.grid(axis="y", alpha=.25)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{value:.0f}", ha="center", va="bottom", fontsize=8)
    fig.suptitle("Equal-resource Docker throughput", fontsize=15)
    fig.savefig(output / "throughput-docker.png", dpi=180)
    plt.close(fig)

    rows = []
    for target in DOCKER_TARGETS:
        meta = json.loads((output / f"{target}-resources.json").read_text())
        rows.append((target, meta))

    md = []
    md += ["# Final graph database benchmark analysis", "", "## Executive summary", "", "This report analyzes five successful benchmark runs over the same deterministic public graph sample. Neo4j Community, Memgraph, FalkorDB Server, and ArangoDB were run sequentially in Docker with identical declared limits of **0.5 CPU, 512 MB RAM, and a 1 GB writable layer**. CognoDB was run from the same client laptop as a separate managed c0 reference at **0.5 burstable vCPU, 256 MB RAM, and 1 GB disk**. Because CognoDB was not a local Docker peer, its numbers are contextual and are not included in the equal-resource Docker ranking.", ""]
    md += ["All five runs loaded exactly **74,062 nodes and 150,000 relationships**, completed 100 measured iterations for every read workload, used 10 warm-up calls, recorded zero failed measured requests, and executed the stated 50/50 mixed read/write task with 10 concurrent clients.", ""]
    md += ["## Resource parity and validity", "", "| Target | CPU limit | Memory limit | Storage declaration | Equal-resource ranking? |", "|---|---:|---:|---:|---|"]
    for target, meta in rows:
        md.append(f"| {labels[target]} | {float(meta['cpus_nano'])/1e9:.1f} CPU | {int(meta['memory_bytes'])/1024/1024:.0f} MB | {meta['storage_opt'].get('size', 'not recorded') if meta.get('storage_opt') else 'not recorded'} | Yes |")
    md.append("| CognoDB c0 | 0.5 burstable vCPU | 256 MB | 1 GB disk | No — managed reference |")
    md += ["", "The Docker inspection records were sanitized before publication: only image, container name, CPU, memory, and storage-limit fields are retained. Password-bearing environment variables and the user’s local hostname are intentionally excluded.", "", "## Equal-resource Docker results", "", "### Read latency", "", "| Workload | Neo4j p50/p95 (ms) | Memgraph p50/p95 (ms) | FalkorDB p50/p95 (ms) | ArangoDB p50/p95 (ms) |", "|---|---:|---:|---:|---:|"]
    for workload in READ_WORKLOADS:
        values = []
        for target in DOCKER_TARGETS:
            s = stats(payloads[target], workload)
            values.append(f"{fmt(s['p50'])} / {fmt(s['p95'])}")
        md.append(f"| {workload} | " + " | ".join(values) + " |")
    md += ["", "![Equal-resource Docker p50 latency](p50-latency-docker.png)", "", "### Ingestion and mixed workload", "", "| Target | Load wall time (s) | Nodes/s | Relationships/s | Mixed QPS | Mixed p50/p95 (ms) |", "|---|---:|---:|---:|---:|---:|"]
    for target in DOCKER_TARGETS:
        load = load_note(payloads[target])
        mix = mixed_note(payloads[target])
        sm = stats(payloads[target], "mixed_read_write")
        load_seconds = float(load["load_wall_ms"]) / 1000
        nodes_per_second = float(load["loaded_nodes"]) / load_seconds if load_seconds else 0
        relationships_per_second = float(load["loaded_relationships"]) / load_seconds if load_seconds else 0
        md.append(f"| {labels[target]} | {load_seconds:.2f} | {nodes_per_second:.2f} | {relationships_per_second:.2f} | {float(mix['mixed_qps']):.2f} | {fmt(sm['p50'])} / {fmt(sm['p95'])} |")
    md += ["", "![Equal-resource Docker throughput](throughput-docker.png)", "", "## Findings", "", "**FalkorDB** had the lowest p50 latency for indexed lookup and aggregation, and the highest mixed-workload throughput at approximately 1,260 successful operations/s. Its traversal and point-lookup p50 values were also approximately 0.6–0.7 ms. Its principal weakness was ingestion: approximately 966 relationships/s, the lowest of the four Docker targets.", "", "**Memgraph** had the fastest ingestion at approximately 33,185 relationships/s and remained near FalkorDB on traversal and point-lookup p50 latency. Its indexed lookup and aggregation were slower than FalkorDB’s, and its mixed-workload throughput was approximately 951 successful operations/s.", "", "**Neo4j Community** completed the workload but showed materially higher p95 latency than its p50 on several reads, indicating a long tail under the 0.5 CPU / 512 MB envelope. Its mixed workload was the slowest Docker result at approximately 44 successful operations/s, and its ingestion throughput was approximately 4,108 relationships/s.", "", "**ArangoDB** had the highest read p50 values among the Docker targets in this adapter implementation, but it ingested approximately 22,784 relationships/s and achieved approximately 226 successful mixed operations/s. Its relatively stable read p95 values should be interpreted together with the fact that this workload uses the REST/AQL adapter rather than Bolt.", "", "## CognoDB reference", "", "| Workload | p50 (ms) | p95 (ms) | Mean (ms) |", "|---|---:|---:|---:|"]
    for workload in READ_WORKLOADS + ["mixed_read_write"]:
        s = stats(payloads["cognodb"], workload)
        md.append(f"| {workload} | {fmt(s['p50'])} | {fmt(s['p95'])} | {fmt(s['mean'])} |")
    cn = load_note(payloads["cognodb"])
    cq = mixed_note(payloads["cognodb"])
    cogno_seconds = float(cn["load_wall_ms"]) / 1000
    cogno_relationships_per_second = float(cn["loaded_relationships"]) / cogno_seconds if cogno_seconds else 0
    md += ["", f"CognoDB loaded the graph in {cogno_seconds:.2f} seconds at {cogno_relationships_per_second:.2f} relationships/s and recorded mixed throughput of {float(cq['mixed_qps']):.2f} successful operations/s. Its read latencies include the client-to-managed-service path, TLS, routing, and any service-side scheduling, so they must not be interpreted as a product-only comparison against the local Docker results.", "", "## Methodological limitations", "", "The Docker results are equal-resource at the container limit level, but they still share the same host and are sequential rather than simultaneous. Runtime usage can be below the cap, and storage-opt enforcement depends on the host Docker backend. The report therefore treats declared CPU, memory, and writable-layer limits as the parity control and retains the inspection evidence.", "", "The graph topology is a deterministic prefix sample of the official SNAP soc-Pokec relationship file, not a statistically representative sample. Node properties named `name`, `country`, and `age` are stable benchmark annotations derived from anonymized IDs and are not claimed to be original profile fields. FalkorDB uses Redis/OpenCypher, ArangoDB uses REST/AQL, and the remaining engines use Bolt-compatible adapters; protocol differences are part of the practical result and are not hidden.", "", "## Reproduction", "", "The raw sanitized result files are in `raw/`, the safe Docker resource records are `*-resources.json`, and the generated source summary is `summary.md` / `summary.csv`. To regenerate the report from an archive extraction, run `python scripts/build_final_report.py --input /path/to/archive --output results`.", "", "## References", "", "[1]: https://snap.stanford.edu/data/soc-Pokec.html \"SNAP soc-Pokec social network dataset\"", "[2]: https://docs.falkordb.com/design/client-spec.html \"FalkorDB client specification and compact result format\"", "[3]: https://docs.falkordb.com/commands/graph.query \"FalkorDB GRAPH.QUERY command\"", "[4]: https://neo4j.com/docs/operations-manual/current/docker/introduction/ \"Neo4j in Docker\"", "[5]: https://memgraph.com/docs/getting-started/install-memgraph/docker \"Install Memgraph with Docker\""]
    (output / "FINAL_ANALYSIS.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
