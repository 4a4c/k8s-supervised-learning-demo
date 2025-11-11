#!/usr/bin/env python3
"""
Validate ML-readiness of pod_risk_data.csv
Reports: row count, label distribution, feature variance, and ML-ready status.
"""
import sys
import pandas as pd

def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "data/pod_risk_data.csv"
    
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"❌ CSV not found: {csv_path}")
        sys.exit(1)
    
    print(f"\n📊 Dataset Summary: {csv_path}")
    print("=" * 60)
    
    # Row count
    n_rows = len(df)
    print(f"\n  Total rows: {n_rows}")
    
    # Label distribution
    print(f"\n  Risk label distribution:")
    if 'risk' in df.columns:
        counts = df['risk'].value_counts()
        for label, count in counts.items():
            pct = 100.0 * count / n_rows
            print(f"    {label:8s}: {count:4d} ({pct:5.1f}%)")
    else:
        print("    ❌ 'risk' column not found")

    # Label source distribution
    if 'label_source' in df.columns:
        print(f"\n  Label source:")
        src_counts = df['label_source'].value_counts()
        for src, count in src_counts.items():
            pct = 100.0 * count / n_rows
            print(f"    {src:12s}: {count:4d} ({pct:5.1f}%)")
    else:
        print("\n  ⚠️  No 'label_source' column; consider adding to distinguish ground_truth vs heuristic labels.")
    
    # Feature variance
    print(f"\n  Feature ranges:")
    features = [
        ('cpu_request_m', 'CPU request'),
        ('cpu_limit_m', 'CPU limit'),
        ('mem_request_mi', 'Mem request'),
        ('mem_limit_mi', 'Mem limit'),
        ('node_cpu_pressure_pct', 'Node CPU%'),
        ('node_mem_pressure_pct', 'Node Mem%'),
        ('pod_cpu_usage_pct', 'Pod CPU%'),
        ('pod_mem_usage_mi', 'Pod Mem (Mi)'),
    ]
    
    for col, desc in features:
        if col in df.columns:
            min_val = df[col].min()
            max_val = df[col].max()
            mean_val = df[col].mean()
            nonzero = (df[col] > 0).sum()
            nonzero_pct = 100.0 * nonzero / n_rows
            print(f"    {desc:16s}: [{min_val:7.2f}, {max_val:7.2f}]  mean={mean_val:7.2f}  non-zero={nonzero_pct:5.1f}%")
        else:
            print(f"    {desc:16s}: ❌ column not found")
    
    # ML-ready assessment
    print(f"\n  ML-Ready Assessment:")
    print("=" * 60)
    
    checks = []
    
    # Check 1: Minimum rows
    min_rows = 500
    row_check = n_rows >= min_rows
    checks.append(row_check)
    status = "✅" if row_check else "❌"
    print(f"  {status} Sample size: {n_rows} rows (need {min_rows}+)")
    
    # Check 2: Label variance
    if 'risk' in df.columns:
        label_counts = df['risk'].value_counts()
        has_variance = len(label_counts) > 1 and label_counts.min() >= 5
        checks.append(has_variance)
        status = "✅" if has_variance else "❌"
        print(f"  {status} Label variance: {len(label_counts)} unique labels, min count {label_counts.min()}")
    else:
        checks.append(False)
        print(f"  ❌ Label variance: 'risk' column missing")
    
    # Check 3: Usage metrics non-zero
    usage_cols = ['pod_cpu_usage_pct', 'pod_mem_usage_mi']
    usage_ok = all(
        col in df.columns and (df[col] > 0).sum() / n_rows > 0.5
        for col in usage_cols
    )
    checks.append(usage_ok)
    status = "✅" if usage_ok else "❌"
    print(f"  {status} Usage metrics: >50% non-zero CPU/Mem usage")
    
    # Check 4: Node pressure variance
    pressure_cols = ['node_cpu_pressure_pct', 'node_mem_pressure_pct']
    pressure_ok = all(
        col in df.columns and df[col].std() > 5.0
        for col in pressure_cols
    )
    checks.append(pressure_ok)
    status = "✅" if pressure_ok else "⚠️ "
    print(f"  {status} Node pressure: stdev > 5% (captures contention variance)")
    
    # Overall verdict
    print("\n" + "=" * 60)
    if all(checks[:3]):  # First 3 are critical
        print("✅ Dataset is ML-READY")
        if not checks[3]:
            print("⚠️  Note: Low node pressure variance may reduce feature importance")
    else:
        print("❌ Dataset NOT ML-ready")
        print("\n  Next steps:")
        if not checks[0]:
            print("    - Run more cycles to increase sample size")
        if not checks[1]:
            print("    - Increase stress intensity to trigger more OOM/eviction")
        if not checks[2]:
            print("    - Extend observation windows to capture pod usage")

    # Heuristic-label leakage warning
    if 'label_source' in df.columns and df['label_source'].eq('heuristic').all():
        uses_mem_usage = 'pod_mem_usage_mi' in df.columns
        uses_mem_limit = 'mem_limit_mi' in df.columns
        if uses_mem_usage and uses_mem_limit:
            print("\n⚠️  Leakage risk: Labels are heuristic based on memory pressure, and features include memory usage and limits.\n    When training, drop features that directly define the heuristic (e.g., pod_mem_usage_mi, mem_limit_mi, or their ratio),\n    or use a temporal split (features from t, label from t+Δ) to reduce shortcut learning.")
    
    print("=" * 60 + "\n")
    
    sys.exit(0 if all(checks[:3]) else 1)

if __name__ == "__main__":
    main()
