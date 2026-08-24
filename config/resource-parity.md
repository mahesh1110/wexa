# Resource-parity policy

The assignment’s primary comparison must not mix a 256 MB CognoDB c0 instance with multi-gigabyte local databases. Before any result is called a fair comparison, record the provider, region, vCPU, memory, storage, plan, and observability status for every target.

## Decision rule

1. Prefer the smallest managed tier that can run the complete dataset and workloads on every platform.
2. If managed tiers differ materially, do not normalize the numbers or claim a winner. Label the run **constrained / not equal resources** and explain the differences.
3. A controlled self-hosted comparison is valid only when every self-hosted database is run on the same host, in the same region, one at a time, with identical CPU, memory, and storage limits. A suggested Docker shape is `--cpus=0.5 --memory=256m` plus a dedicated 1 GB volume, but it must be verified as a viable runtime for each product. If a database cannot start or load the minimum 100,000 relationships under that envelope, it is not comparable under that configuration.
4. CognoDB remains a managed external endpoint. Its network path is not identical to a laptop-local or VM-local deployment. The final analysis must therefore separate **database execution/resource effects** from **client-to-service network effects**.
5. If the fairness gate fails for a platform, retain its connectivity and compatibility notes if useful, but exclude its performance values from the equal-resource ranking.

## Required run record

| Field | Example value | Source |
|---|---|---|
| Platform and plan | CognoDB c0 | Console or assignment |
| Provider and region | AWS / ap-south-1 | Console |
| vCPU | 0.5 burstable | Console or published documentation |
| RAM | 256 MB | Console or published documentation |
| Storage | 1 GB | Console or published documentation |
| Client region | Record once for the benchmark host | Host/cloud metadata |
| Dataset fit | Pass/fail and observed footprint | Database console or API |
| Observability | Exact metric or `not observable` | Product documentation/console |

The raw JSON result must carry the same resource-specification string used in the README. Never infer hidden CPU, RAM, or storage from latency.
