"""EDA — Interactive Exploratory Data Analysis"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import pandas as pd
from components.branding import apply_branding, section_header, COLORS, CHART_PALETTE, sidebar_tab
from components.charts import branded_histogram, branded_heatmap, branded_bar
from src.data_loader import load_for_dashboard, ACTIVITY_COUNT_COLS, NAME_COLS, DEMOGRAPHIC_COLS

st.set_page_config(page_title="EDA | FamilySearch", page_icon="\U0001F333", layout="wide")
apply_branding()

st.title("Exploratory Data Analysis")
st.markdown("*Interactive exploration of engagement metrics, demographics, and behavioral patterns*")
st.markdown("---")

active_tab = sidebar_tab()
sample_size = 250_000
if active_tab == "controls":
    sample_size = st.sidebar.selectbox("Sample Size", [100_000, 250_000, 500_000],
                                        index=1, format_func=lambda x: f"{x:,}")
df = load_for_dashboard(n=sample_size)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Distributions", "Login Analysis", "Heavy Tails", "Correlations", "Time Patterns"
])

# ── Tab 1: Distributions ─────────────────────────────────────────────
with tab1:
    section_header("Activity Distributions", "Select a metric to explore its distribution")
    numeric_cols = ACTIVITY_COUNT_COLS + NAME_COLS
    metric = st.selectbox("Select Metric", [c for c in numeric_cols if c in df.columns])
    vals = df[metric].dropna()

    col1, col2 = st.columns(2)
    with col1:
        fig = branded_histogram(vals, f"{metric} — Raw Distribution", nbins=80)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = branded_histogram(vals, f"{metric} — Log1p Distribution", nbins=80, log=True)
        st.plotly_chart(fig, use_container_width=True)

    stats = vals.describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.95, 0.99]).round(2)
    st.dataframe(stats.to_frame().T, use_container_width=True)

    # Box plot by demographic
    demo_col = st.selectbox("Compare by", ["ACCOUNT_TYPE", "USER_WORLD_REGION", "AGE_GROUP"],
                             key="dist_demo")
    if demo_col == "AGE_GROUP":
        from src.features.engineering import add_age_group
        plot_df = add_age_group(df)
    else:
        plot_df = df
    fig = px.box(plot_df, x=demo_col, y=metric, color=demo_col,
                 color_discrete_sequence=CHART_PALETTE,
                 title=f"{metric} by {demo_col}")
    fig.update_layout(height=400, showlegend=False,
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      yaxis_type="log" if vals.max() > 100 else "linear")
    st.plotly_chart(fig, use_container_width=True)

# ── Tab 2: Login Analysis ────────────────────────────────────────────
with tab2:
    section_header("Login Frequency Analysis")
    active = df.dropna(subset=["DAYS_LOGGING_IN"]).copy()
    bins = [0, 0.5, 1.5, 5.5, 30.5, 9999]
    labels = ["0 logins", "1 login", "2-5 logins", "6-30 logins", "31+ logins"]
    active["login_tier"] = pd.cut(active["DAYS_LOGGING_IN"], bins=bins, labels=labels)
    tier_counts = active["login_tier"].value_counts().reindex(labels)

    col1, col2 = st.columns(2)
    with col1:
        fig = px.pie(values=tier_counts.values, names=tier_counts.index,
                     title="Login Frequency Tiers",
                     color_discrete_sequence=CHART_PALETTE)
        fig.update_layout(height=400, plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.dataframe(pd.DataFrame({
            "Tier": labels,
            "Count": tier_counts.values,
            "Pct": (tier_counts.values / tier_counts.values.sum() * 100).round(1)
        }), use_container_width=True)

        st.markdown("""
        <div class="insight-box">
        <strong>Key Finding</strong>: ~64% of users log in 0&ndash;1 times.
        The engagement funnel has massive drop-off between account creation
        and sustained usage.
        </div>
        """, unsafe_allow_html=True)

# ── Tab 3: Heavy Tails ───────────────────────────────────────────────
with tab3:
    section_header("Heavy Tail & Concentration Analysis",
                   "How much activity do the top percentiles contribute?")
    cols_to_show = ["DAYS_LOGGING_IN", "TREE_EDITS", "SOURCES_ADDED",
                    "TOTAL_NAMES_ADDED", "GET_INVOLVED_ITEMS_REVIEWED"]
    available_cols = [c for c in cols_to_show if c in df.columns]
    percentiles = [0.5, 0.75, 0.9, 0.95, 0.99, 1.0]
    pct_data = {}
    for c in available_cols:
        vals = df[c].dropna()
        pct_data[c] = [vals.quantile(p) for p in percentiles]
    pct_df = pd.DataFrame(pct_data, index=[f"p{int(p*100)}" for p in percentiles])
    st.dataframe(pct_df.round(1), use_container_width=True)

    st.markdown("#### Top 1% Concentration")
    concentration_data = []
    for c in available_cols:
        vals = df[c].dropna()
        p99 = vals.quantile(0.99)
        top1_sum = vals[vals >= p99].sum()
        total = vals.sum()
        if total > 0:
            concentration_data.append({"Metric": c, "Top 1% Share": f"{top1_sum/total*100:.1f}%"})
    st.dataframe(pd.DataFrame(concentration_data), use_container_width=True)

# ── Tab 4: Correlations ──────────────────────────────────────────────
with tab4:
    section_header("Feature Correlations")
    corr_cols = [c for c in ACTIVITY_COUNT_COLS + NAME_COLS if c in df.columns]
    corr_matrix = df[corr_cols].corr()
    fig = branded_heatmap(corr_matrix.values, corr_cols, "Activity Metric Correlations")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("""
    <div class="insight-box">
    <strong>Distinct activity modes</strong>: TREE_EDITS, SOURCES_ADDED, and TOTAL_NAMES_ADDED
    are highly correlated (r>0.5) &mdash; they represent "tree building." GET_INVOLVED_ITEMS_REVIEWED
    is nearly independent (r&lt;0.08) &mdash; a separate "indexing" activity mode.
    </div>
    """, unsafe_allow_html=True)

# ── Tab 5: Time Patterns ─────────────────────────────────────────────
with tab5:
    section_header("Account Creation Patterns")
    if "ACCOUNT_CREATE_DATE" in df.columns:
        daily = df.groupby(df["ACCOUNT_CREATE_DATE"].dt.to_period("W")).size()
        fig = go.Figure(go.Scatter(x=[str(p) for p in daily.index], y=daily.values,
                                   mode="lines", line=dict(color=COLORS["primary"], width=1.5),
                                   fill="tozeroy", fillcolor="rgba(59,133,32,0.1)"))
        fig.update_layout(title="Weekly Account Creations", xaxis_title="Week",
                          yaxis_title="New Accounts",
                          height=400, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig, use_container_width=True)
