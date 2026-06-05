"""About — Author Information & Methodology Credits"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from components.branding import apply_branding, section_header, fisher_quote, COLORS

st.set_page_config(page_title="About | FamilySearch", page_icon="\U0001F333", layout="wide")
apply_branding()

st.title("About This Analysis")
st.markdown("---")

# ── Fisher Quote (prominent) ─────────────────────────────────────────
fisher_quote()

st.markdown("")

# ── Author ───────────────────────────────────────────────────────────
section_header("Author")
col1, col2 = st.columns([1, 3])
with col1:
    st.markdown("""
    <div style="background:#e8f0e3;border-radius:50%;width:120px;height:120px;
                display:flex;align-items:center;justify-content:center;
                font-size:3rem;color:#3b8520;margin:0 auto;">
        NC
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown("""
    ### Nathaniel Cannon

    **Data Scientist & ML Engineer**

    [GitHub: CannonCoPilot](https://github.com/CannonCoPilot/familysearch-user-segmentation)

    *LinkedIn, resume highlights, and additional portfolio details can be added here.*
    """)

st.markdown("---")

# ── Methodology ──────────────────────────────────────────────────────
section_header("Methodology & Approach")

st.markdown("""
This analysis follows a structured workflow designed for reproducibility, rigor, and clarity:

| Phase | Description | Key Decisions |
|-------|-------------|---------------|
| **Data Ingestion** | 7.6M-row CSV -> stratified 250K sample (Parquet cache) | Deterministic sampling, seed=42 |
| **Data Quality** | Missing data audit, outlier treatment, bias assessment | 10% null block imputed as zero; ages capped 0-110 |
| **Feature Engineering** | 20 features: tenure-normalized rates, activity flags, engagement depth | Log1p transforms for skewed counts; per-week normalization |
| **Scaling** | StandardScaler (default), RobustScaler, MinMaxScaler options | User-selectable in Clustering Lab |
| **Clustering** | K-Means, HDBSCAN, Gaussian Mixture Models | Multiple algorithms for comparison |
| **Validation** | Silhouette, Calinski-Harabasz, Davies-Bouldin, Kruskal-Wallis significance | Elbow analysis for k selection |
| **Interpretation** | Radar profiles, demographic breakdowns, auto-generated personas | Statistical significance testing |
| **Communication** | Audience-adaptive presentation (Technical / Business / Non-Technical) | Downloadable Markdown reports |
""")

# ── Technology Stack ─────────────────────────────────────────────────
section_header("Technology Stack")

col1, col2 = st.columns(2)
with col1:
    st.markdown("""
    #### Data & ML
    - **Python 3.12+** — Core language
    - **pandas** — Data manipulation
    - **NumPy** — Numerical computing
    - **scikit-learn** — Clustering (KMeans, GMM), scaling, evaluation
    - **HDBSCAN** — Density-based clustering
    - **UMAP** — Non-linear dimensionality reduction
    - **SciPy** — Statistical tests (Kruskal-Wallis)
    """)
with col2:
    st.markdown("""
    #### Visualization & UI
    - **Streamlit** — Interactive dashboard framework
    - **Plotly** — Interactive, publication-quality charts
    - **Custom CSS** — FamilySearch-inspired branding
    - **Google Fonts** — Libre Baskerville (headings) + Source Sans 3 (body)
    """)

# ── Design Philosophy ────────────────────────────────────────────────
section_header("Design Philosophy")

st.markdown("""
This dashboard was designed with three audiences in mind:

1. **Technical reviewers** who want to inspect methodology, evaluate statistical rigor,
   and understand algorithmic choices.

2. **Business leaders** who need concise, actionable insights translated into
   strategic recommendations with clear prioritization.

3. **Non-technical stakeholders** who benefit from plain-language explanations,
   visual summaries, and intuitive navigation.

The audience-adaptive toggle on the Insights page adjusts language, detail level,
and emphasis accordingly. The underlying analysis remains identical — only the
presentation changes.
""")

st.markdown("---")

# ── Repository ───────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; padding:1.5rem; background:#e8f0e3; border-radius:8px;">
    <p style="font-size:1.1rem; color:#1a4314;">
        <strong>Source Code</strong><br>
        <a href="https://github.com/CannonCoPilot/familysearch-user-segmentation"
           style="color:#3b8520;">
            github.com/CannonCoPilot/familysearch-user-segmentation
        </a>
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("")
st.markdown("""
<div style="text-align:center; color:#6b8f6b; font-style:italic; padding:1rem;">
    Built with care for the FamilySearch Data Science team.
</div>
""", unsafe_allow_html=True)
