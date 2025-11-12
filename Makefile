.PHONY: help minikube-start minikube-start-oom minikube-start-ml minikube-stop minikube-delete minikube-status minikube-dashboard minikube-addons-enable k8s-nodes cluster-info kubectl-reconcile \
	risk-demo-apply risk-demo-delete risk-demo-fast-apply \
	datagen-local-setup datagen-cleanup-pods datagen-cleanup-pods-b datagen-cleanup-pods-all \
	datagen-fast-run-a datagen-fast-run-b datagen-fast-parallel datagen-fast-checkpoint datagen-fast-merge datagen-fast-merge-checkpoint \
	validate-data ml-setup train-baseline train-baseline-fast-checkpoint

# Tunables for SSH bridge enforcement during start
# Override at invocation time, e.g.:
#   make ENSURE_BRIDGE_SECS=60 ENSURE_BRIDGE_INTERVAL_SECS=0.2 minikube-start-verbose
ENSURE_BRIDGE_SECS ?= 35
ENSURE_BRIDGE_INTERVAL_SECS ?= 0.25
export ENSURE_BRIDGE_SECS
export ENSURE_BRIDGE_INTERVAL_SECS

help:
	@echo "Pod OOM/Eviction Risk ML Demo - Makefile Targets"
	@echo ""
	@echo "=== Quick Start ==="
	@echo "  make minikube-start-oom      # Start cluster with strict eviction (6Gi, kubelet tuned)"
	@echo "  make risk-demo-apply         # Apply namespace, priority classes, resource constraints"
	@echo "  make validate-data           # Check CSV quality and ML-readiness"
	@echo "  make train-baseline          # Train RandomForest with leakage mitigation"
	@echo ""
	@echo "=== Cluster Management ==="
	@echo "  minikube-start               # Standard cluster (default resources)"
	@echo "  minikube-start-oom           # OOM/Evict cluster (6Gi, strict kubelet thresholds)"
	@echo "  minikube-start-ml            # ML cluster (8Gi, 4 CPUs, metrics-server)"
	@echo "  minikube-stop                # Stop cluster (preserves state)"
	@echo "  minikube-delete              # Delete cluster completely"
	@echo "  minikube-status              # Show cluster status"
	@echo "  minikube-dashboard           # Open Kubernetes dashboard in browser"
	@echo "  minikube-addons-enable       # Enable addon (pass ADDON='metrics-server')"
	@echo ""
	@echo "=== Risk Demo Environment ==="
	@echo "  risk-demo-apply              # Deploy namespace, priority classes, limits, kube-state-metrics"
	@echo "  risk-demo-delete             # Delete all risk-demo resources"
	@echo ""
	@echo "=== Data Generation (Fast Mode) ==="
	@echo "  datagen-local-setup          # One-time: create venv for generator (required by fast mode)"
	@echo "  risk-demo-fast-apply         # Apply optional second namespace (risk-demo-b) for parallel runs"
	@echo "  datagen-fast-run-a           # Fast run in risk-demo (40 cycles, 4 victims, 1 stress, 180s observe)"
	@echo "  datagen-fast-run-b           # Fast run in risk-demo-b (same settings)"
	@echo "  datagen-fast-parallel        # Start A + B in background with logs in /tmp/fast-a.log, /tmp/fast-b.log"
	@echo "  datagen-fast-checkpoint      # Write checkpoint CSVs from running generators (SIGUSR1)"
	@echo "  datagen-fast-merge           # Merge final A/B CSVs into data/pod_risk_data_fast_combined.csv"
	@echo "  datagen-fast-merge-checkpoint# Merge checkpoint A/B into data/pod_risk_data_fast_combined_checkpoint.csv"
	@echo "  datagen-cleanup-pods         # Manually clean up victim/stress pods in risk-demo"
	@echo "  datagen-cleanup-pods-b       # Manually clean up victim/stress pods in risk-demo-b"
	@echo "  datagen-cleanup-pods-all     # Clean up pods in both namespaces"
	@echo ""
	@echo "=== Validation & Training ==="
	@echo "  validate-data                # Validate CSV: row count, labels, features, ML-readiness"
	@echo "  ml-setup                     # Install scikit-learn (one-time)"
	@echo "  train-baseline               # Train RandomForest (auto-drops leaky features)"
	@echo ""
	@echo "=== Kubernetes Utilities ==="
	@echo "  k8s-nodes                    # Show nodes"
	@echo "  cluster-info                 # Show cluster endpoints"
	@echo "  kubectl-reconcile            # Install kubectl matching cluster version"
	@echo ""
	@echo "=== Notes ==="
	@echo "  - For ground-truth OOM/Evict labels: use minikube-start-oom"
	@echo "  - For heuristic labels (faster iteration): use minikube-start or minikube-start-ml"
	@echo "  - Tune heuristics via HEUR_HIGH_RATIO/HEUR_MED_RATIO (e.g., 0.80/0.65 in fast mode)"
	@echo "  - See docs/eviction-tuning.md for cluster config details"

