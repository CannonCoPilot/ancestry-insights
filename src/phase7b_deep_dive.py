"""
═══════════════════════════════════════════════════════════════════════════════
PHASE 7B: DEEP DIVE — Top Solutions with Publication-Quality Visualization
═══════════════════════════════════════════════════════════════════════════════

Focuses on the 3 winning configurations from Phase 7:
  A) Factor Analysis (5 components) on volume_reduced → K-Means k=5,6
  B) PCA(3)+LDA(1) on volume_reduced → K-Means k=5,6
  C) PCA(7) + GMM on behavioral_only → k=5,6

For each:
  1. Full cluster profiling (mean features, persistence rates, demographics)
  2. PCA biplot with cluster overlays (matching fig08b style)
  3. Persistence gradient with cluster boundaries
  4. Radar profiles per cluster
  5. Cluster stability across bootstrap subsamples
  6. Comparison of k=5 vs k=6 within each method
  7. Construct-weighted re-analysis

Output: outputs/phase7b/
═══════════════════════════════════════════════════════════════════════════════
"""

import pandas as pd
import numpy as np
import json
import warnings
from pathlib import Path
from datetime import datetime

from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA, FactorAnalysis
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import silhouette_score, silhouette_samples
from scipy.stats import chi2_contingency
from scipy import stats

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import duckdb

warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

PROJECT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT / "data" / "familysearch.duckdb"
OUTPUT = PROJECT / "outputs" / "phase7b"
OUTPUT.mkdir(parents=True, exist_ok=True)

SEED = 42
SAMPLE_SIZE = 10_000

# Feature definitions
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

CONSTRUCT_MAP = {}
for f in VELOCITY: CONSTRUCT_MAP[f] = "Velocity"
for f in VOLUME: CONSTRUCT_MAP[f] = "Volume"
for f in SEQUENCING: CONSTRUCT_MAP[f] = "Sequencing"
for f in CONTEXTUAL: CONSTRUCT_MAP[f] = "Contextual"

# The three winning feature sets
VOLUME_REDUCED = ["log_logins_pw", "logins_90d", "log_tree_edits_pw"] + VELOCITY + SEQUENCING
BEHAVIORAL_ONLY = VELOCITY + VOLUME + SEQUENCING
BIPLOT_FEATURES = (
    ["days_to_first_login", "days_login_to_tree_edit", "days_login_to_name",
     "activation_speed"]
    + VOLUME + ["activity_breadth", "funnel_stage"]
    + ["login_consistency"]
    + ["gdp_per_capita_ppp", "hdi", "pct_christian", "govt_restrictions_index",
       "social_hostilities_index", "lds_members_per_capita",
       "religious_diversity_index", "gepi"]
    + ["user_age"]
)

# Profile features for reporting
PROFILE_FEATURES = [
    "logins_90d", "log_logins_pw", "tree_edits_90d", "log_tree_edits_pw",
    "names_90d", "sources_90d", "activity_breadth", "funnel_stage",
    "activation_speed", "days_to_first_login", "days_login_to_tree_edit",
    "user_age",
]

# Colors
CLUSTER_COLORS_5 = ["#e74c3c", "#e67e22", "#f1c40f", "#27ae60", "#2980b9"]
CLUSTER_COLORS_6 = ["#e74c3c", "#e67e22", "#f1c40f", "#27ae60", "#2980b9", "#8e44ad"]
TIER_COLORS = {"T1": "#1a4314", "T2": "#3b8520", "T3": "#2980b9",
               "T4": "#e67e22", "T5": "#c0392b"}

# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_contributors(n_sample=SAMPLE_SIZE):
    print(f"Loading contributors (n={n_sample})...")
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

    if len(df) > n_sample:
        df = df.sample(n=n_sample, random_state=SEED).reset_index(drop=True)

    median_c = df["persistence_c"].median()
    df["persist_binary"] = (df["persistence_c"] >= median_c).astype(int)
    print(f"  Loaded {len(df):,} contributors")
    return df


def cramers_v(labels, persist_binary):
    ct = pd.crosstab(labels, persist_binary)
    chi2 = chi2_contingency(ct)[0]
    n = ct.sum().sum()
    min_dim = min(ct.shape) - 1
    return np.sqrt(chi2 / (n * min_dim)) if min_dim > 0 and n > 0 else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# SOLUTION RUNNERS
