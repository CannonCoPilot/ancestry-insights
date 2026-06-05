"""Phase 5: Supervised Classification (Discriminant Analysis)
Builds discriminant functions comparing behavioral (H1) vs contextual (H0) feature blocks.
Run after Phase 4. Outputs: outputs/phase5/ reports and model results.
"""
import pandas as pd
import numpy as np
import json
import warnings
from pathlib import Path
from datetime import datetime
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score)

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBSAMPLE_DIR = PROJECT_ROOT / "data" / "subsamples"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "phase5"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

T = 10  # Number of subsamples

# ═══════════════════════════════════════════════════
# FEATURE BLOCK DEFINITIONS
# ═══════════════════════════════════════════════════

VELOCITY_FEATURES = [
    "days_to_first_login", "days_login_to_tree_edit", "days_login_to_name",
    "days_to_first_tree_edit", "days_to_first_name", "activation_speed",
]

VOLUME_FEATURES = [
    "log_logins_pw", "log_tree_edits_pw", "log_names_pw", "log_sources_pw",
    "logins_90d", "tree_edits_90d", "names_90d", "sources_90d",
]

SEQUENCING_FEATURES = [
    "activity_breadth", "funnel_stage",
    "has_login", "has_tree_edits", "has_names", "has_sources",
    "has_memories", "has_record_edits", "has_get_involved",
]

CONTEXTUAL_FEATURES = [
    "user_age", "gdp_per_capita_ppp", "hdi", "internet_pct",
    "pct_christian", "govt_restrictions_index", "social_hostilities_index",
    "lds_members_per_capita", "religious_diversity_index",
]
# Categorical contextual features (will be one-hot encoded)
CONTEXTUAL_CATEGORICAL = ["country_cluster", "age_group"]

# Construct labels for each feature
CONSTRUCT_MAP = {}
for f in VELOCITY_FEATURES: CONSTRUCT_MAP[f] = "Velocity"
for f in VOLUME_FEATURES: CONSTRUCT_MAP[f] = "Volume"
for f in SEQUENCING_FEATURES: CONSTRUCT_MAP[f] = "Sequencing"
for f in CONTEXTUAL_FEATURES + CONTEXTUAL_CATEGORICAL: CONSTRUCT_MAP[f] = "Contextual"

qc_log = []
all_results = []

def log_qc(step, metric, value, note=""):
    entry = {"step": step, "metric": metric, "value": value, "note": note,
             "timestamp": datetime.now().isoformat()}
    qc_log.append(entry)
    print(f"  [{step}] {metric} = {value}  {note}")


def prepare_features(df, feature_list, categorical_list=None):
    """Prepare feature matrix: fill NaN, one-hot encode categoricals, return X and feature names."""
    X_parts = []
    feat_names = []

    # Continuous features
    for f in feature_list:
        if f in df.columns:
            X_parts.append(df[[f]].fillna(0).values)
            feat_names.append(f)

    # Categorical features (one-hot)
    if categorical_list:
        for f in categorical_list:
            if f in df.columns:
                dummies = pd.get_dummies(df[f], prefix=f, drop_first=True).fillna(0)
                X_parts.append(dummies.values)
                feat_names.extend(dummies.columns.tolist())

    if X_parts:
        X = np.hstack(X_parts)
    else:
        X = np.zeros((len(df), 1))
        feat_names = ["dummy"]

    return X, feat_names


def evaluate_model(y_true, y_pred, y_prob):
    """Compute classification metrics."""
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "auc": roc_auc_score(y_true, y_prob) if len(np.unique(y_true)) > 1 else 0.5,
    }


