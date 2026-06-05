"""Feature Lab — Comprehensive Feature Engineering & Derived Variables"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from components.branding import apply_branding, section_header, CHART_PALETTE, insight_box, sidebar_tab
from components.charts import branded_heatmap
from src.data_loader import load_for_dashboard

st.set_page_config(page_title="Feature Lab | FamilySearch", page_icon="\U0001F333", layout="wide")
apply_branding()

st.title("Feature Engineering Lab")
st.markdown("*Explore, transform, and compose variables for deeper analysis*")
st.markdown("---")

# ── Sidebar ──────────────────────────────────────────────────────────
active_tab = sidebar_tab()
sample_size = 250_000
if active_tab == "controls":
    sample_size = st.sidebar.selectbox("Sample Size", [100_000, 250_000], index=1,
                                        format_func=lambda x: f"{x:,}")

df = load_for_dashboard(n=sample_size)

# ── Initialize derived features store ────────────────────────────────
if "derived_features" not in st.session_state:
    st.session_state["derived_features"] = pd.DataFrame(index=range(len(df)))


def _suggest_transforms(col_name, col_type, series):
    """Suggest 1-2 derived features for a column."""
    suggestions = []
    col_upper = col_name.upper()
    if col_type == "Numeric":
        skew = series.dropna().skew() if len(series.dropna()) > 100 else 0
        if abs(skew) > 2:
            suggestions.append("log1p (high skew)")
        if series.min() >= 0 and "DAYS" in col_upper:
            suggestions.append("tenure-normalized rate")
        if "AGE" in col_upper:
            suggestions.append("bin into age groups")
        if series.min() >= 0 and not suggestions:
            suggestions.append("binary (>0 flag)")
        if not suggestions:
            suggestions.append("zscore")
    elif col_type == "Datetime":
        if "EARLIEST" in col_upper:
            suggestions.append("days-to-first (from account creation)")
        suggestions.append("extract month/day-of-week")
    elif col_type == "Categorical":
        if series.nunique() <= 10:
            suggestions.append("one-hot encode")
        else:
            suggestions.append("frequency encode")
        if "REGION" in col_upper or "COUNTRY" in col_upper:
            suggestions.append("group by engagement level")
    return suggestions[:2]


# =====================================================================
# TABS
# =====================================================================
tab_explore, tab_transform, tab_compose, tab_saved = st.tabs([
    "Column Explorer", "Transformations", "Composite Features", "Saved Features"
])

# ── Tab 1: Column Explorer ───────────────────────────────────────────
with tab_explore:
    section_header("Full Column Inventory", f"All {df.shape[1]} columns")

    col_meta = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        pct_miss = df[col].isna().mean() * 100
        n_unique = df[col].nunique()
        if pd.api.types.is_numeric_dtype(df[col]):
            cat = "Numeric"
            v = df[col].dropna()
            stats = f"mean={v.mean():.2f}, med={v.median():.1f}, std={v.std():.2f}"
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            cat = "Datetime"
            stats = f"{df[col].min()} to {df[col].max()}"
        else:
            cat = "Categorical"
            top = df[col].value_counts().head(3)
            stats = ", ".join(f"{k} ({v:,})" for k, v in top.items())
        suggestions = _suggest_transforms(col, cat, df[col])
        col_meta.append({
            "Column": col, "Type": cat, "Missing %": f"{pct_miss:.1f}",
            "Unique": n_unique, "Summary": stats,
            "Suggested Transforms": "; ".join(suggestions),
        })
    st.dataframe(
        pd.DataFrame(col_meta), use_container_width=True, height=500,
        column_config={"Column": st.column_config.TextColumn("Column", pinned=True)},
    )

    # Drill-down
    section_header("Column Drill-Down")
    selected_col = st.selectbox("Inspect column:", df.columns.tolist())
    if selected_col:
        col_data = df[selected_col]
        c1, c2 = st.columns(2)
        with c1:
            if pd.api.types.is_numeric_dtype(col_data):
                fig = px.histogram(col_data.dropna(), nbins=60, title=f"{selected_col}",
                                   color_discrete_sequence=[CHART_PALETTE[0]])
            elif pd.api.types.is_datetime64_any_dtype(col_data):
                daily = col_data.dropna().dt.date.value_counts().sort_index()
                fig = px.line(x=daily.index, y=daily.values, title=selected_col,
                              color_discrete_sequence=[CHART_PALETTE[0]])
            else:
                top_n = col_data.value_counts().head(15)
                fig = px.bar(x=top_n.values, y=top_n.index, orientation="h",
                             title=selected_col, color_discrete_sequence=[CHART_PALETTE[0]])
            fig.update_layout(height=300, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            if pd.api.types.is_numeric_dtype(col_data):
                st.dataframe(col_data.describe(percentiles=[.25,.5,.75,.9,.95,.99]).round(3))
            else:
                st.write(f"**Unique**: {col_data.nunique()}")
                st.write(f"**Missing**: {col_data.isna().sum():,} ({col_data.isna().mean()*100:.1f}%)")
                st.write(f"**Mode**: {col_data.mode().iloc[0] if len(col_data.mode()) > 0 else 'N/A'}")

# ── Tab 2: Transformations ───────────────────────────────────────────
with tab_transform:
    section_header("Column Transformations", "Transform individual columns into derived features")

    source_col = st.selectbox("Source Column:",
        [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])], key="tsrc")
    transform = st.selectbox("Transform:", [
        "log1p (log(1+x))", "sqrt", "square", "zscore", "rank (percentile)",
        "bin: quartiles", "bin: deciles", "bin: custom edges",
        "binary (>0)", "clip outliers (1-99 pct)", "inverse (1/x)",
    ], key="ttype")

    preview = None
    new_name = None
    if source_col:
        vals = df[source_col].fillna(0)
        if transform == "log1p (log(1+x))":
            preview = np.log1p(vals); new_name = f"{source_col}_LOG"
        elif transform == "sqrt":
            preview = np.sqrt(vals.clip(lower=0)); new_name = f"{source_col}_SQRT"
        elif transform == "square":
            preview = vals ** 2; new_name = f"{source_col}_SQ"
        elif transform == "zscore":
            m, s = vals.mean(), vals.std()
            preview = (vals - m) / s if s > 0 else vals * 0; new_name = f"{source_col}_Z"
        elif transform == "rank (percentile)":
            preview = vals.rank(pct=True); new_name = f"{source_col}_RANK"
        elif transform == "bin: quartiles":
            preview = pd.qcut(vals, 4, labels=["Q1","Q2","Q3","Q4"], duplicates="drop")
            new_name = f"{source_col}_Q4"
        elif transform == "bin: deciles":
            preview = pd.qcut(vals, 10, labels=[f"D{i}" for i in range(1,11)], duplicates="drop")
            new_name = f"{source_col}_D10"
        elif transform == "bin: custom edges":
            n_bins = st.slider("Bins:", 2, 20, 5, key="cb")
            preview = pd.cut(vals, bins=n_bins, labels=[f"B{i+1}" for i in range(n_bins)], duplicates="drop")
            new_name = f"{source_col}_B{n_bins}"
        elif transform == "binary (>0)":
            preview = (vals > 0).astype(int); new_name = f"HAS_{source_col}"
        elif transform == "clip outliers (1-99 pct)":
            lo, hi = vals.quantile(0.01), vals.quantile(0.99)
            preview = vals.clip(lower=lo, upper=hi); new_name = f"{source_col}_CLIP"
        elif transform == "inverse (1/x)":
            preview = 1.0 / vals.replace(0, np.nan); new_name = f"{source_col}_INV"

    if preview is not None:
        new_name = st.text_input("Name:", value=new_name, key="tn")
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Original"); st.write(vals.describe().round(3))
        with c2:
            st.caption("Transformed")
            if pd.api.types.is_numeric_dtype(preview):
                st.write(preview.describe().round(3))
            else:
                st.write(preview.value_counts())
        if st.button("Save", key="tsave", type="primary"):
            st.session_state["derived_features"][new_name] = preview.values[:len(st.session_state["derived_features"])]
            st.success(f"Saved **{new_name}** ({len(st.session_state['derived_features'].columns)} derived features)")

# ── Tab 3: Composite Features ────────────────────────────────────────
with tab_compose:
    section_header("Composite Features", "Combine columns into derived phenotypes")
    st.markdown("*Composite features are multi-variable derived indicators — analogous to "
                "derived phenotypes in health informatics.*")

    compose_type = st.selectbox("Composition:", [
        "Ratio (A / B)", "Product (A * B)", "Difference (A - B)",
        "Sum of columns", "Weighted score",
        "Tenure-normalized rate (A / weeks)", "Days-to-first event",
        "Activity breadth (count non-zero)",
    ], key="ctype")

    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    result = None
    cname = None

    if compose_type == "Ratio (A / B)":
        a = st.selectbox("Numerator:", numeric_cols, key="ra")
        b = st.selectbox("Denominator:", numeric_cols, key="rb", index=min(1, len(numeric_cols)-1))
        denom = df[b].fillna(0).replace(0, np.nan)
        result = df[a].fillna(0) / denom; cname = f"{a}_per_{b}"

    elif compose_type == "Product (A * B)":
        a = st.selectbox("A:", numeric_cols, key="pa")
        b = st.selectbox("B:", numeric_cols, key="pb", index=min(1, len(numeric_cols)-1))
        result = df[a].fillna(0) * df[b].fillna(0); cname = f"{a}_x_{b}"

    elif compose_type == "Difference (A - B)":
        a = st.selectbox("A:", numeric_cols, key="da")
        b = st.selectbox("B:", numeric_cols, key="db", index=min(1, len(numeric_cols)-1))
        result = df[a].fillna(0) - df[b].fillna(0); cname = f"{a}_minus_{b}"

    elif compose_type == "Sum of columns":
        sel = st.multiselect("Columns:", numeric_cols, key="sc")
        if sel:
            result = df[sel].fillna(0).sum(axis=1)
            cname = "SUM_" + "_".join(c[:8] for c in sel[:3])

    elif compose_type == "Weighted score":
        sel = st.multiselect("Columns:", numeric_cols, key="wc", default=numeric_cols[:3])
        if sel:
            weights = {}
            wcols = st.columns(min(len(sel), 4))
            for i, c in enumerate(sel):
                with wcols[i % len(wcols)]:
                    weights[c] = st.number_input(f"w({c[:10]})", value=1.0, step=0.1, key=f"w_{c}")
            result = sum(df[c].fillna(0) * w for c, w in weights.items())
            cname = "WEIGHTED_SCORE"

    elif compose_type == "Tenure-normalized rate (A / weeks)":
        a = st.selectbox("Activity:", numeric_cols, key="ta")
        if "ACCOUNT_CREATE_DATE" in df.columns:
            weeks = ((pd.Timestamp("2026-03-24") - df["ACCOUNT_CREATE_DATE"]).dt.days.clip(lower=1)) / 7
            result = df[a].fillna(0) / weeks; cname = f"{a}_PER_WEEK"

    elif compose_type == "Days-to-first event":
        d = st.selectbox("Event date:", date_cols, key="dtf")
        if "ACCOUNT_CREATE_DATE" in df.columns:
            result = (df[d] - df["ACCOUNT_CREATE_DATE"]).dt.days.clip(lower=0)
            cname = f"DAYS_TO_{d.replace('EARLIEST_','').replace('_DATE','')}"

    elif compose_type == "Activity breadth (count non-zero)":
        sel = st.multiselect("Activity cols:", numeric_cols, key="bc",
            default=[c for c in numeric_cols if any(k in c for k in ["DAYS","ADDED","EDITS"])][:6])
        if sel:
            result = (df[sel].fillna(0) > 0).sum(axis=1); cname = "ACTIVITY_BREADTH"

    if result is not None:
        cname = st.text_input("Name:", value=cname, key="cn")
        st.write(result.describe().round(4))
        if pd.api.types.is_numeric_dtype(result):
            fig = px.histogram(result.dropna(), nbins=50, title=cname,
                               color_discrete_sequence=[CHART_PALETTE[0]])
            fig.update_layout(height=250, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, use_container_width=True)
        if st.button("Save", key="csave", type="primary"):
            st.session_state["derived_features"][cname] = result.values[:len(st.session_state["derived_features"])]
            st.success(f"Saved **{cname}**")

# ── Tab 4: Saved Features ────────────────────────────────────────────
with tab_saved:
    section_header("Saved Derived Features", "Available for Clustering Lab and other pages")
    derived = st.session_state.get("derived_features", pd.DataFrame())

    if derived.empty or len(derived.columns) == 0:
        st.info("No derived features yet. Use **Transformations** or **Composite Features** tabs.")
    else:
        st.success(f"**{len(derived.columns)}** derived features ready for clustering")
        stats = []
        for col in derived.columns:
            v = derived[col]
            if pd.api.types.is_numeric_dtype(v):
                stats.append({"Feature": col, "Type": "numeric", "Non-Null": f"{v.notna().sum():,}",
                               "Mean": f"{v.mean():.4f}", "Std": f"{v.std():.4f}"})
            else:
                stats.append({"Feature": col, "Type": "categorical", "Non-Null": f"{v.notna().sum():,}",
                               "Mean": "—", "Std": "—"})
        st.dataframe(pd.DataFrame(stats), use_container_width=True)

        numeric_d = derived.select_dtypes(include=[np.number])
        if len(numeric_d.columns) >= 2:
            section_header("Derived Feature Correlations")
            corr = numeric_d.corr()
            fig = branded_heatmap(corr.values, list(corr.columns), "Correlation Matrix")
            st.plotly_chart(fig, use_container_width=True)

        to_del = st.multiselect("Delete:", derived.columns.tolist(), key="df_del")
        if to_del and st.button("Delete Selected"):
            st.session_state["derived_features"] = derived.drop(columns=to_del)
            st.rerun()
