#!/usr/bin/env bash
set -euo pipefail

# Wait for any existing generator to finish
echo "[fast-parallel] Waiting for current generator to finish..."
while pgrep -af "services/generate-data/.venv/bin/python .*generate_data.py" >/dev/null; do
  echo "[fast-parallel] Generator still running at $(date +%T). Sleeping 60s..."
  sleep 60
done

echo "[fast-parallel] Starting fast runs in parallel namespaces at $(date +%T)"

# Common knobs
OBSERVE_SECONDS=${OBSERVE_SECONDS:-180}
METRICS_WAIT_SECONDS=${METRICS_WAIT_SECONDS:-30}
HEUR_HIGH_RATIO=${HEUR_HIGH_RATIO:-0.80}
HEUR_MED_RATIO=${HEUR_MED_RATIO:-0.65}
VICTIMS_MIN=${VICTIMS_MIN:-4}
VICTIMS_MAX=${VICTIMS_MAX:-4}
STRESS_MIN=${STRESS_MIN:-1}
STRESS_MAX=${STRESS_MAX:-1}
MAX_CPU_M=${MAX_CPU_M:-500}
MAX_MEM_MI=${MAX_MEM_MI:-256}
N_CYCLES=${N_CYCLES:-40}
TEMPLATES_DIR=${TEMPLATES_DIR:-deploy/k8s/risk-demo-fast}
PYBIN=services/generate-data/.venv/bin/python
GEN=services/generate-data/generate_data.py

# Namespace A
(
  NAMESPACE=risk-demo \
  OBSERVE_SECONDS="$OBSERVE_SECONDS" METRICS_WAIT_SECONDS="$METRICS_WAIT_SECONDS" \
  HEUR_HIGH_RATIO="$HEUR_HIGH_RATIO" HEUR_MED_RATIO="$HEUR_MED_RATIO" \
  VICTIMS_MIN="$VICTIMS_MIN" VICTIMS_MAX="$VICTIMS_MAX" \
  STRESS_MIN="$STRESS_MIN" STRESS_MAX="$STRESS_MAX" \
  MAX_CPU_M="$MAX_CPU_M" MAX_MEM_MI="$MAX_MEM_MI" \
  TEMPLATES_DIR="$TEMPLATES_DIR" N_CYCLES="$N_CYCLES" \
  OUTPUT_PATH=./data/pod_risk_data_fast_ns_a.csv \
  nohup bash -c "$PYBIN $GEN" > /tmp/fast-a.log 2>&1 &
  echo "[fast-parallel] Started NS A PID $!"
)

# Namespace B
(
  NAMESPACE=risk-demo-b \
  OBSERVE_SECONDS="$OBSERVE_SECONDS" METRICS_WAIT_SECONDS="$METRICS_WAIT_SECONDS" \
  HEUR_HIGH_RATIO="$HEUR_HIGH_RATIO" HEUR_MED_RATIO="$HEUR_MED_RATIO" \
  VICTIMS_MIN="$VICTIMS_MIN" VICTIMS_MAX="$VICTIMS_MAX" \
  STRESS_MIN="$STRESS_MIN" STRESS_MAX="$STRESS_MAX" \
  MAX_CPU_M="$MAX_CPU_M" MAX_MEM_MI="$MAX_MEM_MI" \
  TEMPLATES_DIR="$TEMPLATES_DIR" N_CYCLES="$N_CYCLES" \
  OUTPUT_PATH=./data/pod_risk_data_fast_ns_b.csv \
  nohup bash -c "$PYBIN $GEN" > /tmp/fast-b.log 2>&1 &
  echo "[fast-parallel] Started NS B PID $!"
)

# Simple status notifier
(cat <<'SH'
while true; do
  echo "== $(date +%F\ %T) =="
  for ns in risk-demo risk-demo-b; do
    echo "-- $ns --"
    kubectl get pods -n "$ns" | awk 'NR==1 || /victim|stress/'
  done
  for f in /tmp/fast-a.log /tmp/fast-b.log; do
    echo "-- tail $f --"; tail -n 3 "$f" || true
  done
  echo
  sleep 300
done
SH
) | nohup bash > /tmp/fast-parallel-status.log 2>&1 &

echo "[fast-parallel] Watcher started. Tails: /tmp/fast-a.log, /tmp/fast-b.log, status: /tmp/fast-parallel-status.log"