def run_block(block_name, X_train, X_test, y_train, y_test, feat_names, subsample_id):
    """Run LDA, Logistic Regression, and Random Forest on a feature block."""
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    results = []

    # LDA
    try:
        lda = LinearDiscriminantAnalysis()
        lda.fit(X_train_s, y_train)
        y_pred = lda.predict(X_test_s)
        y_prob = lda.predict_proba(X_test_s)[:, 1]
        metrics = evaluate_model(y_test, y_pred, y_prob)
        metrics.update({"block": block_name, "model": "LDA", "subsample": subsample_id})

        # Extract loadings
        if hasattr(lda, "coef_") and lda.coef_.shape[1] == len(feat_names):
            loadings = dict(zip(feat_names, np.abs(lda.coef_[0])))
            metrics["top_features"] = sorted(loadings.items(), key=lambda x: -x[1])[:10]
        results.append(metrics)
    except Exception as e:
        results.append({"block": block_name, "model": "LDA", "subsample": subsample_id,
                        "accuracy": 0, "auc": 0.5, "error": str(e)})

    # Logistic Regression
    try:
        lr = LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced")
        lr.fit(X_train_s, y_train)
        y_pred = lr.predict(X_test_s)
        y_prob = lr.predict_proba(X_test_s)[:, 1]
        metrics = evaluate_model(y_test, y_pred, y_prob)
        metrics.update({"block": block_name, "model": "LogReg", "subsample": subsample_id})

        if lr.coef_.shape[1] == len(feat_names):
            loadings = dict(zip(feat_names, np.abs(lr.coef_[0])))
            metrics["top_features"] = sorted(loadings.items(), key=lambda x: -x[1])[:10]
        results.append(metrics)
    except Exception as e:
        results.append({"block": block_name, "model": "LogReg", "subsample": subsample_id,
                        "accuracy": 0, "auc": 0.5, "error": str(e)})

    # Random Forest
    try:
        rf = RandomForestClassifier(n_estimators=300, max_depth=None, random_state=42,
                                     class_weight="balanced", n_jobs=-1)
        rf.fit(X_train, y_train)  # RF doesn't need scaling
        y_pred = rf.predict(X_test)
        y_prob = rf.predict_proba(X_test)[:, 1]
        metrics = evaluate_model(y_test, y_pred, y_prob)
        metrics.update({"block": block_name, "model": "RF", "subsample": subsample_id})

        importances = dict(zip(feat_names, rf.feature_importances_))
        metrics["top_features"] = sorted(importances.items(), key=lambda x: -x[1])[:10]
        results.append(metrics)
    except Exception as e:
        results.append({"block": block_name, "model": "RF", "subsample": subsample_id,
                        "accuracy": 0, "auc": 0.5, "error": str(e)})

    return results


