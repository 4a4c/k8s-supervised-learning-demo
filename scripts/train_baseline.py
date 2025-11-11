#!/usr/bin/env python3
"""
Baseline trainer for pod risk classification.
- Loads CSV (default: data/pod_risk_data.csv)
- Optionally filters by label_source (heuristic|ground_truth|any)
- Mitigates leakage when training on heuristic labels by dropping features that encode the rule:
  * drops ['pod_mem_usage_mi','mem_limit_mi'] when label_source is heuristic-only (or --drop-leakage)
- Trains a RandomForest classifier and prints metrics and feature importances.
"""
import argparse
import sys
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.ensemble import RandomForestClassifier

DEFAULT_CSV = "data/pod_risk_data.csv"
BASE_FEATURES = [
    'cpu_request_m', 'cpu_limit_m', 'mem_request_mi', 'mem_limit_mi',
    'priority', 'node_cpu_pressure_pct', 'node_mem_pressure_pct',
    'pod_cpu_usage_pct', 'pod_mem_usage_mi'
]
LEAKY_FEATURES = ['pod_mem_usage_mi', 'mem_limit_mi']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', default=DEFAULT_CSV)
    p.add_argument('--label-source', default='any', choices=['any','heuristic','ground_truth'],
                   help='Filter rows by label_source before training')
    p.add_argument('--drop-leakage', action='store_true',
                   help='Drop features known to encode the heuristic rule (recommended when training on heuristic labels)')
    p.add_argument('--test-size', type=float, default=0.2)
    p.add_argument('--random-state', type=int, default=42)
    args = p.parse_args()

    try:
        df = pd.read_csv(args.csv)
    except FileNotFoundError:
        print(f"❌ CSV not found: {args.csv}")
        return 1

    if 'risk' not in df.columns:
        print("❌ 'risk' column missing in CSV")
        return 1

    if args.label_source != 'any':
        if 'label_source' not in df.columns:
            print("⚠️  No 'label_source' column; cannot filter, proceeding with all rows")
        else:
            df = df[df['label_source'] == args.label_source]
            print(f"ℹ️  Filtered by label_source={args.label_source}: {len(df)} rows")

    # Prepare features and target
    X_cols = [c for c in BASE_FEATURES if c in df.columns]

    # Auto-drop leakage if all labels are heuristic and features exist
    if 'label_source' in df.columns and df['label_source'].eq('heuristic').all():
        if args.drop_leakage:
            X_cols = [c for c in X_cols if c not in LEAKY_FEATURES]
            print(f"ℹ️  Dropped potential leakage features: {LEAKY_FEATURES}")
        else:
            print("⚠️  Heuristic labels detected; consider --drop-leakage to remove ['pod_mem_usage_mi','mem_limit_mi']")

    if not X_cols:
        print("❌ No usable features found")
        return 1

    X = df[X_cols]
    y = df['risk']

    # Encode y to categorical (str ok for RF)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.random_state, stratify=y if len(y.unique())>1 else None
    )

    # Train
    clf = RandomForestClassifier(n_estimators=200, random_state=args.random_state, class_weight='balanced')
    clf.fit(X_train, y_train)

    # Evaluate
    y_pred = clf.predict(X_test)
    print("\nClassification Report:\n")
    print(classification_report(y_test, y_pred, digits=3))

    print("Confusion Matrix:\n")
    print(confusion_matrix(y_test, y_pred))

    # Feature importances
    importances = pd.Series(clf.feature_importances_, index=X_cols).sort_values(ascending=False)
    print("\nTop features:\n")
    print(importances.head(12))

    return 0


if __name__ == '__main__':
    sys.exit(main())
