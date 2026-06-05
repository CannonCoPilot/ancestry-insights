"""Data Quality — Health Report, Missing Data, Biases, Sample Preview"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from components.branding import apply_branding, section_header, metric_card, warning_box, insight_box, sidebar_tab
from src.data_loader import (
    load_for_dashboard, get_data_health_report,
    ACTIVITY_COUNT_COLS, NAME_COLS, DATE_COLS,
)

st.set_page_config(page_title="Data Quality | FamilySearch", page_icon="\U0001F333", layout="wide")
apply_branding()

st.title("Data Quality & Health Report")
st.markdown("*Assessing completeness, consistency, and potential biases in the dataset*")
st.markdown("---")

# ── Sidebar Controls ─────────────────────────────────────────────────
active_tab = sidebar_tab()
sample_size = 250_000
if active_tab == "controls":
    sample_size = st.sidebar.selectbox("Sample Size", [100_000, 250_000, 500_000],
                                        index=1, format_func=lambda x: f"{x:,}")
df = load_for_dashboard(n=sample_size)

# ── Column inventory ─────────────────────────────────────────────────
ID_COLS = ["USER_ID"]
GEO_COLS = ["COUNTRY", "PROVINCE", "CITY", "USER_WORLD_REGION", "USER_AREA_NAME"]
ALL_COLS = list(df.columns)

def _col_group(col: str) -> str:
    if col in ID_COLS:
        return "Identity"
    if col in ["ACCOUNT_CREATE_DATE", "ACCOUNT_TYPE"]:
        return "Account"
    if col == "USER_CURRENT_AGE":
        return "Demographics"
    if col in GEO_COLS:
        return "Geography"
    if col in DATE_COLS:
        return "Date Milestones"
    if col in ACTIVITY_COUNT_COLS:
        return "Activity Counts"
    if col in NAME_COLS:
        return "Name Columns"
    return "Other"

# ── Summary Cards ────────────────────────────────────────────────────
section_header("Dataset Overview")
cols = st.columns(6)
with cols[0]: metric_card("Rows", f"{len(df):,}")
with cols[1]: metric_card("Columns", str(df.shape[1]))
with cols[2]:
    pct_complete = (1 - df.isnull().mean().mean()) * 100
    metric_card("Completeness", f"{pct_complete:.1f}%")
with cols[3]:
    n_active = (df["DAYS_LOGGING_IN"].fillna(0) > 0).sum()
    metric_card("Active Users", f"{n_active:,}")
with cols[4]:
    metric_card("Activity Rate", f"{n_active/len(df)*100:.1f}%")
with cols[5]:
    n_null_block = df["DAYS_LOGGING_IN"].isna().sum()
    metric_card("MNAR Block", f"{n_null_block/len(df)*100:.1f}%")

st.markdown("")

# ── Health Report Table ──────────────────────────────────────────────
section_header("Column-by-Column Health Report", f"All {len(ALL_COLS)} columns assessed")

health = get_data_health_report(df)
health.insert(1, "group", health["column"].map(_col_group))
health = health.sort_values(["group", "column"]).reset_index(drop=True)

# Highlight rows with quality concerns
def _highlight_health(row):
    styles = [""] * len(row)
    if row.get("pct_missing", 0) > 90:
        styles = ["background-color: rgba(192,57,43,0.15)"] * len(row)
    elif row.get("pct_missing", 0) > 40:
        styles = ["background-color: rgba(212,168,67,0.15)"] * len(row)
    return styles

# Format float columns to 2 decimal places
float_fmt_cols = ["pct_missing", "pct_zeros", "mean", "std", "skewness"]
fmt_dict = {c: "{:.2f}" for c in float_fmt_cols if c in health.columns}

styled_health = (
    health.style
    .apply(_highlight_health, axis=1)
    .format(fmt_dict, na_rep="")
)

st.dataframe(
    styled_health,
    use_container_width=True, height=600,
    column_config={"column": st.column_config.TextColumn("column", pinned=True)},
)
st.caption("Red highlight: >90% missing/Unknown. Yellow: >40% missing. All 33 raw columns included.")

# ── Missing Data Visualization ───────────────────────────────────────
section_header("Missing Data Analysis")
tab1, tab2, tab3 = st.tabs(["By Column", "MNAR Block Analysis", "Co-occurrence Heatmap"])

with tab1:
    missing_pct = df.isnull().mean().sort_values(ascending=True) * 100
    colors = ["#c0392b" if v > 90 else "#d4a843" if v > 40 else "#3b8520" for v in missing_pct.values]
    fig = go.Figure(go.Bar(
        x=missing_pct.values, y=missing_pct.index, orientation="h",
        marker_color=colors,
        text=[f"{v:.1f}%" for v in missing_pct.values],
        textposition="outside",
    ))
    fig.update_layout(
        height=700, showlegend=False,
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        xaxis_title="% Missing", yaxis_title="",
        title="Missing Data by Column (all 33 columns)",
    )
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.markdown("#### MNAR (Missing Not At Random) Activity Block")
    st.markdown("""
    **10.2% of users** have ALL 11 activity count columns null simultaneously — a block-or-nothing
    pattern indicating a systematic data pipeline issue, not random missingness.
    """)

    # Characterize the MNAR block
    is_null_block = df["DAYS_LOGGING_IN"].isna()
    null_block = df[is_null_block]
    non_null = df[~is_null_block]

    mnar_cols = st.columns(3)
    with mnar_cols[0]:
        metric_card("Null Block Size", f"{len(null_block):,} ({len(null_block)/len(df)*100:.1f}%)")
    with mnar_cols[1]:
        pct_public = (null_block["ACCOUNT_TYPE"] == "Public").mean() * 100
        metric_card("% Public (null block)", f"{pct_public:.1f}%")
    with mnar_cols[2]:
        has_login = null_block["EARLIEST_LOGIN_DATE"].notna().mean() * 100
        metric_card("Has Login Date", f"{has_login:.1f}%")

    # Compare demographics
    st.markdown("##### Null Block vs Non-Null Demographics")
    compare_data = []
    for region in df["USER_WORLD_REGION"].value_counts().index:
        compare_data.append({
            "Region": region,
            "Null Block %": (null_block["USER_WORLD_REGION"] == region).mean() * 100,
            "Non-Null %": (non_null["USER_WORLD_REGION"] == region).mean() * 100,
        })
    compare_df = pd.DataFrame(compare_data).round(1)
    st.dataframe(compare_df, use_container_width=True, hide_index=True)

    insight_box(
        "The MNAR block is <strong>not random</strong>: 99.9% Public accounts, only 1.3% have login dates, "
        "and disproportionately European (vs baseline). These are accounts the data pipeline never captured. "
        "Treatment: flag as <code>is_null_activity_block</code> and <strong>exclude</strong> from clustering "
        "(not impute)."
    )

with tab3:
    st.markdown("#### Null Co-occurrence Across All Activity + Name Columns")
    cooc_cols = ACTIVITY_COUNT_COLS + NAME_COLS
    cooc_present = [c for c in cooc_cols if c in df.columns]
    null_corr = df[cooc_present].isnull().corr()

    fig = px.imshow(
        null_corr, text_auto=".2f",
        color_continuous_scale=["#e8f0e3", "#3b8520"],
        title=f"Null Co-occurrence ({len(cooc_present)} columns)",
        aspect="auto",
    )
    fig.update_layout(height=600, plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        "Activity counts (11 cols) show r=1.0 null co-occurrence — the MNAR block. "
        "Name columns (6 cols) have a separate ~48% null block (users who never added names)."
    )

# ── Key Quality Observations ─────────────────────────────────────────
section_header("Key Quality Observations")
col1, col2 = st.columns(2)
with col1:
    warning_box(
        f"<strong>10.2% MNAR activity block</strong>: {n_null_block:,} "
        f"users have ALL activity metrics null. Treatment: exclude from clustering (pipeline artifact)."
    )
    warning_box(
        "<strong>Province/City</strong>: 97%+ 'Unknown' &mdash; excluded from analysis. "
        "US state data available only for 3.7% of US users (all Members)."
    )
    warning_box(
        "<strong>Age=0</strong>: 757 accounts (0.3%). Min account age is 8; no ages 1-7 exist. "
        "Treated as missing (NULL) in cleaning."
    )
with col2:
    insight_box(
        f"<strong>Name columns</strong>: ~48% null is meaningful &mdash; it means 'never added a name'. "
        f"Treated as zero in feature engineering, not imputed."
    )
    insight_box(
        "<strong>Login-before-creation</strong>: 21% have earliest_login_date before account_create_date. "
        "Likely timezone artifacts in the data pipeline. Days-to-first-login capped at 0."
    )
    insight_box(
        "<strong>Extreme skew</strong>: All activity metrics are massively right-skewed (mean >> median). "
        "Log1p transforms applied before clustering."
    )

# ── Bias Assessment ──────────────────────────────────────────────────
section_header("Demographic Bias Assessment")
st.markdown("""
The dataset may contain sampling biases related to FamilySearch's user base:
- **Religious affiliation**: ~3% "Member" accounts likely represent LDS church members with different motivations
- **Geographic concentration**: Latin America (39%) and North America (28%) dominate
- **Youth cohort**: ~20% ages 8-19 — likely church youth program participants with non-organic sign-up patterns (sharp enrollment ramp at age 13-14)
- **Gender**: Not available in dataset — potential confound for engagement analysis
""")

col1, col2 = st.columns(2)
with col1:
    region_counts = df["USER_WORLD_REGION"].value_counts()
    fig = px.pie(values=region_counts.values, names=region_counts.index,
                 title="Geographic Distribution",
                 color_discrete_sequence=["#3b8520", "#2980b9", "#c0392b", "#8e44ad",
                                           "#d4a843", "#1abc9c", "#e67e22"])
    fig.update_layout(height=350, plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)
with col2:
    type_counts = df["ACCOUNT_TYPE"].value_counts()
    fig = px.pie(values=type_counts.values, names=type_counts.index,
                 title="Account Type Distribution",
                 color_discrete_sequence=["#3b8520", "#2980b9"])
    fig.update_layout(height=350, plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)

# ── Sample Data Preview ──────────────────────────────────────────────
section_header("Sample Data Preview", "Semi-stratified sample (n=500) for inspection")

@st.cache_data(show_spinner="Drawing stratified sample...")
def _draw_preview_sample(_df: pd.DataFrame, n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Draw a semi-stratified sample: proportional by COUNTRY × ACCOUNT_TYPE,
    with a floor of 1 per stratum to ensure rare groups are represented."""
    rng = np.random.RandomState(seed)

    # Build strata: top-15 countries individually, rest as "Other"
    top_countries = _df["COUNTRY"].value_counts().head(15).index.tolist()
    strat_col = _df["COUNTRY"].where(_df["COUNTRY"].isin(top_countries), "Other")
    _df = _df.copy()
    _df["_strat"] = strat_col + " | " + _df["ACCOUNT_TYPE"].astype(str)

    strata_counts = _df["_strat"].value_counts()
    total = len(_df)
    samples = []

    for stratum, count in strata_counts.items():
        stratum_df = _df[_df["_strat"] == stratum]
        # Proportional allocation with floor of 1
        n_draw = max(1, int(round(count / total * n)))
        n_draw = min(n_draw, len(stratum_df))
        samples.append(stratum_df.sample(n=n_draw, random_state=rng))

    result = pd.concat(samples, ignore_index=True)

    # Trim or pad to exactly n
    if len(result) > n:
        result = result.sample(n=n, random_state=rng).reset_index(drop=True)
    elif len(result) < n:
        remaining = _df[~_df.index.isin(result.index)]
        extra = remaining.sample(n=n - len(result), random_state=rng)
        result = pd.concat([result, extra], ignore_index=True)

    result = result.drop(columns=["_strat"])
    return result

preview = _draw_preview_sample(df, n=500)

# Summary of what the sample contains
p_cols = st.columns(4)
with p_cols[0]: metric_card("Sample Rows", str(len(preview)))
with p_cols[1]: metric_card("Countries", str(preview["COUNTRY"].nunique()))
with p_cols[2]:
    pct_member = (preview["ACCOUNT_TYPE"] == "Member").mean() * 100
    metric_card("% Member", f"{pct_member:.1f}%")
with p_cols[3]:
    pct_active = (preview["DAYS_LOGGING_IN"].fillna(0) > 0).mean() * 100
    metric_card("% Active", f"{pct_active:.1f}%")

st.dataframe(preview, use_container_width=True, height=400)
st.caption(
    "Semi-stratified by Country (top 15 + Other) × Account Type. "
    "Proportional allocation with floor of 1 per stratum ensures rare groups appear. "
    "Seed=42 for reproducibility."
)
