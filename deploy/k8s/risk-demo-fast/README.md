# Fast Mode Assets

This directory provides alternative manifests to accelerate data generation:

- `victim-pod-template.yaml`: Minimal pause container (128Mi) so most memory limit applies only to workload container. Reduces total namespace limit footprint.
- `stress-pod-template.yaml`: Same shape as standard; used with lower METRICS_WAIT_SECONDS for faster cycles.
- `namespace-b.yaml`: Optional second namespace (`risk-demo-b`) with identical quotas for parallel generation.

## Usage (Makefile Targets Preferred)

Recommended workflow (fast parallel runs):
```bash
make datagen-local-setup         # create venv and install deps
make risk-demo-fast-apply        # optional second namespace (risk-demo-b)
make datagen-fast-parallel       # start A + B runs in background
make datagen-fast-checkpoint     # (optional) mid-run snapshot CSVs
make datagen-fast-merge          # merge final A/B CSVs when complete
```

Manual (single namespace) invocation if needed:
```bash
TEMPLATES_DIR=deploy/k8s/risk-demo-fast \
OBSERVE_SECONDS=180 METRICS_WAIT_SECONDS=30 \
VICTIMS_MIN=4 VICTIMS_MAX=4 STRESS_MIN=1 STRESS_MAX=1 \
HEUR_HIGH_RATIO=0.80 HEUR_MED_RATIO=0.65 \
N_CYCLES=40 OUTPUT_PATH=./data/pod_risk_data_fast_ns_a.csv \
services/generate-data/.venv/bin/python services/generate-data/generate_data.py
```

To run second namespace in parallel manually:
```bash
NAMESPACE=risk-demo-b TEMPLATES_DIR=deploy/k8s/risk-demo-fast \
OBSERVE_SECONDS=180 METRICS_WAIT_SECONDS=30 \
VICTIMS_MIN=4 VICTIMS_MAX=4 STRESS_MIN=1 STRESS_MAX=1 \
HEUR_HIGH_RATIO=0.80 HEUR_MED_RATIO=0.65 \
N_CYCLES=40 OUTPUT_PATH=./data/pod_risk_data_fast_ns_b.csv \
services/generate-data/.venv/bin/python services/generate-data/generate_data.py
```

Merge (Makefile does this; manual alternative):
```bash
awk 'FNR==1 && NR!=1 {next} {print}' \
  data/pod_risk_data_fast_ns_a.csv data/pod_risk_data_fast_ns_b.csv \
  > data/pod_risk_data_fast_combined.csv
```

## Expected Throughput
- ~4 victims per cycle * 40 cycles * 2 namespaces ≈ 320 rows
- Cycle time ≈ 180s observe + 30s metrics wait + overhead ≈ ~3.7 min → 40 cycles ≈ 2.5 hours (parallel halves wall time)

## Notes
- Keep thresholds at 0.80/0.65 to ensure label variance under shorter observe windows.
- If high labels drop, increase workload_mem or lower HEUR_MED_RATIO further (e.g. 0.60).
- Avoid raising pod memory limits too high or you may re-hit the namespace quota when parallelizing.
- Use `make datagen-fast-checkpoint` to write `_checkpoint` CSVs mid-run without stopping generators.
