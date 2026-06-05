"""
═══════════════════════════════════════════════════════════════════════════════
PHASE 7: DEEP CLUSTER OPTIMIZATION — Rotation, Weighting & Boundary Analysis
═══════════════════════════════════════════════════════════════════════════════

Systematically explores clustering/classification methods to find the feature
weighting and rotation that maximizes correspondence with the naturally striated
segments visible in:
  - fig08b_biplot_tiers.png (5 development tiers in combined PCA space)
  - fig_pca_clusters.png (6 behavioral clusters with comet-tail structure)
  - fig_pca_persistence.png (diagonal persistence gradient)

Strategy:
  1. Feature composition experiments (behavioral, combined, weighted)
  2. Rotation experiments (PCA, Varimax, ICA, Factor Analysis)
  3. Clustering methods (K-Means, GMM, HDBSCAN, Spectral, Agglomerative)
  4. Re-weighting strategies (equal-construct, LDA-discriminative, manual)
  5. Optimization target: silhouette × Cramer's V at k≈5

Output: outputs/phase7/
═══════════════════════════════════════════════════════════════════════════════
"""

import pandas as pd
import numpy as np
import json
import warnings
from pathlib import Path
from datetime import datetime
from itertools import product as iterproduct

from sklearn.preprocessing import StandardScaler, RobustScaler, MinMaxScaler
from sklearn.decomposition import PCA, FastICA, FactorAnalysis
from sklearn.cluster import KMeans, SpectralClustering, AgglomerativeClustering
from sklearn.mixture import GaussianMixture
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
from scipy.stats import chi2_contingency
from scipy.spatial.transform import Rotation as R

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import duckdb

try:
    from hdbscan import HDBSCAN
    HAS_HDBSCAN = True
except ImportError:
    HAS_HDBSCAN = False

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

PROJECT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT / "data" / "familysearch.duckdb"
OUTPUT = PROJECT / "outputs" / "phase7"
OUTPUT.mkdir(parents=True, exist_ok=True)

SEED = 42
SAMPLE_SIZE = 10_000  # For speed during exploration
K_RANGE = range(3, 9)  # k=3..8
K_TARGET = 5  # Target ~5 clusters

# ─────────────────────────────────────────────────────────────────────────────
# FEATURE DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

VELOCITY = [
    "days_to_first_login", "days_login_to_tree_edit", "days_login_to_name",
    "activation_speed",
]

VOLUME = [
    "log_logins_pw", "log_tree_edits_pw", "log_names_pw", "log_sources_pw",
    "logins_90d", "tree_edits_90d", "names_90d", "sources_90d",
]

SEQUENCING = [
    "activity_breadth", "funnel_stage",
    "has_sources", "has_memories", "has_record_edits", "has_get_involved",
]

CONTEXTUAL = [
    "gdp_per_capita_ppp", "hdi", "pct_christian",
    "govt_restrictions_index", "social_hostilities_index",
    "lds_members_per_capita", "religious_diversity_index",
    "user_age",
]

# Construct map for weighting
CONSTRUCT_MAP = {}
for f in VELOCITY: CONSTRUCT_MAP[f] = "Velocity"
for f in VOLUME: CONSTRUCT_MAP[f] = "Volume"
for f in SEQUENCING: CONSTRUCT_MAP[f] = "Sequencing"
for f in CONTEXTUAL: CONSTRUCT_MAP[f] = "Contextual"

# Feature sets to test
FEATURE_SETS = {
    "behavioral_only": VELOCITY + VOLUME + SEQUENCING,
    "behavioral_no_flags": VELOCITY + VOLUME + ["activity_breadth", "funnel_stage"],
    "combined_full": VELOCITY + VOLUME + SEQUENCING + CONTEXTUAL,
    "combined_no_flags": VELOCITY + VOLUME + ["activity_breadth", "funnel_stage"] + CONTEXTUAL,
    "volume_reduced": ["log_logins_pw", "logins_90d", "log_tree_edits_pw"] + VELOCITY + SEQUENCING,
    "biplot_features": (  # Same as ALL_FEATURES_FOR_PCA from final_analysis
        ["days_to_first_login", "days_login_to_tree_edit", "days_login_to_name",
         "activation_speed"]
        + VOLUME + ["activity_breadth", "funnel_stage"]
        + ["login_consistency"]
        + ["gdp_per_capita_ppp", "hdi", "pct_christian", "govt_restrictions_index",
           "social_hostilities_index", "lds_members_per_capita",
           "religious_diversity_index", "gepi"]
        + ["user_age"]
    ),
}