# ─────────────────────────────────────────────────────────────────────────────

def run_solution_A(df, k):
    """Factor Analysis (5 comp) on volume_reduced → K-Means."""
    avail = [f for f in VOLUME_REDUCED if f in df.columns]
    X_raw = df[avail].fillna(0).values
    X_scaled = StandardScaler().fit_transform(X_raw)

    fa = FactorAnalysis(n_components=5, random_state=SEED)
    X_fa = fa.fit_transform(X_scaled)

    km = KMeans(n_clusters=k, random_state=SEED, n_init=10)
    labels = km.fit_predict(X_fa)

    # PCA on FA-space for 2D viz
    pca_viz = PCA(n_components=2, random_state=SEED)
    X_viz = pca_viz.fit_transform(X_fa)

    return labels, X_viz, pca_viz, X_fa, fa, avail


def run_solution_B(df, k):
    """PCA(3)+LDA(1) on volume_reduced → K-Means."""
    avail = [f for f in VOLUME_REDUCED if f in df.columns]
    X_raw = df[avail].fillna(0).values
    X_scaled = StandardScaler().fit_transform(X_raw)
    y = df["persist_binary"].values

    pca = PCA(n_components=3, random_state=SEED)
    X_pca = pca.fit_transform(X_scaled)

    lda = LinearDiscriminantAnalysis(n_components=1)
    X_lda = lda.fit_transform(X_scaled, y)

    X_combined = np.hstack([X_pca, X_lda])

    km = KMeans(n_clusters=k, random_state=SEED, n_init=10)
    labels = km.fit_predict(X_combined)

    # PCA on combined space for 2D viz
    pca_viz = PCA(n_components=2, random_state=SEED)
    X_viz = pca_viz.fit_transform(X_combined)

    return labels, X_viz, pca_viz, X_combined, (pca, lda), avail


def run_solution_C(df, k):
    """PCA(7) + GMM on behavioral_only."""
    avail = [f for f in BEHAVIORAL_ONLY if f in df.columns]
    X_raw = df[avail].fillna(0).values
    X_scaled = StandardScaler().fit_transform(X_raw)

    pca = PCA(n_components=7, random_state=SEED)
    X_pca = pca.fit_transform(X_scaled)

    gmm = GaussianMixture(n_components=k, random_state=SEED, n_init=5,
                           covariance_type="full", max_iter=300)
    labels = gmm.fit_predict(X_pca)

    # PCA on PCA-space for 2D viz
    pca_viz = PCA(n_components=2, random_state=SEED)
    X_viz = pca_viz.fit_transform(X_pca)

    return labels, X_viz, pca_viz, X_pca, (pca, gmm), avail


def run_biplot_tiers(df, k=5):
    """Reproduce the biplot tier approach from final_analysis for comparison."""
    avail = [f for f in BIPLOT_FEATURES if f in df.columns]
    X_raw = df[avail].fillna(0).values
    X_scaled = StandardScaler().fit_transform(X_raw)

    pca = PCA(n_components=3, random_state=SEED)
    X_pca = pca.fit_transform(X_scaled)

    # K-Means tiers on PC2 (contextual axis)
    km = KMeans(n_clusters=k, random_state=SEED, n_init=10)
    tier_labels = km.fit_predict(X_pca[:, 1:2])  # PC2 only
    centroid_order = np.argsort(km.cluster_centers_.flatten())
    label_map = {old: new for new, old in enumerate(centroid_order)}
    tier_labels = np.array([label_map[l] for l in tier_labels])

    return tier_labels, X_pca, pca, avail


# ─────────────────────────────────────────────────────────────────────────────
# PROFILING
# ─────────────────────────────────────────────────────────────────────────────

def profile_clusters(df, labels, solution_name):
    """Generate comprehensive cluster profiles."""
    df_work = df.copy()
    df_work["cluster"] = labels
    k = len(set(labels) - {-1})

    profiles = []
    for c in range(k):
        mask = df_work["cluster"] == c
        sub = df_work[mask]
        n = mask.sum()
        if n == 0:
            continue

        profile = {
            "solution": solution_name,
            "cluster": c,
            "n": n,
            "pct_of_total": round(n / len(df_work) * 100, 1),
            "pct_persistent": round(sub["persist_binary"].mean() * 100, 1),
            "mean_persistence_c": round(sub["persistence_c"].mean(), 4),
            "std_persistence_c": round(sub["persistence_c"].std(), 4),
        }

        for feat in PROFILE_FEATURES:
            if feat in sub.columns:
                profile[f"mean_{feat}"] = round(sub[feat].fillna(0).mean(), 3)

        # Account type breakdown
        if "ACCOUNT_TYPE" in sub.columns:
            profile["pct_member"] = round((sub["ACCOUNT_TYPE"] == "Member").mean() * 100, 1)

        profiles.append(profile)

    return pd.DataFrame(profiles)


