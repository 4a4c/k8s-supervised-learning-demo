#!/usr/bin/env python3
import os
import random
import sys
import time
import yaml
import pandas as pd
import signal
from datetime import datetime, timedelta, timezone
from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

# -------------------------------------------------
# 0. CONFIG
# -------------------------------------------------
NAMESPACE = os.environ.get("NAMESPACE", "risk-demo")
# Use env vars for easy testing: TEST_MODE=1 runs 3 cycles with shorter observe
TEST_MODE = os.environ.get("TEST_MODE", "0") == "1"
N_CYCLES_DEFAULT = 3 if TEST_MODE else 80
N_CYCLES = int(os.environ.get("N_CYCLES", str(N_CYCLES_DEFAULT)))  # Override cycles if needed
VICTIMS_PER_CYCLE = (2, 5) if TEST_MODE else (6, 12)
STRESS_PER_CYCLE = (1, 2) if TEST_MODE else (2, 4)
# Longer observation windows to capture OOM/eviction events
OBSERVE_SECONDS = int(os.environ.get("OBSERVE_SECONDS", "90" if TEST_MODE else "180"))
# Metrics scrape wait (after observe). Can be lowered when polling or when scrape interval is shorter.
METRICS_WAIT_SECONDS = int(os.environ.get("METRICS_WAIT_SECONDS", "70"))

# Optional caps to comply with namespace LimitRange/ResourceQuota
MAX_CPU_M = int(os.environ.get("MAX_CPU_M", "500"))        # align with lr-risk-demo-defaults max cpu
MAX_MEM_MI = int(os.environ.get("MAX_MEM_MI", "1024"))      # align with lr-risk-demo-defaults max memory

# Optional overrides for victim/stress counts
VICTIMS_MIN = int(os.environ.get("VICTIMS_MIN", str(VICTIMS_PER_CYCLE[0])))
VICTIMS_MAX = int(os.environ.get("VICTIMS_MAX", str(VICTIMS_PER_CYCLE[1])))
STRESS_MIN = int(os.environ.get("STRESS_MIN", str(STRESS_PER_CYCLE[0])))
STRESS_MAX = int(os.environ.get("STRESS_MAX", str(STRESS_PER_CYCLE[1])))
# Allow overriding Prometheus URL and templates directory for local/dev runs
# Prometheus removed—metrics-server only
TEMPLATES_DIR = os.environ.get("TEMPLATES_DIR", "/app/templates")

# Heuristic labeling thresholds (when no OOM/Evict observed)
HEUR_HIGH_RATIO = float(os.environ.get("HEUR_HIGH_RATIO", "1.0"))   # >= 100% of mem limit → high
HEUR_MED_RATIO = float(os.environ.get("HEUR_MED_RATIO", "0.9"))    # >= 90% of mem limit → medium

# -------------------------------------------------
# 1. K8s client
# -------------------------------------------------
# Use in-cluster config when running as a Pod, fall back to kubeconfig for local dev
try:
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()

# -------------------------------------------------
# 2. Metrics API (metrics.k8s.io)
# -------------------------------------------------
custom = client.CustomObjectsApi()

# -------------------------------------------------
# 2a. Helpers: quantity parsing
# -------------------------------------------------
def parse_mem_to_bytes(q: str) -> int:
    s = str(q).strip().lower()
    try:
        if s.endswith("ki"):
            return int(float(s[:-2]) * 1024)
        if s.endswith("mi"):
            return int(float(s[:-2]) * 1024 * 1024)
        if s.endswith("gi"):
            return int(float(s[:-2]) * 1024 * 1024 * 1024)
        if s.endswith("ti"):
            return int(float(s[:-2]) * 1024**4)
        return int(float(s))
    except Exception:
        return 0

def parse_cpu_to_mcpu(q: str) -> float:
    s = str(q).strip().lower()
    try:
        if s.endswith("m"):
            return float(s[:-1])
        if s.endswith("n"):
            return float(s[:-1]) / 1_000_000.0
        if s.endswith("u"):
            return float(s[:-1]) / 1_000.0
        # assume cores
        return float(s) * 1000.0
    except Exception:
        return 0.0