# Plot colors
CLUSTER_COLORS = px.colors.qualitative.Set2 + px.colors.qualitative.Set1


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_contributors(n_sample=SAMPLE_SIZE):
    """Load contributors from DuckDB, sample for speed."""
    print(f"Loading contributors from DuckDB (sample={n_sample})...")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    df = con.execute("""
        SELECT f.*, e.gdp_per_capita_ppp, e.hdi, e.pct_christian,
               e.govt_restrictions_index, e.social_hostilities_index,
               e.lds_membership, e.lds_members_per_capita, e.gepi,
               e.pct_relig_important, e.religious_diversity_index
        FROM users_features f
        LEFT JOIN country_enrichment e ON f.iso3_code = e.iso3_code
        WHERE f.is_mnar = FALSE AND f.tenure_days >= 31
          AND COALESCE(f.DAYS_LOGGING_IN, 0) >= 2
          AND COALESCE(f.TREE_EDITS, 0) > 0
          AND COALESCE(f.TOTAL_NAMES_ADDED, 0) > 0
          AND f.earliest_login_date IS NOT NULL
          AND f.earliest_tree_edit_date IS NOT NULL
          AND f.earliest_name_date IS NOT NULL
    """).df()
    con.close()

    # Sample for speed
    if len(df) > n_sample:
        df = df.sample(n=n_sample, random_state=SEED).reset_index(drop=True)

    # Persistence dichotomization
    median_c = df["persistence_c"].median()
    df["persist_binary"] = (df["persistence_c"] >= median_c).astype(int)

    print(f"  Loaded {len(df):,} contributors")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def cramers_v(labels, persist_binary):
    """Compute Cramer's V between cluster labels and persistence."""
    ct = pd.crosstab(labels, persist_binary)
    chi2 = chi2_contingency(ct)[0]
    n = ct.sum().sum()
    min_dim = min(ct.shape) - 1
    if min_dim == 0 or n == 0:
        return 0.0
    return np.sqrt(chi2 / (n * min_dim))


