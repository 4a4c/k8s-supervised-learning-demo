# Enabling reliable OOM/Evict events in minikube (Path A)

This doc shows a reproducible setup to trigger pod OOMKilled/Evicted events in a local minikube cluster so you can collect ground-truth labels.

## Using Make Targets (Recommended)

If you're in the dev container, prefer the Makefile wrappers instead of raw `minikube start` flags:

```bash
# Standard heuristic-friendly cluster (8Gi / metrics-server):
make minikube-start-ml

# Strict eviction cluster (6Gi + tuned kubelet thresholds):
make minikube-start-oom

# Check status and addons:
make minikube-status
kubectl get pods -A | grep metrics-server || echo "⚠️ metrics-server missing"
```

Ground-truth labeling requires the strict eviction cluster (`make minikube-start-oom`). Heuristic labeling (faster iteration) can use `make minikube-start` or `make minikube-start-ml`.

Notes
- Assumes Linux host. Swap should be off for kubelet memory accounting to work as expected.
- These settings trade stability for observability. Don’t use in production.

## Option 1: Start a fresh minikube with tighter memory and kubelet evictions

- Allocate small VM memory (e.g., 4096–6144 MiB) so node memory pressure occurs.
- Configure kubelet eviction thresholds to be more aggressive.

Example (run on your host shell):

```bash
# Stop and delete existing cluster (destructive)
minikube stop
minikube delete

# Start with 6Gi memory and stricter eviction thresholds
minikube start \
  --memory=6144 \
  --cpus=4 \
  --extra-config='kubelet.eviction-hard=memory.available<500Mi,nodefs.available<5%,imagefs.available<5%' \
  --extra-config=kubelet.eviction-pressure-transition-period=30s \
  --extra-config=kubelet.image-gc-high-threshold=95 \
  --extra-config=kubelet.image-gc-low-threshold=80

# Verify metrics-server is installed
minikube addons enable metrics-server
```

Equivalent using Make targets (non-destructive cluster already deleted):

```bash
make minikube-start-oom
kubectl get pods -A | grep metrics-server || echo "⚠️ enable with: minikube addons enable metrics-server"
```

Tips
- If evictions still don’t trigger, reduce `--memory` (e.g., 4096) or tighten `eviction-hard` further (e.g., `memory.available<300Mi`).
- Keep swap off: `sudo swapoff -a` (temporarily) or disable swap entries in `/etc/fstab`.

## Option 2: Reconfigure an existing minikube

```bash
# Update kubelet config via minikube start
minikube start \
  --memory=6144 \
  --cpus=4 \
  --extra-config='kubelet.eviction-hard=memory.available<500Mi,nodefs.available<5%,imagefs.available<5%' \
  --extra-config=kubelet.eviction-pressure-transition-period=30s
```

## Kubernetes knobs that influence OOM/Evict

- Pod QoS: BestEffort < Burstable < Guaranteed. Tighter limits and lower priority (`PriorityClass`) increase eviction likelihood under pressure.
- PriorityClass: Lower priority pods are evicted first under resource pressure.
- Node memory: Smaller nodes make pressure easier to induce.
- Workloads: Increase `stress-ng` VM workers and bytes so total working set exceeds pod limits and/or node headroom.

## Verifying ground-truth events

- Check pod status/reason: `kubectl get pod -n risk-demo -o wide`
- Inspect container state: `kubectl describe pod/<name> -n risk-demo | grep -i -E "oomkilled|evicted|reason|message" -n`
- Node conditions: `kubectl get nodes -o json | jq '.items[0].status.conditions'`

You should observe:
- Container termination reason `OOMKilled` for real OOM at the cgroup level.
- Pod status reason `Evicted` for kubelet evictions under node pressure.

Once confirmed, rerun the data generator—rows with these outcomes will be labeled with `label_source = ground_truth`.
