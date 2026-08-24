# Official Docker source notes

- Neo4j Operations Manual: https://neo4j.com/docs/operations-manual/current/docker/introduction/
  - The official image is available on Docker Hub.
  - The documented current example uses `neo4j:2026.07.1`.
  - The container exposes Bolt on port 7687 and Browser on 7474.
  - `NEO4J_AUTH=neo4j/<password>` sets the initial credentials.
- Memgraph Docker documentation: https://memgraph.com/docs/getting-started/install-memgraph/docker
  - The documented quickstart uses `memgraph/memgraph-mage`.
  - The database client port is 7687; port 7444 is for log streaming to Memgraph Lab.

These notes support image/port choices only. Final benchmark README must record the exact image digests or tags actually used during the run.
