from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from graphbench.runner import make_adapter

for name in ("cognodb", "neo4j_aura", "memgraph", "falkordb", "arango"):
    try:
        adapter = make_adapter(name)
        adapter.ping()
        adapter.close()
        print(f"{name}: reachable")
    except Exception as exc:
        print(f"{name}: unavailable ({type(exc).__name__}: {exc})")
