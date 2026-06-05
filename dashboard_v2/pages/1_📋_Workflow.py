"""Workflow — Analysis Plan & Methodology"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from components.branding import apply_branding, section_header, insight_box

st.set_page_config(page_title="Workflow | FamilySearch Segmentation", page_icon="\U0001F333", layout="wide")
apply_branding()

st.title("Analysis Workflow & Methodology")
st.markdown("*A structured approach to unsupervised user segmentation*")
st.markdown("---")

# ── Goal Interpretation ──────────────────────────────────────────────
section_header("Goal Interpretation", "What we are solving and why")
st.markdown("""
**Primary objective**: Build an unsupervised machine-learning segmentation model that groups
FamilySearch's newly created user accounts into meaningful behavioral archetypes.

**This is NOT** a prediction task (no target variable). It is a **descriptive clustering** problem
whose value lies in revealing the natural structure of user behavior to inform product strategy.

**Key constraint**: The dataset represents accounts created within a single year, meaning all users
have <=12 months of tenure. Activity metrics must be normalized by account age to avoid
clustering by tenure rather than behavior.
""")

# ── Research Questions ───────────────────────────────────────────────
section_header("Research Questions", "Ordered by priority")

questions = [
    ("What does the engagement funnel look like?",
     "Account creation -> first login -> first contribution -> sustained engagement. Where are the biggest drop-offs?"),
    ("Are there natural clusters in user behavior?",
     "Do users fall into distinct groups based on what they do (tree edits, sources, memories, indexing)?"),
    ("How do demographics relate to engagement?",
     "Do age groups, regions, or account types predict engagement patterns?"),
    ("What distinguishes power users from casual visitors?",
     "What behavioral signals in the first weeks predict long-term contribution?"),
    ("Are there underserved segments with growth potential?",
     "Users who show intent (created account, logged in) but don't contribute—what's blocking them?"),
]

for i, (q, detail) in enumerate(questions, 1):
    with st.expander(f"Q{i}: {q}"):
        st.markdown(detail)

# ── Workflow Diagram ─────────────────────────────────────────────────
section_header("Analysis Workflow")
st.markdown("""
```
 DATA INGESTION          FEATURE ENGINEERING        MODELING              INSIGHTS
 ┌──────────┐           ┌─────────────────┐       ┌──────────────┐      ┌───────────────┐
 │ 7.6M CSV │ ──sample──│ Tenure-normalize │──────│ K-Means      │─────│ Segment       │
 │ 33 cols   │     │     │ Activity flags   │      │ HDBSCAN      │     │ Profiles      │
 │ 12 months │     │     │ Engagement depth │      │ GMM          │     │ Radar charts  │
 └──────────┘     │     │ Log transforms   │      │ Elbow/Silh.  │     │ Significance  │
                  │     │ Demographic bins │      └──────────────┘     │ Recommendations│
            ┌─────┴────┐ └─────────────────┘                           └───────────────┘
            │ 250K-500K│
            │ stratified│          ┌──────────────────────────────────┐
            │ sample   │          │ DATA QUALITY                     │
            └──────────┘          │ Missing data analysis            │
                                  │ Outlier detection & treatment    │
                                  │ Bias assessment                  │
                                  └──────────────────────────────────┘
```
""")

# ── Assumptions ──────────────────────────────────────────────────────
section_header("Assumptions")
assumptions = [
    "**Null activity = zero activity**: If a user's login/edit/source count is null, they simply never performed that action.",
    "**Account age is a confound**: Older accounts naturally accumulate more activity. All features are normalized by tenure (rates per week).",
    "**Province/City are unusable**: 97%+ 'Unknown' — these columns are excluded from analysis.",
    "**10% null block is systematic**: The ~10% of rows with ALL activity metrics null likely represent an incomplete data pipeline cohort, not random missingness.",
    "**Name columns are conditional**: The 48% null rate in name columns reflects users who never added names, not missing data.",
]
for a in assumptions:
    st.markdown(f"- {a}")

# ── Risks & Edge Cases ───────────────────────────────────────────────
section_header("Risks & Edge Cases")
col1, col2 = st.columns(2)
with col1:
    st.markdown("#### Data Quality Risks")
    st.markdown("""
    - **Extreme right skew**: Top 1% dominates totals. Log transforms essential.
    - **Sparse activities**: Sources (8%), Memories (2%), Get Involved (0.6%) — may need binary treatment.
    - **Login-before-creation anomaly**: 21% have first login before account creation (timezone artifact).
    """)
with col2:
    st.markdown("#### Modeling Risks")
    st.markdown("""
    - **Dominant inactive segment**: ~64% single-login users may overwhelm clustering.
    - **Curse of dimensionality**: 15-20 features with 250K+ samples — PCA/feature selection important.
    - **Cluster stability**: Results may vary with random seeds — bootstrap validation needed.
    """)

# ── Reproducibility ──────────────────────────────────────────────────
section_header("Reproducibility")
st.markdown("""
| Element | Implementation |
|---------|---------------|
| **Random seeds** | All algorithms seeded (`random_state=42`) |
| **Sampling** | Deterministic 250K sample cached as Parquet |
| **Code modularity** | `src/` package: `data_loader`, `features/engineering`, `models/clustering` |
| **Environment** | `requirements.txt` with pinned versions; Python 3.12+ |
| **Version control** | Git repository with tagged releases |
| **Interactive dashboard** | Streamlit app for exploratory analysis |
""")
