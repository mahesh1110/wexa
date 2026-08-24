from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from graphbench.core import percentiles


def summarize_directory(results_dir: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(results_dir).glob("*.json")):
        if path.name.endswith("-docker-inspect.json") or path.name.endswith("_docker-inspect.json"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or "database" not in payload or "samples" not in payload:
            continue
        note_objects = []
        for note in payload.get("notes", []):
            try:
                note_objects.append(json.loads(note))
            except json.JSONDecodeError:
                pass
        load_note = next((n for n in note_objects if "load_wall_ms" in n), None)
        mixed_note = next((n for n in note_objects if "mixed_qps" in n), None)
        if load_note:
            load_seconds = float(load_note["load_wall_ms"]) / 1000
            rows.append({
                "database": payload["database"],
                "workload": "ingest",
                "count": load_note.get("loaded_relationships", 0),
                "p50": None,
                "p95": None,
                "p99": None,
                "mean": None,
                "successful": load_note.get("loaded_nodes", 0),
                "failed": 0,
                "concurrency": None,
                "load_wall_ms": load_note["load_wall_ms"],
                "nodes_per_second": load_note.get("loaded_nodes", 0) / load_seconds if load_seconds else None,
                "relationships_per_second": load_note.get("loaded_relationships", 0) / load_seconds if load_seconds else None,
            })
        if mixed_note:
            rows.append({
                "database": payload["database"],
                "workload": "mixed_read_write_qps",
                "count": mixed_note.get("mixed_ok", 0),
                "p50": None,
                "p95": None,
                "p99": None,
                "mean": mixed_note.get("mixed_qps"),
                "successful": mixed_note.get("mixed_ok", 0),
                "failed": 0,
                "concurrency": mixed_note.get("mixed_clients"),
                "load_wall_ms": None,
                "nodes_per_second": None,
                "relationships_per_second": None,
            })
        for workload in sorted({s["workload"] for s in payload.get("samples", [])}):
            samples = [s for s in payload["samples"] if s["workload"] == workload and s["ok"]]
            stats = percentiles(s["duration_ms"] for s in samples if s["duration_ms"] > 0)
            rows.append({
                "database": payload["database"],
                "workload": workload,
                **stats,
                "successful": len(samples),
                "failed": sum(1 for s in payload.get("samples", []) if s["workload"] == workload and not s["ok"]),
                "concurrency": next((s.get("concurrency") for s in samples if s.get("concurrency") is not None), None),
                "load_wall_ms": None,
                "nodes_per_second": None,
                "relationships_per_second": None,
            })
    return {"rows": rows}


def render_markdown(summary: dict[str, Any]) -> str:
    rows = summary.get("rows", [])
    lines = [
        "| Database | Workload | n | p50 (ms) | p95 (ms) | p99 (ms) | Mean (ms) | Failed | Concurrency | Load ms | Nodes/s | Relationships/s |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        def fmt(value: Any) -> str:
            return "—" if value is None else f"{value:.2f}" if isinstance(value, float) else str(value)
        lines.append(
            f"| {row['database']} | {row['workload']} | {row['count']} | {fmt(row['p50'])} | "
            f"{fmt(row['p95'])} | {fmt(row['p99'])} | {fmt(row['mean'])} | {row['failed']} | "
            f"{row['concurrency'] or '—'} | {fmt(row.get('load_wall_ms'))} | {fmt(row.get('nodes_per_second'))} | "
            f"{fmt(row.get('relationships_per_second'))} |"
        )
    return "\n".join(lines) + "\n"


def write_reports(results_dir: str, markdown_path: str, csv_path: str) -> None:
    summary = summarize_directory(results_dir)
    Path(markdown_path).write_text(render_markdown(summary), encoding="utf-8")
    rows = summary["rows"]
    with Path(csv_path).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["database", "workload"])
        writer.writeheader()
        writer.writerows(rows)
