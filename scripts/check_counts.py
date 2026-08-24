from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from graphbench.runner import make_adapter

for name in ("cognodb", "neo4j_aura"):
    try:
        adapter = make_adapter(name)
        print(name, adapter.counts())
        adapter.close()
    except Exception as exc:
        print(name, type(exc).__name__, exc)
