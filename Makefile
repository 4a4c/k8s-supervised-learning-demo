.PHONY: help minikube-start minikube-start-ml minikube-start-verbose minikube-logs minikube-docker-logs minikube-stop minikube-delete minikube-status minikube-dashboard minikube-dashboard-open minikube-dashboard-stop minikube-dashboard-url k8s-nodes k8s-contexts cluster-info helm-version k kubectl-mk mkubectl kubectl-reconcile minikube-addons-list minikube-addons-enable app-build app-deploy app-delete app-port-forward app-url loadtest-install-deps loadtest-run risk-demo-apply risk-demo-delete risk-demo-port-forward-prom

# Tunables for SSH bridge enforcement during start
# Override at invocation time, e.g.:
#   make ENSURE_BRIDGE_SECS=60 ENSURE_BRIDGE_INTERVAL_SECS=0.2 minikube-start-verbose
ENSURE_BRIDGE_SECS ?= 35
ENSURE_BRIDGE_INTERVAL_SECS ?= 0.25
export ENSURE_BRIDGE_SECS
export ENSURE_BRIDGE_INTERVAL_SECS

help:
	@echo "Kubernetes Dev Environment - Makefile Targets"
	@echo ""
	@echo "Quick Start:"
	@echo "  make minikube-start          # Start local Kubernetes cluster"
	@echo "  make minikube-status         # Check cluster health"
	@echo "  kubectl get nodes            # Verify cluster is ready"
	@echo "  make minikube-dashboard      # Open dashboard in browser"
	@echo ""
	@echo "Cluster Management:"
	@echo "  minikube-start               Start cluster (auto-reconciles kubectl to v1.34.0)"
	@echo "  minikube-start-ml            Start cluster with AI/ML defaults (4 CPUs, 8GB RAM, metrics-server)"
	@echo "  minikube-start-verbose       Start with debug logs (pass ARGS='...' for extra flags)"
	@echo "  minikube-stop                Stop cluster (preserves state)"
	@echo "  minikube-delete              Delete cluster completely"
	@echo "  minikube-status              Show cluster status (auto-heals SSH if needed)"
	@echo "  minikube-logs                Print recent minikube logs"
	@echo "  minikube-docker-logs         Print Docker container logs"
	@echo "  minikube-addons-list         List available addons"
	@echo "  minikube-addons-enable       Enable addon (pass ADDON='name')"
	@echo ""
	@echo "Risk Demo:"
	@echo "  risk-demo-apply              Apply namespace, priority classes, kube-state-metrics, prometheus"
	@echo "  risk-demo-port-forward-prom  Forward localhost:9090 -> svc/prometheus:9090"
	@echo "  risk-demo-delete             Delete risk-demo resources"
	@echo ""
	@echo "Sample App (test-app):"
	@echo "  app-build                    Build Docker image (test-app:dev) and load into minikube"
	@echo "  app-deploy                   Apply Kubernetes manifests for test-app"
	@echo "  app-delete                   Remove test-app manifests"
	@echo "  app-port-forward             Forward localhost:8000 -> svc/test-app:80"
	@echo "  app-url                      Print local URL for test-app"
	@echo ""
	@echo "Load Testing:"
	@echo "  loadtest-install-deps        Install Python deps for stress script"
	@echo "  loadtest-run                 Run stress (URL=http://127.0.0.1:8000 C=20 D=30)"
	@echo ""
	@echo "Dashboard:"
	@echo "  minikube-dashboard           Open dashboard (non-blocking, uses host browser)"
	@echo "  minikube-dashboard-url       Print dashboard URL"
	@echo "  minikube-dashboard-stop      Stop dashboard proxy"
	@echo ""
	@echo "Kubernetes Tools:"
	@echo "  k8s-nodes                    Show nodes"
	@echo "  k8s-contexts                 List kubeconfig contexts"
	@echo "  cluster-info                 Show cluster endpoints"
	@echo "  k CMD='...'                  Version-matched kubectl (e.g., k CMD='get pods -A')"
	@echo "  kubectl-reconcile            Install kubectl binary matching cluster version"
	@echo ""
	@echo "Helm:"
	@echo "  helm-version                 Show Helm version"
	@echo ""
	@echo "Tunables:"
	@echo "  ENSURE_BRIDGE_SECS=60        Extend SSH bridge enforcement during start"
	@echo "  ENSURE_BRIDGE_INTERVAL_SECS=0.2  Change bridge polling interval"

