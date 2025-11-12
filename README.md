# k8s-supervised-learning-demo

Machine learning demo for predicting Kubernetes pod OOMKilled/Eviction risk using supervised learning. Collects training data by observing pod behavior under resource pressure in a local minikube cluster.

## What's here

- **Data generation**: Automated pod stress testing with metrics collection
- **Ground truth labels**: OOMKilled/Evicted events (Path A) or heuristic memory pressure (Path B)
- **Baseline training**: RandomForest classifier with automatic leakage mitigation
- **Dev environment**: Minikube + kubectl + metrics-server in Dev Container

## Quick Start

### 🎯 For Assignment Review: Interactive Notebook (No Setup Required)

**Click here to run the complete analysis in your browser:**

[![Binder](https://mybinder.org/badge_logo.svg)](https://mybinder.org/v2/gh/4a4c/k8s-supervised-learning-demo/main?filepath=pod_risk_evaluation.ipynb)

The notebook includes:
- Pre-generated training data (`pod_risk_data_fast_combined.csv`)
- Complete model training pipeline (RandomForest with leakage mitigation)
- Performance metrics (accuracy, balanced accuracy, ROC-AUC curves)
- Confusion matrix analysis
- No Kubernetes cluster or local setup needed

**That's it!** All cells are ready to run sequentially to reproduce the results.

---

### 🛠️ Optional: Full Development Environment (For Data Generation & Experimentation)

*Only needed if you want to generate new training data or modify the pipeline.*

#### Generate data quickly (fast parallel mode)
```bash
# Start standard ML cluster (8Gi, metrics-server)
make minikube-start-ml

# Apply dual-namespace manifests for fast runs
make risk-demo-fast-apply

# One-time: set up generator venv
make datagen-local-setup

# Run two generators concurrently and merge outputs
make datagen-fast-parallel
make datagen-fast-merge  # → data/pod_risk_data_fast_combined.csv
```

#### Alternative: Ground-truth labels (slower, production-faithful)
```bash
# Strict eviction cluster (6Gi, tuned kubelet)
make minikube-start-oom

# Apply single-namespace environment
make risk-demo-apply

# Run single generator (see docs/architecture.md for options)
make datagen-local
```

#### Validate and train locally
*After generating fresh data:*
```bash
# Validate CSV quality
make validate-data

# Train baseline model
make ml-setup
make train-baseline
```

## Repository structure

```
services/
  generate-data/          # Data generation script and requirements
deploy/
  k8s/risk-demo/          # Namespace, priority classes, resource constraints, pod templates
  k8s/risk-demo-fast/     # Dual-namespace manifests for fast parallel data generation
scripts/
  validate_data.py        # CSV quality check and ML-readiness assessment
  train_baseline.py       # RandomForest trainer with leakage mitigation
  requirements-ml.txt     # scikit-learn
data/
  pod_risk_data.csv       # Single-run CSV (heuristic or ground-truth)
  pod_risk_data_fast_combined.csv  # Merged fast-mode CSV (A+B namespaces)
docs/
  architecture.md         # Architecture & workflow overview
  eviction-tuning.md      # Kubelet settings for ground-truth OOM/Evict
  dev-environment.md      # Dev Container setup
```

## Training Data

Data collected with fast parallel mode is merged into `data/pod_risk_data_fast_combined.csv`. Each row represents a victim pod snapshot after an observation window + metrics scrape.

**Key features:** CPU/memory requests & limits, priority class, node pressure %, pod usage (CPU %, memory MiB).

**Target labels:** `low` | `medium` | `high` risk of eviction/OOM.

**Label sources:**
- `ground_truth` — Real OOMKilled/Evicted events (requires strict eviction cluster).
- `heuristic` — Memory usage ratio thresholds (faster iteration; configurable via `HEUR_HIGH_RATIO`/`HEUR_MED_RATIO`).

For complete column definitions, units, derivations, and leakage mitigation guidance, see **[Dataset Columns](docs/architecture.md#dataset-columns-pod_risk_data_fast_combinedcsv)** in `docs/architecture.md`.


## Workflow Options

### Fast Parallel (default in this repo)
Two concurrent generators → merged `pod_risk_data_fast_combined.csv`. Higher throughput, heuristic labels.

### Ground-truth (strict eviction cluster)
`make minikube-start-oom` → captures real OOMKilled/Evicted events. Production-faithful but slower.

### Single-namespace heuristic (development)
`make datagen-local` → simplest setup for feature iteration.

For detailed workflow diagrams, execution modes, and architecture, see **[docs/architecture.md](docs/architecture.md)**.


## Key Make Targets

**Cluster:**
- `make minikube-start-oom` — 6Gi cluster with strict eviction
- `make minikube-start-ml` — 8Gi cluster for heuristic mode
- `make minikube-dashboard` — Open Kubernetes dashboard

**Data generation:**
- `make datagen-local-setup` — Create venv (one-time)
- `make risk-demo-fast-apply` — Deploy dual namespaces
- `make datagen-fast-parallel` — Start A+B generators
- `make datagen-fast-merge` — Merge → `data/pod_risk_data_fast_combined.csv`
- `make datagen-fast-checkpoint` — Mid-run snapshot (SIGUSR1)
- See `make help` or [docs/architecture.md](docs/architecture.md#execution-modes) for all options

**Validation & training:**
- `make validate-data` — Check CSV quality and ML-readiness
- `make ml-setup` — Install scikit-learn (one-time)
- `make train-baseline` — Train RandomForest with leakage mitigation
- `make train-baseline-fast-checkpoint` — Train on merged checkpoint CSV

**Environment:**
- `make risk-demo-apply` — Deploy namespace, limits, priorities, kube-state-metrics
- `make risk-demo-delete` — Clean up risk-demo resources

## Documentation

- **Architecture & workflow**: `docs/architecture.md`
- **Eviction tuning**: `docs/eviction-tuning.md`
- **Dev environment**: `docs/dev-environment.md`
- **Fast-mode manifests**: `deploy/k8s/risk-demo-fast/README.md`

## Tuning

**Eviction thresholds (ground-truth mode):**
- See [docs/eviction-tuning.md](docs/eviction-tuning.md)

**Heuristic thresholds:**
- Adjust `HEUR_HIGH_RATIO`/`HEUR_MED_RATIO` environment variables (defaults: 0.95/0.85)

**Resource constraints:**
- Edit `deploy/k8s/risk-demo/resource-constraints.yaml` for namespace quotas and per-container limits

## Current Status

- ✅ Data generation with metrics-server (no Prometheus dependency)
- ✅ Ground-truth and heuristic labeling
- ✅ Validation script with ML-readiness checks
- ✅ Baseline RandomForest trainer with leakage mitigation
- ✅ Streamlined Makefile for local runs
- 🔄 Ready for full data collection and model iteration
