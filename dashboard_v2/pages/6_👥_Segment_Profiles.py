"""Segment Profiles — Cluster Interpretation & Profiling"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from components.branding import apply_branding, section_header, CHART_PALETTE, insight_box
from components.charts import branded_radar, branded_bar
from components.metrics import segment_card
from src.features.engineering import add_age_group

st.set_page_config(page_title="Segment Profiles | FamilySearch", page_icon="\U0001F333", layout="wide")
apply_branding()

st.title("Segment Profiles & Interpretation")
st.markdown("*Understanding what makes each user segment distinct*")
st.markdown("---")

# ── Check for clustering results ─────────────────────────────────────
if "cluster_labels" not in st.session_state:
    st.warning("Run clustering first in the **Clustering Lab** page.")
    st.info("Navigate to Clustering Lab, configure and run a model, then return here.")
    st.stop()

labels = st.session_state["cluster_labels"]
features = st.session_state["cluster_features"]
selected_features = st.session_state["cluster_selected_features"]
algorithm = st.session_state["cluster_algorithm"]
metrics = st.session_state["cluster_metrics"]
df = st.session_state["cluster_df"]

n_clusters = metrics["n_clusters"]
# Merge engineered features into raw df so all columns are accessible
df_work = pd.concat([df.reset_index(drop=True), features.reset_index(drop=True)], axis=1)
df_work = df_work.loc[:, ~df_work.columns.duplicated()]
df_work["cluster"] = labels
df_work = df_work[df_work["cluster"] >= 0]

# ── Segment Personas ─────────────────────────────────────────────────
section_header("Segment Overview", f"{n_clusters} segments identified via {algorithm}")

# Compute cluster profiles
features_work = features.copy()
features_work["cluster"] = labels
cluster_means = features_work[features_work["cluster"] >= 0].groupby("cluster")[selected_features].mean()
cluster_sizes = df_work["cluster"].value_counts().sort_index()

# Auto-generate persona names based on dominant characteristics
persona_names = {}
for c in cluster_means.index:
    row = cluster_means.loc[c]
    # Determine dominant trait
    login_rate = row.get("LOGINS_PER_WEEK", row.get("DAYS_LOGGING_IN_LOG", 0))
    tree_rate = row.get("TREE_EDITS_PER_WEEK", row.get("TREE_EDITS_LOG", 0))
    activity_breadth = row.get("N_ACTIVITY_TYPES", 0)

    if login_rate <= cluster_means.get("LOGINS_PER_WEEK", cluster_means.iloc[:, 0]).quantile(0.25):
        persona_names[c] = "Dormant Accounts"
    elif activity_breadth >= cluster_means.get("N_ACTIVITY_TYPES", cluster_means.iloc[:, 0]).quantile(0.9):
        persona_names[c] = "Power Contributors"
    elif tree_rate >= cluster_means.get("TREE_EDITS_PER_WEEK", cluster_means.iloc[:, 0]).quantile(0.75):
        persona_names[c] = "Active Tree Builders"
    elif login_rate >= cluster_means.get("LOGINS_PER_WEEK", cluster_means.iloc[:, 0]).quantile(0.5):
        persona_names[c] = "Engaged Browsers"
    else:
        persona_names[c] = f"Casual Visitors (Seg {c})"

# Display persona cards
cols = st.columns(min(n_clusters, 4))
for i, c in enumerate(sorted(cluster_sizes.index)):
    with cols[i % len(cols)]:
        top_feats = cluster_means.loc[c].nlargest(4).index.tolist()
        top_desc = [f"{f}: {cluster_means.loc[c, f]:.3f}" for f in top_feats]
        segment_card(
            persona_names.get(c, f"Segment {c}"),
            int(cluster_sizes[c]),
            cluster_sizes[c] / cluster_sizes.sum() * 100,
            top_desc,
            color_idx=i
        )

st.markdown("")

# ── Radar Charts ─────────────────────────────────────────────────────
section_header("Segment Radar Profiles", "Normalized feature means per cluster (0=min, 1=max across clusters)")

# Normalize to 0-1 range across clusters for radar
radar_features = [c for c in selected_features if not c.endswith("_LOG")][:8]
if len(radar_features) >= 3:
    normalized = cluster_means[radar_features].copy()
    for col in normalized.columns:
        rng = normalized[col].max() - normalized[col].min()
        if rng > 0:
            normalized[col] = (normalized[col] - normalized[col].min()) / rng
        else:
            normalized[col] = 0.5

    values_dict = {persona_names.get(c, f"Seg {c}"): normalized.loc[c].values
                   for c in normalized.index}
    fig = branded_radar(radar_features, values_dict, "Segment Feature Profiles")
    st.plotly_chart(fig, use_container_width=True)

# ── Feature Comparison Table ─────────────────────────────────────────
section_header("Feature Comparison Table")
display_means = cluster_means.copy()
display_means.index = [persona_names.get(c, f"Segment {c}") for c in display_means.index]
st.dataframe(display_means.round(4).style.background_gradient(cmap="Greens", axis=0),
             use_container_width=True)

# ── Demographic Breakdown ────────────────────────────────────────────
section_header("Demographic Breakdown by Segment")

tab1, tab2, tab3 = st.tabs(["Account Type", "World Region", "Age Group"])

with tab1:
    cross = pd.crosstab(df_work["cluster"], df_work["ACCOUNT_TYPE"], normalize="index") * 100
    cross.index = [persona_names.get(c, f"Seg {c}") for c in cross.index]
    fig = px.bar(cross, barmode="stack", color_discrete_sequence=CHART_PALETTE,
                 title="Account Type Distribution by Segment (%)")
    fig.update_layout(height=350, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      yaxis_title="% of Segment")
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    cross = pd.crosstab(df_work["cluster"], df_work["USER_WORLD_REGION"], normalize="index") * 100
    cross.index = [persona_names.get(c, f"Seg {c}") for c in cross.index]
    fig = px.bar(cross, barmode="stack", color_discrete_sequence=CHART_PALETTE,
                 title="World Region Distribution by Segment (%)")
    fig.update_layout(height=350, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      yaxis_title="% of Segment")
    st.plotly_chart(fig, use_container_width=True)

with tab3:
    df_aged = add_age_group(df_work)
    cross = pd.crosstab(df_aged["cluster"], df_aged["AGE_GROUP"], normalize="index") * 100
    cross.index = [persona_names.get(c, f"Seg {c}") for c in cross.index]
    fig = px.bar(cross, barmode="stack", color_discrete_sequence=CHART_PALETTE,
                 title="Age Group Distribution by Segment (%)")
    fig.update_layout(height=350, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      yaxis_title="% of Segment")
    st.plotly_chart(fig, use_container_width=True)

# ── Statistical Significance ─────────────────────────────────────────
section_header("Statistical Significance", "Kruskal-Wallis test for feature differences across segments")

from scipy.stats import kruskal

sig_results = []
for feat in selected_features[:12]:
    groups = [df_work.loc[df_work["cluster"] == c, feat].dropna().values
              for c in sorted(df_work["cluster"].unique())
              if len(df_work.loc[df_work["cluster"] == c, feat].dropna()) > 0]
    if len(groups) >= 2 and all(len(g) > 0 for g in groups):
        try:
            stat, p = kruskal(*groups)
            sig_results.append({
                "Feature": feat,
                "H-statistic": round(stat, 2),
                "p-value": f"{p:.2e}",
                "Significant": "Yes" if p < 0.001 else ("Marginal" if p < 0.05 else "No"),
            })
        except Exception:
            pass

if sig_results:
    sig_df = pd.DataFrame(sig_results)
    st.dataframe(sig_df, use_container_width=True)
    n_sig = sum(1 for r in sig_results if r["Significant"] == "Yes")
    insight_box(f"<strong>{n_sig}/{len(sig_results)}</strong> features show statistically "
                f"significant differences across segments (p < 0.001, Kruskal-Wallis).")