minikube-start:
	# Ensure SSH bridge watcher is running and aggressively establish port forward during startup
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	( nohup bash .devcontainer/minikube-ensure-ssh-bridge.sh >/dev/null 2>&1 & )
	minikube start --driver=docker --native-ssh=false \
		--addons=dashboard,metrics-server,storage-provisioner
	# Reconcile kubectl to the server version (non-fatal on failure)
	( bash .devcontainer/reconcile-kubectl.sh >/dev/null 2>&1 || true )

minikube-start-ml:
	# Start cluster with AI/ML-friendly configuration
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	( nohup bash .devcontainer/minikube-ensure-ssh-bridge.sh >/dev/null 2>&1 & )
	minikube start --driver=docker --native-ssh=false \
		--cpus=4 --memory=8192 \
		--addons=dashboard,metrics-server,storage-provisioner
	# Reconcile kubectl to the server version (non-fatal on failure)
	( bash .devcontainer/reconcile-kubectl.sh >/dev/null 2>&1 || true )
	@echo ""
	@echo "✅ ML cluster ready with metrics-server enabled"
	@echo "💡 Tip: Use 'kubectl top nodes' and 'kubectl top pods' to monitor resource usage"
	@echo "💡 Enable more addons: make minikube-addons-list"

minikube-start-verbose:
	# Ensure SSH bridge watcher is running and aggressively establish port forward during startup
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	( nohup bash .devcontainer/minikube-ensure-ssh-bridge.sh >/dev/null 2>&1 & )
	minikube start --driver=docker --native-ssh=false --alsologtostderr -v=7 --wait-timeout=10m $(ARGS)
	# Reconcile kubectl to the server version (non-fatal on failure)
	( bash .devcontainer/reconcile-kubectl.sh >/dev/null 2>&1 || true )

minikube-stop:
	# Ensure SSH bridge is in place before stopping
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	( bash .devcontainer/minikube-ssh-forwarder.sh once >/dev/null 2>&1 || true )
	minikube stop

minikube-delete:
	# Ensure SSH bridge is in place before deleting
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	( bash .devcontainer/minikube-ssh-forwarder.sh once >/dev/null 2>&1 || true )
	minikube delete

minikube-status:
	# Ensure SSH bridge is in place before querying status
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	( bash .devcontainer/minikube-ssh-forwarder.sh once >/dev/null 2>&1 || true )
	minikube status

minikube-dashboard:
	bash .devcontainer/minikube-dashboard.sh open

minikube-dashboard-open:
	bash .devcontainer/minikube-dashboard.sh open

minikube-dashboard-url:
	bash .devcontainer/minikube-dashboard.sh url

minikube-dashboard-stop:
	bash .devcontainer/minikube-dashboard.sh stop

k8s-nodes:
	kubectl get nodes -o wide

k8s-contexts:
	kubectl config get-contexts

cluster-info:
	kubectl cluster-info

helm-version:
	helm version

# Version-matched kubectl via minikube (pass CMD='get pods -A', etc.)
k kubectl-mk mkubectl:
	@minikube kubectl -- $(CMD)

kubectl-reconcile:
	bash .devcontainer/reconcile-kubectl.sh

