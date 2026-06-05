"""Clustering Lab — Interactive ML Model Builder"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from components.branding import apply_branding, section_header, metric_card, COLORS, CHART_PALETTE, insight_box, sidebar_tab
from components.charts import elbow_chart
from src.data_loader import load_for_dashboard
from src.features.engineering import build_clustering_features
from src.models.clustering import (
    scale_features, scale_features_multi, run_kmeans, run_gmm,
    evaluate_clusters, elbow_analysis, compute_pca, profile_clusters,
)

st.set_page_config(page_title="Clustering Lab | FamilySearch", page_icon="\U0001F333", layout="wide")
apply_branding()

st.title("Clustering Lab")
st.markdown("*Build, compare, and evaluate segmentation models interactively*")
st.markdown("---")

# ── Sidebar Controls (only on Controls tab) ──────────────────────────
active_tab = sidebar_tab()

# Defaults (used if Controls tab not active)
algorithm = "K-Means"
scaler_method = "standard"
n_clusters = 5
min_cluster_size = 500
min_samples = 50
run_elbow = False
sample_size = 100_000

if active_tab == "controls":
    st.sidebar.markdown("### Model Configuration")
    algorithm = st.sidebar.selectbox("Algorithm", ["K-Means", "Gaussian Mixture (GMM)", "HDBSCAN"])

    scaler_method = st.sidebar.selectbox("Scaling Method",
        ["standard", "robust", "minmax"],
        help="StandardScaler (default), RobustScaler (outlier-resistant), MinMaxScaler (0-1)")

    if algorithm in ["K-Means", "Gaussian Mixture (GMM)"]:
        n_clusters = st.sidebar.slider("Number of Clusters", 2, 12, 5)
    else:
        min_cluster_size = st.sidebar.slider("Min Cluster Size", 100, 5000, 500, step=100)
        min_samples = st.sidebar.slider("Min Samples", 10, 500, 50, step=10)

    run_elbow = st.sidebar.checkbox("Run Elbow Analysis", value=False,
                                     help="Test k=2..10 (takes ~30s)")

    st.sidebar.markdown("---")
    sample_size = st.sidebar.selectbox("Sample Size", [100_000, 250_000], index=0,
                                        format_func=lambda x: f"{x:,}")

# ── Load & Prepare ───────────────────────────────────────────────────
df = load_for_dashboard(n=sample_size)

section_header("Feature Selection", "Choose from raw columns, engineered features, and your derived features")

# Build the full feature pool: engineered + all raw numeric + derived from Feature Lab
features_eng = build_clustering_features(df)
raw_numeric = df.select_dtypes(include=[np.number]).drop(columns=[c for c in features_eng.columns if c in df.columns], errors="ignore")
derived = st.session_state.get("derived_features", pd.DataFrame())
derived_numeric = derived.select_dtypes(include=[np.number]) if not derived.empty else pd.DataFrame()

# Combine all available features
all_pool = pd.concat([features_eng, raw_numeric, derived_numeric], axis=1)
all_pool = all_pool.loc[:, ~all_pool.columns.duplicated()]  # drop dupes
available_features = list(all_pool.columns)

# Label sources for clarity
eng_cols = set(features_eng.columns)
raw_cols = set(raw_numeric.columns)
derived_cols = set(derived_numeric.columns) if not derived_numeric.empty else set()

st.caption(f"**{len(eng_cols)}** engineered + **{len(raw_cols)}** raw numeric + "
           f"**{len(derived_cols)}** derived features = **{len(available_features)}** total")

# Sensible defaults
default_features = [c for c in [
    "LOGINS_PER_WEEK", "TREE_EDITS_PER_WEEK", "SOURCES_PER_WEEK",
    "NAMES_PER_WEEK", "N_ACTIVITY_TYPES", "LOGIN_CONSISTENCY",
    "PCT_DECEASED_NAMES", "USER_CURRENT_AGE",
    "DAYS_LOGGING_IN_LOG", "TREE_EDITS_LOG", "SOURCES_ADDED_LOG",
] if c in available_features]

selected_features = st.multiselect("Features for clustering:", available_features,
                                    default=default_features)

if not selected_features:
    st.warning("Select at least 2 features to proceed.")
    st.stop()

features = all_pool[selected_features].fillna(0).copy()
st.info(f"Using **{len(selected_features)} features** on **{len(features):,} users**")

# ── Scale ────────────────────────────────────────────────────────────
X, scaler = scale_features_multi(features, method=scaler_method)

# ── Elbow Analysis ───────────────────────────────────────────────────
if run_elbow and algorithm != "HDBSCAN":
    section_header("Elbow Analysis", "Inertia and silhouette score for k=2..10")
    with st.spinner("Running elbow analysis..."):
        elbow_df = elbow_analysis(X, k_range=range(2, 11))
    fig = elbow_chart(elbow_df)
    st.plotly_chart(fig, use_container_width=True)

    best_k = elbow_df.loc[elbow_df["silhouette"].idxmax(), "k"]
    insight_box(f"Best silhouette score at <strong>k={best_k}</strong> "
                f"(score={elbow_df['silhouette'].max():.4f})")

# ── Run Clustering ───────────────────────────────────────────────────
section_header("Clustering Results")

with st.spinner(f"Running {algorithm}..."):
    if algorithm == "K-Means":
        result = run_kmeans(X, n_clusters)
    elif algorithm == "Gaussian Mixture (GMM)":
        result = run_gmm(X, n_clusters)
    else:
        try:
            from src.models.clustering import run_hdbscan
            result = run_hdbscan(X, min_cluster_size=min_cluster_size, min_samples=min_samples)
        except ImportError:
            st.error("HDBSCAN not installed. Use K-Means or GMM.")
            st.stop()

labels = result["labels"]
metrics = evaluate_clusters(X, labels)

# ── Quality Metrics ──────────────────────────────────────────────────
cols = st.columns(4)
with cols[0]: metric_card("Clusters Found", str(metrics["n_clusters"]))
with cols[1]: metric_card("Silhouette", f"{metrics['silhouette']:.4f}" if metrics["silhouette"] else "N/A")
with cols[2]: metric_card("Calinski-Harabasz", f"{metrics['calinski_harabasz']:,.0f}" if metrics["calinski_harabasz"] else "N/A")
with cols[3]: metric_card("Davies-Bouldin", f"{metrics['davies_bouldin']:.4f}" if metrics["davies_bouldin"] else "N/A")

st.markdown("")

# GMM-specific metrics
if algorithm == "Gaussian Mixture (GMM)":
    col1, col2 = st.columns(2)
    with col1: metric_card("BIC", f"{result['bic']:,.0f}")
    with col2: metric_card("AIC", f"{result['aic']:,.0f}")
    st.caption("Lower BIC/AIC = better model fit. BIC penalizes complexity more than AIC.")

# ── Cluster Size Distribution ────────────────────────────────────────
section_header("Cluster Size Distribution")
cluster_counts = pd.Series(labels[labels >= 0]).value_counts().sort_index()
fig = go.Figure(go.Bar(
    x=[f"Cluster {i}" for i in cluster_counts.index],
    y=cluster_counts.values,
    marker_color=[CHART_PALETTE[i % len(CHART_PALETTE)] for i in range(len(cluster_counts))],
    text=[f"{v:,} ({v/cluster_counts.sum()*100:.1f}%)" for v in cluster_counts.values],
    textposition="outside"))
fig.update_layout(height=350, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                  xaxis_title="Cluster", yaxis_title="Users")
st.plotly_chart(fig, use_container_width=True)

if (labels == -1).sum() > 0:
    st.warning(f"**{(labels == -1).sum():,} noise points** ({(labels == -1).mean()*100:.1f}%) "
               "not assigned to any cluster (HDBSCAN noise).")

# ── 2D Visualization ─────────────────────────────────────────────────
section_header("2D Visualization", "Dimensionality reduction to visualize cluster separation")
viz_tab1, viz_tab2 = st.tabs(["PCA", "UMAP"])

with viz_tab1:
    X_pca, pca_model = compute_pca(X)
    var_explained = pca_model.explained_variance_ratio_
    fig = px.scatter(x=X_pca[:, 0], y=X_pca[:, 1], color=labels.astype(str),
                     labels={"x": f"PC1 ({var_explained[0]*100:.1f}%)",
                             "y": f"PC2 ({var_explained[1]*100:.1f}%)",
                             "color": "Cluster"},
                     color_discrete_sequence=CHART_PALETTE, opacity=0.4,
                     title="PCA Projection")
    fig.update_layout(height=500, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"Total variance explained by 2 components: {sum(var_explained[:2])*100:.1f}%")

with viz_tab2:
    try:
        from src.models.clustering import compute_umap
        with st.spinner("Computing UMAP (may take 30-60s)..."):
            X_umap, umap_idx = compute_umap(X, sample_size=min(30_000, len(X)))
        fig = px.scatter(x=X_umap[:, 0], y=X_umap[:, 1],
                         color=labels[umap_idx].astype(str),
                         labels={"x": "UMAP-1", "y": "UMAP-2", "color": "Cluster"},
                         color_discrete_sequence=CHART_PALETTE, opacity=0.4,
                         title="UMAP Projection")
        fig.update_layout(height=500, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        st.info("UMAP not available. Install umap-learn for non-linear dimensionality reduction.")

# ── Cluster Profiles ─────────────────────────────────────────────────
section_header("Cluster Feature Profiles", "Mean feature values per cluster")
sizes_df, means_df = profile_clusters(features, labels, selected_features)

st.markdown("#### Cluster Sizes")
st.dataframe(sizes_df, use_container_width=True)

st.markdown("#### Feature Means by Cluster")
st.dataframe(means_df.style.background_gradient(cmap="Greens", axis=0), use_container_width=True)

# ── Store in session state for Profiles page ─────────────────────────
st.session_state["cluster_labels"] = labels
st.session_state["cluster_features"] = features
st.session_state["cluster_selected_features"] = selected_features
st.session_state["cluster_algorithm"] = algorithm
st.session_state["cluster_metrics"] = metrics
st.session_state["cluster_df"] = df

st.success("Clustering complete. Visit **Segment Profiles** to interpret the results.")
