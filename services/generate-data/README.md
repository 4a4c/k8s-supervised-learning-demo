# Data Generation Service

Generates training data for pod OOM/Eviction risk prediction by:
1. Creating victim pods with varied resource specs and priorities
2. Creating stress pods to induce resource pressure
3. Observing pod behavior (90s test mode, 180s full mode)
4. Querying metrics-server for node/pod metrics
5. Labeling each victim based on OOMKilled/Evicted status (ground truth) or memory pressure (heuristic)

## Prerequisites

- Minikube cluster running
  - For ground-truth labels: `make minikube-start-oom` (6Gi, strict eviction)
  - For heuristic labels: `make minikube-start-ml` (8Gi, standard)
- Risk demo infrastructure: `make risk-demo-apply`
- Local Python venv: `make datagen-local-setup`

## Usage (Fast Mode - Recommended)

Use the Makefile fast-mode targets for consistent, parallel data collection:

```bash
make datagen-local-setup          # one-time venv for generator
make risk-demo-fast-apply         # optional: add risk-demo-b namespace
make datagen-fast-parallel        # start A + B runs in background
make datagen-fast-checkpoint      # (optional) write mid-run checkpoint CSVs
make datagen-fast-merge           # merge final CSVs when runs complete
```

Outputs:
- `data/pod_risk_data_fast_ns_a.csv` and `..._ns_b.csv` — per-namespace
- `data/pod_risk_data_fast_combined.csv` — merged final CSV
- `*_checkpoint.csv` — mid-run snapshots written via SIGUSR1

## Configuration

### Fast Mode presets
- 40 cycles per namespace
- 180s observation window + 30s metrics wait
- 4 victim pods + 1 stress pod per cycle
- ~300–320 combined rows when running A+B in parallel

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `N_CYCLES` | 40 | Number of experiment cycles (per namespace) |
| `OBSERVE_SECONDS` | 180 | Observation window per cycle |
| `VICTIMS_MIN/MAX` | 4-4 | Victim pods per cycle (fast mode) |
| `STRESS_MIN/MAX` | 1-1 | Stress pods per cycle |
| `HEUR_HIGH_RATIO` | 1.0 | Memory usage ≥ this → high (heuristic) |
| `HEUR_MED_RATIO` | 0.9 | Memory usage ≥ this → medium (heuristic) |
| `MAX_CPU_M` | 500 | Max CPU limit per container (millicores) |
| `MAX_MEM_MI` | 1024 | Max memory limit per container (MiB) |
| `TEMPLATES_DIR` | `deploy/k8s/risk-demo-fast` | Pod template directory (fast) |
| `OUTPUT_PATH` | e.g. `./data/pod_risk_data_fast_ns_a.csv` | Output CSV path |

## Output

**CSV columns:**
- `cpu_request_m`, `cpu_limit_m`, `mem_request_mi`, `mem_limit_mi` — Pod resource spec
- `priority` — Priority class (-10, 0, 10)
- `node_cpu_pressure_pct`, `node_mem_pressure_pct` — Cluster pressure
- `pod_cpu_usage_pct`, `pod_mem_usage_mi` — Pod usage
- `risk` — Label: low, medium, high
- `label_source` — ground_truth (OOM/Evicted) or heuristic
- `risk_intended` — Profile assigned (low/medium/high)

## Label Logic

**Ground truth (label_source=ground_truth):**
- Pod or container terminated with reason `OOMKilled` → high
- Pod or container terminated with reason `Evicted` → medium

**Heuristic fallback (label_source=heuristic):**
- Any container memory usage ≥ HEUR_HIGH_RATIO of its limit → high
- Any container memory usage ≥ HEUR_MED_RATIO of its limit → medium
- Otherwise → low

Note: Thresholds are configurable via env vars. For faster runs where we want clear label variance within shorter observation windows, we commonly use `HEUR_HIGH_RATIO=0.80` and `HEUR_MED_RATIO=0.65`.

### Heuristic rationale and leakage

- Heuristic labels approximate escalating memory pressure when ground-truth OOM/Evict events are rare over short windows. This mirrors "early warning" behavior used by SRE tooling.
- Because the heuristic depends on memory usage vs limit, features like `pod_mem_usage_mi` and `mem_limit_mi` can encode the rule. The baseline trainer (`scripts/train_baseline.py`) supports a de-leaked variant (`--drop-leakage`) that removes those columns when training on heuristic-only labels.

## Checkpoint Writes (optional)

During long runs, you can write a checkpoint CSV of in-memory data without stopping the generator by sending SIGUSR1 to the process:

1. Find the PID in logs (the generator prints: "Send SIGUSR1 to PID <pid> to write checkpoint CSV").
2. Trigger a checkpoint:
  ```bash
  kill -USR1 <pid>
  ```
3. Checkpoint will be written alongside the output as `<OUTPUT_PATH>` with `_checkpoint` suffix, e.g. `data/pod_risk_data_fast_ns_a_checkpoint.csv`.

## Metrics Source

Uses metrics-server (`metrics.k8s.io/v1beta1`) exclusively:
- Node metrics: CPU/memory usage vs allocatable
- Pod metrics: Sum of container CPU/memory usage

**Timing:**
- Waits for all pods to be Running (up to 60s)
- Observes for configured window (90s or 180s)
- Waits additional 70s for metrics-server to scrape

## Cleanup

**Automatic:** Experiment pods (victim/stress) deleted after each cycle and on exit

**Manual:** `make datagen-cleanup-pods`, `...-b`, or `...-all`

## Troubleshooting

**All "low" labels in short tests:**
- OOM/Evict may not trigger in 90s windows on standard clusters
- Use `minikube-start-oom` for stricter eviction, or
- Lower heuristic thresholds: `HEUR_HIGH_RATIO=0.95 HEUR_MED_RATIO=0.85`

**Quota exceeded errors:**
- 6Gi cluster uses tighter quotas (5Gi namespace limit)
- Reduce stress limits via `STRESS_LIM_CPU=1 STRESS_LIM_MEM=1Gi`

**Zero metrics:**
- Ensure metrics-server addon enabled: `minikube addons enable metrics-server`
- Increase observation window: `OBSERVE_SECONDS=120` or longer
