#!/usr/bin/env python3
"""
Train-and-demo script for pod risk classification assignment.
- Trains a RandomForest classifier on the dataset
- Saves the trained model
- Runs three example predictions from the assignment
- Prints output in assignment-friendly format
"""
import argparse
import sys
import pandas as pd
import pickle
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score, balanced_accuracy_score
from sklearn.ensemble import RandomForestClassifier

DEFAULT_CSV = "data/pod_risk_data_fast_combined.csv"
BASE_FEATURES = [
    'cpu_request_m', 'cpu_limit_m', 'mem_request_mi', 'mem_limit_mi',
    'priority', 'node_cpu_pressure_pct', 'node_mem_pressure_pct',
    'pod_cpu_usage_pct', 'pod_mem_usage_mi'
]
LEAKY_FEATURES = ['pod_mem_usage_mi', 'mem_limit_mi']


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', default=DEFAULT_CSV, help='Path to training CSV')
    p.add_argument('--drop-leakage', action='store_true',
                   help='Drop features that encode heuristic rule (recommended for heuristic labels)')
    p.add_argument('--test-size', type=float, default=0.2)
    p.add_argument('--random-state', type=int, default=42)
    p.add_argument('--model-out', default='pod_risk_model.pkl', help='Output model file')
    args = p.parse_args()

    print("=" * 60)
    print("K8s Pod Eviction Risk Predictor - Train & Demo")
    print("=" * 60)

    # Load data
    try:
        df = pd.read_csv(args.csv)
    except FileNotFoundError:
        print(f"❌ CSV not found: {args.csv}")
        return 1

    if 'risk' not in df.columns:
        print("❌ 'risk' column missing in CSV")
        return 1

    print(f"\n📊 Dataset: {len(df)} samples")
    print(f"   Class distribution:\n{df['risk'].value_counts()}\n")

    # Prepare features
    X_cols = [c for c in BASE_FEATURES if c in df.columns]

    # Drop leakage if requested or all labels are heuristic
    if 'label_source' in df.columns and df['label_source'].eq('heuristic').all():
        if args.drop_leakage:
            X_cols = [c for c in X_cols if c not in LEAKY_FEATURES]
            print(f"ℹ️  Dropped leakage features: {LEAKY_FEATURES}")
        else:
            print("⚠️  All labels are heuristic; consider --drop-leakage")

    if not X_cols:
        print("❌ No usable features found")
        return 1

    print(f"ℹ️  Features used: {X_cols}\n")

    X = df[X_cols]
    y = df['risk']

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.random_state,
        stratify=y if len(y.unique()) > 1 else None
    )

    print(f"📈 Train: {len(X_train)} samples, Test: {len(X_test)} samples")

    # Train
    print("\n🔧 Training RandomForest classifier...")
    clf = RandomForestClassifier(n_estimators=200, random_state=args.random_state, class_weight='balanced')
    clf.fit(X_train, y_train)

    # Save model
    with open(args.model_out, 'wb') as f:
        pickle.dump((clf, X_cols), f)
    print(f"✅ Model saved: {args.model_out}")

    # Evaluate
    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    bal_acc = balanced_accuracy_score(y_test, y_pred)

    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print(f"\nAccuracy: {acc:.3f}")
    print(f"Balanced Accuracy: {bal_acc:.3f}")
    print("\nClassification Report:\n")
    print(classification_report(y_test, y_pred, digits=3))
    print("Confusion Matrix:\n")
    print(confusion_matrix(y_test, y_pred))
    print("\nFeature Importances:")
    importances = pd.Series(clf.feature_importances_, index=X_cols).sort_values(ascending=False)
    for feat, imp in importances.items():
        print(f"  {feat:30s} {imp:.4f}")

    # Demo: Three example predictions
    print("\n" + "=" * 60)
    print("DEMO: THREE EXAMPLE PREDICTIONS")
    print("=" * 60)

    # Example 1: Low risk
    # Input: CPU request 500m, limit 1, memory request 1Gi, node CPU pressure 65%, pod priority 0
    # Expected output: low
    ex1 = {
        'cpu_request_m': 500,
        'cpu_limit_m': 1000,
        'mem_request_mi': 1024,
        'mem_limit_mi': 1024,
        'priority': 0,
        'node_cpu_pressure_pct': 65.0,
        'node_mem_pressure_pct': 50.0,  # estimate
        'pod_cpu_usage_pct': 40.0,  # estimate: healthy usage
        'pod_mem_usage_mi': 600.0   # ~60% of 1024Mi
    }

    # Example 2: High risk
    # Input: CPU request 2, limit 2, memory request 4Gi, node CPU pressure 92%, pod priority -5
    # Expected output: high
    ex2 = {
        'cpu_request_m': 2000,
        'cpu_limit_m': 2000,
        'mem_request_mi': 4096,
        'mem_limit_mi': 4096,
        'priority': -5,
        'node_cpu_pressure_pct': 92.0,
        'node_mem_pressure_pct': 85.0,  # high pressure
        'pod_cpu_usage_pct': 95.0,  # near limit
        'pod_mem_usage_mi': 3900.0  # ~95% of 4096Mi
    }

    # Example 3: Medium risk
    # Input: CPU request 1, limit 2, memory request 2Gi, node CPU pressure 78%, pod priority 0
    # Expected output: medium
    ex3 = {
        'cpu_request_m': 1000,
        'cpu_limit_m': 2000,
        'mem_request_mi': 2048,
        'mem_limit_mi': 2048,
        'priority': 0,
        'node_cpu_pressure_pct': 78.0,
        'node_mem_pressure_pct': 70.0,  # moderate pressure
        'pod_cpu_usage_pct': 65.0,  # moderate
        'pod_mem_usage_mi': 1500.0  # ~73% of 2048Mi
    }

    examples = [
        ("Example 1 (Expected: low)", ex1),
        ("Example 2 (Expected: high)", ex2),
        ("Example 3 (Expected: medium)", ex3)
    ]

    for label, ex in examples:
        # Build input frame matching training features
        input_data = {col: [ex.get(col, 0)] for col in X_cols}
        input_df = pd.DataFrame(input_data)
        pred = clf.predict(input_df)[0]
        proba = clf.predict_proba(input_df)[0]
        proba_dict = dict(zip(clf.classes_, proba))

        print(f"\n{label}")
        print(f"  Input:")
        print(f"    CPU request: {ex['cpu_request_m']}m, limit: {ex['cpu_limit_m']}m")
        print(f"    Memory request: {ex['mem_request_mi']}Mi, limit: {ex['mem_limit_mi']}Mi")
        print(f"    Node CPU pressure: {ex['node_cpu_pressure_pct']:.1f}%")
        print(f"    Pod priority: {ex['priority']}")
        print(f"  Output: {pred}")
        print(f"  Confidence: {proba_dict}")

    print("\n" + "=" * 60)
    print("✅ Training and demo complete!")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    sys.exit(main())
