# Risk Demo (Single Namespace)

Base Kubernetes environment for collecting pod eviction / OOM risk training data.

## Contents
- `namespace.yaml`: Creates the `risk-demo` namespace.
- `priority-classes.yaml`: Defines three PriorityClasses (low, medium, high) mapped to -10 / 0 / +10.
- `resource-constraints.yaml`: Namespace ResourceQuota & LimitRange (caps CPU/memory; constrains per-container resources).
- `kube-state-metrics.yaml`: Observability addon (labels/metrics context; not used for usage values which come from metrics-server).
- `victim-pod-template.yaml`: Victim pod template (pause + stress sidecar) parameterized via placeholder tokens replaced by the generator.
- `stress-pod-template.yaml`: Stress pod template used to induce cluster pressure.

## Purpose
Provides a deterministic sandbox for the data generator (`services/generate-data/generate_data.py`) to:
1. Launch victim pods with varied resource specs & priority.
2. Launch stress pods to raise node pressure.
3. Observe, collect usage metrics (metrics-server), and assign `risk` labels.

## Apply
Preferred via Make:
```bash
make risk-demo-apply
```

Manual:
```bash
kubectl apply -f deploy/k8s/risk-demo/
```

Verify:
```bash
kubectl get ns risk-demo
kubectl get priorityclasses | grep -E 'low|medium|high'
kubectl -n risk-demo get resourcequota,limitrange
```

## Generate Data (Local Single Mode)
```bash
make datagen-local-setup      # venv + deps
make datagen-local            # runs generator (heuristic or ground-truth depending on cluster)
```

For a quick test run:
```bash
OBSERVE_SECONDS=60 N_CYCLES=3 make datagen-local
```

Output: `data/pod_risk_data.csv` (or fast combined file in parallel mode)

## Labeling Modes
- Ground truth: Run cluster with strict eviction (`make minikube-start-oom`); generator detects OOMKilled/Evicted.
- Heuristic: Standard cluster; generator infers high/medium by memory usage ratio thresholds.

## Placeholder Tokens (victim template)
Replaced during generation:
- `victim-PLACEHOLDER`
- `PRIORITY_PLACEHOLDER`
- `CPU_REQ_PLACEHOLDER`, `CPU_LIM_PLACEHOLDER`
- `MEM_REQ_PLACEHOLDER`, `MEM_LIM_PLACEHOLDER`
- Workload sizing: `WORKLOAD_MEM_BYTES`, `WORKLOAD_MEM_LIMIT`, optional VM count tokens.

## Cleanup
```bash
make risk-demo-delete           # Removes namespace & all resources
```
Or manually:
```bash
kubectl delete -f deploy/k8s/risk-demo/ --ignore-not-found
```

## Relationship to Fast Mode
Fast parallel mode lives in `deploy/k8s/risk-demo-fast/` and adds a second namespace (`risk-demo-b`) plus tuned templates for shorter cycles. Use:
```bash
make risk-demo-fast-apply
make datagen-fast-parallel
```

## Troubleshooting
- Missing metrics: Ensure `metrics-server` addon enabled (`minikube addons enable metrics-server`).
- Quota exceeded errors: Reduce victim/stress counts or lower requested CPU/memory.
- Few high labels: Tighten thresholds (`HEUR_HIGH_RATIO`, `HEUR_MED_RATIO`) or increase workload memory sidecar size.
- Flat node pressure: Increase stress pod workers or VM bytes.

## Next Steps
- See `docs/architecture.md` for end-to-end workflow.
- See `docs/eviction-tuning.md` for enabling ground-truth eviction events.