def assign_personas(profiles_df):
    """Assign descriptive persona labels based on cluster characteristics."""
    personas = {}
    for _, row in profiles_df.iterrows():
        c = int(row["cluster"])
        persist = row["pct_persistent"]
        logins = row.get("mean_logins_90d", 0)
        breadth = row.get("mean_activity_breadth", 0)
        speed = row.get("mean_activation_speed", 0)
        n = row["n"]

        if n < 10:
            personas[c] = "Micro-cluster (artifact)"
        elif persist >= 95 and breadth >= 4:
            personas[c] = "Power Contributors"
        elif persist >= 90 and logins >= 15:
            personas[c] = "Heavy Loggers"
        elif persist >= 85:
            personas[c] = "Steady Persisters"
        elif persist >= 70:
            personas[c] = "Moderate Engagers"
        elif persist >= 50:
            personas[c] = "At-Risk Contributors"
        else:
            personas[c] = "Likely Churners"

    return personas


# ─────────────────────────────────────────────────────────────────────────────
# BOOTSTRAP STABILITY
# ─────────────────────────────────────────────────────────────────────────────

def bootstrap_stability(df, solution_fn, k, n_boot=10):
    """Test cluster stability across bootstrap resamples."""
    from sklearn.metrics import adjusted_rand_score

    all_labels = []
    all_sil = []
    all_cv = []

    for i in range(n_boot):
        rng = np.random.RandomState(SEED + i)
        boot_idx = rng.choice(len(df), size=len(df), replace=True)
        df_boot = df.iloc[boot_idx].reset_index(drop=True)

        labels, X_viz, _, X_space, _, _ = solution_fn(df_boot, k)
        all_labels.append(labels)

        sil = silhouette_score(X_space, labels) if len(set(labels)) > 1 else 0
        cv = cramers_v(labels, df_boot["persist_binary"].values)
        all_sil.append(sil)
        all_cv.append(cv)

    # Cross-bootstrap ARI
    ari_values = []
    for i in range(n_boot):
        for j in range(i + 1, n_boot):
            ari = adjusted_rand_score(all_labels[i], all_labels[j])
            ari_values.append(ari)

    return {
        "mean_ari": round(np.mean(ari_values), 4),
        "std_ari": round(np.std(ari_values), 4),
        "mean_silhouette": round(np.mean(all_sil), 4),
        "std_silhouette": round(np.std(all_sil), 4),
        "mean_cramers_v": round(np.mean(all_cv), 4),
        "std_cramers_v": round(np.std(all_cv), 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# VISUALIZATION FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def plot_cluster_scatter(df, labels, X_viz, pca_viz, solution_name, k,
                          cluster_colors, var_explained=None):
    """Cluster scatter + persistence gradient side by side."""
    fig = make_subplots(rows=1, cols=2,
                         subplot_titles=[f"Clusters (k={k})", "Persistence Gradient"],
                         horizontal_spacing=0.08)

    for c in range(k):
        mask = labels == c
        n = mask.sum()
        persist_pct = df.loc[mask, "persist_binary"].mean() * 100 if mask.sum() > 0 else 0
        fig.add_trace(go.Scatter(
            x=X_viz[mask, 0], y=X_viz[mask, 1], mode="markers",
            marker=dict(size=3, color=cluster_colors[c % len(cluster_colors)], opacity=0.35),
            name=f"C{c} (n={n}, {persist_pct:.0f}%)",
        ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=X_viz[:, 0], y=X_viz[:, 1], mode="markers",
        marker=dict(size=3, color=df["persistence_c"], colorscale="RdYlGn",
                    opacity=0.35, showscale=True,
                    colorbar=dict(title="Persist. C", x=1.02, thickness=12, len=0.8)),
        showlegend=False,
    ), row=1, col=2)

    title = f"{solution_name}"
    if var_explained is not None:
        title += f"<br>PC1={var_explained[0]*100:.1f}%  PC2={var_explained[1]*100:.1f}%"

    fig.update_layout(
        title=dict(text=title, font=dict(size=14)),
        height=500, width=1200,
        plot_bgcolor="rgba(245,245,240,1)", paper_bgcolor="white",
        font=dict(size=11), margin=dict(t=70, b=50, l=60, r=80),
    )
    fig.update_xaxes(gridcolor="rgba(200,200,200,0.3)")
    fig.update_yaxes(gridcolor="rgba(200,200,200,0.3)")
    return fig


def plot_biplot_overlay(df, labels, X_pca_full, pca_full, feature_names,
                         solution_name, k, cluster_colors):
    """PCA biplot with cluster coloring and feature loading arrows (matching fig08b)."""
    fig = go.Figure()

    # Scatter colored by cluster
    for c in range(k):
        mask = labels == c
        n = mask.sum()
        persist_pct = df.loc[mask, "persist_binary"].mean() * 100 if mask.sum() > 0 else 0
        fig.add_trace(go.Scatter(
            x=X_pca_full[mask, 0], y=X_pca_full[mask, 1], mode="markers",
            marker=dict(size=3, color=cluster_colors[c % len(cluster_colors)], opacity=0.3),
            name=f"C{c} (n={n}, {persist_pct:.0f}%)",
        ))

    # Feature loading arrows (top 10 by magnitude)
    if hasattr(pca_full, 'components_') and pca_full.components_.shape[0] >= 2:
        loadings = pd.DataFrame(
            pca_full.components_[:2].T,
            index=feature_names[:pca_full.components_.shape[1]],
            columns=["PC1", "PC2"]
        )
        combined_mag = (loadings["PC1"] ** 2 + loadings["PC2"] ** 2)
        top_feats = combined_mag.nlargest(10).index

        scale = abs(X_pca_full[:, 0].max()) / loadings["PC1"].abs().max() * 0.5
        for feat in top_feats:
            x_end = loadings.loc[feat, "PC1"] * scale
            y_end = loadings.loc[feat, "PC2"] * scale
            c_type = CONSTRUCT_MAP.get(feat, "Contextual")
            arrow_color = "#1a4314" if c_type in ("Volume", "Velocity", "Sequencing") else "#8e44ad"
            fig.add_trace(go.Scatter(
                x=[0, x_end], y=[0, y_end], mode="lines+text",
                line=dict(color=arrow_color, width=2),
                text=["", feat.replace("_", " ")], textposition="top center",
                textfont=dict(size=8, color=arrow_color), showlegend=False,
            ))

    var = pca_full.explained_variance_ratio_ if hasattr(pca_full, 'explained_variance_ratio_') else [0, 0]
    fig.update_layout(
        title=f"PCA Biplot: {solution_name} (k={k})<br>"
              f"PC1={var[0]*100:.1f}%  PC2={var[1]*100:.1f}%"
              f"  Dark=Behavioral  Purple=Enrichment",
        height=650, width=900,
        plot_bgcolor="rgba(245,245,240,1)", paper_bgcolor="white",
        xaxis_title=f"PC1 ({var[0]*100:.1f}%)",
        yaxis_title=f"PC2 ({var[1]*100:.1f}%)",
        font=dict(size=11),
    )
    return fig


def plot_radar_profiles(profiles_df, solution_name, k, cluster_colors):
    """Radar chart of cluster profiles (normalized 0-1)."""
    radar_feats = ["mean_logins_90d", "mean_log_logins_pw", "mean_activity_breadth",
                    "mean_activation_speed", "mean_tree_edits_90d",
                    "mean_names_90d", "mean_sources_90d", "mean_funnel_stage"]
    radar_labels = ["Logins (90d)", "Log Logins/wk", "Breadth", "Activ. Speed",
                     "Tree Edits (90d)", "Names (90d)", "Sources (90d)", "Funnel"]

    avail_feats = [f for f in radar_feats if f in profiles_df.columns]
    avail_labels = [radar_labels[i] for i, f in enumerate(radar_feats) if f in profiles_df.columns]

    if not avail_feats:
        return None

    # Normalize to 0-1
    vals = profiles_df[avail_feats].copy()
    for col in avail_feats:
        vmax = vals[col].max()
        if vmax > 0:
            vals[col] = vals[col] / vmax

    fig = go.Figure()
    for _, row in profiles_df.iterrows():
        c = int(row["cluster"])
        r_vals = [vals.loc[row.name, f] for f in avail_feats]
        r_vals.append(r_vals[0])  # Close the polygon
        theta = avail_labels + [avail_labels[0]]

        fig.add_trace(go.Scatterpolar(
            r=r_vals, theta=theta, fill="toself",
            name=f"C{c} ({row['pct_persistent']:.0f}% persist, n={int(row['n'])})",
            line_color=cluster_colors[c % len(cluster_colors)],
            opacity=0.6,
        ))

    fig.update_layout(
        title=f"Cluster Radar Profiles: {solution_name} (k={k})",
        polar=dict(radialaxis=dict(visible=True, range=[0, 1.05])),
        height=550, width=700,
        font=dict(size=11),
    )
    return fig


def plot_persistence_bars(profiles_df, solution_name, k, cluster_colors, personas):
    """Persistence rate bar chart per cluster with persona labels."""
    sorted_profiles = profiles_df.sort_values("pct_persistent")

    fig = go.Figure()
    for _, row in sorted_profiles.iterrows():
        c = int(row["cluster"])
        persona = personas.get(c, f"Cluster {c}")
        fig.add_trace(go.Bar(
            x=[f"C{c}: {persona}"],
            y=[row["pct_persistent"]],
            marker_color=cluster_colors[c % len(cluster_colors)],
            text=[f"{row['pct_persistent']:.0f}%<br>n={int(row['n'])}"],
            textposition="outside",
            showlegend=False,
        ))

    fig.update_layout(
        title=f"Persistence Rate by Cluster: {solution_name} (k={k})",
        yaxis_title="% Persistent",
        yaxis_range=[0, 110],
        height=400, width=max(600, k * 120),
        plot_bgcolor="rgba(245,245,240,1)", paper_bgcolor="white",
        font=dict(size=12),
    )
    return fig


def plot_silhouette_per_cluster(X_space, labels, solution_name, k, cluster_colors):
    """Silhouette plot showing per-sample scores grouped by cluster."""
    sil_samples = silhouette_samples(X_space, labels)
    mean_sil = silhouette_score(X_space, labels)

    fig = go.Figure()
    y_lower = 0
    for c in range(k):
        mask = labels == c
        cluster_sil = np.sort(sil_samples[mask])
        size = mask.sum()

        fig.add_trace(go.Bar(
            x=cluster_sil, y=list(range(y_lower, y_lower + size)),
            orientation="h",
            marker_color=cluster_colors[c % len(cluster_colors)],
            name=f"C{c} (n={size})",
            showlegend=True,
        ))
        y_lower += size + 10

    fig.add_vline(x=mean_sil, line_dash="dash", line_color="red",
                   annotation_text=f"Mean: {mean_sil:.3f}")
    fig.update_layout(
        title=f"Silhouette Plot: {solution_name} (k={k})",
        xaxis_title="Silhouette Coefficient",
        height=500, width=800,
        plot_bgcolor="rgba(245,245,240,1)",
        yaxis=dict(showticklabels=False),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 90)
    print("PHASE 7B: DEEP DIVE — Top Clustering Solutions")
    print("=" * 90)
    start_time = datetime.now()

    df = load_contributors()

    solutions = {
        "A_FA5_KM": ("Factor Analysis(5) + K-Means", run_solution_A),
        "B_PCA3LDA_KM": ("PCA(3)+LDA(1) + K-Means", run_solution_B),
        "C_PCA7_GMM": ("PCA(7) + GMM", run_solution_C),
    }

    all_profiles = []
    all_stability = []
    summary_rows = []

    for sol_key, (sol_name, sol_fn) in solutions.items():
        for k in [5, 6]:
            tag = f"{sol_key}_k{k}"
            colors = CLUSTER_COLORS_5 if k == 5 else CLUSTER_COLORS_6
            print(f"\n{'='*70}")
            print(f"  {sol_name}, k={k}")
            print(f"{'='*70}")

            # ── Run solution ──
            labels, X_viz, pca_viz, X_space, model, avail = sol_fn(df, k)

            # ── Metrics ──
            sil = silhouette_score(X_space, labels)
            cv = cramers_v(labels, df["persist_binary"].values)
            composite = sil * cv
            print(f"  Silhouette: {sil:.4f}")
            print(f"  Cramer's V: {cv:.4f}")
            print(f"  Composite:  {composite:.4f}")

            # ── Profile ──
            profiles = profile_clusters(df, labels, tag)
            personas = assign_personas(profiles)
            all_profiles.append(profiles)

            print(f"\n  Cluster Profiles:")
            print(f"  {'C':>3} {'n':>6} {'%Persist':>9} {'Logins90d':>10} {'Breadth':>8} {'Speed':>6} {'Persona'}")
            print("  " + "-" * 70)
            for _, row in profiles.iterrows():
                c = int(row["cluster"])
                print(f"  {c:>3} {int(row['n']):>6} {row['pct_persistent']:>8.1f}% "
                      f"{row.get('mean_logins_90d', 0):>10.1f} "
                      f"{row.get('mean_activity_breadth', 0):>8.1f} "
                      f"{row.get('mean_activation_speed', 0):>6.2f} "
                      f"{personas.get(c, '?')}")

            # ── Stability (bootstrap) ──
            print(f"\n  Running bootstrap stability (10 resamples)...")
            stability = bootstrap_stability(df, sol_fn, k, n_boot=10)
            stability["solution"] = tag
            all_stability.append(stability)
            print(f"  ARI: {stability['mean_ari']:.4f} ± {stability['std_ari']:.4f}")
            print(f"  Sil: {stability['mean_silhouette']:.4f} ± {stability['std_silhouette']:.4f}")
            print(f"  CV:  {stability['mean_cramers_v']:.4f} ± {stability['std_cramers_v']:.4f}")

            # ── Summary row ──
            summary_rows.append({
                "solution": tag, "name": sol_name, "k": k,
                "silhouette": round(sil, 4), "cramers_v": round(cv, 4),
                "composite": round(composite, 4),
                "ari_stability": stability["mean_ari"],
                "n_degenerate": sum(1 for _, r in profiles.iterrows() if r["n"] < 20),
            })

            # ── Visualizations ──
            var_explained = pca_viz.explained_variance_ratio_ if hasattr(pca_viz, 'explained_variance_ratio_') else None

            # 1. Cluster scatter + persistence
            fig = plot_cluster_scatter(df, labels, X_viz, pca_viz,
                                        f"{sol_name}", k, colors, var_explained)
            fig.write_image(OUTPUT / f"fig_{tag}_scatter.png", scale=2)

            # 2. Biplot overlay (only for solutions that have loadings)
            avail_biplot = [f for f in BIPLOT_FEATURES if f in df.columns]
            X_biplot_raw = df[avail_biplot].fillna(0).values
            X_biplot_scaled = StandardScaler().fit_transform(X_biplot_raw)
            pca_biplot = PCA(n_components=2, random_state=SEED)
            X_biplot_pca = pca_biplot.fit_transform(X_biplot_scaled)

            fig = plot_biplot_overlay(df, labels, X_biplot_pca, pca_biplot,
                                      avail_biplot, sol_name, k, colors)
            fig.write_image(OUTPUT / f"fig_{tag}_biplot.png", scale=2)

            # 3. Radar profiles
            fig = plot_radar_profiles(profiles, sol_name, k, colors)
            if fig:
                fig.write_image(OUTPUT / f"fig_{tag}_radar.png", scale=2)

            # 4. Persistence bars
            fig = plot_persistence_bars(profiles, sol_name, k, colors, personas)
            fig.write_image(OUTPUT / f"fig_{tag}_persist.png", scale=2)

            # 5. Silhouette per cluster
            fig = plot_silhouette_per_cluster(X_space, labels, sol_name, k, colors)
            fig.write_image(OUTPUT / f"fig_{tag}_silhouette.png", scale=2)

            print(f"  5 figures saved for {tag}")

    # ── Also generate biplot-tier comparison ──
    print(f"\n{'='*70}")
    print("  Reference: Biplot Tier Approach (k=5)")
    print(f"{'='*70}")

    tier_labels, X_tier_pca, tier_pca, tier_avail = run_biplot_tiers(df, k=5)
    sil_tier = silhouette_score(X_tier_pca[:, :2], tier_labels)
    cv_tier = cramers_v(tier_labels, df["persist_binary"].values)
    print(f"  Silhouette: {sil_tier:.4f}")
    print(f"  Cramer's V: {cv_tier:.4f}")
    print(f"  Composite:  {sil_tier * cv_tier:.4f}")

    tier_profiles = profile_clusters(df, tier_labels, "biplot_tiers_k5")
    all_profiles.append(tier_profiles)

    summary_rows.append({
        "solution": "biplot_tiers_k5", "name": "Biplot Tiers (PC2 KM)", "k": 5,
        "silhouette": round(sil_tier, 4), "cramers_v": round(cv_tier, 4),
        "composite": round(sil_tier * cv_tier, 4),
        "ari_stability": np.nan, "n_degenerate": 0,
    })

    # Biplot tier scatter
    fig = make_subplots(rows=1, cols=2,
                         subplot_titles=["Biplot Tiers (k=5)", "Persistence Gradient"])
    for t in range(5):
        mask = tier_labels == t
        fig.add_trace(go.Scatter(
            x=X_tier_pca[mask, 0], y=X_tier_pca[mask, 1], mode="markers",
            marker=dict(size=3, color=list(TIER_COLORS.values())[t], opacity=0.3),
            name=f"T{t+1} (n={mask.sum()})",
        ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=X_tier_pca[:, 0], y=X_tier_pca[:, 1], mode="markers",
        marker=dict(size=3, color=df["persistence_c"], colorscale="RdYlGn", opacity=0.3,
                    colorbar=dict(title="Persist.", x=1.02)),
        showlegend=False,
    ), row=1, col=2)
    var_tier = tier_pca.explained_variance_ratio_
    fig.update_layout(
        title=f"Reference: Biplot Tiers — PC1={var_tier[0]*100:.1f}%  PC2={var_tier[1]*100:.1f}%",
        height=500, width=1200,
        plot_bgcolor="rgba(245,245,240,1)",
    )
    fig.write_image(OUTPUT / "fig_reference_biplot_tiers.png", scale=2)
    print("  Reference figure saved")

    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY TABLE
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print("SOLUTION COMPARISON SUMMARY")
    print(f"{'='*90}")

    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values("composite", ascending=False)

    print(f"\n  {'Solution':<25} {'k':>3} {'Sil':>6} {'CV':>6} {'Comp':>6} {'ARI':>6} {'Degen':>5}")
    print("  " + "-" * 60)
    for _, row in summary_df.iterrows():
        ari_str = f"{row['ari_stability']:.3f}" if not pd.isna(row["ari_stability"]) else "  N/A"
        print(f"  {row['name']:<25} {row['k']:>3} {row['silhouette']:>6.3f} "
              f"{row['cramers_v']:>6.3f} {row['composite']:>6.3f} {ari_str:>6} "
              f"{int(row['n_degenerate']):>5}")

    # Save all outputs
    all_prof_df = pd.concat(all_profiles, ignore_index=True)
    all_prof_df.to_csv(OUTPUT / "all_cluster_profiles.csv", index=False)
    summary_df.to_csv(OUTPUT / "solution_comparison.csv", index=False)
    pd.DataFrame(all_stability).to_csv(OUTPUT / "stability_results.csv", index=False)

    # ── Summary comparison figure ──
    fig = go.Figure()
    for _, row in summary_df.iterrows():
        fig.add_trace(go.Scatter(
            x=[row["silhouette"]], y=[row["cramers_v"]],
            mode="markers+text",
            marker=dict(size=row["composite"] * 80 + 10,
                        color=row["composite"], colorscale="Viridis",
                        showscale=False, opacity=0.7,
                        line=dict(width=1, color="black")),
            text=[f"{row['name']}<br>k={int(row['k'])}"],
            textposition="top center", textfont=dict(size=9),
            showlegend=False,
        ))

    fig.update_layout(
        title="Solution Comparison: Silhouette vs Cramer's V<br>(bubble size = composite score)",
        xaxis_title="Silhouette Score", yaxis_title="Cramer's V",
        height=550, width=800,
        plot_bgcolor="rgba(245,245,240,1)",
    )
    fig.write_image(OUTPUT / "fig_solution_comparison.png", scale=2)
    print("  fig_solution_comparison.png saved")

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'='*90}")
    print(f"PHASE 7B COMPLETE — {elapsed:.0f}s")
    print(f"{'='*90}")
    print(f"Output: {OUTPUT}")
    print(f"Figures: {len(list(OUTPUT.glob('fig_*.png')))}")


if __name__ == "__main__":
    main()
