# k8s-supervised-learning-demo

A Kubernetes-based playground for supervised learning and AI performance experiments. This repo includes a productive dev environment and scaffolding to run a sample application, load tests, and future ML training/analysis.

## What's here

- Dev environment: Minikube + kubectl + Helm (inside a Dev Container)
- Sample app scaffold (FastAPI) and Kubernetes manifests
- Load testing script scaffold
- Room to grow: models, datasets, notebooks, and performance analysis

## Getting started

1) Set up the dev environment and start Minikube:

   See: docs/dev-environment.md

2) Deploy the sample app (once created):

   - Build the image and load into minikube
   - Apply Kubernetes manifests
   - Port-forward and hit the endpoint

3) Run a simple load test and collect metrics.

## Repository structure

Planned structure as we add components:

- `services/` — Application services
  - `test-app/` — Minimal FastAPI app (hello world + /health)
- `deploy/` — Deployment artifacts
  - `k8s/` — Raw Kubernetes manifests
    - `test-app/` — Deployment and Service for the sample app
- `scripts/` — Utilities and automation
  - `stress/` — Simple load test scripts (Python)
- `models/` — ML models, training code, checkpoints (gitignored)
- `data/` — Datasets or generated data (gitignored)
- `notebooks/` — Experiment notebooks (gitignored checkpoints)
- `docs/` — Documentation
  - `dev-environment.md` — Full Dev Container + Minikube guide
  - `architecture.md` — Project layout and design notes

As we implement each piece, we'll wire convenient Makefile targets (e.g., app deploy, port-forward, load test).

## Documentation

- Dev environment guide: docs/dev-environment.md
- Architecture and layout: docs/architecture.md (WIP)

## Next steps

Open an issue or ask for the next scaffold you'd like first:
- Sample app + deploy targets
- Load test script wired to Makefile
- Perf stack (Prometheus + Grafana) for dashboards
- Model training skeleton and data ingestion
