"""Phase 6: Unsupervised Clustering with Persistence Overlay
Discovers natural structure and compares clusters to Persistence classification.
Run after Phase 5. Outputs: outputs/phase6/ reports and figures.
"""
import pandas as pd
import numpy as np
import json
import warnings
from pathlib import Path
from datetime import datetime
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture
from sklearn.metrics import (silhouette_score, calinski_harabasz_score,
                             davies_bouldin_score, adjusted_rand_score)
from scipy.stats import chi2_contingency

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBSAMPLE_DIR = PROJECT_ROOT / "data" / "subsamples"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "phase6"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

T = 10
K_RANGE = range(3, 9)  # k=3,4,5,6,7,8

# Top 15 features from Phase 5 RF importance (no constant or collinear)
CLUSTER_FEATURES = [
    "logins_90d", "log_logins_pw", "activity_breadth", "funnel_stage",
    "log_sources_pw", "sources_90d", "log_tree_edits_pw", "tree_edits_90d",
    "names_90d", "log_names_pw", "has_sources", "has_memories",
    "days_to_first_login", "activation_speed", "user_age",
]

qc_log = []

def log_qc(step, metric, value, note=""):
    entry = {"step": step, "metric": metric, "value": value, "note": note,
             "timestamp": datetime.now().isoformat()}
    qc_log.append(entry)
    print(f"  [{step}] {metric} = {value}  {note}")


def cramers_v(contingency_table):
    """Compute Cramer's V from a contingency table."""
    chi2 = chi2_contingency(contingency_table)[0]
    n = contingency_table.sum().sum()
    min_dim = min(contingency_table.shape) - 1
    if min_dim == 0 or n == 0:
        return 0
    return np.sqrt(chi2 / (n * min_dim))


