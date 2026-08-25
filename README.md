# Graph Database Cloud Benchmark

A reproducible, protocol-aware benchmark harness for the Wexa AI take-home assignment. The project compares **CognoDB Cloud** as a managed reference with Neo4j Community, Memgraph, FalkorDB Server, and ArangoDB in a controlled local Docker comparison using the same public graph topology, the same client machine, the same logical workloads, and percentile-based reporting.

> **Important:** This repository never contains passwords, connection URIs, or fabricated performance numbers. Raw benchmark results are generated only after the operator supplies credentials and runs the commands below.

## Scope and platform selection

The final run uses CognoDB Cloud as a managed reference and four local Docker engines: Neo4j Community, Memgraph, FalkorDB Server, and ArangoDB. CognoDB, Neo4j, and Memgraph use Bolt-compatible drivers; FalkorDB uses Redis/OpenCypher; ArangoDB uses REST/AQL. The formal resource-parity decision rule is in [`config/resource-parity.md`](config/resource-parity.md): unequal tiers are not silently normalized, and CognoDB is excluded from the equal-resource Docker ranking because it cannot run as a local peer from the supplied access.

| Platform | Access used for this benchmark | Client protocol | Resource-parity record |
|---|---|---|---|
| CognoDB Cloud | c0 free instance | Bolt + Cypher | Advertised c0 values from the assignment: burstable 0.5 vCPU, 256 MB RAM, 1 GB disk |
| Neo4j Community Docker | `neo4j:2026.07.1` | Bolt + Cypher | 0.5 CPU; 512 MB RAM; 1 GB writable layer |
| Memgraph Docker | `memgraph/memgraph:2.14.1` | Bolt + Memgraph dialect | 0.5 CPU; 512 MB RAM; 1 GB writable layer |
| FalkorDB Server Docker | `falkordb/falkordb-server:latest` | Redis protocol + OpenCypher | 0.5 CPU; 512 MB RAM; 1 GB writable layer; latest tag digest retained in inspect file |
| ArangoDB Docker | `arangodb:3.12.4` | HTTP REST + AQL | 0.5 CPU; 512 MB RAM; 1 GB writable layer |

The assignment asks for at least four comparison targets in addition to CognoDB. The final run covers five total targets: CognoDB Cloud, Neo4j Community Docker, Memgraph Docker, FalkorDB Server Docker, and ArangoDB Docker. Arango is implemented through its REST/AQL API, and FalkorDB through Redis/OpenCypher, which keeps query-language differences explicit rather than pretending all products share one protocol. All five targets completed the measured run.

The final Docker comparison uses a common 512 MB memory and 1 GB writable-layer envelope. The CognoDB reference uses its fixed c0 allocation and is not part of the equal-resource ranking.

## Dataset

The benchmark uses the official Stanford Network Analysis Project **soc-Pokec** relationship graph. SNAP reports 1,632,803 nodes and 30,622,564 directed edges in the full graph [1]. The preparation script downloads the official relationship file and takes a deterministic prefix sample of 150,000 non-self-loop relationships. It writes `nodes.csv`, `edges.csv`, and a manifest containing the exact node and relationship counts.

The topology is real public data. Because the source relationship file is anonymized, the benchmark adds stable, non-sensitive properties derived from each anonymized ID (`name`, `country`, and `age`) solely to exercise point, filtered, and aggregation queries. The README does not claim these annotations are original Pokec profile fields.

```bash
python scripts/prepare_pokec.py --out data/pokec_sample --relationships 150000
```

The source page and citation are recorded in `data/pokec_sample/MANIFEST.md`. Keep that manifest in the repository after preparation so the exact dataset size is visible to reviewers.

## Docker comparison topology