minikube-start:
	# Ensure SSH bridge watcher is running and aggressively establish port forward during startup
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	( nohup bash .devcontainer/minikube-ensure-ssh-bridge.sh >/dev/null 2>&1 & )
	minikube start --driver=docker --native-ssh=false \
		--addons=dashboard,metrics-server,storage-provisioner
	# Reconcile kubectl to the server version (non-fatal on failure)
	( bash .devcontainer/reconcile-kubectl.sh >/dev/null 2>&1 || true )

minikube-start-oom:
	# Start cluster with strict eviction for ground-truth OOM/Evict labels
	# See docs/eviction-tuning.md for details
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	( nohup bash .devcontainer/minikube-ensure-ssh-bridge.sh >/dev/null 2>&1 & )
	minikube start --driver=docker --native-ssh=false \
		--memory=6144 --cpus=4 \
		--extra-config='kubelet.eviction-hard=memory.available<500Mi,nodefs.available<5%,imagefs.available<5%' \
		--extra-config=kubelet.eviction-pressure-transition-period=30s \
		--extra-config=kubelet.image-gc-high-threshold=95 \
		--extra-config=kubelet.image-gc-low-threshold=80 \
		--addons=metrics-server,storage-provisioner
	( bash .devcontainer/reconcile-kubectl.sh >/dev/null 2>&1 || true )
	@echo ""
	@echo "✅ OOM/Evict cluster ready (6Gi, strict kubelet thresholds)"
	@echo "💡 Next: make risk-demo-apply && make datagen-local-test"

minikube-start-ml:
	# Start cluster with AI/ML-friendly configuration (larger, for heuristic labels)
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	( nohup bash .devcontainer/minikube-ensure-ssh-bridge.sh >/dev/null 2>&1 & )
	minikube start --driver=docker --native-ssh=false \
		--cpus=4 --memory=8192 \
		--addons=metrics-server,storage-provisioner
	( bash .devcontainer/reconcile-kubectl.sh >/dev/null 2>&1 || true )
	@echo ""
	@echo "✅ ML cluster ready (8Gi, metrics-server enabled)"
	@echo "💡 Next: make risk-demo-apply && make datagen-local-test"

minikube-stop:
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	minikube stop

minikube-delete:
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	minikube delete

minikube-status:
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	minikube status

minikube-dashboard:
	bash .devcontainer/minikube-dashboard.sh open

k8s-nodes:
	kubectl get nodes -o wide

cluster-info:
	kubectl cluster-info

kubectl-reconcile:
	bash .devcontainer/reconcile-kubectl.sh

minikube-addons-enable:
	@if [ -z "$(ADDON)" ]; then \
		echo "❌ Error: ADDON not specified"; \
		echo "Usage: make minikube-addons-enable ADDON=<addon-name>"; \
		echo "Example: make minikube-addons-enable ADDON=metrics-server"; \
		exit 1; \
	fi
	minikube addons enable $(ADDON)



# --- Risk demo apply/delete ---

RISK_DIR := deploy/k8s/risk-demo
RISK_FAST_DIR := deploy/k8s/risk-demo-fast

risk-demo-apply:
	kubectl apply -f $(RISK_DIR)/namespace.yaml
	kubectl apply -f $(RISK_DIR)/resource-constraints.yaml
	kubectl apply -f $(RISK_DIR)/priority-classes.yaml
	kubectl apply -f $(RISK_DIR)/kube-state-metrics.yaml
	@echo "Waiting for kube-state-metrics..."
	@kubectl -n risk-demo rollout status deploy/kube-state-metrics --timeout=60s
	@echo "✔ Risk demo applied (namespace, limits, priorities, kube-state-metrics)"

risk-demo-delete:
	-kubectl delete -f $(RISK_DIR)/kube-state-metrics.yaml --ignore-not-found
	-kubectl delete -f $(RISK_DIR)/resource-constraints.yaml --ignore-not-found
	-kubectl delete -f $(RISK_DIR)/priority-classes.yaml --ignore-not-found
	-kubectl delete -f $(RISK_DIR)/namespace.yaml --ignore-not-found
	@echo "✔ Risk demo deleted."