minikube-logs:
	# Ensure SSH bridge is in place before fetching logs
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	( bash .devcontainer/minikube-ssh-forwarder.sh once >/dev/null 2>&1 || true )
	minikube logs --file=- | tail -n 200 || true

minikube-docker-logs:
	docker logs minikube --tail=200 || true

minikube-addons-list:
	# Ensure SSH bridge is in place before querying addons
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	( bash .devcontainer/minikube-ssh-forwarder.sh once >/dev/null 2>&1 || true )
	minikube addons list

minikube-addons-enable:
	# Enable a specific addon (e.g., make minikube-addons-enable ADDON=ingress)
	( bash .devcontainer/minikube-ssh-forwarder.sh run >/dev/null 2>&1 || true )
	( bash .devcontainer/minikube-ssh-forwarder.sh once >/dev/null 2>&1 || true )
	@if [ -z "$(ADDON)" ]; then \
		echo "❌ Error: ADDON not specified"; \
		echo "Usage: make minikube-addons-enable ADDON=<addon-name>"; \
		echo "Example: make minikube-addons-enable ADDON=ingress"; \
		echo "Run 'make minikube-addons-list' to see available addons"; \
		exit 1; \
	fi
	minikube addons enable $(ADDON)

# --- Sample application: test-app ---

APP_IMAGE ?= test-app:dev
APP_DIR := services/test-app
APP_MANIFEST := deploy/k8s/test-app/k8s.yaml

app-build:
	# Build the Docker image for test-app and load it into minikube
	docker build -t $(APP_IMAGE) $(APP_DIR)
	minikube image load $(APP_IMAGE)

app-deploy:
	# Deploy or update test-app manifests
	kubectl apply -f $(APP_MANIFEST)
	@echo "Waiting for rollout..."
	kubectl rollout status deploy/test-app

app-delete:
	# Delete test-app manifests (ignore if missing)
	kubectl delete -f $(APP_MANIFEST) --ignore-not-found

app-port-forward:
	# Forward local 8000 to service/test-app:80
	@echo "Visit: http://127.0.0.1:8000/"
	kubectl port-forward svc/test-app 8000:80

app-url:
	@echo "http://127.0.0.1:8000/"

# --- Load testing ---

URL ?= http://127.0.0.1:8000/
C ?= 20
D ?= 30

loadtest-install-deps:
	pip3 install -r scripts/stress/requirements.txt

loadtest-run:
	python3 scripts/stress/simple_stress.py --url $(URL) --concurrency $(C) --duration $(D)

# --- Risk demo apply/delete ---

RISK_DIR := deploy/k8s/risk-demo

risk-demo-apply:
	kubectl apply -f $(RISK_DIR)/namespace.yaml
	kubectl apply -f $(RISK_DIR)/priority-classes.yaml
	kubectl apply -f $(RISK_DIR)/kube-state-metrics.yaml
	kubectl apply -f $(RISK_DIR)/prometheus.yaml
	@echo "Waiting for kube-state-metrics..." && \
		kubectl -n risk-demo rollout status deploy/kube-state-metrics
	@echo "Waiting for prometheus..." && \
		kubectl -n risk-demo rollout status deploy/prometheus
	@echo "✔ Risk demo applied. Use 'make risk-demo-port-forward-prom' to open Prometheus."

risk-demo-port-forward-prom:
	@echo "Visit: http://127.0.0.1:9090/"
	kubectl -n risk-demo port-forward svc/prometheus 9090:9090

risk-demo-delete:
	# Delete namespaced resources first, then cluster-scoped
	-kubectl delete -f $(RISK_DIR)/prometheus.yaml --ignore-not-found
	-kubectl delete -f $(RISK_DIR)/kube-state-metrics.yaml --ignore-not-found
	-kubectl delete -f $(RISK_DIR)/priority-classes.yaml --ignore-not-found
	-kubectl delete -f $(RISK_DIR)/namespace.yaml --ignore-not-found
	@echo "✔ Risk demo deleted."