For the strict resource-parity run, the four comparison engines run locally in Docker on the same host, one benchmark at a time, while the benchmark client runs on that host. The Compose file declares **0.5 CPU, 512 MB RAM, and a 1 GB writable layer per service**. The local services are Neo4j Community, Memgraph, FalkorDB Server, and ArangoDB. CognoDB cannot be made a local Docker peer from the credentials supplied, so it remains the external managed reference at its fixed c0 allocation; its result is reported in a separate section with the client-to-cloud network caveat. The four Docker results are the equal-resource comparison, while CognoDB is a contextual reference rather than part of that ranking.

```bash
cp .env.docker.example .env.docker
mkdir -p docker-data/{neo4j,memgraph,falkordb,arango,arango-apps}
docker compose --env-file .env.docker -f docker-compose.local.yml up -d
docker compose --env-file .env.docker -f docker-compose.local.yml ps
```

The local Docker connection variables are `bolt://localhost:17687` for Neo4j, `bolt://localhost:27687` for Memgraph, Redis port `36379` for FalkorDB, and `http://localhost:18529` for ArangoDB. Before measuring, record the actual image tags or immutable digests and confirm that every container reports healthy. If Docker on the host does not support `storage_opt`, the run must record that storage was not hard-capped and must not call the comparison fully equal-resource. The 512 MB envelope was selected because the verified Memgraph 2.14.1 image exited with code 139 at 256 MB but stayed healthy at 512 MB. If any engine fails to start or cannot load the minimum 100,000 relationships within 512 MB, mark it as **not comparable under the common envelope** rather than raising its memory limit for only that engine.

Run the four local targets with:

```bash
graphbench run --database neo4j_docker --data data/pokec_sample --out results/neo4j_docker.json --warmup 10 --iterations 100 --clients 10
graphbench run --database memgraph_docker --data data/pokec_sample --out results/memgraph_docker.json --warmup 10 --iterations 100 --clients 10
graphbench run --database falkordb_docker --data data/pokec_sample --out results/falkordb_docker.json --warmup 10 --iterations 100 --clients 10
graphbench run --database arango_docker --data data/pokec_sample --out results/arango_docker.json --warmup 10 --iterations 100 --clients 10
```

Stop and remove the local data only after copying raw results:

```bash
docker compose --env-file .env.docker -f docker-compose.local.yml down
```

## Installation

