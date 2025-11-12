# Architecture & Repo Layout

This repository demonstrates supervised learning for Kubernetes pod OOM/Eviction risk prediction. The workflow collects training data by stressing a minikube cluster, observing pod behavior, and labeling outcomes.

## Top-level directories

```
services/
  generate-data/        # Data generation script and requirements
deploy/
  k8s/
    risk-demo/          # Namespace, priority classes, resource constraints
                        # Pod templates (victim, stress)
    risk-demo-fast/     # Fast parallel mode manifests (dual namespaces a/b for higher throughput)
scripts/
  validate_data.py      # CSV quality check and ML-readiness assessment
  train_baseline.py     # RandomForest trainer with leakage mitigation
  train_and_demo.py     # CLI trainer + three-example demo (non-notebook)
  run_fast_parallel.sh  # Launch two generators concurrently (internal helper)
  requirements-ml.txt   # scikit-learn
data/                   # Generated CSV (gitignored)
docs/
  architecture.md       # This document
  eviction-tuning.md    # Kubelet settings for ground-truth labels
  dev-environment.md    # Dev Container setup
```

## Data Generation Architecture

### Components

**1. Risk Demo Environments**
- **Single-namespace mode** (`deploy/k8s/risk-demo/`): One namespace with ResourceQuota and LimitRange
- **Fast parallel mode** (`deploy/k8s/risk-demo-fast/`): Two namespaces (risk-demo-a, risk-demo-b) for concurrent generation
- Three PriorityClasses: low-priority (-10), medium-priority (0), high-priority (10)
- kube-state-metrics deployment for cluster observability

**2. Pod Templates**
- `victim-pod-template.yaml`: Target pod with pause + stress-ng sidecar workload
- `stress-pod-template.yaml`: Stress pod using stress-ng (CPU/memory load)

**3. Data Generator (`services/generate-data/generate_data.py`)**
- Creates victim pods with randomized resources and priorities (low/medium/high profiles)
- Creates stress pods to induce cluster pressure
- Observes pods for 90-180s
- Queries metrics-server for node and pod usage
- Labels victims based on OOMKilled/Evicted events or heuristic memory pressure
- Outputs CSV with features and risk labels
- Supports checkpoint writes via SIGUSR1 signal for long-running jobs

### Workflow

#### Standard Mode (Single Generator)
```
┌─────────────────────────────────────────────────────────────┐
│ 1. Setup Phase                                              │
│    - Start minikube (standard or strict eviction)           │
│    - Deploy risk-demo namespace, limits, priorities         │
│    - make risk-demo-apply                                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Collection Cycle (repeated N times)                      │
│    a) Create 2-12 victim pods (varied resources/priority)   │
│    b) Create 1-4 stress pods (CPU/memory pressure)          │
│    c) Wait for Running + observe (90-180s)                  │
│    d) Query metrics-server for node/pod usage               │
│    e) Check for OOMKilled/Evicted → label                   │
│    f) Cleanup victim/stress pods                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Output                                                   │
│    - CSV with features, labels, label_source                │
│    - make datagen-local (produces data/pod_risk_data.csv)   │
└─────────────────────────────────────────────────────────────┘
```
#### Fast Parallel Mode (Two Concurrent Generators)
```
┌─────────────────────────────────────────────────────────────┐
│ 1. Setup Phase                                              │
│    - Start minikube with adequate resources (4CPU/8GB)      │
│    - Deploy two namespaces (risk-demo-a, risk-demo-b)       │
│    - make risk-demo-fast-apply                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Parallel Collection (both generators run simultaneously) │
│    - Generator A → risk-demo-a → data/fast/a.csv            │
│    - Generator B → risk-demo-b → data/fast/b.csv            │
│    - make datagen-fast-parallel (launches both processes)   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Merge & Output                                           │
│    - Combine CSVs, deduplicate, shuffle                     │
│    - make datagen-fast-merge                                │
│    - Output: data/pod_risk_data_fast_combined.csv           │
└─────────────────────────────────────────────────────────────┘
```
#### Training (Both Modes)
```
┌─────────────────────────────────────────────────────────────┐
│ 4. Validation & Training                                    │
│    - Validate CSV quality (scripts/validate_data.py)        │
│    - Load CSV, drop leaky features if heuristic labels      │
│    - Train RandomForest classifier (scripts/train_baseline) │
│    - Or use pod_risk_evaluation.ipynb for full analysis     │
│    - Evaluate and report feature importances                │
└─────────────────────────────────────────────────────────────┘
```

## Label Provenance

### Ground Truth (label_source=ground_truth)
- Requires strict kubelet eviction (6Gi cluster, `minikube-start-oom`)
- Labels based on actual OOMKilled/Evicted pod terminations
- Slower but production-faithful

### Heuristic (label_source=heuristic)
- Works on standard clusters (`minikube-start` or `minikube-start-ml`)
- Labels based on memory usage vs limit ratio thresholds
- Faster iteration, tunable via `HEUR_HIGH_RATIO` and `HEUR_MED_RATIO`
- Training mitigates leakage by dropping `pod_mem_usage_mi` and `mem_limit_mi` features

## Metrics Architecture

**Source:** metrics-server (`metrics.k8s.io/v1beta1`)