def evaluate_solution(X, labels, persist_binary):
    """Full evaluation of a clustering solution."""
    n_clusters = len(set(labels) - {-1})
    valid = labels >= 0

    if n_clusters < 2 or valid.sum() < 100:
        return {"n_clusters": n_clusters, "silhouette": -1, "calinski_harabasz": 0,
                "davies_bouldin": 99, "cramers_v": 0, "composite_score": -1}

    X_clean, labels_clean = X[valid], labels[valid]
    persist_clean = persist_binary[valid]

    # Subsample for silhouette if large
    if len(X_clean) > 10000:
        idx = np.random.RandomState(SEED).choice(len(X_clean), 10000, replace=False)
        sil = silhouette_score(X_clean[idx], labels_clean[idx])
    else:
        sil = silhouette_score(X_clean, labels_clean)

    ch = calinski_harabasz_score(X_clean, labels_clean)
    db = davies_bouldin_score(X_clean, labels_clean)
    cv = cramers_v(labels_clean, persist_clean)

    # Composite: silhouette × Cramer's V (both [0,1], higher = better)
    composite = sil * cv

    return {
        "n_clusters": n_clusters,
        "silhouette": round(sil, 4),
        "calinski_harabasz": round(ch, 2),
        "davies_bouldin": round(db, 4),
        "cramers_v": round(cv, 4),
        "composite_score": round(composite, 4),
        "n_noise": int((~valid).sum()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# WEIGHTING STRATEGIES
# ─────────────────────────────────────────────────────────────────────────────

def apply_weighting(X_scaled, feature_names, strategy):
    """Apply feature weighting strategy to scaled features."""
    weights = np.ones(X_scaled.shape[1])

    if strategy == "equal_construct":
        # Normalize each construct to contribute equally
        constructs = [CONSTRUCT_MAP.get(f, "Other") for f in feature_names]
        unique_constructs = list(set(constructs))
        for c in unique_constructs:
            idxs = [i for i, cc in enumerate(constructs) if cc == c]
            if idxs:
                w = 1.0 / len(idxs)
                for i in idxs:
                    weights[i] = w

    elif strategy == "downweight_volume":
        # Reduce volume dominance by 50%, upweight velocity 2×
        for i, f in enumerate(feature_names):
            c = CONSTRUCT_MAP.get(f, "Other")
            if c == "Volume":
                weights[i] = 0.5
            elif c == "Velocity":
                weights[i] = 2.0
            elif c == "Sequencing":
                weights[i] = 1.5

    elif strategy == "sqrt_volume":
        # Square-root compress volume features (reduce outlier influence)
        for i, f in enumerate(feature_names):
            c = CONSTRUCT_MAP.get(f, "Other")
            if c == "Volume":
                weights[i] = 0.7  # Still present but reduced

    elif strategy == "velocity_boost":
        # Strongly boost velocity to make onboarding speed visible
        for i, f in enumerate(feature_names):
            c = CONSTRUCT_MAP.get(f, "Other")
            if c == "Velocity":
                weights[i] = 3.0
            elif c == "Volume":
                weights[i] = 0.5

    elif strategy == "uniform":
        pass  # All 1.0

    return X_scaled * weights


# ─────────────────────────────────────────────────────────────────────────────
# ROTATION / DIMENSIONALITY REDUCTION METHODS
# ─────────────────────────────────────────────────────────────────────────────

def apply_rotation(X_scaled, method, n_components=None):
    """Apply rotation/dimensionality reduction."""
    if n_components is None:
        n_components = min(X_scaled.shape[1], 10)

    if method == "pca":
        model = PCA(n_components=n_components, random_state=SEED)
        X_rot = model.fit_transform(X_scaled)
        return X_rot, model, "PCA"

    elif method == "ica":
        model = FastICA(n_components=n_components, random_state=SEED, max_iter=500)
        X_rot = model.fit_transform(X_scaled)
        return X_rot, model, "ICA"

    elif method == "factor_analysis":
        n_comp = min(n_components, X_scaled.shape[1] - 1)
        model = FactorAnalysis(n_components=n_comp, random_state=SEED)
        X_rot = model.fit_transform(X_scaled)
        return X_rot, model, "FA"

    elif method == "pca_varimax":
        # PCA then Varimax rotation
        pca = PCA(n_components=n_components, random_state=SEED)
        X_pca = pca.fit_transform(X_scaled)
        # Varimax rotation of PCA loadings
        loadings = pca.components_.T  # (features × components)
        rotated_loadings = _varimax(loadings)
        X_rot = X_scaled @ rotated_loadings
        return X_rot, (pca, rotated_loadings), "PCA+Varimax"

    elif method == "none":
        return X_scaled, None, "None"

    return X_scaled, None, method


def _varimax(loadings, max_iter=100, tol=1e-6):
    """Varimax rotation of factor loadings matrix."""
    p, k = loadings.shape
    rotation = np.eye(k)
    d = 0

    for _ in range(max_iter):
        old_d = d
        B = loadings @ rotation
        # Varimax criterion
        u, s, vt = np.linalg.svd(
            loadings.T @ (B ** 3 - (1.0 / p) * B @ np.diag(np.sum(B ** 2, axis=0)))
        )
        rotation = u @ vt
        d = np.sum(s)
        if abs(d - old_d) < tol:
            break

    return loadings @ rotation


# ─────────────────────────────────────────────────────────────────────────────
# CLUSTERING METHODS
# ─────────────────────────────────────────────────────────────────────────────

def run_clustering(X, method, k):
    """Run a clustering algorithm, return labels."""
    if method == "kmeans":
        model = KMeans(n_clusters=k, random_state=SEED, n_init=10)
        return model.fit_predict(X)

    elif method == "gmm":
        model = GaussianMixture(n_components=k, random_state=SEED, n_init=5,
                                covariance_type="full", max_iter=300)
        return model.fit_predict(X)

    elif method == "spectral":
        if len(X) > 8000:
            # Subsample for spectral (expensive)
            idx = np.random.RandomState(SEED).choice(len(X), 8000, replace=False)
            model = SpectralClustering(n_clusters=k, random_state=SEED,
                                       affinity="rbf", n_init=3)
            sub_labels = model.fit_predict(X[idx])
            # Assign remaining points to nearest cluster center
            from sklearn.neighbors import NearestCentroid
            nc = NearestCentroid()
            nc.fit(X[idx], sub_labels)
            labels = nc.predict(X)
            return labels
        else:
            model = SpectralClustering(n_clusters=k, random_state=SEED,
                                       affinity="rbf", n_init=3)
            return model.fit_predict(X)

    elif method == "agglomerative":
        model = AgglomerativeClustering(n_clusters=k, linkage="ward")
        return model.fit_predict(X)

    elif method == "hdbscan" and HAS_HDBSCAN:
        # HDBSCAN ignores k; finds natural clusters
        model = HDBSCAN(min_cluster_size=max(50, len(X) // 50),
                        min_samples=10, core_dist_n_jobs=-1)
        return model.fit_predict(X)

    return np.zeros(len(X), dtype=int)


# ─────────────────────────────────────────────────────────────────────────────
# LDA-GUIDED ROTATION (discriminant boundary optimization)
# ─────────────────────────────────────────────────────────────────────────────

def lda_discriminant_space(X, y, n_components=1):
    """Project onto LDA discriminant axis for persistence-optimized rotation."""
    lda = LinearDiscriminantAnalysis(n_components=n_components)
    X_lda = lda.fit_transform(X, y)
    return X_lda, lda


def lda_augmented_pca(X, y, n_pca=5):
    """
    Combine PCA with LDA: first n_pca PCA components + LDA discriminant axis.
    This gives a space that preserves variance (PCA) while optimizing for
    the persistence boundary (LDA).
    """
    pca = PCA(n_components=n_pca, random_state=SEED)
    X_pca = pca.fit_transform(X)

    lda = LinearDiscriminantAnalysis(n_components=1)
    X_lda = lda.fit_transform(X, y)

    # Concatenate: PCA components + LDA discriminant
    X_combined = np.hstack([X_pca, X_lda])
    return X_combined, (pca, lda)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN EXPLORATION ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 90)
    print("PHASE 7: DEEP CLUSTER OPTIMIZATION")
    print("=" * 90)
    start_time = datetime.now()

    df = load_contributors()

    # ══════════════════════════════════════════════════════════════════════════
    # EXPERIMENT 1: Feature Set × Weighting × Clustering Grid Search
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print("EXPERIMENT 1: Feature Set × Weighting × Clustering Grid Search")
    print(f"{'='*90}")

    weighting_strategies = ["uniform", "equal_construct", "downweight_volume",
                            "velocity_boost", "sqrt_volume"]
    cluster_methods = ["kmeans", "gmm", "agglomerative"]
    if HAS_HDBSCAN:
        cluster_methods.append("hdbscan")

    all_results = []
    total_combos = len(FEATURE_SETS) * len(weighting_strategies) * len(cluster_methods) * len(K_RANGE)
    combo_count = 0

    for fset_name, features in FEATURE_SETS.items():
        avail = [f for f in features if f in df.columns]
        if len(avail) < 3:
            continue

        X_raw = df[avail].fillna(0).values
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_raw)

        for weight_strategy in weighting_strategies:
            X_weighted = apply_weighting(X_scaled, avail, weight_strategy)

            for cluster_method in cluster_methods:
                for k in K_RANGE:
                    combo_count += 1
                    if combo_count % 50 == 0:
                        print(f"  [{combo_count}/{total_combos}] {fset_name} / {weight_strategy} / {cluster_method} / k={k}")

                    if cluster_method == "hdbscan":
                        labels = run_clustering(X_weighted, cluster_method, k)
                        k_actual = len(set(labels) - {-1})
                        # Only evaluate once per (fset, weight, hdbscan) combo
                        if k != list(K_RANGE)[0]:
                            continue
                    else:
                        labels = run_clustering(X_weighted, cluster_method, k)
                        k_actual = k

                    metrics = evaluate_solution(X_weighted, labels, df["persist_binary"].values)

                    all_results.append({
                        "feature_set": fset_name,
                        "n_features": len(avail),
                        "weighting": weight_strategy,
                        "cluster_method": cluster_method,
                        "k_requested": k,
                        "k_actual": metrics["n_clusters"],
                        **metrics,
                    })

    results_df = pd.DataFrame(all_results)
    results_df.to_csv(OUTPUT / "exp1_grid_search.csv", index=False)

    # Top 20 by composite score
    top20 = results_df.nlargest(20, "composite_score")
    print(f"\n  TOP 20 CONFIGURATIONS (by silhouette × Cramer's V):")
    print(f"  {'Feature Set':<25} {'Weight':<20} {'Method':<12} {'k':>3} {'Sil':>6} {'CV':>6} {'Comp':>6}")
    print("  " + "-" * 85)
    for _, row in top20.iterrows():
        print(f"  {row['feature_set']:<25} {row['weighting']:<20} {row['cluster_method']:<12} "
              f"{row['k_actual']:>3} {row['silhouette']:>6.3f} {row['cramers_v']:>6.3f} {row['composite_score']:>6.3f}")

    # ── Best at k=5 specifically ──
    k5 = results_df[results_df["k_actual"] == K_TARGET].nlargest(10, "composite_score")
    print(f"\n  TOP 10 AT k={K_TARGET}:")
    print(f"  {'Feature Set':<25} {'Weight':<20} {'Method':<12} {'Sil':>6} {'CV':>6} {'Comp':>6}")
    print("  " + "-" * 80)
    for _, row in k5.iterrows():
        print(f"  {row['feature_set']:<25} {row['weighting']:<20} {row['cluster_method']:<12} "
              f"{row['silhouette']:>6.3f} {row['cramers_v']:>6.3f} {row['composite_score']:>6.3f}")

    # ══════════════════════════════════════════════════════════════════════════
    # EXPERIMENT 2: Rotation Methods × Best Feature Sets
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print("EXPERIMENT 2: Rotation Methods on Top Feature Sets")
    print(f"{'='*90}")

    # Pick top 3 feature sets from Experiment 1
    best_fsets = results_df.groupby("feature_set")["composite_score"].max().nlargest(3).index.tolist()
    rotation_methods = ["pca", "ica", "factor_analysis", "pca_varimax", "none"]
    n_components_list = [5, 7, 10]

    rotation_results = []

    for fset_name in best_fsets:
        features = FEATURE_SETS[fset_name]
        avail = [f for f in features if f in df.columns]
        X_raw = df[avail].fillna(0).values
        X_scaled = StandardScaler().fit_transform(X_raw)

        # Use best weighting from Experiment 1
        best_weight = results_df[results_df["feature_set"] == fset_name].nlargest(1, "composite_score").iloc[0]["weighting"]
        X_weighted = apply_weighting(X_scaled, avail, best_weight)

        for rot_method in rotation_methods:
            for n_comp in n_components_list:
                if n_comp > len(avail):
                    continue

                try:
                    X_rot, model, rot_label = apply_rotation(X_weighted, rot_method, n_comp)
                except Exception as e:
                    continue

                for k in [4, 5, 6]:  # Focus around target
                    for clust in ["kmeans", "gmm"]:
                        labels = run_clustering(X_rot, clust, k)
                        metrics = evaluate_solution(X_rot, labels, df["persist_binary"].values)
                        rotation_results.append({
                            "feature_set": fset_name,
                            "weighting": best_weight,
                            "rotation": rot_label,
                            "n_components": n_comp,
                            "cluster_method": clust,
                            "k": k,
                            **metrics,
                        })

    rot_df = pd.DataFrame(rotation_results)
    rot_df.to_csv(OUTPUT / "exp2_rotations.csv", index=False)

    # Top 10 rotation results
    if len(rot_df) > 0:
        top10_rot = rot_df.nlargest(10, "composite_score")
        print(f"\n  TOP 10 ROTATION CONFIGURATIONS:")
        print(f"  {'Feature Set':<25} {'Rotation':<15} {'nComp':>5} {'Method':<8} {'k':>3} {'Sil':>6} {'CV':>6} {'Comp':>6}")
        print("  " + "-" * 90)
        for _, row in top10_rot.iterrows():
            print(f"  {row['feature_set']:<25} {row['rotation']:<15} {row['n_components']:>5} "
                  f"{row['cluster_method']:<8} {row['k']:>3} {row['silhouette']:>6.3f} "
                  f"{row['cramers_v']:>6.3f} {row['composite_score']:>6.3f}")

    # ══════════════════════════════════════════════════════════════════════════
    # EXPERIMENT 3: LDA-Guided Rotation (Discriminant Boundary Optimization)
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print("EXPERIMENT 3: LDA-Guided Rotation (Discriminant Boundaries)")
    print(f"{'='*90}")

    lda_results = []
    for fset_name in best_fsets:
        features = FEATURE_SETS[fset_name]
        avail = [f for f in features if f in df.columns]
        X_raw = df[avail].fillna(0).values
        X_scaled = StandardScaler().fit_transform(X_raw)

        y = df["persist_binary"].values

        # Method A: Pure LDA on scaled features (just 1 discriminant axis)
        try:
            X_lda, lda_model = lda_discriminant_space(X_scaled, y, n_components=1)
            # Combine LDA axis with top PCA axes
            for n_pca in [3, 4, 5, 6]:
                X_aug, _ = lda_augmented_pca(X_scaled, y, n_pca=n_pca)
                for k in [4, 5, 6]:
                    for clust in ["kmeans", "gmm"]:
                        labels = run_clustering(X_aug, clust, k)
                        metrics = evaluate_solution(X_aug, labels, y)
                        lda_results.append({
                            "feature_set": fset_name,
                            "method": f"PCA({n_pca})+LDA(1)",
                            "n_dims": n_pca + 1,
                            "cluster_method": clust,
                            "k": k,
                            **metrics,
                        })
        except Exception as e:
            print(f"  LDA failed for {fset_name}: {e}")

    lda_df = pd.DataFrame(lda_results)
    lda_df.to_csv(OUTPUT / "exp3_lda_guided.csv", index=False)

    if len(lda_df) > 0:
        top10_lda = lda_df.nlargest(10, "composite_score")
        print(f"\n  TOP 10 LDA-GUIDED CONFIGURATIONS:")
        print(f"  {'Feature Set':<25} {'Method':<18} {'Clust':<8} {'k':>3} {'Sil':>6} {'CV':>6} {'Comp':>6}")
        print("  " + "-" * 80)
        for _, row in top10_lda.iterrows():
            print(f"  {row['feature_set']:<25} {row['method']:<18} {row['cluster_method']:<8} "
                  f"{row['k']:>3} {row['silhouette']:>6.3f} {row['cramers_v']:>6.3f} {row['composite_score']:>6.3f}")

    # ══════════════════════════════════════════════════════════════════════════
    # EXPERIMENT 4: Volume Compression Experiments
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print("EXPERIMENT 4: Volume Compression (log, sqrt, rank transforms)")
    print(f"{'='*90}")

    compression_results = []
    # Use combined_full feature set
    features = FEATURE_SETS["combined_full"]
    avail = [f for f in features if f in df.columns]

    for transform_name, transform_fn in [
        ("standard", lambda x: x),
        ("log1p_volume", lambda x: _log_volume(x, avail)),
        ("sqrt_volume", lambda x: _sqrt_volume(x, avail)),
        ("rank_volume", lambda x: _rank_volume(x, avail)),
        ("winsorize_volume", lambda x: _winsorize_volume(x, avail)),
    ]:
        X_raw = df[avail].fillna(0).copy()
        X_transformed = transform_fn(X_raw)
        X_scaled = StandardScaler().fit_transform(X_transformed)

        for weight in ["uniform", "equal_construct", "downweight_volume"]:
            X_weighted = apply_weighting(X_scaled, avail, weight)

            for k in [4, 5, 6]:
                for clust in ["kmeans", "gmm"]:
                    labels = run_clustering(X_weighted, clust, k)
                    metrics = evaluate_solution(X_weighted, labels, df["persist_binary"].values)
                    compression_results.append({
                        "transform": transform_name,
                        "weighting": weight,
                        "cluster_method": clust,
                        "k": k,
                        **metrics,
                    })

    comp_df = pd.DataFrame(compression_results)
    comp_df.to_csv(OUTPUT / "exp4_volume_compression.csv", index=False)

    if len(comp_df) > 0:
        top10_comp = comp_df.nlargest(10, "composite_score")
        print(f"\n  TOP 10 VOLUME COMPRESSION CONFIGURATIONS:")
        print(f"  {'Transform':<20} {'Weight':<20} {'Method':<8} {'k':>3} {'Sil':>6} {'CV':>6} {'Comp':>6}")
        print("  " + "-" * 80)
        for _, row in top10_comp.iterrows():
            print(f"  {row['transform']:<20} {row['weighting']:<20} {row['cluster_method']:<8} "
                  f"{row['k']:>3} {row['silhouette']:>6.3f} {row['cramers_v']:>6.3f} {row['composite_score']:>6.3f}")

    # ══════════════════════════════════════════════════════════════════════════
    # EXPERIMENT 5: Best Configuration Visualization
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print("EXPERIMENT 5: Visualization of Best Solutions")
    print(f"{'='*90}")

    # Collect ALL results
    all_experiments = []
    for name, df_exp in [("grid", results_df), ("rotation", rot_df),
                          ("lda", lda_df), ("compression", comp_df)]:
        if len(df_exp) > 0:
            df_copy = df_exp.copy()
            df_copy["experiment"] = name
            all_experiments.append(df_copy)

    if all_experiments:
        combined = pd.concat(all_experiments, ignore_index=True)
        combined.to_csv(OUTPUT / "all_experiments_combined.csv", index=False)

        # Overall top 20
        overall_top = combined.nlargest(20, "composite_score")
        print(f"\n  OVERALL TOP 20 (across all experiments):")
        for i, (_, row) in enumerate(overall_top.iterrows(), 1):
            exp = row.get("experiment", "?")
            fset = row.get("feature_set", row.get("transform", "?"))
            print(f"  {i:2d}. [{exp}] {fset} | "
                  f"k={row.get('k_actual', row.get('k', '?'))} | "
                  f"sil={row['silhouette']:.3f} | cv={row['cramers_v']:.3f} | "
                  f"composite={row['composite_score']:.3f}")

    # ── Generate visualizations for top configurations ──
    _visualize_top_solutions(df, results_df, rot_df, lda_df, comp_df)

    # ── Summary metrics comparison plot ──
    _plot_metrics_comparison(results_df, rot_df, lda_df, comp_df)

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'='*90}")
    print(f"PHASE 7 COMPLETE — {elapsed:.0f}s")
    print(f"{'='*90}")
    print(f"Output: {OUTPUT}")