Use Python 3.10 or later. A virtual environment is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
```

Copy `.env.example` to `.env` and fill it locally. The `.env` file is ignored by Git.

```bash
cp .env.example .env
```

## Connection configuration

The harness reads credentials only from environment variables. Required variables are:

| Platform | Required variables |
|---|---|
| CognoDB | `COGNODB_URI`, `COGNODB_PASSWORD`; default user is `cognodb` |
| Neo4j Aura | `NEO4J_AURA_URI`, `NEO4J_AURA_PASSWORD`; default user is `neo4j` |
| Memgraph | `MEMGRAPH_URI`, `MEMGRAPH_PASSWORD`; default user is `memgraph` unless overridden |
| FalkorDB | `FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_PASSWORD`, optional `FALKORDB_GRAPH`, `FALKORDB_SSL` |
| Arango Managed Platform | `ARANGO_URL`, `ARANGO_USER`, `ARANGO_PASSWORD`, optional `ARANGO_DATABASE` and collection names |

Record resource specifications in the corresponding `*_SPECS` variables. Include provider, region, advertised memory, vCPU, storage, and whether the value was observable or not. This is a methodology requirement, not optional metadata.

## Running the benchmark

Run each platform from the same client machine and, as far as possible, the same cloud region. The default is ten warm-up calls and 100 measured iterations per read workload, as required by the assignment.

```bash
graphbench run --database cognodb --data data/pokec_sample --out results/cognodb.json --warmup 10 --iterations 100 --clients 10
graphbench run --database neo4j_aura --data data/pokec_sample --out results/neo4j_aura.json --warmup 10 --iterations 100 --clients 10
graphbench run --database memgraph --data data/pokec_sample --out results/memgraph.json --warmup 10 --iterations 100 --clients 10
graphbench run --database falkordb --data data/pokec_sample --out results/falkordb.json --warmup 10 --iterations 100 --clients 10
graphbench run --database arango --data data/pokec_sample --out results/arango.json --warmup 10 --iterations 100 --clients 10
```

After all real runs complete:

```bash
graphbench report --results results --markdown results/summary.md --csv results/summary.csv
```

The raw JSON preserves individual observations, failures, host information, dataset counts, settings, and notes. The generated summary reports count, p50, p95, p99, mean, failed requests, and mixed-workload concurrency. The implementation uses a nearest-rank percentile definition so that the calculation is deterministic and easy to audit. The completed sanitized analysis is in [`results/final/FINAL_ANALYSIS.md`](results/final/FINAL_ANALYSIS.md), with supporting charts and resource records in the same directory.

## Workloads and fairness controls

Every adapter implements the same logical workload contract: node and relationship ingestion, 1-hop/2-hop/3-hop directed traversals from a deterministic set of start IDs, an unindexed point lookup, an indexed country lookup, a country aggregation, and concurrent benchmark writes. The Cypher syntax is kept inside the adapter because FalkorDB’s Redis/OpenCypher command surface is not the same as Bolt/Cypher.

The harness resets the database, loads the same CSV rows, verifies node and relationship counts, creates the required indexes, warms each read workload, measures 100 iterations, and records failures rather than hiding them. The mixed workload uses a stated client concurrency and emits sustained successful operations per second. Cold start numbers are not mixed into warm read measurements; if cold start behavior is important, run a separate documented pass after pausing or recreating the instance.

For a strong final submission, repeat mixed workload runs at 1, 10, and 40 clients where the smallest tier can tolerate it, then record throttling, timeouts, provider differences, network region, and any query-language incompatibilities. Do not compare a paid tier with a free tier while describing the result as fair.

## Results table template

The completed run is documented in [`results/final/FINAL_ANALYSIS.md`](results/final/FINAL_ANALYSIS.md); `results/summary.md` is the generated machine-readable summary table.

| Database | Workload | p50 (ms) | p95 (ms) | Successful | Failed | Notes |
|---|---|---:|---:|---:|---:|---|
| CognoDB reference | See generated `results/summary.md` | — | — | — | — | Managed c0 reference |
| Neo4j Community Docker | See generated `results/summary.md` | — | — | — | — | Equal-resource Docker comparison |
| Memgraph Docker | See generated `results/summary.md` | — | — | — | — | Equal-resource Docker comparison |
| FalkorDB Server Docker | See generated `results/summary.md` | — | — | — | — | Equal-resource Docker comparison |
| ArangoDB Docker | See generated `results/summary.md` | — | — | — | — | Equal-resource Docker comparison |

The final report includes every required metric for every database: ingestion throughput and wall time; p50/p95 for 1-hop, 2-hop, and 3-hop traversals; p50/p95 for point and indexed/filtered lookup; p50/p95 for aggregation; mixed read/write throughput with concurrency; and observable footprint. Use “not observable” when a managed service does not expose a metric.

## Known limitations and honest caveats

The benchmark is networked: client-to-cloud latency, routing, TLS, throttling, instance idling, and transient provider load can dominate very small queries. The dataset sampler uses a deterministic prefix rather than a statistically representative graph sample; this is reproducible but should be stated in the final analysis. The harness does not infer hidden vCPU or memory values. If a console or container runtime does not expose a value, report “not observable.”

The implementation records the sustained successful operation rate for the configured 50% read / 50% write task mix, not as a vendor-independent database QPS number. The raw samples record per-operation mixed-workload latency and concurrency.

## References

[1]: https://snap.stanford.edu/data/soc-Pokec.html "SNAP Pokec social network dataset"
[2]: https://neo4j.com/videos/getting-started-with-aura-free-tier/ "Neo4j AuraDB Free tier overview"
[3]: https://docs.falkordb.com/cloud/tiers/free "FalkorDB Cloud Free Tier"
[4]: https://memgraph.com/docs/help-center/faq "Memgraph FAQ and resource requirements"
[5]: https://cognodb.com/developers "CognoDB Cloud developer documentation"
