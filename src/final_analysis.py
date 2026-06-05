"""
═══════════════════════════════════════════════════════════════════════════════
FINAL COMPREHENSIVE ANALYSIS: FamilySearch User Persistence
═══════════════════════════════════════════════════════════════════════════════

Single end-to-end script implementing the streamlined factorial design:

    Population: Contributors Only (2+ logins, Tier D)
    ├── Full population (T=10 × 5,000)
    ├── Member stratum (T=5 × 2,500)
    └── Public stratum (T=5 × 5,000)

    Per stratum:
    ├── Classification (B4 H1 vs B5 H0 vs B6 Full, RF)
    ├── Feature importance with corrected velocity
    ├── Velocity partial correlation (the suppression-corrected signal)
    ├── Tier segmentation (K-Means on PC2, k=5)
    ├── Per-tier nonlinearity (linear vs quadratic vs logarithmic)
    └── PCA biplot

Key improvements over iterative analysis:
    - Decollineared velocity features (3 independent transitions + composite)
    - Single pass on contributors-only (no two-pass redundancy)
    - Pre-planned factorial design (no ad-hoc discoveries)
    - Persistence dichotomized within each stratum
    - Optimized plot formatting for sparse data visibility

Output: outputs/final/
═══════════════════════════════════════════════════════════════════════════════
"""

import pandas as pd
import numpy as np
import json
import warnings
from pathlib import Path
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.metrics import roc_auc_score, f1_score
from sklearn.linear_model import LinearRegression
from scipy import stats
from scipy.optimize import curve_fit
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
OUTPUT = PROJECT / "outputs" / "final"
OUTPUT.mkdir(parents=True, exist_ok=True)

T_FULL = 10       # Subsamples for full population
T_STRAT = 5       # Subsamples for Member/Public strata
N_FULL = 5000     # Per-subsample size (full)
N_MEMBER = 2500   # Per-subsample size (Member)
N_PUBLIC = 5000   # Per-subsample size (Public)
K_TIERS = 5       # Number of contextual-development tiers

# ─────────────────────────────────────────────────────────────────────────────
# FEATURE DEFINITIONS (decollineared velocity)
#
# Velocity: 5 features, all independent (VIF < 1.5)
#   - 3 independent transition times (the actual measurements)
#   - 1 composite z-score (mean of standardized transitions, inverted)
#   - 1 activation speed (original, already independent)
#
# Volume: 8 features (tenure-normalized rates + 90-day window)
# Sequencing: 6 features (breadth, funnel, binary flags for rare activities)
# Contextual: 8 continuous + 2 categorical (age, country cluster, enrichment)
# ─────────────────────────────────────────────────────────────────────────────

VELOCITY = [
    "days_to_first_login",        # Account creation → first login (usually 0)
    "days_login_to_tree_edit",    # First login → first tree edit (independent)
    "days_login_to_name",         # First login → first name (independent)
    "velocity_score",             # Composite: -mean(z-scores of above 3) [higher = faster]
    "activation_speed",           # 1/(1 + dtfl + dltte) [higher = faster]
]

VOLUME = [
    "log_logins_pw", "log_tree_edits_pw", "log_names_pw", "log_sources_pw",
    "logins_90d", "tree_edits_90d", "names_90d", "sources_90d",
]

SEQUENCING = [
    "activity_breadth", "funnel_stage",
    "has_sources", "has_memories", "has_record_edits", "has_get_involved",
]

CONTEXTUAL_CONT = [
    "user_age", "gdp_per_capita_ppp", "hdi", "pct_christian",
    "govt_restrictions_index", "social_hostilities_index",
    "lds_members_per_capita", "religious_diversity_index",
]
CONTEXTUAL_CAT = ["country_cluster", "age_group"]

# All behavioral features (H1 block)
H1_FEATURES = VELOCITY + VOLUME + SEQUENCING

# All features used for PCA and tier segmentation
ALL_FEATURES_FOR_PCA = (
    ["days_to_first_login", "days_login_to_tree_edit", "days_login_to_name",
     "activation_speed"]  # velocity (without composite — it's derived from these)
    + VOLUME + SEQUENCING[:2]  # breadth + funnel only (flags cause VIF issues)
    + ["login_consistency"]
    + ["gdp_per_capita_ppp", "hdi", "pct_christian", "govt_restrictions_index",
       "social_hostilities_index", "lds_members_per_capita",
       "religious_diversity_index", "gepi"]
    + ["user_age"]
)