# ─────────────────────────────────────────────────────────────────────────────
# VOLUME COMPRESSION TRANSFORMS
# ─────────────────────────────────────────────────────────────────────────────

def _log_volume(df_raw, features):
    """Apply log1p to volume features."""
    df = df_raw.copy()
    for f in features:
        if CONSTRUCT_MAP.get(f) == "Volume" and not f.startswith("log_"):
            df[f] = np.log1p(df[f].clip(lower=0))
    return df


def _sqrt_volume(df_raw, features):
    """Apply sqrt to volume features."""
    df = df_raw.copy()
    for f in features:
        if CONSTRUCT_MAP.get(f) == "Volume":
            df[f] = np.sqrt(df[f].clip(lower=0).abs())
    return df


def _rank_volume(df_raw, features):
    """Rank-transform volume features (percentile)."""
    df = df_raw.copy()
    for f in features:
        if CONSTRUCT_MAP.get(f) == "Volume":
            df[f] = df[f].rank(pct=True)
    return df


def _winsorize_volume(df_raw, features, pct=0.95):
    """Winsorize volume features at 95th percentile."""
    df = df_raw.copy()
    for f in features:
        if CONSTRUCT_MAP.get(f) == "Volume":
            cap = df[f].quantile(pct)
            df[f] = df[f].clip(upper=cap)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# VISUALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def _visualize_top_solutions(df, grid_df, rot_df, lda_df, comp_df):
    """Generate PCA scatter plots for top solutions at k≈5."""

    # Pick best k=5 solution from each experiment
    solutions_to_plot = []

    for name, exp_df in [("Grid", grid_df), ("Rotation", rot_df),
                          ("LDA", lda_df), ("Compression", comp_df)]:
        if len(exp_df) == 0:
            continue
        k5 = exp_df[exp_df.get("k_actual", exp_df.get("k", pd.Series(dtype=int))) == K_TARGET]
        if "k_actual" not in exp_df.columns:
            k5 = exp_df[exp_df["k"] == K_TARGET]
        if len(k5) == 0:
            k5 = exp_df[exp_df.get("n_clusters", pd.Series(dtype=int)) == K_TARGET]
        if len(k5) > 0:
            best = k5.nlargest(1, "composite_score").iloc[0]
            solutions_to_plot.append((name, best))

    if not solutions_to_plot:
        print("  No k=5 solutions found for visualization")
        return

    # Re-run best solutions to get labels for plotting
    n_plots = min(len(solutions_to_plot), 4)
    fig = make_subplots(rows=2, cols=2,
                         subplot_titles=[f"{name}: comp={row['composite_score']:.3f}"
                                         for name, row in solutions_to_plot[:4]],
                         vertical_spacing=0.12, horizontal_spacing=0.08)

    for idx, (name, config) in enumerate(solutions_to_plot[:4]):
        row_plot = idx // 2 + 1
        col_plot = idx % 2 + 1

        # Re-create the feature space
        fset_name = config.get("feature_set", "combined_full")
        if fset_name in FEATURE_SETS:
            features = FEATURE_SETS[fset_name]
        else:
            features = FEATURE_SETS["combined_full"]

        avail = [f for f in features if f in df.columns]
        X_raw = df[avail].fillna(0).values
        X_scaled = StandardScaler().fit_transform(X_raw)

        weight = config.get("weighting", "uniform")
        X_weighted = apply_weighting(X_scaled, avail, weight)

        # PCA for viz
        pca_viz = PCA(n_components=2, random_state=SEED)
        X_pca = pca_viz.fit_transform(X_weighted)

        # Re-run clustering
        clust = config.get("cluster_method", "kmeans")
        k = int(config.get("k_actual", config.get("k", K_TARGET)))
        labels = run_clustering(X_weighted, clust, k)

        for c in range(k):
            mask = labels == c
            fig.add_trace(go.Scatter(
                x=X_pca[mask, 0], y=X_pca[mask, 1], mode="markers",
                marker=dict(size=2, color=CLUSTER_COLORS[c % len(CLUSTER_COLORS)], opacity=0.3),
                name=f"C{c}", showlegend=(idx == 0),
            ), row=row_plot, col=col_plot)

    fig.update_layout(
        title="Top k=5 Solutions: PCA Projections",
        height=900, width=1100,
        plot_bgcolor="rgba(245,245,240,1)",
        font=dict(size=11),
    )
    fig.write_image(OUTPUT / "fig_top_solutions_pca.png", scale=2)
    print("  fig_top_solutions_pca.png saved")

    # ── Persistence overlay for best solution ──
    if solutions_to_plot:
        name, config = solutions_to_plot[0]
        fset_name = config.get("feature_set", "combined_full")
        features = FEATURE_SETS.get(fset_name, FEATURE_SETS["combined_full"])
        avail = [f for f in features if f in df.columns]
        X_raw = df[avail].fillna(0).values
        X_scaled = StandardScaler().fit_transform(X_raw)
        weight = config.get("weighting", "uniform")
        X_weighted = apply_weighting(X_scaled, avail, weight)
        pca_viz = PCA(n_components=2, random_state=SEED)
        X_pca = pca_viz.fit_transform(X_weighted)
        var_explained = pca_viz.explained_variance_ratio_

        clust = config.get("cluster_method", "kmeans")
        k = int(config.get("k_actual", config.get("k", K_TARGET)))
        labels = run_clustering(X_weighted, clust, k)

        # Plot with persistence gradient + cluster boundaries
        fig = make_subplots(rows=1, cols=2,
                             subplot_titles=["Colored by Cluster", "Colored by Persistence"])

        for c in range(k):
            mask = labels == c
            fig.add_trace(go.Scatter(
                x=X_pca[mask, 0], y=X_pca[mask, 1], mode="markers",
                marker=dict(size=3, color=CLUSTER_COLORS[c % len(CLUSTER_COLORS)], opacity=0.3),
                name=f"Cluster {c} (n={mask.sum()}, {df.loc[mask, 'persist_binary'].mean()*100:.0f}% persist)",
            ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=X_pca[:, 0], y=X_pca[:, 1], mode="markers",
            marker=dict(size=3, color=df["persistence_c"], colorscale="RdYlGn",
                        opacity=0.3, colorbar=dict(title="Persist.", x=1.02)),
            showlegend=False,
        ), row=1, col=2)

        fig.update_layout(
            title=f"Best k={k} Solution: {name} ({fset_name}, {weight})<br>"
                  f"PC1={var_explained[0]*100:.1f}%  PC2={var_explained[1]*100:.1f}%",
            height=550, width=1200,
            plot_bgcolor="rgba(245,245,240,1)",
        )
        fig.write_image(OUTPUT / "fig_best_solution_detail.png", scale=2)
        print("  fig_best_solution_detail.png saved")


