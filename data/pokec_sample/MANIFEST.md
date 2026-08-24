# Dataset manifest

The graph topology is a deterministic first-150,000-relationship sample from the official SNAP soc-Pokec relationship file.

| Field | Value |
|---|---|
| Source | [SNAP Pokec](https://snap.stanford.edu/data/soc-Pokec.html) |
| Relationship count | 150,000 |
| Node count | 74,062 |
| Sampling seed | 20260824 |
| Sampling method | Prefix of non-self-loop relationships after deterministic source processing |
| Orientation | Directed, as provided by SNAP |
| Node properties | Stable benchmark annotations derived from anonymized IDs; not source profile claims |

The same `nodes.csv` and `edges.csv` files were loaded into every target. CognoDB was measured as a separate managed c0 reference; Neo4j Community, Memgraph, FalkorDB Server, and ArangoDB were measured in Docker under the common local resource envelope documented in `config/resource-parity.md`.