# Construct labels for importance reporting
CONSTRUCT_MAP = {}
for f in VELOCITY: CONSTRUCT_MAP[f] = "Velocity"
for f in VOLUME: CONSTRUCT_MAP[f] = "Volume"
for f in SEQUENCING: CONSTRUCT_MAP[f] = "Sequencing"
for f in CONTEXTUAL_CONT + CONTEXTUAL_CAT: CONSTRUCT_MAP[f] = "Contextual"

# Plot colors
TIER_COLORS = {"T1": "#1a4314", "T2": "#3b8520", "T3": "#2980b9",
               "T4": "#e67e22", "T5": "#c0392b"}
GROUP_COLORS = {"Full": "#1a4314", "Member": "#8e44ad", "Public": "#2980b9"}
CONSTRUCT_COLORS = {"Volume": "#3b8520", "Sequencing": "#2980b9",
                    "Velocity": "#e67e22", "Contextual": "#c0392b"}

qc_log = []

def log_qc(step, metric, value, note=""):
    qc_log.append({"step": step, "metric": metric, "value": value, "note": note,
                    "timestamp": datetime.now().isoformat()})


# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING AND PREPARATION
# ─────────────────────────────────────────────────────────────────────────────

def load_contributors():
    """
    Load the full Tier D contributors population from DuckDB.
    Tier D = non-MNAR, tenure ≥ 31 days, 2+ logins, has tree edits + names + dates.
    Joins enrichment data in the same query.
    Returns a single DataFrame ready for subsampling.
    """
    print("Loading contributors from DuckDB...")
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

    # Engineer the decollineared velocity composite
    transitions = ["days_to_first_login", "days_login_to_tree_edit", "days_login_to_name"]
    for f in transitions:
        df[f"_z_{f}"] = (df[f].fillna(0) - df[f].fillna(0).mean()) / max(df[f].fillna(0).std(), 0.001)
    df["velocity_score"] = -df[[f"_z_{f}" for f in transitions]].mean(axis=1)
    df.drop(columns=[f"_z_{f}" for f in transitions], inplace=True)

    print(f"  Loaded {len(df):,} contributors")
    print(f"  Member: {(df['ACCOUNT_TYPE'] == 'Member').sum():,} ({(df['ACCOUNT_TYPE'] == 'Member').mean()*100:.1f}%)")
    print(f"  Public: {(df['ACCOUNT_TYPE'] == 'Public').sum():,}")
    return df


def draw_subsamples(df, n_per, t, seed_base=42):
    """Draw T independent random subsamples, each with 70/30 train/test split."""
    subs = []
    for i in range(t):
        rng = np.random.RandomState(seed_base + i)
        s = df.sample(n=min(n_per, len(df)), random_state=rng).copy()
        # Persistence dichotomization within this subsample
        median_c = s["persistence_c"].median()
        s["y"] = (s["persistence_c"] >= median_c).astype(int)
        # Train/test split
        s["split"] = "test"
        train_idx = rng.choice(s.index, size=int(len(s) * 0.7), replace=False)
        s.loc[train_idx, "split"] = "train"
        subs.append(s)
    return subs


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSIS FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def prepare_features(df, cont_list, cat_list=None):
    """Build feature matrix: fill NaN, one-hot encode categoricals."""
    parts, names = [], []
    for f in cont_list:
        if f in df.columns:
            parts.append(df[[f]].fillna(0).values)
            names.append(f)
    if cat_list:
        for f in cat_list:
            if f in df.columns:
                dummies = pd.get_dummies(df[f], prefix=f, drop_first=True).fillna(0)
                parts.append(dummies.values)
                names.extend(dummies.columns.tolist())
    return (np.hstack(parts), names) if parts else (np.zeros((len(df), 1)), ["dummy"])


