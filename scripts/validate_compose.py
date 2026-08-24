from __future__ import annotations

from pathlib import Path
import yaml

compose = yaml.safe_load(Path("docker-compose.local.yml").read_text(encoding="utf-8"))
services = compose["services"]
assert set(services) == {"neo4j", "memgraph", "falkordb", "arango"}
for name, service in services.items():
    assert service["cpus"] == "0.5", name
    assert service["mem_limit"] == "256m", name
    assert service["storage_opt"]["size"] == "1G", name
print(f"validated {len(services)} services at 0.5 CPU / 256 MB / 1 GB")
