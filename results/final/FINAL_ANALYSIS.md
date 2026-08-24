# Final graph database benchmark analysis

## Executive summary

This report analyzes five successful benchmark runs over the same deterministic public graph sample. Neo4j Community, Memgraph, FalkorDB Server, and ArangoDB were run sequentially in Docker with identical declared limits of **0.5 CPU, 512 MB RAM, and a 1 GB writable layer**. CognoDB was run from the same client laptop as a separate managed c0 reference at **0.5 burstable vCPU, 256 MB RAM, and 1 GB disk**. Because CognoDB was not a local Docker peer, its numbers are contextual and are not included in the equal-resource Docker ranking.

All five runs loaded exactly **74,062 nodes and 150,000 relationships**, completed 100 measured iterations for every read workload, used 10 warm-up calls, recorded zero failed measured requests, and executed the stated 50/50 mixed read/write task with 10 concurrent clients.

## Resource parity and validity

| Target | CPU limit | Memory limit | Storage declaration | Equal-resource ranking? |
|---|---:|---:|---:|---|
| Neo4j | 0.5 CPU | 512 MB | 1G | Yes |
| Memgraph | 0.5 CPU | 512 MB | 1G | Yes |
| FalkorDB | 0.5 CPU | 512 MB | 1G | Yes |
| ArangoDB | 0.5 CPU | 512 MB | 1G | Yes |
| CognoDB c0 | 0.5 burstable vCPU | 256 MB | 1 GB disk | No — managed reference |

The Docker inspection records were sanitized before publication: only image, container name, CPU, memory, and storage-limit fields are retained. Password-bearing environment variables and the user’s local hostname are intentionally excluded.

## Equal-resource Docker results

### Read latency

| Workload | Neo4j p50/p95 (ms) | Memgraph p50/p95 (ms) | FalkorDB p50/p95 (ms) | ArangoDB p50/p95 (ms) |
|---|---:|---:|---:|---:|
| traversal_1hop | 4.21 / 80.43 | 0.62 / 1.23 | 0.63 / 0.81 | 43.98 / 47.64 |
| traversal_2hop | 3.12 / 71.48 | 0.56 / 0.74 | 0.61 / 0.86 | 43.98 / 46.63 |
| traversal_3hop | 2.83 / 76.58 | 0.63 / 1.32 | 0.63 / 0.98 | 43.98 / 47.69 |
| point_lookup | 2.18 / 6.30 | 0.55 / 0.72 | 0.58 / 0.76 | 44.08 / 47.19 |
| indexed_lookup | 2.68 / 55.91 | 5.54 / 49.25 | 1.49 / 2.00 | 47.56 / 49.05 |
| aggregation | 15.14 / 101.61 | 16.88 / 66.21 | 7.80 / 56.35 | 56.80 / 60.27 |

![Equal-resource Docker p50 latency](p50-latency-docker.png)

### Ingestion and mixed workload

| Target | Load wall time (s) | Nodes/s | Relationships/s | Mixed QPS | Mixed p50/p95 (ms) |
|---|---:|---:|---:|---:|---:|
| Neo4j | 36.52 | 2028.20 | 4107.77 | 43.82 | 1773.30 / 2269.50 |
| Memgraph | 4.52 | 16384.89 | 33184.82 | 951.19 | 78.35 / 95.54 |
| FalkorDB | 155.26 | 477.02 | 966.12 | 1260.44 | 13.76 / 69.71 |
| ArangoDB | 6.58 | 11249.74 | 22784.44 | 226.24 | 212.01 / 404.62 |

![Equal-resource Docker throughput](throughput-docker.png)

## Findings

**FalkorDB** had the lowest p50 latency for indexed lookup and aggregation, and the highest mixed-workload throughput at approximately 1,260 successful operations/s. Its traversal and point-lookup p50 values were also approximately 0.6–0.7 ms. Its principal weakness was ingestion: approximately 966 relationships/s, the lowest of the four Docker targets.

**Memgraph** had the fastest ingestion at approximately 33,185 relationships/s and remained near FalkorDB on traversal and point-lookup p50 latency. Its indexed lookup and aggregation were slower than FalkorDB’s, and its mixed-workload throughput was approximately 951 successful operations/s.

**Neo4j Community** completed the workload but showed materially higher p95 latency than its p50 on several reads, indicating a long tail under the 0.5 CPU / 512 MB envelope. Its mixed workload was the slowest Docker result at approximately 44 successful operations/s, and its ingestion throughput was approximately 4,108 relationships/s.

**ArangoDB** had the highest read p50 values among the Docker targets in this adapter implementation, but it ingested approximately 22,784 relationships/s and achieved approximately 226 successful mixed operations/s. Its relatively stable read p95 values should be interpreted together with the fact that this workload uses the REST/AQL adapter rather than Bolt.

## CognoDB reference

| Workload | p50 (ms) | p95 (ms) | Mean (ms) |
|---|---:|---:|---:|
| traversal_1hop | 263.42 | 266.14 | 263.82 |
| traversal_2hop | 263.45 | 267.80 | 265.29 |
| traversal_3hop | 263.82 | 281.39 | 276.23 |
| point_lookup | 263.06 | 264.91 | 263.38 |
| indexed_lookup | 281.40 | 318.19 | 284.44 |
| aggregation | 398.06 | 473.45 | 403.38 |
| mixed_read_write | 2567.75 | 3748.04 | 2545.25 |

CognoDB loaded the graph in 28.77 seconds at 5214.62 relationships/s and recorded mixed throughput of 25.34 successful operations/s. Its read latencies include the client-to-managed-service path, TLS, routing, and any service-side scheduling, so they must not be interpreted as a product-only comparison against the local Docker results.

## Methodological limitations

The Docker results are equal-resource at the container limit level, but they still share the same host and are sequential rather than simultaneous. Runtime usage can be below the cap, and storage-opt enforcement depends on the host Docker backend. The report therefore treats declared CPU, memory, and writable-layer limits as the parity control and retains the inspection evidence.

The graph topology is a deterministic prefix sample of the official SNAP soc-Pokec relationship file, not a statistically representative sample. Node properties named `name`, `country`, and `age` are stable benchmark annotations derived from anonymized IDs and are not claimed to be original profile fields. FalkorDB uses Redis/OpenCypher, ArangoDB uses REST/AQL, and the remaining engines use Bolt-compatible adapters; protocol differences are part of the practical result and are not hidden.

## Reproduction

The raw sanitized result files are in `raw/`, the safe Docker resource records are `*-resources.json`, and the generated source summary is `summary.md` / `summary.csv`. To regenerate the report from an archive extraction, run `python scripts/build_final_report.py --input /path/to/archive --output results`.

## References

[1]: https://snap.stanford.edu/data/soc-Pokec.html "SNAP soc-Pokec social network dataset"
[2]: https://docs.falkordb.com/design/client-spec.html "FalkorDB client specification and compact result format"
[3]: https://docs.falkordb.com/commands/graph.query "FalkorDB GRAPH.QUERY command"
[4]: https://neo4j.com/docs/operations-manual/current/docker/introduction/ "Neo4j in Docker"
[5]: https://memgraph.com/docs/getting-started/install-memgraph/docker "Install Memgraph with Docker"
