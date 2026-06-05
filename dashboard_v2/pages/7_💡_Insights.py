"""Insights — Business Recommendations & Audience-Adaptive Presentation"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
from components.branding import apply_branding, section_header, metric_card, insight_box, COLORS, sidebar_tab

st.set_page_config(page_title="Insights | FamilySearch", page_icon="\U0001F333", layout="wide")
apply_branding()

st.title("Insights & Recommendations")
st.markdown("*Translating analytical findings into actionable business strategy*")
st.markdown("---")

# ── Sidebar Controls ─────────────────────────────────────────────────
active_tab = sidebar_tab()
audience = "Business Leader"
if active_tab == "controls":
    audience = st.sidebar.radio("Audience Mode", ["Business Leader", "Technical", "Non-Technical"],
                                 help="Adjusts detail level and language")

# ── Executive Summary ────────────────────────────────────────────────
section_header("Executive Summary")

if audience == "Non-Technical":
    st.markdown("""
    We analyzed **7.6 million new FamilySearch accounts** to understand how different types
    of users behave in their first year. Using machine learning, we grouped users into
    distinct segments based on what they do (or don't do) on the platform.

    **The big picture**: Most new users try FamilySearch once and don't come back. But within
    the active users, there are clear groups with different needs and potential.
    """)
elif audience == "Business Leader":
    st.markdown("""
    Analysis of 7.6M new accounts reveals a **severe activation bottleneck**: 64% of users
    log in once or never. The remaining 36% segment into distinct behavioral archetypes
    with differentiated engagement, contribution, and retention potential.

    **Strategic implication**: The largest ROI opportunity is activation — converting
    single-session visitors into repeat users — not optimizing for power users.
    """)
else:
    st.markdown("""
    Unsupervised segmentation (K-Means, k=5, silhouette=0.38) on 250K stratified sample
    with 15 tenure-normalized features reveals 5 distinct behavioral clusters. All inter-cluster
    feature differences are statistically significant (Kruskal-Wallis, p < 0.001).
    Clusters validated via bootstrap stability and compared against HDBSCAN/GMM alternatives.
    """)

# ── Key Findings ─────────────────────────────────────────────────────
section_header("Key Findings")

col1, col2, col3, col4 = st.columns(4)
with col1: metric_card("One-and-Done Rate", "64%", delta="Largest segment")
with col2: metric_card("Multi-Activity Users", "8.6%", delta="High-value minority")
with col3: metric_card("Power Contributors", "~2%", delta="Disproportionate impact")
with col4: metric_card("Member Lift", "3x", delta="vs Public accounts")

st.markdown("")

findings = [
    {
        "title": "The Activation Cliff",
        "business": "64% of new users log in once or never. Every percentage point improvement in Day-1 retention represents ~76,000 additional engaged users.",
        "technical": "Login distribution is bimodal: a dominant single-login peak and a long tail. The activation cliff between login 1 and login 2 is the steepest drop in the funnel.",
        "simple": "Most people create an account and never come back. Getting people to come back just one more time would make a huge difference.",
    },
    {
        "title": "Three Independent Activity Modes",
        "business": "Users specialize: tree builders, indexers, and record editors are largely separate populations. Cross-selling between modes could unlock new engagement.",
        "technical": "Factor analysis reveals 3 orthogonal activity dimensions: tree-building (TREE_EDITS + SOURCES + NAMES, r>0.5), indexing (GET_INVOLVED, r<0.08 with others), and record editing. These are structurally independent behaviors.",
        "simple": "People tend to do ONE thing on FamilySearch, not everything. Tree builders don't usually do indexing, and vice versa.",
    },
    {
        "title": "Age-Driven Engagement Gradient",
        "business": "Users 56-65 engage 2x more than 18-25. The 13-17 cohort (12.5%) shows church-program-driven patterns distinct from organic sign-ups. Tailored onboarding by age could improve activation.",
        "technical": "USER_CURRENT_AGE correlates with LOGINS_PER_WEEK (r=0.18) and N_ACTIVITY_TYPES (r=0.12). The 13-17 cohort has high tree edit rates but low login consistency — burst activity during youth programs.",
        "simple": "Older users are much more engaged than younger ones. Teenagers seem to use the site for school or church projects and then stop.",
    },
    {
        "title": "Members Are Super-Users",
        "business": "The 3% 'Member' accounts (likely LDS church members) show 3x login rates, 2x tree edits, and 37x Get Involved participation. Understanding their motivations could inform broader product strategy.",
        "technical": "ACCOUNT_TYPE='Member' has statistically significant uplift across all engagement metrics (Mann-Whitney U, p<0.001). Effect size (Cohen's d) ranges from 0.4 (tree edits) to 1.2 (Get Involved).",
        "simple": "Church members use FamilySearch way more than other users. They're the most active group by far.",
    },
    {
        "title": "Africa: Small but Mighty",
        "business": "The Africa region has the highest average tree edits (41) and sources added (21) despite being the smallest user group. This suggests high-intent users in an underserved market.",
        "technical": "Africa region (n~2% of dataset) shows mean TREE_EDITS=41 vs global mean=17. Likely a selection effect (only highly motivated users in Africa create accounts), but worth investigating for targeted growth.",
        "simple": "Users from Africa, though few in number, are some of the most active on the platform.",
    },
]

for f in findings:
    with st.expander(f"**{f['title']}**", expanded=True):
        key = {"Business Leader": "business", "Technical": "technical", "Non-Technical": "simple"}[audience]
        st.markdown(f[key])

# ── Recommendations ──────────────────────────────────────────────────
section_header("Strategic Recommendations")

recs = [
    ("Activation Campaign", "HIGH",
     "Target the 64% one-and-done users with personalized re-engagement within 48 hours of first login. "
     "Surface quick-win activities (e.g., 'See what we found about your surname') to demonstrate value before churn."),
    ("Age-Adaptive Onboarding", "HIGH",
     "Create distinct onboarding flows for youth (13-17, guided projects), young adults (18-35, mobile-first), "
     "and mature users (55+, desktop, deeper genealogy tools). Current one-size-fits-all approach underserves all groups."),
    ("Cross-Mode Discovery", "MEDIUM",
     "Users who build trees rarely discover Get Involved (indexing). Surface cross-activity recommendations: "
     "'You've added 50 names — want to help others find theirs?' Potential to 3x multi-activity users."),
    ("Member Playbook Export", "MEDIUM",
     "Study what makes Member accounts 3x more engaged. Identify transferable practices (community, "
     "goal-setting, guided curriculum) that could be adapted for Public accounts."),
    ("Africa Market Investment", "LOW",
     "Small but highly engaged user base suggests product-market fit with unmet demand. "
     "Explore localization, offline access, and community partnerships in key African markets."),
]

for title, priority, desc in recs:
    color = {"HIGH": COLORS["primary"], "MEDIUM": COLORS["warning"], "LOW": COLORS["info"]}[priority]
    st.markdown(f"""
    <div style="background:white;border:1px solid #d4e6cd;border-left:5px solid {color};
                border-radius:6px;padding:1rem;margin:0.5rem 0;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <strong style="font-size:1.05rem;">{title}</strong>
            <span style="background:{color};color:white;padding:2px 10px;border-radius:12px;
                         font-size:0.75rem;font-weight:600;">{priority}</span>
        </div>
        <p style="margin:0.5rem 0 0 0;color:#2c3e2d;font-size:0.9rem;">{desc}</p>
    </div>""", unsafe_allow_html=True)

# ── Downloadable Report ──────────────────────────────────────────────
section_header("Export Report")

report_md = f"""# FamilySearch User Segmentation — Key Findings

## Executive Summary
Analysis of 7.6M new user accounts reveals a severe activation bottleneck (64% one-and-done)
with distinct behavioral segments among active users.

## Key Findings
{"".join(f"### {f['title']}{chr(10)}{f['business']}{chr(10)}{chr(10)}" for f in findings)}

## Recommendations
{"".join(f"### [{p}] {t}{chr(10)}{d}{chr(10)}{chr(10)}" for t, p, d in recs)}

---
*Generated from FamilySearch User Segmentation Dashboard*
"""

st.download_button("Download Report (Markdown)", report_md,
                   file_name="familysearch_insights_report.md", mime="text/markdown")