def _plot_metrics_comparison(grid_df, rot_df, lda_df, comp_df):
    """Compare metrics across experiments for k=5."""

    fig = make_subplots(rows=1, cols=3,
                         subplot_titles=["Silhouette Score", "Cramer's V", "Composite Score"])

    for name, exp_df, color in [
        ("Grid", grid_df, "#3b8520"),
        ("Rotation", rot_df, "#2980b9"),
        ("LDA", lda_df, "#e67e22"),
        ("Compression", comp_df, "#c0392b"),
    ]:
        if len(exp_df) == 0:
            continue

        # Filter to k=5 (approximate)
        k_col = "k_actual" if "k_actual" in exp_df.columns else "k"
        k5 = exp_df[(exp_df.get(k_col, pd.Series(dtype=int)) >= 4) &
                     (exp_df.get(k_col, pd.Series(dtype=int)) <= 6)]
        if len(k5) == 0:
            continue

        for col_idx, metric in enumerate(["silhouette", "cramers_v", "composite_score"], 1):
            if metric in k5.columns:
                fig.add_trace(go.Box(
                    y=k5[metric], name=name, marker_color=color,
                    boxpoints="outliers", showlegend=(col_idx == 1),
                ), row=1, col=col_idx)

    fig.update_layout(
        title="Metrics Distribution for k≈5 Solutions (All Experiments)",
        height=450, width=1200,
        plot_bgcolor="rgba(245,245,240,1)",
    )
    fig.write_image(OUTPUT / "fig_metrics_comparison.png", scale=2)
    print("  fig_metrics_comparison.png saved")

    # ── Silhouette vs Cramer's V scatter (all solutions) ──
    fig = go.Figure()
    for name, exp_df, color in [
        ("Grid", grid_df, "#3b8520"),
        ("Rotation", rot_df, "#2980b9"),
        ("LDA", lda_df, "#e67e22"),
        ("Compression", comp_df, "#c0392b"),
    ]:
        if len(exp_df) == 0:
            continue
        fig.add_trace(go.Scatter(
            x=exp_df["silhouette"], y=exp_df["cramers_v"], mode="markers",
            marker=dict(size=4, color=color, opacity=0.4),
            name=name,
        ))

    # Iso-composite lines
    for comp_val in [0.05, 0.10, 0.15, 0.20]:
        x_line = np.linspace(0.01, 0.8, 100)
        y_line = comp_val / x_line
        mask = y_line <= 1.0
        fig.add_trace(go.Scatter(
            x=x_line[mask], y=y_line[mask], mode="lines",
            line=dict(color="gray", dash="dot", width=1),
            showlegend=False,
        ))

    fig.update_layout(
        title="Silhouette vs Cramer's V: All Solutions (iso-composite curves in gray)",
        xaxis_title="Silhouette Score", yaxis_title="Cramer's V",
        height=600, width=800,
        plot_bgcolor="rgba(245,245,240,1)",
    )
    fig.write_image(OUTPUT / "fig_silhouette_vs_cramersv.png", scale=2)
    print("  fig_silhouette_vs_cramersv.png saved")


if __name__ == "__main__":
    main()