**Node metrics:**
- CPU and memory usage vs allocatable → pressure percentages

**Pod metrics:**
- Sum of container CPU/memory usage
- CPU % computed as usage / sum of container limits
- Per-container memory/limit ratio used for heuristic labeling

**Timing:**
- Metrics-server scrapes every ~60s
- Generator waits 70s after observation window to ensure fresh data

### Dataset columns (pod_risk_data_fast_combined.csv)

The merged dataset produced by the fast workflow contains the following columns. Units and derivations are listed to avoid ambiguity.

- cpu_request_m (float): Pod CPU request in millicores (m). Example: 250 means 0.25 cores.
- cpu_limit_m (float): Pod CPU limit in millicores. Example: 1000 means 1 core.
- mem_request_mi (float): Pod memory request in mebibytes (MiB). Example: 512 MiB.
- mem_limit_mi (float): Pod memory limit in MiB. Example: 1024 MiB.
- priority (int): Numeric priority derived from PriorityClass: high=+10, medium=0, low=-10.
- node_cpu_pressure_pct (float): 100 × node CPU usage millicores / allocatable millicores at sampling time.
- node_mem_pressure_pct (float): 100 × node memory usage bytes / allocatable bytes at sampling time.
- pod_cpu_usage_pct (float): 100 × sum(container CPU usage m) / sum(container CPU limits m) for the pod.
- pod_mem_usage_mi (float): Sum of container memory usage in MiB across the pod at sampling time.
- risk (string): Target label: 'low' | 'medium' | 'high'.
- label_source (string, optional): 'ground_truth' if OOMKilled/Evicted observed; 'heuristic' if inferred by memory-usage ratio thresholds.
- risk_intended (string, optional): Intended risk profile used when creating the victim pod ('low' | 'medium' | 'high'); useful for QA, not for training.

Notes
- Leakage: When label_source='heuristic', mem_limit_mi and pod_mem_usage_mi directly influence the heuristic rule. Drop these columns at training time to prevent shortcut learning.
- Ranges: node_*_pressure_pct typically 0–100; pod_cpu_usage_pct can exceed 100 briefly if limits are very small or metrics lag, but in practice is ~0–120.
- Units: All memory quantities are MiB; all CPU quantities are in millicores (m) except percentages.

## Training Architecture

**Baseline model:** RandomForestClassifier (scikit-learn)

**Features:**
- Pod resource spec (CPU/memory requests and limits)
- Priority class (numeric)
- Node pressure (CPU/memory %)
- Pod usage (CPU %, memory MiB)

**Target:** `risk` (low / medium / high)

**Leakage mitigation:**
- When `label_source=heuristic` for all rows, drops `pod_mem_usage_mi` and `mem_limit_mi` features
- Prevents shortcut learning from heuristic labeling rule

**Evaluation:**
- Classification report (precision, recall, F1)
- Confusion matrix
- Feature importances

## Design Decisions

**Why metrics-server only?**
- Simpler: No Prometheus/node-exporter/cAdvisor deployment
- Sufficient: Provides node and pod metrics at ~60s resolution
- Reliable: Metrics-server is a standard addon

**Why two execution modes (local vs k8s Job)?**
- **Local mode** (`make datagen-local`): Fast iteration during development, direct logs, no image build overhead
- **Fast parallel mode** (`make datagen-fast-parallel`): Maximize throughput by running two generators concurrently in separate namespaces
- **K8s Job/CronJob deployment** (optional, see `deploy/k8s/generate-data/`): Production-ready scheduled data collection with RBAC, ServiceAccount, and persistent output

**Why two label sources?**
- Ground truth (Path A) for production-faithful models
- Heuristic (Path B) for fast prototyping and pipeline validation

**Why RandomForest baseline?**
- Interpretable: Feature importances reveal what drives risk
- Robust: Handles mixed numeric features without scaling
- Fast: Trains in seconds on ~1000 samples
- Strong baseline: Often competitive with complex models on tabular data

## Execution Modes

**Local (Development)**
```bash
make datagen-local-setup    # Create venv, install deps
make datagen-local          # Single run → data/pod_risk_data.csv
```

**Fast Parallel (Production Data Collection)**
```bash
make datagen-local-setup         # Same venv setup
make risk-demo-fast-apply        # Deploy two namespaces
make datagen-fast-parallel       # Launch parallel generators
make datagen-fast-merge          # Combine outputs → data/pod_risk_data_fast_combined.csv
```

**Kubernetes Job/CronJob (Scheduled Production)**
```bash
# Build and load image
make datagen-build
make datagen-load

# Deploy Job with RBAC
kubectl apply -f deploy/k8s/generate-data/
kubectl wait --for=condition=complete job/generate-data-job -n risk-demo --timeout=30m
kubectl logs job/generate-data-job -n risk-demo
```

## Future Extensions

- Temporal features (resource usage trends over last N minutes)
- Node-level features (total pods, memory fragmentation)
- Multi-class imbalance handling (SMOTE, class weights, focal loss)
- Model comparison (XGBoost, LightGBM, Neural Network)
- Online learning (incremental updates as new data arrives)
- Deployment as admission webhook (real-time risk scoring)
- Multi-cluster data aggregation for federated learning