def main():
    print("Phase 5: Supervised Classification (Discriminant Analysis)")
    print(f"Subsamples: T={T}, Output: {OUTPUT_DIR}")

    all_feature_importances = []

    for t in range(1, T + 1):
        print(f"\n{'='*60}")
        print(f"Subsample {t:02d}")
        print(f"{'='*60}")

        df = pd.read_parquet(SUBSAMPLE_DIR / f"subsample_{t:02d}.parquet")
        train = df[df["split"] == "train"].copy()
        test = df[df["split"] == "test"].copy()

        # ═══ Step 5.A.2: Recompute persistence dichotomization WITHIN Tier D ═══
        median_c = df["persistence_c"].median()
        train["y"] = (train["persistence_c"] >= median_c).astype(int)
        test["y"] = (test["persistence_c"] >= median_c).astype(int)

        y_train = train["y"].values
        y_test = test["y"].values

        if t == 1:
            log_qc("5.A.2", "tier_d_median_persistence_c", round(median_c, 4))
            log_qc("5.A.2", "class_balance_train", f"0:{(y_train==0).sum()}, 1:{(y_train==1).sum()}")
            log_qc("5.A.2", "class_balance_test", f"0:{(y_test==0).sum()}, 1:{(y_test==1).sum()}")

        # ═══ Run all 6 blocks ═══
        blocks = {
            "B1_Velocity": (VELOCITY_FEATURES, []),
            "B2_Volume": (VOLUME_FEATURES, []),
            "B3_Sequencing": (SEQUENCING_FEATURES, []),
            "B4_H1_Combined": (VELOCITY_FEATURES + VOLUME_FEATURES + SEQUENCING_FEATURES, []),
            "B5_H0_Contextual": (CONTEXTUAL_FEATURES, CONTEXTUAL_CATEGORICAL),
            "B6_Full": (VELOCITY_FEATURES + VOLUME_FEATURES + SEQUENCING_FEATURES + CONTEXTUAL_FEATURES,
                        CONTEXTUAL_CATEGORICAL),
        }

        for block_name, (cont_feats, cat_feats) in blocks.items():
            X_train, feat_names = prepare_features(train, cont_feats, cat_feats)
            X_test, _ = prepare_features(test, cont_feats, cat_feats)

            results = run_block(block_name, X_train, X_test, y_train, y_test, feat_names, t)
            all_results.extend(results)

            # Collect feature importances for aggregation
            for r in results:
                if "top_features" in r:
                    for feat, imp in r["top_features"]:
                        all_feature_importances.append({
                            "subsample": t, "block": block_name, "model": r["model"],
                            "feature": feat, "importance": imp,
                            "construct": CONSTRUCT_MAP.get(feat.split("_")[0] if "_" not in feat else feat, "Contextual"),
                        })

            # Print summary for this block
            for r in results:
                auc = r.get("auc", "N/A")
                f1 = r.get("f1", "N/A")
                if isinstance(auc, float):
                    print(f"  {block_name:20s} {r['model']:8s} AUC={auc:.4f} F1={f1:.4f}")
                else:
                    print(f"  {block_name:20s} {r['model']:8s} ERROR: {r.get('error', 'unknown')}")

    # ═══ Step 5.D: Aggregation ═══
    print(f"\n{'='*60}")
    print("AGGREGATION")
    print(f"{'='*60}")

    results_df = pd.DataFrame(all_results)

    # Block comparison table
    agg = results_df.groupby(["block", "model"]).agg(
        mean_auc=("auc", "mean"), std_auc=("auc", "std"),
        mean_f1=("f1", "mean"), std_f1=("f1", "std"),
        mean_acc=("accuracy", "mean"), std_acc=("accuracy", "std"),
    ).round(4).sort_values("mean_auc", ascending=False)

    print("\n=== Block Comparison Table ===")
    print(agg.to_string())

    # Incremental AUC analysis
    print("\n=== Incremental AUC Analysis ===")
    for model in ["LDA", "LogReg", "RF"]:
        m_df = results_df[results_df["model"] == model]
        b4 = m_df[m_df["block"] == "B4_H1_Combined"]["auc"]
        b5 = m_df[m_df["block"] == "B5_H0_Contextual"]["auc"]
        b6 = m_df[m_df["block"] == "B6_Full"]["auc"]

        if len(b4) > 0 and len(b5) > 0 and len(b6) > 0:
            delta_h1 = (b6.values - b5.values).mean()  # Value of adding engagement to context
            delta_h0 = (b6.values - b4.values).mean()  # Value of adding context to engagement
            log_qc("5.D.5", f"{model}_B4_mean_auc", round(b4.mean(), 4))
            log_qc("5.D.5", f"{model}_B5_mean_auc", round(b5.mean(), 4))
            log_qc("5.D.5", f"{model}_B6_mean_auc", round(b6.mean(), 4))
            log_qc("5.D.5", f"{model}_delta_H1", round(delta_h1, 4), "Incremental value of engagement features")
            log_qc("5.D.5", f"{model}_delta_H0", round(delta_h0, 4), "Incremental value of contextual features")

    # Feature importance aggregation (RF model, full block)
    print("\n=== Top Features (RF, Full Model, aggregated) ===")
    imp_df = pd.DataFrame(all_feature_importances)
    if len(imp_df) > 0:
        rf_full = imp_df[(imp_df["model"] == "RF") & (imp_df["block"] == "B6_Full")]
        if len(rf_full) > 0:
            top_feats = rf_full.groupby("feature")["importance"].mean().sort_values(ascending=False).head(20)
            for feat, imp in top_feats.items():
                construct = CONSTRUCT_MAP.get(feat, "Contextual")
                # Handle one-hot encoded features
                for prefix in ["country_cluster_", "age_group_"]:
                    if feat.startswith(prefix):
                        construct = "Contextual"
                        break
                print(f"  {feat:40s} {imp:.4f}  [{construct}]")
                log_qc("5.D.4", f"rf_importance:{feat}", round(imp, 4), construct)

    # Write outputs
    results_df.to_csv(OUTPUT_DIR / "block_results.csv", index=False)
    agg.to_csv(OUTPUT_DIR / "block_comparison.csv")
    if len(imp_df) > 0:
        imp_df.to_csv(OUTPUT_DIR / "feature_importances.csv", index=False)

    # QC log
    (OUTPUT_DIR / "qc_log.json").write_text(json.dumps(qc_log, indent=2, default=str))

    # Summary report
    report = [
        "# Phase 5: Classification Results Summary",
        f"\n**Generated**: {datetime.now().isoformat()}",
        f"**Subsamples**: T={T}",
        "\n---\n",
        "## Block Comparison (sorted by Mean AUC)\n",
        agg.to_markdown(),
        "\n## QC Log\n",
        "| Step | Metric | Value | Note |",
        "|------|--------|-------|------|",
    ]
    for entry in qc_log:
        val = str(entry["value"])[:80]
        report.append(f"| {entry['step']} | {entry['metric']} | {val} | {entry.get('note', '')} |")

    (OUTPUT_DIR / "classification_report.md").write_text("\n".join(report))

    print(f"\n=== Phase 5 Complete ===")
    print(f"Results: {OUTPUT_DIR}")
    print(f"Total model runs: {len(results_df)}")


if __name__ == "__main__":
    main()