# -------------------------------------------------
# 3. Helper: render + apply YAML template
# -------------------------------------------------
def apply_template(path: str, subs: dict):
    with open(path) as f:
        tmpl = f.read()
    rendered = tmpl
    for k, v in subs.items():
        rendered = rendered.replace(k, str(v))
    obj = yaml.safe_load(rendered)
    if obj["apiVersion"].startswith("v1") and obj["kind"] == "Pod":
        v1.create_namespaced_pod(namespace=NAMESPACE, body=obj)
    else:
        raise ValueError("Only Pod templates supported")
    return obj["metadata"]["name"]

# -------------------------------------------------
# 4. Clean victim and stress pods only
# -------------------------------------------------
def delete_all_pods():
    # Only delete pods with labels app=victim or app=stress
    for label in ["app=victim", "app=stress"]:
        pods = v1.list_namespaced_pod(namespace=NAMESPACE, label_selector=label)
        for p in pods.items:
            try:
                v1.delete_namespaced_pod(name=p.metadata.name,
                                         namespace=NAMESPACE,
                                         body=client.V1DeleteOptions(),
                                         grace_period_seconds=0)
            except Exception:
                pass  # Ignore deletion errors (already deleted, etc.)

def wait_for_pods_deleted(timeout=60, check_interval=2):
    """
    Wait until all victim and stress pods are fully deleted.
    Returns True if all deleted, False if timeout reached.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        remaining = []
        for label in ["app=victim", "app=stress"]:
            try:
                pods = v1.list_namespaced_pod(namespace=NAMESPACE, label_selector=label)
                remaining.extend([p.metadata.name for p in pods.items])
            except Exception:
                pass
        
        if not remaining:
            return True
        
        time.sleep(check_interval)
    
    # Timeout reached
    print(f"⚠️  Warning: {len(remaining)} pod(s) still terminating after {timeout}s", flush=True)
    return False

# -------------------------------------------------
# 5. DataFrame columns
# -------------------------------------------------
columns = [
    "cpu_request_m", "cpu_limit_m",
    "mem_request_mi", "mem_limit_mi",
    "priority",
    "node_cpu_pressure_pct", "node_mem_pressure_pct",
    "pod_cpu_usage_pct", "pod_mem_usage_mi",
    "risk",                # observed risk (low/medium/high)
    "label_source",        # 'ground_truth' (OOM/Evicted) or 'heuristic'
    "risk_intended"        # profile assigned (low/medium/high)
]
df = pd.DataFrame(columns=columns)

# -------------------------------------------------
# Signal handler for checkpoint writes
# -------------------------------------------------
def write_checkpoint(signum, frame):
    """Write current DataFrame to a checkpoint CSV when SIGUSR1 is received"""
    output_path = os.environ.get("OUTPUT_PATH", "/data/pod_risk_data.csv")
    checkpoint_path = output_path.replace(".csv", "_checkpoint.csv")
    if len(df) > 0:
        df.to_csv(checkpoint_path, index=False)
        print(f"\n📊 Checkpoint written: {checkpoint_path} ({len(df)} rows)", flush=True)
    else:
        print(f"\n⚠️  No data yet for checkpoint", flush=True)

signal.signal(signal.SIGUSR1, write_checkpoint)

# -------------------------------------------------
# 6. Main loop
# -------------------------------------------------
print(f"Running in {'TEST' if TEST_MODE else 'FULL'} mode: {N_CYCLES} cycles, {OBSERVE_SECONDS}s observe")
print(f"💡 Send SIGUSR1 to PID {os.getpid()} to write checkpoint CSV", flush=True)

try:
    for cycle in range(1, N_CYCLES + 1):
        print(f"\n=== CYCLE {cycle}/{N_CYCLES} ===")
        delete_all_pods()
        # Allow a bit more time for kubelet to fully terminate pods between cycles
        wait_for_pods_deleted(timeout=60)
        time.sleep(2)

        # ---- 6.1 Create victim pods (risk-profiled) ----
        victim_names = []
        victim_specs = []
        n_victims = random.randint(VICTIMS_MIN, VICTIMS_MAX)
        for i in range(n_victims):
            suffix = ''.join(random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(4))
            # Choose intended risk profile and derive requests/limits + priority
            if TEST_MODE:
                # Bias toward medium/high in tests to surface label variance quickly
                profile = random.choices(["low", "medium", "high"], weights=[0.5, 0.3, 0.2], k=1)[0]
            else:
                profile = random.choice(["low", "medium", "high"]) 
            base = {
                # low risk: high priority, generous resources
                "low":    {"prio": "high-priority",  "cpu_req": 500, "cpu_lim": 1000, "mem_req": 512,  "mem_lim": 1024, "workload_mem": "200M", "workload_limit": "512Mi", "workload_vm": 1},
                # medium risk: medium priority, moderate resources (borderline)
                "medium": {"prio": "medium-priority","cpu_req": 250, "cpu_lim": 500,  "mem_req": 256,  "mem_lim": 384, "workload_mem": "380M", "workload_limit": "384Mi", "workload_vm": 1},
                # high risk: low priority, tight resources → likely OOM (workload > limit)
                "high":   {"prio": "low-priority",   "cpu_req": 100, "cpu_lim": 150,  "mem_req": 128,  "mem_lim": 256, "workload_mem": "600M", "workload_limit": "256Mi", "workload_vm": 2},
            }[profile]

            # Clamp to namespace caps
            cpu_req = min(base["cpu_req"], MAX_CPU_M)
            cpu_lim = min(base["cpu_lim"], MAX_CPU_M)
            mem_req = min(base["mem_req"], MAX_MEM_MI)
            mem_lim = min(base["mem_lim"], MAX_MEM_MI)
            prio_class = base["prio"]
            name = f"victim-c{cycle}-{i}-{suffix}"

            subs = {
                "victim-PLACEHOLDER": name,
                "PRIORITY_PLACEHOLDER": prio_class,
                "CPU_REQ_PLACEHOLDER": f"{cpu_req}m",
                "CPU_LIM_PLACEHOLDER": f"{cpu_lim}m",
                "MEM_REQ_PLACEHOLDER": f"{mem_req}Mi",
                "MEM_LIM_PLACEHOLDER": f"{mem_lim}Mi",
                "RISK_LABEL_PLACEHOLDER": profile,
                "WORKLOAD_MEM_BYTES": base["workload_mem"],
                "WORKLOAD_MEM_LIMIT": base["workload_limit"],
                "WORKLOAD_VM": str(base["workload_vm"]),
            }
            try:
                apply_template(os.path.join(TEMPLATES_DIR, "victim-pod-template.yaml"), subs)
            except ApiException as e:
                if e.status == 403 and 'exceeded quota' in str(e).lower():
                    print(f"⚠️  Quota exceeded when creating {name}. Proceeding with fewer victims this cycle.", flush=True)
                    break
                else:
                    raise
            victim_names.append(name)
            victim_specs.append({
                "name": name,
                "cpu_req": cpu_req,
                "cpu_lim": cpu_lim,
                "mem_req": mem_req,
                "mem_lim": mem_lim,
                "prio": {"low-priority": -10, "medium-priority": 0, "high-priority": 10}[prio_class],
                "risk_intended": profile,
            })

        # ---- 6.2 Create stress pods ----
        n_stress = random.randint(STRESS_MIN, STRESS_MAX)
        for i in range(n_stress):
            suffix = ''.join(random.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(4))
            name = f"stress-c{cycle}-{i}-{suffix}"
            # Stress intensity knobs (env-overridable) - increased for more failures
            cpu_threads = int(os.environ.get("STRESS_CPU_THREADS", str(random.randint(6, 10))))
            vm_workers = int(os.environ.get("STRESS_VM_WORKERS", str(random.randint(4, 8))))
            vm_bytes_m = int(os.environ.get("STRESS_VM_BYTES_M", str(random.choice([512, 1024, 1536, 2048]))))

            # Stress pod resource requests/limits (env-overridable strings)
            stress_req_cpu_m = os.environ.get("STRESS_REQ_CPU_M", "500")
            stress_req_mem_mi = os.environ.get("STRESS_REQ_MEM_MI", "512")
            stress_lim_cpu = os.environ.get("STRESS_LIM_CPU", "4")
            stress_lim_mem = os.environ.get("STRESS_LIM_MEM", "4Gi")
            subs = {
                "stress-PLACEHOLDER": name,
                "CPU_STRESS": str(cpu_threads),
                "VM_STRESS": str(vm_workers),
                "VM_BYTES": f"{vm_bytes_m}M",
                "CPU_REQ_STRESS": f"{stress_req_cpu_m}m",
                "MEM_REQ_STRESS": f"{stress_req_mem_mi}Mi",
                "CPU_LIM_STRESS": stress_lim_cpu,
                "MEM_LIM_STRESS": stress_lim_mem,
            }
            try:
                apply_template(os.path.join(TEMPLATES_DIR, "stress-pod-template.yaml"), subs)
            except ApiException as e:
                # Gracefully degrade when hitting namespace ResourceQuota
                if e.status == 403 and 'exceeded quota' in str(e).lower():
                    print(f"⚠️  Quota exceeded when creating {name}. Skipping additional stress pods this cycle.", flush=True)
                    break
                else:
                    raise

        # ---- 6.3 Wait for pods to be Running ----
        print("Waiting for all pods to be Running...")
        max_wait = 60
        start_wait = time.time()
        all_running = False
        while time.time() - start_wait < max_wait:
            pods = v1.list_namespaced_pod(namespace=NAMESPACE, label_selector="app in (victim,stress)")
            if all(p.status.phase == "Running" for p in pods.items):
                all_running = True
                break
            time.sleep(2)
        if not all_running:
            print("⚠️  Not all pods Running after 60s, proceeding anyway...")

        # ---- 6.4 Observe workload ----
        print(f"Observing for {OBSERVE_SECONDS}s...")
        time.sleep(OBSERVE_SECONDS)

        # ---- 6.5 Wait for metrics-server to scrape (scrapes every ~60s) ----
        print(f"Waiting {METRICS_WAIT_SECONDS}s for metrics-server to scrape pod metrics...")
        time.sleep(METRICS_WAIT_SECONDS)

        # ---- 6.6 Query Metrics API (node + pod usage) ----
        end = datetime.now(timezone.utc)

        # Node pressure from metrics-server: usage vs allocatable
        nodes_metrics = custom.list_cluster_custom_object(
            group="metrics.k8s.io", version="v1beta1", plural="nodes"
        )
        # Assume single-node (minikube); take first item
        cpu_pressure = 0.0
        mem_pressure = 0.0
        try:
            nm = nodes_metrics.get("items", [])[0]
            name = nm["metadata"]["name"]
            usage = nm["usage"]
            cpu_usage_m = parse_cpu_to_mcpu(usage.get("cpu", 0))
            mem_usage_bytes = parse_mem_to_bytes(usage.get("memory", 0))
            # Get allocatable from core API
            node_obj = v1.read_node(name)
            alloc_cpu = node_obj.status.allocatable.get("cpu", "0")
            alloc_mem = node_obj.status.allocatable.get("memory", "0")
            # cpu alloc may be like '4' (cores) or '4000m'
            if alloc_cpu.endswith("m"):
                alloc_cpu_m = int(alloc_cpu[:-1])
            else:
                alloc_cpu_m = int(float(alloc_cpu) * 1000)
            # memory alloc typically in Ki
            if alloc_mem.endswith("Ki"):
                alloc_mem_bytes = int(alloc_mem[:-2]) * 1024
            elif alloc_mem.endswith("Mi"):
                alloc_mem_bytes = int(alloc_mem[:-2]) * 1024 * 1024
            elif alloc_mem.endswith("Gi"):
                alloc_mem_bytes = int(alloc_mem[:-2]) * 1024 * 1024 * 1024
            else:
                alloc_mem_bytes = int(alloc_mem)

            cpu_pressure = round(100.0 * cpu_usage_m / max(alloc_cpu_m, 1), 2)
            mem_pressure = round(100.0 * mem_usage_bytes / max(alloc_mem_bytes, 1), 2)
        except Exception:
            # keep zeros on failure
            pass

        # ---- 6.7 Determine label for each victim ----
        for spec in victim_specs:
            name = spec["name"]
            pod = v1.read_namespaced_pod(name=name, namespace=NAMESPACE)

            # Was it terminated by OOM or eviction?
            terminated = False
            reason = ""
            # Pod-level eviction
            try:
                if getattr(pod.status, 'reason', '') == 'Evicted':
                    terminated = True
                    reason = 'Evicted'
            except Exception:
                pass
            # Container-level OOM/eviction (current or last state) across all containers
            if not terminated and pod.status and pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    try:
                        if cs.state and cs.state.terminated and cs.state.terminated.reason in ("OOMKilled", "Evicted"):
                            terminated = True
                            reason = cs.state.terminated.reason
                            break
                        if cs.last_state and cs.last_state.terminated and cs.last_state.terminated.reason in ("OOMKilled", "Evicted"):
                            terminated = True
                            reason = cs.last_state.terminated.reason
                            break
                    except Exception:
                        continue

            # Pod usage from metrics-server: sum container usage
            pod_cpu_m = 0.0
            pod_mem_mi = 0.0
            max_mem_ratio = 0.0  # per-container memory usage vs its limit
            try:
                pm = custom.get_namespaced_custom_object(
                    group="metrics.k8s.io", version="v1beta1", namespace=NAMESPACE,
                    plural="pods", name=name
                )
                metrics_containers = pm.get("containers", [])
                for mc in metrics_containers:
                    cu = mc.get("usage", {})
                    pod_cpu_m += parse_cpu_to_mcpu(cu.get("cpu", 0))
                    mem_bytes = parse_mem_to_bytes(cu.get("memory", 0))
                    pod_mem_mi += mem_bytes / (1024 * 1024)
                    # find matching spec container to compute ratio against its limit
                    try:
                        if pod and pod.spec and pod.spec.containers:
                            for sc in pod.spec.containers:
                                if sc.name == mc.get("name"):
                                    lims = getattr(sc.resources, "limits", None)
                                    if lims and "memory" in lims:
                                        lim_bytes = parse_mem_to_bytes(lims["memory"])
                                        if lim_bytes > 0:
                                            max_mem_ratio = max(max_mem_ratio, mem_bytes / lim_bytes)
                                    break
                    except Exception:
                        pass
            except Exception:
                pass

            # Denominator: sum of container CPU limits in the pod; fallback to spec cpu_lim
            denom_m = 0.0
            try:
                if pod and pod.spec and pod.spec.containers:
                    for c in pod.spec.containers:
                        lims = getattr(c.resources, "limits", None)
                        if lims and "cpu" in lims:
                            denom_m += parse_cpu_to_mcpu(lims["cpu"])
            except Exception:
                pass
            if denom_m <= 0 and spec.get("cpu_lim"):
                denom_m = float(spec["cpu_lim"])
            pod_cpu_pct = round(100.0 * pod_cpu_m / denom_m, 2) if denom_m > 0 else 0.0

            # ---- Risk label logic ----
            if terminated and reason == "OOMKilled":
                risk = "high"
                label_source = "ground_truth"
            elif terminated and reason == "Evicted":
                risk = "medium"
                label_source = "ground_truth"
            else:
                # Heuristic fallback when no explicit OOM/Evict observed
                # classify as medium if any container is using >= configured threshold of its memory limit
                if max_mem_ratio >= HEUR_HIGH_RATIO:
                    risk = "high"
                elif max_mem_ratio >= HEUR_MED_RATIO:
                    risk = "medium"
                else:
                    risk = "low"
                label_source = "heuristic"

            row = {
                "cpu_request_m": spec["cpu_req"],
                "cpu_limit_m": spec["cpu_lim"],
                "mem_request_mi": spec["mem_req"],
                "mem_limit_mi": spec["mem_lim"],
                "priority": spec["prio"],
                "node_cpu_pressure_pct": cpu_pressure,
                "node_mem_pressure_pct": mem_pressure,
                "pod_cpu_usage_pct": pod_cpu_pct,
                "pod_mem_usage_mi": round(pod_mem_mi, 2),
                "risk": risk,
                "label_source": label_source,
                "risk_intended": spec.get("risk_intended", "")
            }
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

        print(f"Cycle {cycle} → {len(victim_specs)} rows added (total {len(df)})")

    # -------------------------------------------------
    # 7. Save CSV and cleanup
    # -------------------------------------------------
    output_path = os.environ.get("OUTPUT_PATH", "/data/pod_risk_data.csv")
    df.to_csv(output_path, index=False)
    print(f"\nDone! CSV written: {output_path}")
    print(df["risk"].value_counts())
    
    # Final cleanup - delete all experiment pods
    print("\nCleaning up experiment pods...", flush=True)
    delete_all_pods()
    wait_for_pods_deleted(timeout=60)
    print("Cleanup complete!", flush=True)

    # Optional: keep pod alive briefly so kubectl cp can work on Completed Jobs
    post_sleep = int(os.environ.get("POST_SLEEP_SECONDS", "0") or "0")
    if post_sleep > 0:
        print(f"Sleeping {post_sleep}s before exit to allow copy...", flush=True)
        time.sleep(post_sleep)
    
except Exception as e:
    print(f"\n❌ FATAL ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)