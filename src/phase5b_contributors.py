"""Phase 5b+6b: Second-pass analysis on "Contributors Only" (2+ logins).
Filters 1-login users from subsamples, pairs remaining into 5 new subsamples,
re-runs Phase 5 classification and Phase 6 clustering.
All outputs go to outputs/phase5b/ and outputs/phase6b/ to avoid confusion.
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
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score, silhouette_score,
                             calinski_harabasz_score, davies_bouldin_score,
                             adjusted_rand_score)
from scipy.stats import chi2_contingency
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBSAMPLE_DIR = PROJECT_ROOT / "data" / "subsamples"
OUTPUT_5B = PROJECT_ROOT / "outputs" / "phase5b"
OUTPUT_6B = PROJECT_ROOT / "outputs" / "phase6b"
OUTPUT_5B.mkdir(parents=True, exist_ok=True)
OUTPUT_6B.mkdir(parents=True, exist_ok=True)

# Feature blocks (same as Phase 5)
VELOCITY = ["days_to_first_login", "days_login_to_tree_edit", "days_login_to_name",
            "days_to_first_tree_edit", "days_to_first_name", "activation_speed"]
VOLUME = ["log_logins_pw", "log_tree_edits_pw", "log_names_pw", "log_sources_pw",
          "logins_90d", "tree_edits_90d", "names_90d", "sources_90d"]
SEQUENCING = ["activity_breadth", "funnel_stage", "has_sources", "has_memories",
              "has_record_edits", "has_get_involved"]
CONTEXTUAL_CONT = ["user_age", "gdp_per_capita_ppp", "hdi",
                   "pct_christian", "govt_restrictions_index", "social_hostilities_index",
                   "lds_members_per_capita", "religious_diversity_index"]
CONTEXTUAL_CAT = ["country_cluster", "age_group"]

CLUSTER_FEATURES = [
    "logins_90d", "log_logins_pw", "activity_breadth", "funnel_stage",
    "log_sources_pw", "sources_90d", "log_tree_edits_pw", "tree_edits_90d",
    "names_90d", "log_names_pw", "has_sources", "has_memories",
    "days_to_first_login", "activation_speed", "user_age",
]

CONSTRUCT_MAP = {}
for f in VELOCITY: CONSTRUCT_MAP[f] = "Velocity"
for f in VOLUME: CONSTRUCT_MAP[f] = "Volume"
for f in SEQUENCING: CONSTRUCT_MAP[f] = "Sequencing"
for f in CONTEXTUAL_CONT + CONTEXTUAL_CAT: CONSTRUCT_MAP[f] = "Contextual"

qc_log = []

def log_qc(step, metric, value, note=""):
    qc_log.append({"step": step, "metric": metric, "value": value, "note": note,
                    "timestamp": datetime.now().isoformat()})
    print(f"  [{step}] {metric} = {value}  {note}")


def prepare_features(df, cont_list, cat_list=None):
    parts, names = [], []
    for f in cont_list:
        if f in df.columns:
            parts.append(df[[f]].fillna(0).values)
            names.append(f)
    if cat_list:
        for f in cat_list:
            if f in df.columns:
                dummies = pd.get_dummies(df[f], prefix=f, drop_first=True).fillna(0)
                parts.append(dummies.values)
                names.extend(dummies.columns.tolist())
    return np.hstack(parts) if parts else np.zeros((len(df), 1)), names


def eval_model(y_true, y_pred, y_prob):
    return {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "auc": roc_auc_score(y_true, y_prob) if len(np.unique(y_true)) > 1 else 0.5,
    }


def run_block(name, Xtr, Xte, ytr, yte, feat_names, sub_id):
    scaler = StandardScaler()
    Xtr_s, Xte_s = scaler.fit_transform(Xtr), scaler.transform(Xte)
    results = []
    # LDA
    try:
        m = LinearDiscriminantAnalysis().fit(Xtr_s, ytr)
        r = eval_model(yte, m.predict(Xte_s), m.predict_proba(Xte_s)[:, 1])
        r.update({"block": name, "model": "LDA", "subsample": sub_id})
        if hasattr(m, "coef_") and m.coef_.shape[1] == len(feat_names):
            r["top_features"] = sorted(zip(feat_names, np.abs(m.coef_[0])), key=lambda x: -x[1])[:10]
        results.append(r)
    except Exception as e:
        results.append({"block": name, "model": "LDA", "subsample": sub_id, "auc": 0.5, "error": str(e)})
    # LogReg
    try:
        m = LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced").fit(Xtr_s, ytr)
        r = eval_model(yte, m.predict(Xte_s), m.predict_proba(Xte_s)[:, 1])
        r.update({"block": name, "model": "LogReg", "subsample": sub_id})
        if m.coef_.shape[1] == len(feat_names):
            r["top_features"] = sorted(zip(feat_names, np.abs(m.coef_[0])), key=lambda x: -x[1])[:10]
        results.append(r)
    except Exception as e:
        results.append({"block": name, "model": "LogReg", "subsample": sub_id, "auc": 0.5, "error": str(e)})
    # RF
    try:
        m = RandomForestClassifier(n_estimators=300, random_state=42, class_weight="balanced", n_jobs=-1).fit(Xtr, ytr)
        r = eval_model(yte, m.predict(Xte), m.predict_proba(Xte)[:, 1])
        r.update({"block": name, "model": "RF", "subsample": sub_id})
        r["top_features"] = sorted(zip(feat_names, m.feature_importances_), key=lambda x: -x[1])[:10]
        results.append(r)
    except Exception as e:
        results.append({"block": name, "model": "RF", "subsample": sub_id, "auc": 0.5, "error": str(e)})
    return results


def cramers_v(ct):
    chi2 = chi2_contingency(ct)[0]
    n = ct.sum().sum()
    return np.sqrt(chi2 / (n * (min(ct.shape) - 1))) if min(ct.shape) > 1 and n > 0 else 0


def main():
    print("=" * 70)
    print("SECOND-PASS ANALYSIS: Contributors Only (2+ logins)")
    print("=" * 70)

    # ═══ BUILD CONTRIBUTOR SUBSAMPLES ═══
    print("\n=== Building contributor subsamples (pair originals) ===")
    contrib_subs = []
    pairs = [(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)]

    for i, (a, b) in enumerate(pairs, 1):
        da = pd.read_parquet(SUBSAMPLE_DIR / f"subsample_{a:02d}.parquet")
        db = pd.read_parquet(SUBSAMPLE_DIR / f"subsample_{b:02d}.parquet")
        # Filter to 2+ logins
        ca = da[da["DAYS_LOGGING_IN"] >= 2]
        cb = db[db["DAYS_LOGGING_IN"] >= 2]
        combined = pd.concat([ca, cb], ignore_index=True)
        # Re-split 70/30
        rng = np.random.RandomState(42 + i)
        combined["split"] = "test"
        train_idx = rng.choice(combined.index, size=int(len(combined) * 0.7), replace=False)
        combined.loc[train_idx, "split"] = "train"
        contrib_subs.append(combined)
        n_tr = (combined["split"] == "train").sum()
        n_te = (combined["split"] == "test").sum()
        log_qc("prep", f"contrib_sub_{i}", f"n={len(combined)}, train={n_tr}, test={n_te}",
                f"from subs {a}+{b}")

    # ═══ PHASE 5b: CLASSIFICATION ═══
    print(f"\n{'='*70}")
    print("PHASE 5b: CLASSIFICATION (Contributors Only)")
    print(f"{'='*70}")

    all_results = []
    all_importances = []

    for t, df in enumerate(contrib_subs, 1):
        print(f"\n--- Contributor Subsample {t} (n={len(df)}) ---")
        median_c = df["persistence_c"].median()
        df["y"] = (df["persistence_c"] >= median_c).astype(int)
        train, test = df[df["split"] == "train"], df[df["split"] == "test"]
        ytr, yte = train["y"].values, test["y"].values

        if t == 1:
            log_qc("5b.A", "median_persistence_c", round(median_c, 4))
            log_qc("5b.A", "class_balance", f"0:{(ytr==0).sum()}, 1:{(ytr==1).sum()}")

        blocks = {
            "B1_Velocity": (VELOCITY, []),
            "B2_Volume": (VOLUME, []),
            "B3_Sequencing": (SEQUENCING, []),
            "B4_H1_Combined": (VELOCITY + VOLUME + SEQUENCING, []),
            "B5_H0_Contextual": (CONTEXTUAL_CONT, CONTEXTUAL_CAT),
            "B6_Full": (VELOCITY + VOLUME + SEQUENCING + CONTEXTUAL_CONT, CONTEXTUAL_CAT),
        }

        for bname, (cont, cat) in blocks.items():
            Xtr, fnames = prepare_features(train, cont, cat)
            Xte, _ = prepare_features(test, cont, cat)
            results = run_block(bname, Xtr, Xte, ytr, yte, fnames, t)
            all_results.extend(results)
            for r in results:
                auc = r.get("auc", "N/A")
                if isinstance(auc, float):
                    print(f"  {bname:20s} {r['model']:8s} AUC={auc:.4f}")
                if "top_features" in r:
                    for feat, imp in r["top_features"]:
                        all_importances.append({"subsample": t, "block": bname, "model": r["model"],
                                                "feature": feat, "importance": imp})

    # Aggregate
    res_df = pd.DataFrame(all_results)
    agg = res_df.groupby(["block", "model"]).agg(
        mean_auc=("auc", "mean"), std_auc=("auc", "std"),
        mean_f1=("f1", "mean"), std_f1=("f1", "std"),
    ).round(4).sort_values("mean_auc", ascending=False)

    print(f"\n{'='*70}")
    print("PHASE 5b BLOCK COMPARISON")
    print(f"{'='*70}")
    print(agg.to_string())

    # Incremental AUC
    for model in ["LDA", "LogReg", "RF"]:
        m = res_df[res_df["model"] == model]
        b4 = m[m["block"] == "B4_H1_Combined"]["auc"]
        b5 = m[m["block"] == "B5_H0_Contextual"]["auc"]
        b6 = m[m["block"] == "B6_Full"]["auc"]
        if len(b4) > 0 and len(b5) > 0 and len(b6) > 0:
            log_qc("5b.D", f"{model}_B4_auc", round(b4.mean(), 4))
            log_qc("5b.D", f"{model}_B5_auc", round(b5.mean(), 4))
            log_qc("5b.D", f"{model}_B6_auc", round(b6.mean(), 4))
            log_qc("5b.D", f"{model}_delta_H1", round((b6.values - b5.values).mean(), 4))
            log_qc("5b.D", f"{model}_delta_H0", round((b6.values - b4.values).mean(), 4))

    # Feature importance (RF full)
    imp_df = pd.DataFrame(all_importances)
    rf_full = imp_df[(imp_df["model"] == "RF") & (imp_df["block"] == "B6_Full")]
    top_feats = rf_full.groupby("feature")["importance"].mean().sort_values(ascending=False).head(15)
    print("\nTop 15 RF features (Contributors Only):")
    for f, v in top_feats.items():
        c = CONSTRUCT_MAP.get(f, "Contextual")
        print(f"  {f:35s} {v:.4f}  [{c}]")

    # Save Phase 5b outputs
    res_df.to_csv(OUTPUT_5B / "block_results.csv", index=False)
    agg.to_csv(OUTPUT_5B / "block_comparison.csv")
    imp_df.to_csv(OUTPUT_5B / "feature_importances.csv", index=False)

    # ═══ PHASE 5b FIGURES ═══
    print("\n=== Phase 5b Figures ===")

    # Fig 5b.1: Block AUC comparison
    block_order = ["B1_Velocity", "B2_Volume", "B3_Sequencing", "B4_H1_Combined", "B5_H0_Contextual", "B6_Full"]
    block_labels = ["B1: Velocity", "B2: Volume", "B3: Sequencing", "B4: H1\nCombined", "B5: H0\nContext", "B6: Full"]
    model_colors = {"LDA": "#2980b9", "LogReg": "#3b8520", "RF": "#1a4314"}
    agg_r = agg.reset_index()
    fig = go.Figure()
    for model, color in model_colors.items():
        m_agg = agg_r[agg_r["model"] == model].set_index("block").reindex(block_order)
        fig.add_trace(go.Bar(x=block_labels, y=m_agg["mean_auc"], name=model, marker_color=color,
                              error_y=dict(type="data", array=m_agg["std_auc"].values, visible=True),
                              text=[f"{v:.3f}" for v in m_agg["mean_auc"]], textposition="outside"))
    fig.update_layout(barmode="group", title="[Contributors Only] AUC by Block and Model (T=5)",
                      yaxis_title="AUC-ROC", yaxis_range=[0.4, 1.05],
                      height=500, width=1000, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.write_image(OUTPUT_5B / "fig_block_auc_comparison.png", scale=2)

    # Fig 5b.2: Feature importance
    top20 = rf_full.groupby("feature")["importance"].mean().sort_values(ascending=True).tail(15)
    construct_colors = {"Volume": "#3b8520", "Sequencing": "#2980b9", "Velocity": "#e67e22", "Contextual": "#c0392b"}
    colors = [construct_colors.get(CONSTRUCT_MAP.get(f, "Contextual"), "#c0392b") for f in top20.index]
    fig = go.Figure(go.Bar(x=top20.values, y=top20.index, orientation="h", marker_color=colors,
                            text=[f"{v:.3f}" for v in top20.values], textposition="outside"))
    fig.update_layout(title="[Contributors Only] Top 15 RF Feature Importances",
                      xaxis_title="Importance", height=500, width=800,
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.write_image(OUTPUT_5B / "fig_feature_importance.png", scale=2)
    print("  5b figures done")

    # ═══ PHASE 6b: CLUSTERING ═══
    print(f"\n{'='*70}")
    print("PHASE 6b: CLUSTERING (Contributors Only)")
    print(f"{'='*70}")

    K_RANGE = range(3, 9)
    all_km = []
    all_labels = []

    for t, df in enumerate(contrib_subs, 1):
        X = StandardScaler().fit_transform(df[CLUSTER_FEATURES].fillna(0))
        w = df["tenure_weight"].values
        for k in K_RANGE:
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(X, sample_weight=w)
            all_km.append({"subsample": t, "k": k, "silhouette": round(silhouette_score(X, labels), 4),
                           "ch": round(calinski_harabasz_score(X, labels), 2),
                           "db": round(davies_bouldin_score(X, labels), 4)})

    km_df = pd.DataFrame(all_km)
    km_avg = km_df.groupby("k").mean(numeric_only=True).round(4)
    print("\nK-Means averages (Contributors Only):")
    print(km_avg.to_string())

    best_k = km_avg["silhouette"].idxmax()
    log_qc("6b.5", "best_k", best_k, f"silhouette={km_avg.loc[best_k, 'silhouette']}")

    # Run final clustering with best k
    all_cluster_labels = []
    all_overlays = []
    all_profiles = []

    for t, df in enumerate(contrib_subs, 1):
        median_c = df["persistence_c"].median()
        df["persist_binary"] = (df["persistence_c"] >= median_c).astype(int)
        X = StandardScaler().fit_transform(df[CLUSTER_FEATURES].fillna(0))
        km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
        labels = km.fit_predict(X, sample_weight=df["tenure_weight"].values)
        df["cluster"] = labels
        all_cluster_labels.append(labels)

        for c in range(best_k):
            mask = df["cluster"] == c
            n = mask.sum()
            all_overlays.append({"subsample": t, "cluster": c, "n": int(n),
                                 "pct_persistent": round(df.loc[mask, "persist_binary"].mean() * 100, 1),
                                 "mean_persist_c": round(df.loc[mask, "persistence_c"].mean(), 4)})
            profile = {"subsample": t, "cluster": c, "n": int(n)}
            for feat in CLUSTER_FEATURES:
                profile[f"mean_{feat}"] = round(df.loc[mask, feat].fillna(0).mean(), 4)
            profile["pct_persistent"] = round(df.loc[mask, "persist_binary"].mean() * 100, 1)
            all_profiles.append(profile)

        if t == 1:
            ct = pd.crosstab(df["cluster"], df["persist_binary"])
            v = cramers_v(ct)
            log_qc("6b.9", "cramers_v", round(v, 4))

    # Cross-subsample ARI
    ari_vals = []
    for i in range(len(all_cluster_labels)):
        for j in range(i + 1, len(all_cluster_labels)):
            if len(all_cluster_labels[i]) == len(all_cluster_labels[j]):
                ari_vals.append(adjusted_rand_score(all_cluster_labels[i], all_cluster_labels[j]))
    if ari_vals:
        log_qc("6b.7", "mean_ari", round(np.mean(ari_vals), 4))

    # Aggregate profiles
    prof_df = pd.DataFrame(all_profiles)
    agg_prof = prof_df.groupby("cluster").mean(numeric_only=True).round(4)
    print(f"\nCluster profiles (k={best_k}, Contributors Only):")
    print(agg_prof[["n", "pct_persistent", "mean_logins_90d", "mean_activity_breadth"]].to_string())

    # ═══ PHASE 6b FIGURES ═══
    print("\n=== Phase 6b Figures ===")

    # PCA scatter colored by cluster (subsample 1)
    df1 = contrib_subs[0].copy()
    X1 = StandardScaler().fit_transform(df1[CLUSTER_FEATURES].fillna(0))
    km1 = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels1 = km1.fit_predict(X1, sample_weight=df1["tenure_weight"].values)
    pca = PCA(n_components=2)
    X_pca = pca.fit_transform(X1)
    var = pca.explained_variance_ratio_

    fig = px.scatter(x=X_pca[:, 0], y=X_pca[:, 1], color=[f"Cluster {l}" for l in labels1],
                     opacity=0.5,
                     labels={"x": f"PC1 ({var[0]*100:.1f}%)", "y": f"PC2 ({var[1]*100:.1f}%)", "color": "Cluster"},
                     title=f"[Contributors Only] PCA — K-Means k={best_k}")
    fig.update_layout(height=550, width=800, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.write_image(OUTPUT_6B / "fig_pca_clusters.png", scale=2)

    # PCA colored by persistence
    fig = px.scatter(x=X_pca[:, 0], y=X_pca[:, 1], color=df1["persistence_c"].values,
                     color_continuous_scale="RdYlGn", opacity=0.5,
                     labels={"x": f"PC1 ({var[0]*100:.1f}%)", "y": f"PC2 ({var[1]*100:.1f}%)", "color": "Persistence C"},
                     title="[Contributors Only] PCA — Colored by Persistence")
    fig.update_layout(height=550, width=800, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.write_image(OUTPUT_6B / "fig_pca_persistence.png", scale=2)

    # Persistence overlay bar
    ov_avg = pd.DataFrame(all_overlays).groupby("cluster").mean(numeric_only=True).reset_index()
    fig = go.Figure(go.Bar(x=[f"Cluster {c}" for c in ov_avg["cluster"]], y=ov_avg["pct_persistent"],
                            marker_color=["#d4a843", "#2980b9", "#1a4314", "#e67e22", "#c0392b", "#8e44ad"][:best_k],
                            text=[f"{v:.0f}%" for v in ov_avg["pct_persistent"]], textposition="outside"))
    fig.update_layout(title=f"[Contributors Only] Persistence Rate per Cluster (k={best_k})",
                      yaxis_title="% Persistent", height=400, width=700,
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.write_image(OUTPUT_6B / "fig_persistence_overlay.png", scale=2)

    # Elbow/silhouette
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Silhouette Score", "Davies-Bouldin"))
    fig.add_trace(go.Scatter(x=list(K_RANGE), y=km_avg["silhouette"].values, mode="lines+markers",
                              marker_color="#3b8520"), row=1, col=1)
    fig.add_trace(go.Scatter(x=list(K_RANGE), y=km_avg["db"].values, mode="lines+markers",
                              marker_color="#c0392b"), row=1, col=2)
    fig.update_layout(title="[Contributors Only] K-Means Metric Selection", showlegend=False,
                      height=400, width=800, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.write_image(OUTPUT_6B / "fig_silhouette_db.png", scale=2)

    print("  6b figures done")

    # ═══ SAVE ALL OUTPUTS ═══
    pd.DataFrame(all_overlays).to_csv(OUTPUT_6B / "persistence_overlay.csv", index=False)
    prof_df.to_csv(OUTPUT_6B / "cluster_profiles.csv", index=False)
    km_df.to_csv(OUTPUT_6B / "kmeans_metrics.csv", index=False)
    (OUTPUT_5B / "qc_log.json").write_text(json.dumps(qc_log, indent=2, default=str))

    print(f"\n{'='*70}")
    print("SECOND-PASS ANALYSIS COMPLETE")
    print(f"{'='*70}")
    print(f"Phase 5b results: {OUTPUT_5B}")
    print(f"Phase 6b results: {OUTPUT_6B}")


if __name__ == "__main__":
    main()
