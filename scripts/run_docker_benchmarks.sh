#!/usr/bin/env bash
set -euo pipefail

COMPOSE=(docker compose --env-file .env.docker -f docker-compose.local.yml)
mkdir -p results docker-data/{neo4j,memgraph,falkordb,arango,arango-apps}
# Ensure no idle database container competes with the target under test.
"${COMPOSE[@]}" down --remove-orphans

for pair in \
  "neo4j:neo4j_docker" \
  "memgraph:memgraph_docker" \
  "falkordb:falkordb_docker" \
  "arango:arango_docker"; do
  service="${pair%%:*}"
  target="${pair##*:}"
  echo "==> Starting ${service}"
  "${COMPOSE[@]}" up -d "${service}"
  "${COMPOSE[@]}" ps
  container="graphbench-${service}"
  docker inspect "${container}" > "results/${target}.docker-inspect.json"
  echo "==> Running ${target}"
  graphbench run --database "${target}" --data data/pokec_sample --out "results/${target}.json" --warmup 10 --iterations 100 --clients 10
  echo "==> Stopping ${service} before the next engine"
  "${COMPOSE[@]}" stop "${service}"
done

graphbench report --results results --markdown results/summary.md --csv results/summary.csv
printf '%s\n' 'Docker benchmark complete. Review results/summary.md and the inspect files before publishing.'
