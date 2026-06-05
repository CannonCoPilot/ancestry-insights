"""Account Type Split Analysis: Independent Member vs Public pipelines.
Runs Phase 5b-style classification + Phase 6b clustering + nonlinearity test
independently for Member and Public account types.
Outputs: outputs/acct_split/
"""
import pandas as pd
import numpy as np
import json
import warnings
from pathlib import Path
from datetime import datetime
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.metrics import (accuracy_score, precision_score, recall_score,
                             f1_score, roc_auc_score, silhouette_score)
from scipy import stats
from scipy.optimize import curve_fit
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import duckdb

warnings.filterwarnings("ignore")

PROJECT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT / "data" / "familysearch.duckdb"
OUTPUT = PROJECT / "outputs" / "acct_split"
OUTPUT.mkdir(parents=True, exist_ok=True)

VELOCITY = ["days_to_first_login", "days_login_to_tree_edit", "days_login_to_name",
            "days_to_first_tree_edit", "days_to_first_name", "activation_speed"]
VOLUME = ["log_logins_pw", "log_tree_edits_pw", "log_names_pw", "log_sources_pw",
          "logins_90d", "tree_edits_90d", "names_90d", "sources_90d"]
SEQUENCING = ["activity_breadth", "funnel_stage", "has_sources", "has_memories",
              "has_record_edits", "has_get_involved"]
CONTEXTUAL_CONT = ["user_age", "gdp_per_capita_ppp", "hdi", "pct_christian",
                   "govt_restrictions_index", "social_hostilities_index",
                   "lds_members_per_capita", "religious_diversity_index"]
CONTEXTUAL_CAT = ["country_cluster", "age_group"]

BEHAVIORAL = VELOCITY + VOLUME + SEQUENCING
ENRICHMENT = ["gdp_per_capita_ppp", "hdi", "pct_christian", "govt_restrictions_index",
              "social_hostilities_index", "lds_members_per_capita", "religious_diversity_index", "gepi"]
ALL_FEATURES = BEHAVIORAL + ENRICHMENT + ["user_age"]

CLUSTER_FEATURES = [
    "logins_90d", "log_logins_pw", "activity_breadth", "funnel_stage",
    "log_sources_pw", "sources_90d", "log_tree_edits_pw", "tree_edits_90d",
    "names_90d", "log_names_pw", "has_sources", "has_memories",
    "days_to_first_login", "activation_speed", "user_age",
]

CONSTRUCT_MAP = {}
for f in VELOCITY: CONSTRUCT_MAP[f] = "Velocity"
for f in VOLUME: CONSTRUCT_MAP[f] = "Volume"
for f in SEQUENCING: CONSTRUCT_MAP[f] = "Sequencing"
for f in CONTEXTUAL_CONT + CONTEXTUAL_CAT: CONSTRUCT_MAP[f] = "Contextual"

qc_log = []

def log_qc(step, metric, value, note=""):
    qc_log.append({"step": step, "metric": metric, "value": value, "note": note,
                    "timestamp": datetime.now().isoformat()})
    print(f"  [{step}] {metric} = {value}  {note}")


def prepare_features(df, cont_list, cat_list=None):
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
    return np.hstack(parts) if parts else np.zeros((len(df), 1)), names


def eval_model(y_true, y_pred, y_prob):
    return {"accuracy": accuracy_score(y_true, y_pred),
            "precision": precision_score(y_true, y_pred, zero_division=0),
            "recall": recall_score(y_true, y_pred, zero_division=0),
            "f1": f1_score(y_true, y_pred, zero_division=0),
            "auc": roc_auc_score(y_true, y_prob) if len(np.unique(y_true)) > 1 else 0.5}


