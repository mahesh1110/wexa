from __future__ import annotations

import argparse
import json
from pathlib import Path

from graphbench.report import write_reports
from graphbench.runner import run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(prog="graphbench")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run one database benchmark")
    run.add_argument("--database", required=True, choices=["cognodb", "neo4j_aura", "neo4j_docker", "memgraph_docker", "falkordb_docker", "arango_docker", "memgraph", "falkordb", "arango"])
    run.add_argument("--data", default="data/pokec_sample")
    run.add_argument("--out", default=None)
    run.add_argument("--warmup", type=int, default=10)
    run.add_argument("--iterations", type=int, default=100)
    run.add_argument("--clients", type=int, default=10)

    report = sub.add_parser("report", help="Build Markdown and CSV summaries from raw JSON results")
    report.add_argument("--results", default="results")
    report.add_argument("--markdown", default="results/summary.md")
    report.add_argument("--csv", default="results/summary.csv")

    args = parser.parse_args()
    if args.command == "run":
        out = args.out or f"results/{args.database}.json"
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        run_benchmark(args.database, args.data, out, args.warmup, args.iterations, args.clients)
        print(f"Wrote {out}")
    elif args.command == "report":
        write_reports(args.results, args.markdown, args.csv)
        print(f"Wrote {args.markdown} and {args.csv}")


if __name__ == "__main__":
    main()