def run_classification(subsamples, group_label):
    """
    Run the 3-block classification comparison (B4 H1, B5 H0, B6 Full)
    on each subsample. Returns results DataFrame and feature importances.
    """
    all_results = []
    all_importances = []

    blocks = {
        "B4_H1": (H1_FEATURES, []),
        "B5_H0": (CONTEXTUAL_CONT, CONTEXTUAL_CAT),
        "B6_Full": (H1_FEATURES + CONTEXTUAL_CONT, CONTEXTUAL_CAT),
    }

    for t, df in enumerate(subsamples, 1):
        train = df[df["split"] == "train"]
        test = df[df["split"] == "test"]
        ytr, yte = train["y"].values, test["y"].values

        for bname, (cont, cat) in blocks.items():
            Xtr, fnames = prepare_features(train, cont, cat)
            Xte, _ = prepare_features(test, cont, cat)

            rf = RandomForestClassifier(n_estimators=300, random_state=42,
                                         class_weight="balanced", n_jobs=-1)
            rf.fit(Xtr, ytr)
            y_prob = rf.predict_proba(Xte)[:, 1]
            auc = roc_auc_score(yte, y_prob) if len(np.unique(yte)) > 1 else 0.5
            f1 = f1_score(yte, rf.predict(Xte), zero_division=0)

            all_results.append({"group": group_label, "block": bname,
                                 "subsample": t, "auc": auc, "f1": f1})

            # Capture feature importances from full model
            if bname == "B6_Full":
                for feat, imp in zip(fnames, rf.feature_importances_):
                    construct = CONSTRUCT_MAP.get(feat, "Contextual")
                    for prefix in ["country_cluster_", "age_group_"]:
                        if feat.startswith(prefix):
                            construct = "Contextual"
                    all_importances.append({"group": group_label, "feature": feat,
                                             "importance": imp, "construct": construct,
                                             "subsample": t})

    return pd.DataFrame(all_results), pd.DataFrame(all_importances)


def run_velocity_partial(df, group_label):
    """
    Compute partial correlation: velocity with persistence, controlling for volume.
    This reveals the true velocity signal hidden by shared variance with volume.
    """
    vol_features = ["log_logins_pw", "logins_90d", "log_tree_edits_pw", "tree_edits_90d"]
    X_vol = df[vol_features].fillna(0).values
    y = df["persistence_c"].values

    lr = LinearRegression().fit(X_vol, y)
    resid = y - lr.predict(X_vol)
    vol_r2 = lr.score(X_vol, y)

    partials = {}
    for f in VELOCITY:
        if f in df.columns:
            r, p = stats.pearsonr(df[f].fillna(0), resid)
            partials[f] = {"r": round(r, 4), "p": f"{p:.2e}", "r_raw": round(stats.pearsonr(df[f].fillna(0), y)[0], 4)}

    return vol_r2, partials