# Optional: apply second namespace for fast parallel runs
risk-demo-fast-apply:
	@echo "Applying risk-demo-b namespace for fast parallel runs..."
	kubectl apply -f $(RISK_FAST_DIR)/namespace-b.yaml
	@echo "✔ risk-demo-b applied."

datagen-cleanup-pods:
	kubectl -n risk-demo delete pods -l 'app in (stress,victim)' --ignore-not-found --grace-period=0 --force 2>/dev/null || true
	@echo "✔ Experiment pods cleaned up."

datagen-cleanup-pods-b:
	kubectl -n risk-demo-b delete pods -l 'app in (stress,victim)' --ignore-not-found --grace-period=0 --force 2>/dev/null || true
	@echo "✔ Experiment pods cleaned up (risk-demo-b)."

datagen-cleanup-pods-all: datagen-cleanup-pods datagen-cleanup-pods-b
	@echo "✔ All experiment pods cleaned up (both namespaces)."

# --- Fast Mode Data Generation ---

DATAGEN_VENV := services/generate-data/.venv

datagen-local-setup:
	@if [ ! -d "$(DATAGEN_VENV)" ]; then \
		python3 -m venv $(DATAGEN_VENV); \
		$(DATAGEN_VENV)/bin/pip install --upgrade pip -q; \
		$(DATAGEN_VENV)/bin/pip install -r services/generate-data/requirements.txt -q; \
		echo "✔ Local venv created at $(DATAGEN_VENV)"; \
	else \
		echo "✔ Venv already exists at $(DATAGEN_VENV)"; \
	fi

datagen-fast-run-a: datagen-local-setup
	@echo "▶ Fast run in risk-demo (40 cycles, 4 victims, 1 stress, 180s observe)"
	PYTHONUNBUFFERED=1 NAMESPACE=risk-demo \
	OBSERVE_SECONDS=180 METRICS_WAIT_SECONDS=30 \
	HEUR_HIGH_RATIO=0.80 HEUR_MED_RATIO=0.65 \
	VICTIMS_MIN=4 VICTIMS_MAX=4 STRESS_MIN=1 STRESS_MAX=1 \
	MAX_CPU_M=500 MAX_MEM_MI=256 STRESS_LIM_CPU=1 STRESS_LIM_MEM=1Gi \
	TEMPLATES_DIR=$(RISK_FAST_DIR) N_CYCLES=40 \
	OUTPUT_PATH=./data/pod_risk_data_fast_ns_a.csv \
	$(DATAGEN_VENV)/bin/python services/generate-data/generate_data.py

datagen-fast-run-b: datagen-local-setup
	@echo "▶ Fast run in risk-demo-b (40 cycles, 4 victims, 1 stress, 180s observe)"
	PYTHONUNBUFFERED=1 NAMESPACE=risk-demo-b \
	OBSERVE_SECONDS=180 METRICS_WAIT_SECONDS=30 \
	HEUR_HIGH_RATIO=0.80 HEUR_MED_RATIO=0.65 \
	VICTIMS_MIN=4 VICTIMS_MAX=4 STRESS_MIN=1 STRESS_MAX=1 \
	MAX_CPU_M=500 MAX_MEM_MI=256 STRESS_LIM_CPU=1 STRESS_LIM_MEM=1Gi \
	TEMPLATES_DIR=$(RISK_FAST_DIR) N_CYCLES=40 \
	OUTPUT_PATH=./data/pod_risk_data_fast_ns_b.csv \
	$(DATAGEN_VENV)/bin/python services/generate-data/generate_data.py