def run_classification(subsamples, label, n_per):
    """Run 6-block classification on a set of subsamples."""
    all_results = []
    all_importances = []

    for t, df in enumerate(subsamples, 1):
        median_c = df["persistence_c"].median()
        df["y"] = (df["persistence_c"] >= median_c).astype(int)

        rng = np.random.RandomState(42 + t)
        df["split"] = "test"
        train_idx = rng.choice(df.index, size=int(len(df) * 0.7), replace=False)
        df.loc[train_idx, "split"] = "train"

        train, test = df[df["split"] == "train"], df[df["split"] == "test"]
        ytr, yte = train["y"].values, test["y"].values

        if t == 1:
            log_qc(f"{label}", "median_persist_c", round(median_c, 4))
            log_qc(f"{label}", "n_per_subsample", len(df))
            log_qc(f"{label}", "class_balance", f"0:{(ytr==0).sum()}, 1:{(ytr==1).sum()}")

        blocks = {
            "B4_H1": (VELOCITY + VOLUME + SEQUENCING, []),
            "B5_H0": (CONTEXTUAL_CONT, CONTEXTUAL_CAT),
            "B6_Full": (VELOCITY + VOLUME + SEQUENCING + CONTEXTUAL_CONT, CONTEXTUAL_CAT),
        }

        for bname, (cont, cat) in blocks.items():
            Xtr, fnames = prepare_features(train, cont, cat)
            Xte, _ = prepare_features(test, cont, cat)
            scaler = StandardScaler()
            Xtr_s, Xte_s = scaler.fit_transform(Xtr), scaler.transform(Xte)

            # RF only (fastest, most robust)
            rf = RandomForestClassifier(n_estimators=300, random_state=42,
                                        class_weight="balanced", n_jobs=-1)
            rf.fit(Xtr, ytr)
            r = eval_model(yte, rf.predict(Xte), rf.predict_proba(Xte)[:, 1])
            r.update({"block": bname, "model": "RF", "subsample": t, "group": label})
            if bname == "B6_Full":
                for feat, imp in zip(fnames, rf.feature_importances_):
                    all_importances.append({"feature": feat, "importance": imp, "group": label, "subsample": t})
            all_results.append(r)

    return pd.DataFrame(all_results), pd.DataFrame(all_importances)


def run_nonlinearity(df, label):
    """Run tier segmentation + nonlinearity test."""
    X = StandardScaler().fit_transform(df[ALL_FEATURES].fillna(0))
    pca = PCA(n_components=3)
    X_pca = pca.fit_transform(X)
    df = df.copy()
    df["PC1"], df["PC2"] = X_pca[:, 0], X_pca[:, 1]

    km = KMeans(n_clusters=5, random_state=42, n_init=10)
    df["tier_raw"] = km.fit_predict(df[["PC2"]].values)
    centroid_order = np.argsort(km.cluster_centers_.flatten())
    label_map = {old: new for new, old in enumerate(centroid_order)}
    df["tier"] = df["tier_raw"].map(label_map)
    df["tier_label"] = df["tier"].map(lambda x: f"T{x+1}")

    def log_model(x, a, b):
        return a * np.log(x + 1) + b

    tier_results = []
    for tier_label in sorted(df["tier_label"].unique()):
        sub = df[df["tier_label"] == tier_label]
        x, y = sub["PC1"].values, sub["persistence_c"].values
        n = len(sub)
        if n < 30:
            continue

        _, _, r_lin, _, _ = stats.linregress(x, y)
        r2_lin = r_lin**2

        coeffs = np.polyfit(x, y, 2)
        y_pred_q = np.polyval(coeffs, x)
        ss_tot = np.sum((y - y.mean())**2)
        r2_quad = 1 - np.sum((y - y_pred_q)**2) / ss_tot if ss_tot > 0 else 0

        x_s = x - x.min() + 0.1
        try:
            popt, _ = curve_fit(log_model, x_s, y, p0=[0.05, 0.2], maxfev=5000)
            r2_log = 1 - np.sum((y - log_model(x_s, *popt))**2) / ss_tot if ss_tot > 0 else 0
        except:
            r2_log = r2_lin

        best_nonlin = max(r2_quad, r2_log)
        delta_r2 = best_nonlin - r2_lin
        best_model = "Log" if r2_log > r2_quad else "Quad"

        tier_results.append({
            "group": label, "tier": tier_label, "n": n,
            "r2_lin": round(r2_lin, 4), "r2_quad": round(r2_quad, 4), "r2_log": round(r2_log, 4),
            "delta_r2": round(delta_r2, 4), "best_model": best_model,
            "quad_coeff": round(coeffs[0], 6),
            "lin_slope": round(stats.linregress(x, y)[0], 4),
        })

    return df, pd.DataFrame(tier_results)


