#!/usr/bin/env python3
"""Download and sample the official SNAP soc-Pokec relationships file.

The topology is real public data from SNAP. The extra node properties are
stable benchmark annotations derived from the anonymized user ID; they are not
claimed to be original profile attributes.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import io
import random
import shutil
import urllib.request
from pathlib import Path

REL_URL = "https://snap.stanford.edu/data/soc-pokec-relationships.txt.gz"
README_URL = "https://snap.stanford.edu/data/soc-pokec-readme.txt"


def download(url: str, path: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as response, path.open("wb") as out:
        shutil.copyfileobj(response, out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/pokec_sample")
    parser.add_argument("--relationships", type=int, default=150_000)
    parser.add_argument("--seed", type=int, default=20260824)
    args = parser.parse_args()
    if args.relationships < 100_000:
        raise SystemExit("The assignment requires at least 100,000 relationships.")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw = out / "soc-pokec-relationships.txt.gz"
    source_readme = out / "soc-pokec-readme.txt"
    if not raw.exists():
        print(f"Downloading {REL_URL}")
        download(REL_URL, raw)
    if not source_readme.exists():
        download(README_URL, source_readme)

    rng = random.Random(args.seed)
    edges: list[tuple[int, int]] = []
    with gzip.open(raw, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            src, dst = int(parts[0]), int(parts[1])
            if src != dst:
                edges.append((src, dst))
            if len(edges) >= args.relationships:
                break
    if len(edges) < 100_000:
        raise RuntimeError(f"Only found {len(edges)} usable edges")

    node_ids = sorted({x for e in edges for x in e})
    with (out / "nodes.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "name", "country", "age"])
        for user_id in node_ids:
            # Stable, non-sensitive benchmark annotations for indexed/grouped queries.
            writer.writerow([user_id, f"user-{user_id}", ("IN", "US", "DE", "GB", "BR", "JP", "CA", "AU")[user_id % 8], 18 + (user_id % 63)])

    with (out / "edges.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["src", "dst", "weight"])
        for src, dst in edges:
            writer.writerow([src, dst, f"{0.5 + rng.random():.6f}"])

    (out / "MANIFEST.md").write_text(
        f"""# Dataset manifest\n\n"
        f"The graph topology is a deterministic first-{len(edges):,}-relationship sample from the official SNAP soc-Pokec relationship file.\n\n"
        f"- Source: [SNAP Pokec](https://snap.stanford.edu/data/soc-Pokec.html)\n"
        f"- Relationship count: {len(edges):,}\n"
        f"- Node count: {len(node_ids):,}\n"
        f"- Sampling seed: {args.seed}\n"
        f"- Orientation: directed, as provided by SNAP\n"
        f"- Node properties: stable benchmark annotations derived from anonymized IDs, not source profile claims\n""",
        encoding="utf-8",
    )
    print(f"Wrote {len(node_ids):,} nodes and {len(edges):,} relationships to {out}")


if __name__ == "__main__":
    main()