def run_tier_analysis(df, group_label):
    """
    Segment users into 5 contextual-development tiers via K-Means on PC2,
    then fit linear, quadratic, and logarithmic models to the persistence
    gradient within each tier.
    """
    # PCA on the full feature set
    avail = [f for f in ALL_FEATURES_FOR_PCA if f in df.columns]
    X = StandardScaler().fit_transform(df[avail].fillna(0))
    pca = PCA(n_components=3)
    X_pca = pca.fit_transform(X)
    df = df.copy()
    df["PC1"], df["PC2"] = X_pca[:, 0], X_pca[:, 1]

    # K-Means tiers on PC2 (contextual axis in contributors data)
    km = KMeans(n_clusters=K_TIERS, random_state=42, n_init=10)
    df["tier_raw"] = km.fit_predict(df[["PC2"]].values)
    centroid_order = np.argsort(km.cluster_centers_.flatten())
    label_map = {old: new for new, old in enumerate(centroid_order)}
    df["tier"] = df["tier_raw"].map(label_map)
    df["tier_label"] = df["tier"].map(lambda x: f"T{x+1}")

    # Nonlinearity test per tier
    def log_model(x, a, b):
        return a * np.log(x + 1) + b

    tier_results = []
    for tl in sorted(df["tier_label"].unique()):
        sub = df[df["tier_label"] == tl]
        x, y = sub["PC1"].values, sub["persistence_c"].values
        n = len(sub)
        if n < 30:
            continue

        # Linear
        slope, intercept, r_lin, p_lin, _ = stats.linregress(x, y)
        r2_lin = r_lin ** 2

        # Quadratic
        coeffs = np.polyfit(x, y, 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2_quad = 1 - np.sum((y - np.polyval(coeffs, x)) ** 2) / ss_tot if ss_tot > 0 else 0

        # Logarithmic
        x_s = x - x.min() + 0.1
        try:
            popt, _ = curve_fit(log_model, x_s, y, p0=[0.05, 0.2], maxfev=5000)
            r2_log = 1 - np.sum((y - log_model(x_s, *popt)) ** 2) / ss_tot if ss_tot > 0 else 0
        except:
            r2_log = r2_lin

        best_nonlin = max(r2_quad, r2_log)
        tier_results.append({
            "group": group_label, "tier": tl, "n": n,
            "r2_lin": round(r2_lin, 4), "r2_quad": round(r2_quad, 4),
            "r2_log": round(r2_log, 4),
            "delta_r2": round(best_nonlin - r2_lin, 4),
            "best_model": "Log" if r2_log > r2_quad else "Quad",
            "lin_slope": round(slope, 5), "quad_a": round(coeffs[0], 6),
        })

    return df, pd.DataFrame(tier_results), pca


# ─────────────────────────────────────────────────────────────────────────────
# PLOTTING FUNCTIONS (optimized for sparse data visibility)
# ─────────────────────────────────────────────────────────────────────────────

def sparse_scatter(fig, x, y, color, name, row=None, col=None, opacity=0.25, size=3):
    """Add a scatter trace optimized for sparse/overlapping data."""
    trace = go.Scatter(
        x=x, y=y, mode="markers",
        marker=dict(size=size, color=color, opacity=opacity,
                    line=dict(width=0)),  # no marker border for cleaner look
        name=name,
    )
    if row and col:
        fig.add_trace(trace, row=row, col=col)
    else:
        fig.add_trace(trace)


def trend_line(fig, x, y, color, name=None, row=None, col=None, dash="solid", width=3):
    """Add a regression trend line."""
    slope, intercept, _, _, _ = stats.linregress(x, y)
    x_line = np.linspace(x.min(), x.max(), 100)
    trace = go.Scatter(
        x=x_line, y=slope * x_line + intercept, mode="lines",
        line=dict(color=color, width=width, dash=dash),
        name=name, showlegend=name is not None,
    )
    if row and col:
        fig.add_trace(trace, row=row, col=col)
    else:
        fig.add_trace(trace)


def styled_layout(fig, title, height=500, width=900, **kwargs):
    """Apply consistent styling to a figure."""
    fig.update_layout(
        title=dict(text=title, font=dict(size=16)),
        height=height, width=width,
        plot_bgcolor="rgba(245,245,240,1)",  # light warm background for contrast
        paper_bgcolor="white",
        font=dict(size=12),
        margin=dict(t=60, b=50, l=60, r=40),
        **kwargs,
    )
    fig.update_xaxes(gridcolor="rgba(200,200,200,0.5)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(200,200,200,0.5)", zeroline=False)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 90)
    print("FINAL COMPREHENSIVE ANALYSIS: FamilySearch User Persistence")
    print("=" * 90)
    start_time = datetime.now()

    # ── Load data ──
    df_all = load_contributors()

    members_pool = df_all[df_all["ACCOUNT_TYPE"] == "Member"].reset_index(drop=True)
    public_pool = df_all[df_all["ACCOUNT_TYPE"] == "Public"].reset_index(drop=True)

    log_qc("data", "total_contributors", len(df_all))
    log_qc("data", "members", len(members_pool))
    log_qc("data", "public", len(public_pool))

    # ── Draw subsamples ──
    print("\nDrawing subsamples...")
    full_subs = draw_subsamples(df_all, N_FULL, T_FULL, seed_base=200)
    member_subs = draw_subsamples(members_pool, N_MEMBER, T_STRAT, seed_base=300)
    public_subs = draw_subsamples(public_pool, N_PUBLIC, T_STRAT, seed_base=400)
    print(f"  Full: T={T_FULL} × {N_FULL}")
    print(f"  Member: T={T_STRAT} × {N_MEMBER}")
    print(f"  Public: T={T_STRAT} × {N_PUBLIC}")

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 1: CLASSIFICATION (H1 vs H0)
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print("STAGE 1: CLASSIFICATION")
    print(f"{'='*90}")

    full_cls, full_imp = run_classification(full_subs, "Full")
    mem_cls, mem_imp = run_classification(member_subs, "Member")
    pub_cls, pub_imp = run_classification(public_subs, "Public")

    all_cls = pd.concat([full_cls, mem_cls, pub_cls], ignore_index=True)
    all_imp = pd.concat([full_imp, mem_imp, pub_imp], ignore_index=True)

    # Aggregate
    cls_agg = all_cls.groupby(["group", "block"]).agg(
        mean_auc=("auc", "mean"), std_auc=("auc", "std"),
        mean_f1=("f1", "mean"),
    ).round(4)

    print("\nBlock Comparison (RF):")
    print(cls_agg.to_string())

    for group in ["Full", "Member", "Public"]:
        g = all_cls[all_cls["group"] == group]
        b4 = g[g["block"] == "B4_H1"]["auc"].mean()
        b5 = g[g["block"] == "B5_H0"]["auc"].mean()
        b6 = g[g["block"] == "B6_Full"]["auc"].mean()
        log_qc(f"cls_{group}", "B4_auc", round(b4, 4))
        log_qc(f"cls_{group}", "B5_auc", round(b5, 4))
        log_qc(f"cls_{group}", "B6_auc", round(b6, 4))
        log_qc(f"cls_{group}", "delta_H1", round(b6 - b5, 4))
        log_qc(f"cls_{group}", "delta_H0", round(b6 - b4, 4))
        print(f"\n  {group}: B4={b4:.4f}, B5={b5:.4f}, B6={b6:.4f}, "
              f"Δ_H1={b6-b5:+.4f}, Δ_H0={b6-b4:+.4f}")

    # ── Fig 1: Block AUC comparison (3 groups) ──
    fig = make_subplots(rows=1, cols=3, subplot_titles=("Full Population", "Member Only", "Public Only"),
                         shared_yaxes=True)
    block_labels = {"B4_H1": "H1\nEngagement", "B5_H0": "H0\nContext", "B6_Full": "Full"}
    block_colors = {"B4_H1": "#3b8520", "B5_H0": "#c0392b", "B6_Full": "#1a4314"}
    for ci, group in enumerate(["Full", "Member", "Public"], 1):
        g_agg = cls_agg.loc[group]
        for block in ["B4_H1", "B5_H0", "B6_Full"]:
            if block in g_agg.index:
                fig.add_trace(go.Bar(
                    x=[block_labels[block]], y=[g_agg.loc[block, "mean_auc"]],
                    marker_color=block_colors[block],
                    error_y=dict(type="data", array=[g_agg.loc[block, "std_auc"]], visible=True),
                    text=[f"{g_agg.loc[block, 'mean_auc']:.3f}"], textposition="outside",
                    showlegend=(ci == 1), name=block_labels[block] if ci == 1 else None,
                ), row=1, col=ci)
    styled_layout(fig, "H1 vs H0 Classification: Full / Member / Public", width=1100)
    fig.update_yaxes(range=[0.4, 1.05], row=1, col=1)
    fig.write_image(OUTPUT / "fig01_block_auc.png", scale=2)
    print("  Fig 01 saved")

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 2: FEATURE IMPORTANCE (corrected velocity)
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print("STAGE 2: FEATURE IMPORTANCE (corrected velocity)")
    print(f"{'='*90}")

    # ── Fig 2: Top 15 features (Full model, with construct colors) ──
    full_imp_agg = all_imp[all_imp["group"] == "Full"].groupby(["feature", "construct"])["importance"].mean()
    full_imp_agg = full_imp_agg.reset_index().sort_values("importance", ascending=True).tail(15)

    # Build one trace per construct so the legend is clean
    for construct, color in CONSTRUCT_COLORS.items():
        mask = full_imp_agg["construct"] == construct
        subset = full_imp_agg[mask]
        if len(subset) > 0:
            fig.add_trace(go.Bar(
                x=subset["importance"], y=subset["feature"], orientation="h",
                marker_color=color, name=construct,
                text=[f"{v:.3f}" for v in subset["importance"]], textposition="outside",
            ))
    styled_layout(fig, "Feature Importance: Full Model (RF, T=10) — Corrected Velocity", height=550, width=900)
    fig.update_xaxes(title_text="Mean Gini Importance")
    fig.write_image(OUTPUT / "fig02_feature_importance.png", scale=2)
    print("  Fig 02 saved")

    # ── Fig 3: Construct share pie (Full) ──
    construct_share = all_imp[all_imp["group"] == "Full"].groupby("construct")["importance"].sum()
    construct_share = construct_share / construct_share.sum() * 100

    fig = go.Figure(go.Pie(
        labels=construct_share.index, values=construct_share.values,
        marker_colors=[CONSTRUCT_COLORS.get(c, "#999") for c in construct_share.index],
        textinfo="label+percent", textfont=dict(size=13),
    ))
    styled_layout(fig, "Construct Share of Discriminant Importance (Full Model)", height=450, width=550)
    fig.write_image(OUTPUT / "fig03_construct_share.png", scale=2)

    # Log construct shares for all groups
    for group in ["Full", "Member", "Public"]:
        g_share = all_imp[all_imp["group"] == group].groupby("construct")["importance"].sum()
        g_share = g_share / g_share.sum() * 100
        for c, v in g_share.items():
            log_qc(f"importance_{group}", f"{c}_pct", round(v, 1))
    print("  Fig 03 saved")

    # ── Fig 4: Feature importance comparison (Member vs Public) ──
    top_feats = all_imp[all_imp["group"] == "Full"].groupby("feature")["importance"].mean().nlargest(12).index
    fig = go.Figure()
    for group, color in [("Member", "#8e44ad"), ("Public", "#2980b9")]:
        g_imp = all_imp[all_imp["group"] == group].groupby("feature")["importance"].mean()
        vals = [g_imp.get(f, 0) for f in top_feats]
        fig.add_trace(go.Bar(x=list(top_feats), y=vals, name=group, marker_color=color))
    styled_layout(fig, "Feature Importance: Member vs Public (Top 12)", width=1000)
    fig.update_layout(barmode="group", xaxis_tickangle=25)
    fig.write_image(OUTPUT / "fig04_importance_member_vs_public.png", scale=2)
    print("  Fig 04 saved")

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 3: VELOCITY PARTIAL CORRELATION
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print("STAGE 3: VELOCITY PARTIAL CORRELATION")
    print(f"{'='*90}")

    partial_results = {}
    for group_label, pool in [("Full", df_all), ("Member", members_pool), ("Public", public_pool)]:
        # Use a 5K sample for consistency
        sample = pool.sample(n=min(5000, len(pool)), random_state=42).copy()
        transitions = ["days_to_first_login", "days_login_to_tree_edit", "days_login_to_name"]
        for f in transitions:
            sample[f"_z_{f}"] = (sample[f].fillna(0) - sample[f].fillna(0).mean()) / max(sample[f].fillna(0).std(), 0.001)
        sample["velocity_score"] = -sample[[f"_z_{f}" for f in transitions]].mean(axis=1)

        vol_r2, partials = run_velocity_partial(sample, group_label)
        partial_results[group_label] = {"vol_r2": vol_r2, "partials": partials}

        print(f"\n  {group_label}: Volume R²={vol_r2:.4f}")
        for f, vals in partials.items():
            print(f"    {f:<30} raw r={vals['r_raw']:>+.4f}  partial r={vals['r']:>+.4f}  p={vals['p']}")
            log_qc(f"partial_{group_label}", f"raw_{f}", vals["r_raw"])
            log_qc(f"partial_{group_label}", f"partial_{f}", vals["r"])

    # ── Fig 5: Partial correlation comparison ──
    fig = go.Figure()
    vel_feats_plot = ["velocity_score", "activation_speed", "days_login_to_tree_edit", "days_login_to_name"]
    x_labels = ["velocity_score", "activation_speed", "login→tree", "login→name"]
    for group, color in GROUP_COLORS.items():
        if group in partial_results:
            raw_vals = [partial_results[group]["partials"].get(f, {}).get("r_raw", 0) for f in vel_feats_plot]
            partial_vals = [partial_results[group]["partials"].get(f, {}).get("r", 0) for f in vel_feats_plot]
            fig.add_trace(go.Bar(x=x_labels, y=[abs(v) for v in partial_vals],
                                  name=f"{group} (partial)", marker_color=color, opacity=0.9))
    styled_layout(fig, "Velocity Partial Correlations with Persistence (|r| after removing Volume)",
                  height=450, width=900)
    fig.update_layout(barmode="group")
    fig.update_yaxes(title_text="|Partial r|")
    fig.write_image(OUTPUT / "fig05_velocity_partial.png", scale=2)
    print("  Fig 05 saved")

    # ══════════════════════════════════════════════════════════════════════════
    # STAGE 4: TIER SEGMENTATION + NONLINEARITY
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print("STAGE 4: TIER SEGMENTATION + NONLINEARITY")
    print(f"{'='*90}")

    # Run on larger samples for stability
    full_sample = df_all.sample(n=min(10000, len(df_all)), random_state=42).copy()
    transitions = ["days_to_first_login", "days_login_to_tree_edit", "days_login_to_name"]
    for pool_df in [full_sample, members_pool, public_pool]:
        for f in transitions:
            pool_df[f"_z_{f}"] = (pool_df[f].fillna(0) - pool_df[f].fillna(0).mean()) / max(pool_df[f].fillna(0).std(), 0.001)
        pool_df["velocity_score"] = -pool_df[[f"_z_{f}" for f in transitions]].mean(axis=1)

    full_tiered, full_tiers, full_pca = run_tier_analysis(full_sample, "Full")
    mem_tiered, mem_tiers, _ = run_tier_analysis(
        members_pool.sample(n=min(5000, len(members_pool)), random_state=42).copy(), "Member")
    pub_tiered, pub_tiers, _ = run_tier_analysis(
        public_pool.sample(n=min(10000, len(public_pool)), random_state=42).copy(), "Public")

    all_tiers = pd.concat([full_tiers, mem_tiers, pub_tiers], ignore_index=True)

    print("\nNonlinearity Results:")
    print(f"{'Group':<8} {'Tier':<6} {'n':>6} {'Lin R²':>8} {'ΔR²':>8} {'Best':>6} {'Slope':>8}")
    print("-" * 60)
    for _, r in all_tiers.iterrows():
        print(f"{r['group']:<8} {r['tier']:<6} {r['n']:>6} {r['r2_lin']:>8.4f} {r['delta_r2']:>8.4f} "
              f"{r['best_model']:>6} {r['lin_slope']:>8.5f}")

    # ── Fig 6: Per-tier gradient (Full) with quadratic fits ──
    fig = go.Figure()
    def log_model(x, a, b):
        return a * np.log(x + 1) + b

    for tier in sorted(full_tiered["tier_label"].unique()):
        sub = full_tiered[full_tiered["tier_label"] == tier]
        x, y = sub["PC1"].values, sub["persistence_c"].values
        color = TIER_COLORS.get(tier, "#999")
        n = len(sub)
        sparse_scatter(fig, x, y, color, f"{tier} (n={n})", opacity=0.15, size=3)

        # Best fit curve
        tier_row = full_tiers[full_tiers["tier"] == tier]
        if len(tier_row) > 0:
            best = tier_row.iloc[0]["best_model"]
            x_line = np.linspace(x.min(), x.max(), 200)
            if best == "Log":
                x_s = x - x.min() + 0.1
                try:
                    popt, _ = curve_fit(log_model, x_s, y, p0=[0.05, 0.2], maxfev=5000)
                    x_line_s = x_line - x.min() + 0.1
                    fig.add_trace(go.Scatter(x=x_line, y=log_model(x_line_s, *popt), mode="lines",
                                              line=dict(color=color, width=3), showlegend=False))
                except:
                    trend_line(fig, x, y, color)
            else:
                coeffs = np.polyfit(x, y, 2)
                fig.add_trace(go.Scatter(x=x_line, y=np.polyval(coeffs, x_line), mode="lines",
                                          line=dict(color=color, width=3), showlegend=False))

    styled_layout(fig, "Persistence Gradient by Development Tier (best-fit curves)", height=600, width=1000)
    fig.update_xaxes(title_text="PC1 (Volume / Engagement →)")
    fig.update_yaxes(title_text="Persistence Score C")
    fig.write_image(OUTPUT / "fig06_tier_gradients.png", scale=2)
    print("  Fig 06 saved")

    # ── Fig 7: ΔR² comparison (Full/Member/Public × Tiers) ──
    fig = go.Figure()
    for group, color in GROUP_COLORS.items():
        g_tiers = all_tiers[all_tiers["group"] == group].sort_values("tier")
        fig.add_trace(go.Bar(x=g_tiers["tier"], y=g_tiers["delta_r2"],
                              name=group, marker_color=color,
                              text=[f"{v:.3f}" for v in g_tiers["delta_r2"]],
                              textposition="outside"))
    styled_layout(fig, "Nonlinearity (ΔR²) by Tier: Full / Member / Public", height=450, width=900)
    fig.update_layout(barmode="group")
    fig.update_yaxes(title_text="ΔR² (Best Nonlinear − Linear)")
    fig.write_image(OUTPUT / "fig07_nonlinearity_comparison.png", scale=2)
    print("  Fig 07 saved")

    # ── Fig 8: PCA biplot (Full population, with enrichment vectors) ──
    pca_loadings = pd.DataFrame(full_pca.components_[:2].T,
                                 index=[f for f in ALL_FEATURES_FOR_PCA if f in full_sample.columns],
                                 columns=["PC1", "PC2"])
    var = full_pca.explained_variance_ratio_

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=full_tiered["PC1"], y=full_tiered["PC2"], mode="markers",
        marker=dict(size=3, color=full_tiered["persistence_c"], colorscale="RdYlGn",
                    opacity=0.25, colorbar=dict(title="Persist.", thickness=15, len=0.5)),
        showlegend=False,
    ))
    # Loading vectors (top 10 by combined magnitude)
    combined_mag = (pca_loadings["PC1"] ** 2 + pca_loadings["PC2"] ** 2).nlargest(10)
    scale = abs(full_tiered["PC1"].max()) / pca_loadings["PC1"].abs().max() * 0.6
    construct_labels_pca = {}
    for f in ALL_FEATURES_FOR_PCA:
        if f in VOLUME or f == "login_consistency":
            construct_labels_pca[f] = "Behavioral"
        elif f in ["days_to_first_login", "days_login_to_tree_edit", "days_login_to_name", "activation_speed"]:
            construct_labels_pca[f] = "Behavioral"
        elif f in ["activity_breadth", "funnel_stage"]:
            construct_labels_pca[f] = "Behavioral"
        else:
            construct_labels_pca[f] = "Enrichment"

    for feat in combined_mag.index:
        x_end = pca_loadings.loc[feat, "PC1"] * scale
        y_end = pca_loadings.loc[feat, "PC2"] * scale
        c_type = construct_labels_pca.get(feat, "Enrichment")
        arrow_color = "#1a4314" if c_type == "Behavioral" else "#2980b9"
        fig.add_trace(go.Scatter(
            x=[0, x_end], y=[0, y_end], mode="lines+text",
            line=dict(color=arrow_color, width=2.5),
            text=["", feat.replace("_", " ")], textposition="top center",
            textfont=dict(size=9, color=arrow_color), showlegend=False,
        ))
    styled_layout(fig, f"PCA Biplot: Feature Vectors over Persistence Gradient\n"
                       f"PC1={var[0]*100:.1f}% (Volume)  PC2={var[1]*100:.1f}% (Context)",
                  height=650, width=950)
    fig.update_xaxes(title_text=f"PC1 ({var[0]*100:.1f}%)")
    fig.update_yaxes(title_text=f"PC2 ({var[1]*100:.1f}%)")
    fig.write_image(OUTPUT / "fig08_biplot.png", scale=2)
    print("  Fig 08 saved")

    # ── Fig 9: PCA colored by tier (shows what tiers look like in feature space) ──
    fig = go.Figure()
    for tier in sorted(full_tiered["tier_label"].unique()):
        sub = full_tiered[full_tiered["tier_label"] == tier]
        sparse_scatter(fig, sub["PC1"].values, sub["PC2"].values,
                       TIER_COLORS.get(tier, "#999"), f"{tier} (n={len(sub)})",
                       opacity=0.3, size=3)
    styled_layout(fig, "PCA: Contextual-Development Tiers (K-Means on PC2)", height=550, width=800)
    fig.update_xaxes(title_text="PC1 (Volume)")
    fig.update_yaxes(title_text="PC2 (Contextual)")
    fig.write_image(OUTPUT / "fig09_pca_tiers.png", scale=2)
    print("  Fig 09 saved")

    # ══════════════════════════════════════════════════════════════════════════
    # SAVE ALL OUTPUTS
    # ══════════════════════════════════════════════════════════════════════════
    all_cls.to_csv(OUTPUT / "classification_results.csv", index=False)
    all_imp.to_csv(OUTPUT / "feature_importances.csv", index=False)
    all_tiers.to_csv(OUTPUT / "nonlinearity_results.csv", index=False)
    (OUTPUT / "qc_log.json").write_text(json.dumps(qc_log, indent=2, default=str))

    # Partial correlations
    partial_summary = []
    for group, data in partial_results.items():
        for feat, vals in data["partials"].items():
            partial_summary.append({"group": group, "feature": feat,
                                     "raw_r": vals["r_raw"], "partial_r": vals["r"], "p": vals["p"]})
    pd.DataFrame(partial_summary).to_csv(OUTPUT / "velocity_partial_correlations.csv", index=False)

    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n{'='*90}")
    print(f"FINAL ANALYSIS COMPLETE — {elapsed:.0f}s")
    print(f"{'='*90}")
    print(f"Output: {OUTPUT}")
    print(f"Figures: 9")
    print(f"Tables: 4 CSV")


if __name__ == "__main__":
    main()