def main():
    print("=" * 80)
    print("ACCOUNT TYPE SPLIT ANALYSIS: Member vs Public Independent Pipelines")
    print("=" * 80)

    # ═══ Draw independent subsamples from full Tier D population ═══
    print("\n=== Drawing subsamples from DuckDB ===")
    con = duckdb.connect(str(DB_PATH), read_only=True)

    tier_d_sql = """
        f.is_mnar = FALSE AND f.tenure_days >= 31
        AND COALESCE(f.DAYS_LOGGING_IN, 0) >= 2
        AND COALESCE(f.TREE_EDITS, 0) > 0
        AND COALESCE(f.TOTAL_NAMES_ADDED, 0) > 0
        AND f.earliest_login_date IS NOT NULL
        AND f.earliest_tree_edit_date IS NOT NULL
        AND f.earliest_name_date IS NOT NULL
    """

    full_df = con.execute(f"""
        SELECT f.*, e.gdp_per_capita_ppp, e.hdi, e.pct_christian,
               e.govt_restrictions_index, e.social_hostilities_index,
               e.lds_membership, e.lds_members_per_capita, e.gepi,
               e.pct_relig_important, e.religious_diversity_index
        FROM users_features f
        LEFT JOIN country_enrichment e ON f.iso3_code = e.iso3_code
        WHERE {tier_d_sql}
    """).df()
    con.close()

    members_all = full_df[full_df["ACCOUNT_TYPE"] == "Member"].reset_index(drop=True)
    public_all = full_df[full_df["ACCOUNT_TYPE"] == "Public"].reset_index(drop=True)

    print(f"Member contributors: {len(members_all):,}")
    print(f"Public contributors: {len(public_all):,}")

    # Draw T=5 subsamples
    T = 5
    member_subs = []
    public_subs = []
    for t in range(T):
        rng = np.random.RandomState(100 + t)
        member_subs.append(members_all.sample(n=2500, random_state=rng).reset_index(drop=True))
        public_subs.append(public_all.sample(n=5000, random_state=rng).reset_index(drop=True))

    # ═══ CLASSIFICATION ═══
    print(f"\n{'='*80}")
    print("CLASSIFICATION: Member vs Public")
    print(f"{'='*80}")

    mem_results, mem_imp = run_classification(member_subs, "Member", 2500)
    pub_results, pub_imp = run_classification(public_subs, "Public", 5000)

    all_results = pd.concat([mem_results, pub_results], ignore_index=True)

    # Aggregate
    agg = all_results.groupby(["group", "block"]).agg(
        mean_auc=("auc", "mean"), std_auc=("auc", "std"),
        mean_f1=("f1", "mean"),
    ).round(4)

    print(f"\n{'='*80}")
    print("BLOCK COMPARISON: Member vs Public")
    print(f"{'='*80}")
    print(agg.to_string())

    # Delta analysis
    for group in ["Member", "Public"]:
        g = all_results[all_results["group"] == group]
        b4 = g[g["block"] == "B4_H1"]["auc"].mean()
        b5 = g[g["block"] == "B5_H0"]["auc"].mean()
        b6 = g[g["block"] == "B6_Full"]["auc"].mean()
        log_qc(f"{group}", "B4_auc", round(b4, 4))
        log_qc(f"{group}", "B5_auc", round(b5, 4))
        log_qc(f"{group}", "B6_auc", round(b6, 4))
        log_qc(f"{group}", "delta_H1", round(b6 - b5, 4))
        log_qc(f"{group}", "delta_H0", round(b6 - b4, 4))

    # ═══ NONLINEARITY TEST ═══
    print(f"\n{'='*80}")
    print("NONLINEARITY: Member vs Public Tier Gradients")
    print(f"{'='*80}")

    # Use first subsample for each (larger analysis)
    mem_df, mem_tiers = run_nonlinearity(member_subs[0], "Member")
    pub_df, pub_tiers = run_nonlinearity(public_subs[0], "Public")

    all_tiers = pd.concat([mem_tiers, pub_tiers], ignore_index=True)

    print(f"\n{'Group':<8} {'Tier':<6} {'n':>6} {'Lin R²':>8} {'Quad R²':>8} {'Log R²':>8} {'ΔR²':>8} {'Best':>6} {'Slope':>8}")
    print("-" * 75)
    for _, r in all_tiers.iterrows():
        print(f"{r['group']:<8} {r['tier']:<6} {r['n']:>6} {r['r2_lin']:>8.4f} {r['r2_quad']:>8.4f} "
              f"{r['r2_log']:>8.4f} {r['delta_r2']:>8.4f} {r['best_model']:>6} {r['lin_slope']:>8.4f}")

    # ═══ FIGURES ═══
    print(f"\n{'='*80}")
    print("GENERATING FIGURES")
    print(f"{'='*80}")

    # Fig 1: Block AUC comparison (Member vs Public side by side)
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Member (n=2,500/sub)", "Public (n=5,000/sub)"),
                         shared_yaxes=True)
    block_labels = {"B4_H1": "B4: H1\nEngagement", "B5_H0": "B5: H0\nContext", "B6_Full": "B6: Full"}
    block_colors = {"B4_H1": "#3b8520", "B5_H0": "#c0392b", "B6_Full": "#1a4314"}

    for col_idx, group in enumerate(["Member", "Public"], 1):
        g_agg = agg.loc[group]
        for block in ["B4_H1", "B5_H0", "B6_Full"]:
            if block in g_agg.index:
                fig.add_trace(go.Bar(
                    x=[block_labels[block]], y=[g_agg.loc[block, "mean_auc"]],
                    marker_color=block_colors[block], name=block if col_idx == 1 else None,
                    showlegend=(col_idx == 1),
                    error_y=dict(type="data", array=[g_agg.loc[block, "std_auc"]], visible=True),
                    text=[f"{g_agg.loc[block, 'mean_auc']:.3f}"], textposition="outside",
                ), row=1, col=col_idx)

    fig.update_layout(title="H1 vs H0: Member vs Public (RF, T=5 subsamples)",
                      yaxis_title="AUC-ROC", yaxis_range=[0.4, 1.05],
                      height=450, width=900, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.write_image(OUTPUT / "fig_block_auc_member_vs_public.png", scale=2)
    print("  fig_block_auc done")

    # Fig 2: Per-tier gradient — Member vs Public
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Member", "Public"), shared_yaxes=True)
    tier_colors = {"T1": "#1a4314", "T2": "#3b8520", "T3": "#2980b9", "T4": "#e67e22", "T5": "#c0392b"}

    for col_idx, (df_plot, group) in enumerate([(mem_df, "Member"), (pub_df, "Public")], 1):
        for tier in sorted(df_plot["tier_label"].unique()):
            sub = df_plot[df_plot["tier_label"] == tier]
            x, y = sub["PC1"].values, sub["persistence_c"].values
            color = tier_colors.get(tier, "#999")

            fig.add_trace(go.Scatter(x=x, y=y, mode="markers",
                                      marker=dict(size=3, color=color, opacity=0.15),
                                      showlegend=(col_idx == 1), name=f"{tier} (n={len(sub)})"),
                          row=1, col=col_idx)
            # Regression line
            if len(sub) >= 30:
                slope, intercept, _, _, _ = stats.linregress(x, y)
                x_line = np.linspace(x.min(), x.max(), 50)
                fig.add_trace(go.Scatter(x=x_line, y=slope * x_line + intercept, mode="lines",
                                          line=dict(color=color, width=2.5), showlegend=False),
                              row=1, col=col_idx)

    fig.update_layout(title="Persistence Gradient by Tier: Member vs Public",
                      height=500, width=1100, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(title_text="PC1 (Volume)")
    fig.update_yaxes(title_text="Persistence C", col=1)
    fig.write_image(OUTPUT / "fig_gradient_member_vs_public.png", scale=2)
    print("  fig_gradient done")

    # Fig 3: ΔR² comparison (nonlinearity by tier, Member vs Public)
    fig = go.Figure()
    for group, color, offset in [("Member", "#8e44ad", -0.15), ("Public", "#2980b9", 0.15)]:
        g_tiers = all_tiers[all_tiers["group"] == group]
        fig.add_trace(go.Bar(
            x=[f"{r['tier']}" for _, r in g_tiers.iterrows()],
            y=g_tiers["delta_r2"].values,
            name=group, marker_color=color,
            text=[f"{v:.3f}" for v in g_tiers["delta_r2"]], textposition="outside",
        ))
    fig.update_layout(barmode="group",
                      title="Nonlinearity (ΔR²) by Tier: Member vs Public",
                      yaxis_title="ΔR² (Best Nonlinear - Linear)",
                      height=450, width=800, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.write_image(OUTPUT / "fig_nonlinearity_member_vs_public.png", scale=2)
    print("  fig_nonlinearity done")

    # Fig 4: PCA scatter Member vs Public colored by persistence
    fig = make_subplots(rows=1, cols=2, subplot_titles=("Member (n=2,500)", "Public (n=5,000)"))
    for col_idx, (df_plot, group) in enumerate([(mem_df, "Member"), (pub_df, "Public")], 1):
        fig.add_trace(go.Scatter(
            x=df_plot["PC1"], y=df_plot["PC2"], mode="markers",
            marker=dict(size=3, color=df_plot["persistence_c"], colorscale="RdYlGn",
                        opacity=0.4, showscale=(col_idx == 2)),
            showlegend=False,
        ), row=1, col=col_idx)
    fig.update_layout(title="PCA Feature Space: Member vs Public (colored by Persistence)",
                      height=500, width=1100, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.write_image(OUTPUT / "fig_pca_member_vs_public.png", scale=2)
    print("  fig_pca done")

    # Fig 5: Feature importance comparison (RF full model)
    all_imp = pd.concat([mem_imp, pub_imp], ignore_index=True)
    imp_agg = all_imp.groupby(["group", "feature"])["importance"].mean().reset_index()

    top_feats_pub = imp_agg[imp_agg["group"] == "Public"].nlargest(12, "importance")["feature"].tolist()
    top_feats_mem = imp_agg[imp_agg["group"] == "Member"].nlargest(12, "importance")["feature"].tolist()
    all_top = list(dict.fromkeys(top_feats_pub + top_feats_mem))[:15]

    fig = go.Figure()
    for group, color in [("Member", "#8e44ad"), ("Public", "#2980b9")]:
        g_imp = imp_agg[imp_agg["group"] == group].set_index("feature")
        vals = [g_imp.loc[f, "importance"] if f in g_imp.index else 0 for f in all_top]
        fig.add_trace(go.Bar(x=all_top, y=vals, name=group, marker_color=color))
    fig.update_layout(barmode="group", title="Top Feature Importances: Member vs Public (RF Full Model)",
                      yaxis_title="Mean Importance", height=450, width=1000,
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      xaxis_tickangle=30)
    fig.write_image(OUTPUT / "fig_importance_member_vs_public.png", scale=2)
    print("  fig_importance done")

    # ═══ SAVE ═══
    all_results.to_csv(OUTPUT / "classification_results.csv", index=False)
    all_tiers.to_csv(OUTPUT / "nonlinearity_results.csv", index=False)
    all_imp.to_csv(OUTPUT / "feature_importances.csv", index=False)
    (OUTPUT / "qc_log.json").write_text(json.dumps(qc_log, indent=2, default=str))

    # ═══ REPORT ═══
    report_lines = [
        "# Account Type Split Analysis: Member vs Public",
        f"\n**Date**: {datetime.now().isoformat()}",
        f"**Design**: Member T=5 × 2,500 | Public T=5 × 5,000",
        f"**Purpose**: Confirm H1 findings hold independently within each account type; "
        "test whether LDS membership confounds the tier gradient pattern.",
        "\n---\n",
        "## Classification Results (RF, T=5)\n",
        agg.to_markdown(),
        "\n## Nonlinearity by Tier\n",
        all_tiers.to_markdown(index=False),
        "\n## QC Log\n",
        "| Step | Metric | Value | Note |",
        "|------|--------|-------|------|",
    ]
    for entry in qc_log:
        report_lines.append(f"| {entry['step']} | {entry['metric']} | {str(entry['value'])[:60]} | {entry.get('note', '')} |")

    (OUTPUT / "acct_split_report.md").write_text("\n".join(report_lines))

    print(f"\n{'='*80}")
    print("ANALYSIS COMPLETE")
    print(f"{'='*80}")
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