def main():
    print("Phase 6: Unsupervised Clustering")

    all_kmeans_metrics = []
    all_gmm_metrics = []
    all_cluster_profiles = []
    all_persistence_overlays = []
    cluster_assignments_by_sub = {}

    for t in range(1, T + 1):
        print(f"\n{'='*60}")
        print(f"Subsample {t:02d}")
        print(f"{'='*60}")

        df = pd.read_parquet(SUBSAMPLE_DIR / f"subsample_{t:02d}.parquet")

        # Recompute persistence within Tier D
        median_c = df["persistence_c"].median()
        df["persist_binary"] = (df["persistence_c"] >= median_c).astype(int)

        # Prepare features
        X_raw = df[CLUSTER_FEATURES].fillna(0).copy()
        scaler = StandardScaler()
        X = scaler.fit_transform(X_raw)
        weights = df["tenure_weight"].values

        # ═══ Step 6.2: K-Means ═══
        for k in K_RANGE:
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(X, sample_weight=weights)
            sil = silhouette_score(X, labels)
            ch = calinski_harabasz_score(X, labels)
            db = davies_bouldin_score(X, labels)
            all_kmeans_metrics.append({
                "subsample": t, "k": k, "method": "KMeans",
                "silhouette": round(sil, 4), "calinski_harabasz": round(ch, 2),
                "davies_bouldin": round(db, 4), "inertia": round(km.inertia_, 2),
            })

        # ═══ Step 6.3: GMM ═══
        for k in K_RANGE:
            gmm = GaussianMixture(n_components=k, covariance_type="full", random_state=42, max_iter=200)
            gmm.fit(X)
            labels = gmm.predict(X)
            sil = silhouette_score(X, labels)
            all_gmm_metrics.append({
                "subsample": t, "k": k, "method": "GMM",
                "silhouette": round(sil, 4), "bic": round(gmm.bic(X), 2),
                "aic": round(gmm.aic(X), 2),
            })

    # ═══ Step 6.5: Select optimal k ═══
    print(f"\n{'='*60}")
    print("OPTIMAL K SELECTION")
    print(f"{'='*60}")

    km_df = pd.DataFrame(all_kmeans_metrics)
    gmm_df = pd.DataFrame(all_gmm_metrics)

    # Average metrics across subsamples
    km_avg = km_df.groupby("k").agg(
        mean_sil=("silhouette", "mean"), mean_ch=("calinski_harabasz", "mean"),
        mean_db=("davies_bouldin", "mean"), mean_inertia=("inertia", "mean"),
    ).round(4)

    gmm_avg = gmm_df.groupby("k").agg(
        mean_sil=("silhouette", "mean"), mean_bic=("bic", "mean"), mean_aic=("aic", "mean"),
    ).round(4)

    print("\nK-Means averages:")
    print(km_avg.to_string())
    print("\nGMM averages:")
    print(gmm_avg.to_string())

    # Select k by best silhouette (K-Means)
    best_k_km = km_avg["mean_sil"].idxmax()
    best_k_gmm = gmm_avg["mean_sil"].idxmax()
    log_qc("6.5", "best_k_kmeans", best_k_km, f"silhouette={km_avg.loc[best_k_km, 'mean_sil']}")
    log_qc("6.5", "best_k_gmm", best_k_gmm, f"silhouette={gmm_avg.loc[best_k_gmm, 'mean_sil']}")

    # Use K-Means best_k for remaining analyses
    selected_k = best_k_km
    log_qc("6.5", "selected_k", selected_k)

    # ═══ Steps 6.6-6.10: Run with selected k on all subsamples ═══
    print(f"\n{'='*60}")
    print(f"DETAILED ANALYSIS WITH k={selected_k}")
    print(f"{'='*60}")

    all_labels = []
    for t in range(1, T + 1):
        df = pd.read_parquet(SUBSAMPLE_DIR / f"subsample_{t:02d}.parquet")
        median_c = df["persistence_c"].median()
        df["persist_binary"] = (df["persistence_c"] >= median_c).astype(int)

        X_raw = df[CLUSTER_FEATURES].fillna(0)
        scaler = StandardScaler()
        X = scaler.fit_transform(X_raw)
        weights = df["tenure_weight"].values

        km = KMeans(n_clusters=selected_k, random_state=42, n_init=10)
        labels = km.fit_predict(X, sample_weight=weights)
        df["cluster"] = labels
        all_labels.append(labels)
        cluster_assignments_by_sub[t] = labels

        # ═══ Step 6.8: Persistence overlay ═══
        for c in range(selected_k):
            mask = df["cluster"] == c
            cluster_df = df[mask]
            n = mask.sum()
            pct_persist = cluster_df["persist_binary"].mean() * 100
            mean_pc = cluster_df["persistence_c"].mean()
            std_pc = cluster_df["persistence_c"].std()
            ci95 = 1.96 * std_pc / np.sqrt(n) if n > 0 else 0

            all_persistence_overlays.append({
                "subsample": t, "cluster": c, "n": int(n),
                "pct_persistent": round(pct_persist, 1),
                "mean_persistence_c": round(mean_pc, 4),
                "ci95": round(ci95, 4),
            })

        # ═══ Step 6.9: Chi-squared + Cramer's V ═══
        ct = pd.crosstab(df["cluster"], df["persist_binary"])
        chi2, p, dof, _ = chi2_contingency(ct)
        v = cramers_v(ct)
        if t == 1:
            log_qc("6.9", "chi2", round(chi2, 2))
            log_qc("6.9", "chi2_p_value", f"{p:.2e}")
            log_qc("6.9", "cramers_v", round(v, 4))

        # ═══ Step 6.10: Cluster profiling ═══
        for c in range(selected_k):
            mask = df["cluster"] == c
            profile = {"subsample": t, "cluster": c, "n": int(mask.sum())}
            for feat in CLUSTER_FEATURES:
                profile[f"mean_{feat}"] = round(df.loc[mask, feat].fillna(0).mean(), 4)
            # Add persistence and demographic info
            profile["pct_persistent"] = round(df.loc[mask, "persist_binary"].mean() * 100, 1)
            profile["mean_age"] = round(df.loc[mask, "user_age"].fillna(0).mean(), 1)
            profile["mean_persistence_c"] = round(df.loc[mask, "persistence_c"].mean(), 4)
            all_cluster_profiles.append(profile)

    # ═══ Step 6.7: Cross-subsample ARI ═══
    print("\n=== Cross-subsample ARI ===")
    ari_values = []
    for i in range(T):
        for j in range(i + 1, T):
            ari = adjusted_rand_score(all_labels[i], all_labels[j])
            ari_values.append(ari)
    mean_ari = np.mean(ari_values)
    log_qc("6.7", "mean_cross_subsample_ari", round(mean_ari, 4))
    log_qc("6.7", "ari_std", round(np.std(ari_values), 4))
    log_qc("6.7", "ari_min", round(min(ari_values), 4))
    log_qc("6.7", "ari_max", round(max(ari_values), 4))

    # ═══ Step 6.6: Bootstrap stability (simplified — Jaccard via subsample agreement) ═══
    print("\n=== Cluster Stability ===")
    # Use cross-subsample agreement as a proxy for bootstrap Jaccard
    # For each cluster in subsample 1, find best-matching cluster in each other subsample
    ref_labels = all_labels[0]
    for c in range(selected_k):
        ref_mask = (ref_labels == c)
        jaccards = []
        for other_labels in all_labels[1:]:
            best_j = 0
            for oc in range(selected_k):
                other_mask = (other_labels == oc)
                intersection = (ref_mask & other_mask).sum()
                union = (ref_mask | other_mask).sum()
                j = intersection / union if union > 0 else 0
                best_j = max(best_j, j)
            jaccards.append(best_j)
        mean_j = np.mean(jaccards)
        log_qc("6.6", f"cluster_{c}_mean_jaccard", round(mean_j, 4),
                "stable" if mean_j >= 0.75 else "borderline" if mean_j >= 0.60 else "unstable")

    # ═══ Generate aggregate profile (mean across subsamples per cluster) ═══
    profiles_df = pd.DataFrame(all_cluster_profiles)
    agg_profiles = profiles_df.groupby("cluster").mean(numeric_only=True).round(4)

    print("\n=== Cluster Profiles (averaged across T=10) ===")
    print(agg_profiles[["n", "pct_persistent", "mean_persistence_c", "mean_age",
                         "mean_logins_90d", "mean_log_logins_pw", "mean_activity_breadth"]].to_string())

    # Assign personas
    personas = {}
    for c in range(selected_k):
        row = agg_profiles.loc[c]
        logins = row.get("mean_logins_90d", 0)
        breadth = row.get("mean_activity_breadth", 0)
        persist = row.get("pct_persistent", 50)

        if logins > agg_profiles["mean_logins_90d"].quantile(0.8):
            personas[c] = "Power Contributors"
        elif persist > 70 and breadth > agg_profiles["mean_activity_breadth"].median():
            personas[c] = "Steady Engagers"
        elif persist < 30:
            personas[c] = "Likely Churners"
        elif breadth > agg_profiles["mean_activity_breadth"].quantile(0.75):
            personas[c] = "Broad Explorers"
        elif logins < agg_profiles["mean_logins_90d"].quantile(0.25):
            personas[c] = "Minimal Engagers"
        else:
            personas[c] = f"Mid-Range (Cluster {c})"

    for c, name in personas.items():
        log_qc("6.10", f"persona_cluster_{c}", name)

    # ═══ Save outputs ═══
    km_df.to_csv(OUTPUT_DIR / "kmeans_metrics.csv", index=False)
    gmm_df.to_csv(OUTPUT_DIR / "gmm_metrics.csv", index=False)
    profiles_df.to_csv(OUTPUT_DIR / "cluster_profiles.csv", index=False)
    pd.DataFrame(all_persistence_overlays).to_csv(OUTPUT_DIR / "persistence_overlay.csv", index=False)
    (OUTPUT_DIR / "qc_log.json").write_text(json.dumps(qc_log, indent=2, default=str))

    # Summary report
    report = [
        "# Phase 6: Clustering Results Summary",
        f"\n**Generated**: {datetime.now().isoformat()}",
        f"**Selected k**: {selected_k}",
        f"**Cross-subsample ARI**: {mean_ari:.4f}",
        "\n---\n",
        "## K-Means Metrics (averaged across T=10)\n",
        km_avg.to_markdown(),
        "\n## GMM Metrics (averaged across T=10)\n",
        gmm_avg.to_markdown(),
        "\n## Cluster Profiles\n",
        agg_profiles.to_markdown(),
        "\n## QC Log\n",
        "| Step | Metric | Value | Note |",
        "|------|--------|-------|------|",
    ]
    for entry in qc_log:
        val = str(entry["value"])[:80]
        report.append(f"| {entry['step']} | {entry['metric']} | {val} | {entry.get('note', '')} |")

    (OUTPUT_DIR / "clustering_report.md").write_text("\n".join(report))

    print(f"\n=== Phase 6 Complete ===")
    print(f"Selected k: {selected_k}")
    print(f"Cross-subsample ARI: {mean_ari:.4f}")
    print(f"Personas: {personas}")
    print(f"Results: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