datagen-fast-parallel: datagen-local-setup
	@echo "▶ Starting fast parallel runs (risk-demo + risk-demo-b) in background"
	nohup bash -c 'PYTHONUNBUFFERED=1 NAMESPACE=risk-demo \
	OBSERVE_SECONDS=180 METRICS_WAIT_SECONDS=30 \
	HEUR_HIGH_RATIO=0.80 HEUR_MED_RATIO=0.65 \
	VICTIMS_MIN=4 VICTIMS_MAX=4 STRESS_MIN=1 STRESS_MAX=1 \
	MAX_CPU_M=500 MAX_MEM_MI=256 STRESS_LIM_CPU=1 STRESS_LIM_MEM=1Gi \
	TEMPLATES_DIR=$(RISK_FAST_DIR) N_CYCLES=40 \
	OUTPUT_PATH=./data/pod_risk_data_fast_ns_a.csv \
	$(DATAGEN_VENV)/bin/python services/generate-data/generate_data.py' > /tmp/fast-a.log 2>&1 & echo "✔ NS A log: /tmp/fast-a.log"
	nohup bash -c 'PYTHONUNBUFFERED=1 NAMESPACE=risk-demo-b \
	OBSERVE_SECONDS=180 METRICS_WAIT_SECONDS=30 \
	HEUR_HIGH_RATIO=0.80 HEUR_MED_RATIO=0.65 \
	VICTIMS_MIN=4 VICTIMS_MAX=4 STRESS_MIN=1 STRESS_MAX=1 \
	MAX_CPU_M=500 MAX_MEM_MI=256 STRESS_LIM_CPU=1 STRESS_LIM_MEM=1Gi \
	TEMPLATES_DIR=$(RISK_FAST_DIR) N_CYCLES=40 \
	OUTPUT_PATH=./data/pod_risk_data_fast_ns_b.csv \
	$(DATAGEN_VENV)/bin/python services/generate-data/generate_data.py' > /tmp/fast-b.log 2>&1 & echo "✔ NS B log: /tmp/fast-b.log"
	@echo "✔ Fast parallel runs started"

datagen-fast-checkpoint:
	@echo "▶ Writing checkpoint CSVs (SIGUSR1) for all running generators"
	@pgrep -f "services/generate-data/generate_data.py" | xargs -r -I{} sh -c 'echo "  - PID {}"; kill -USR1 {}'
	@sleep 2
	@ls -lh data/*checkpoint*.csv 2>/dev/null || echo "(no checkpoint files found yet)"

datagen-fast-merge:
	@echo "▶ Merging final fast CSVs (ns_a + ns_b)"
	@if [ ! -f data/pod_risk_data_fast_ns_a.csv ] || [ ! -f data/pod_risk_data_fast_ns_b.csv ]; then \
		echo "❌ Missing fast CSVs. Expected data/pod_risk_data_fast_ns_a.csv and ..._ns_b.csv"; exit 1; \
	fi
	@awk 'FNR==1 && NR!=1 {next} {print}' data/pod_risk_data_fast_ns_a.csv data/pod_risk_data_fast_ns_b.csv > data/pod_risk_data_fast_combined.csv
	@echo "✔ Combined CSV: data/pod_risk_data_fast_combined.csv"

datagen-fast-merge-checkpoint:
	@echo "▶ Merging fast checkpoint CSVs (ns_a + ns_b)"
	@if [ ! -f data/pod_risk_data_fast_ns_a_checkpoint.csv ] || [ ! -f data/pod_risk_data_fast_ns_b_checkpoint.csv ]; then \
		echo "❌ Missing checkpoint CSVs. Expected *_checkpoint.csv files"; exit 1; \
	fi
	@awk 'FNR==1 && NR!=1 {next} {print}' data/pod_risk_data_fast_ns_a_checkpoint.csv data/pod_risk_data_fast_ns_b_checkpoint.csv > data/pod_risk_data_fast_combined_checkpoint.csv
	@echo "✔ Combined checkpoint: data/pod_risk_data_fast_combined_checkpoint.csv"

# --- Validation and Training ---

validate-data:
	@if [ ! -f data/pod_risk_data.csv ]; then \
		echo "❌ data/pod_risk_data.csv not found. Run a data generation first."; \
		exit 1; \
	fi
	python3 scripts/validate_data.py data/pod_risk_data.csv

ML_REQ := scripts/requirements-ml.txt

ml-setup:
	@if [ ! -f $(ML_REQ) ]; then \
		echo "scikit-learn>=1.3" > $(ML_REQ); \
	fi
	pip3 install -r $(ML_REQ)
	@echo "✔ ML deps installed"

train-baseline: ml-setup
	@if [ ! -f data/pod_risk_data.csv ]; then \
		echo "❌ data/pod_risk_data.csv not found. Run a data generation first."; \
		exit 1; \
	fi
	python3 scripts/train_baseline.py --csv data/pod_risk_data.csv --drop-leakage

train-baseline-fast-checkpoint: ml-setup
	@if [ ! -f data/pod_risk_data_fast_combined_checkpoint.csv ]; then \
		echo "❌ Combined checkpoint CSV not found. Run 'make datagen-fast-merge-checkpoint' first."; \
		exit 1; \
	fi
	python3 scripts/train_baseline.py --csv data/pod_risk_data_fast_combined_checkpoint.csv --drop-leakage
	@echo "✔ Trained on fast checkpoint combined CSV"
