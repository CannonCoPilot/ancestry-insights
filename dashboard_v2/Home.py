"""FamilySearch User Segmentation — Analysis Dashboard (v2)"""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from components.branding import apply_branding, metric_card, COLORS

st.set_page_config(
    page_title="FamilySearch User Segmentation",
    page_icon="\U0001F333",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_branding()

# ── Sidebar is rendered automatically by apply_branding() ────────────

# ── Header ───────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; padding: 0.5rem 0 0.8rem 0;">
    <h1 style="font-size:2.4rem; margin-bottom:0.3rem;">FamilySearch User Segmentation Analysis</h1>
    <p style="font-size:1.1rem; color:#6b8f6b; font-family:'Libre Baskerville',serif;">
        Machine Learning Approaches to Understanding New User Engagement Patterns
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ── Dataset Summary ──────────────────────────────────────────────────
st.markdown("## Dataset at a Glance")
cols = st.columns(5)
with cols[0]:
    metric_card("Total Users", "7.6M")
with cols[1]:
    metric_card("Features", "33")
with cols[2]:
    metric_card("Time Span", "12 months")
with cols[3]:
    metric_card("Account Types", "2")
with cols[4]:
    metric_card("World Regions", "7")

st.markdown("")

# ── Project Overview ─────────────────────────────────────────────────
st.markdown("## Project Overview")

col1, col2 = st.columns(2)
with col1:
    st.markdown("""
    This analysis examines **7.6 million newly created FamilySearch user accounts**
    (all created within the past year) to identify meaningful behavioral segments
    through unsupervised machine learning.

    **Objective**: Discover distinct user archetypes based on early engagement
    behaviors, demographics, and contribution patterns — and translate these
    findings into actionable business recommendations.

    **Approach**: Tenure-normalized feature engineering, multiple clustering
    algorithms (K-Means, HDBSCAN, Gaussian Mixture Models), and rigorous
    validation using silhouette analysis, information criteria, and statistical
    significance testing.
    """)

with col2:
    st.markdown("""
    ### Navigation Guide

    | Page | Purpose |
    |------|---------|
    | **Workflow** | Analysis plan & methodology |
    | **Data Quality** | Missing data, biases, health report |
    | **EDA** | Interactive distributions & correlations |
    | **Feature Lab** | Feature engineering explorer |
    | **Clustering Lab** | Interactive ML model builder |
    | **Segment Profiles** | Cluster interpretation & profiling |
    | **Insights** | Business recommendations |
    | **About** | Author & methodology credits |
    """)

st.markdown("---")

# ── Key Findings Preview ─────────────────────────────────────────────
st.markdown("## Key Findings Preview")
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("""
    <div class="insight-box">
    <strong>64% One-and-Done</strong><br>
    Nearly two-thirds of new users log in once or never.
    The largest opportunity lies in converting single-session
    users into casual contributors.
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown("""
    <div class="insight-box">
    <strong>Distinct Activity Modes</strong><br>
    Tree building, indexing (Get Involved), and record editing
    are largely independent activities &mdash; users specialize
    rather than diversify.
    </div>
    """, unsafe_allow_html=True)
with col3:
    st.markdown("""
    <div class="insight-box">
    <strong>Age Drives Engagement</strong><br>
    Users 56&ndash;65 log in 2&times; as often as 18&ndash;25.
    The 13&ndash;17 youth cohort (12.5%) shows distinct patterns
    likely tied to church programs.
    </div>
    """, unsafe_allow_html=True)

st.markdown("")
st.markdown("""
<div style="text-align:center; padding:2rem; color:#6b8f6b;">
    <em>Use the sidebar to navigate through the analysis sections.</em>
</div>
""", unsafe_allow_html=True)
