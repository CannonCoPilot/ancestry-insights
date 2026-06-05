"""Phase 4: Subsampling & Data Partitioning
Apply exclusions, segment population, draw T=10 stratified subsamples, train/test splits.
Run after Phases 1-3. Outputs: data/subsamples/*.parquet, outputs/phase4/ reports.
"""
import duckdb
import pandas as pd
import numpy as np
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "familysearch.duckdb"
SUBSAMPLE_DIR = PROJECT_ROOT / "data" / "subsamples"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "phase4"
SUBSAMPLE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

T = 10          # Number of subsamples
N_PER = 5000    # Target size per subsample
FLOOR = 15      # Cochran floor per stratum
BASE_SEED = 42

qc_log = []

def log_qc(step, metric, value, note=""):
    entry = {"step": step, "metric": metric, "value": value, "note": note,
             "timestamp": datetime.now().isoformat()}
    qc_log.append(entry)
    print(f"  [{step}] {metric} = {value}  {note}")


def main():
    print("Phase 4: Subsampling & Data Partitioning")
    con = duckdb.connect(str(DB_PATH))

    try:
        total_raw = con.execute("SELECT COUNT(*) FROM users_features").fetchone()[0]
        print(f"Source: users_features ({total_raw:,} rows)")

        # ═══ Step 4.1: Apply exclusions ═══
        print("\n=== Step 4.1: Exclusions ===")
        mnar_count = con.execute("SELECT COUNT(*) FROM users_features WHERE is_mnar = TRUE").fetchone()[0]
        short_tenure = con.execute("SELECT COUNT(*) FROM users_features WHERE is_mnar = FALSE AND tenure_days < 31").fetchone()[0]
        log_qc("4.1", "mnar_excluded", mnar_count, f"{mnar_count/total_raw*100:.1f}%")
        log_qc("4.1", "short_tenure_excluded", short_tenure, f"{short_tenure/total_raw*100:.1f}%")

        after_exclusion = total_raw - mnar_count - short_tenure
        log_qc("4.1", "after_exclusions", after_exclusion)

        # ═══ Step 4.2: Activity-based pre-segmentation ═══
        print("\n=== Step 4.2: Pre-Segmentation ===")

        # Add segment column if not exists
        try:
            con.execute("ALTER TABLE users_features ADD COLUMN activity_segment VARCHAR")
        except Exception:
            pass

        con.execute("""
            UPDATE users_features SET activity_segment = CASE
                WHEN is_mnar = TRUE THEN 'A_MNAR'
                WHEN tenure_days < 31 THEN 'X_SHORT_TENURE'
                WHEN COALESCE(DAYS_LOGGING_IN, 0) = 0 AND activity_breadth = 0 THEN 'B_NO_ACTIVITY'
                WHEN COALESCE(DAYS_LOGGING_IN, 0) = 0 AND activity_breadth > 0 THEN 'C_NONLOGIN_CONTRIB'
                WHEN COALESCE(DAYS_LOGGING_IN, 0) = 1 AND (COALESCE(TREE_EDITS, 0) = 0 AND COALESCE(TOTAL_NAMES_ADDED, 0) = 0 AND COALESCE(SOURCES_ADDED, 0) = 0) THEN 'D_SINGLE_BROWSE'
                WHEN COALESCE(DAYS_LOGGING_IN, 0) <= 2 THEN 'E_LIGHT'
                WHEN COALESCE(DAYS_LOGGING_IN, 0) <= 10 THEN 'F_MODERATE'
                WHEN COALESCE(DAYS_LOGGING_IN, 0) <= 50 THEN 'G_REGULAR'
                ELSE 'H_POWER'
            END
        """)

        segments = con.execute("""
            SELECT activity_segment, COUNT(*) as n FROM users_features
            GROUP BY activity_segment ORDER BY activity_segment
        """).fetchall()
        for seg, n in segments:
            log_qc("4.2", f"segment:{seg}", n, f"{n/total_raw*100:.1f}%")

        # ═══ Step 4.3: Define Tier D analytical population ═══
        print("\n=== Step 4.3: Tier D Analytical Population ===")

        # Tier D: has login + tree edits + names + all 3 dates
        tier_d_sql = """
            is_mnar = FALSE
            AND tenure_days >= 31
            AND COALESCE(DAYS_LOGGING_IN, 0) > 0
            AND COALESCE(TREE_EDITS, 0) > 0
            AND COALESCE(TOTAL_NAMES_ADDED, 0) > 0
            AND earliest_login_date IS NOT NULL
            AND earliest_tree_edit_date IS NOT NULL
            AND earliest_name_date IS NOT NULL
        """

        tier_d_count = con.execute(f"SELECT COUNT(*) FROM users_features WHERE {tier_d_sql}").fetchone()[0]
        log_qc("4.3", "tier_d_count", tier_d_count, f"{tier_d_count/total_raw*100:.1f}%")

        # Also count other segments for the report
        seg_c = con.execute("SELECT COUNT(*) FROM users_features WHERE activity_segment = 'C_NONLOGIN_CONTRIB'").fetchone()[0]
        seg_d = con.execute("SELECT COUNT(*) FROM users_features WHERE activity_segment = 'D_SINGLE_BROWSE'").fetchone()[0]
        log_qc("4.3", "nonlogin_contributors", seg_c)
        log_qc("4.3", "single_browse", seg_d)

        # ═══ Step 4.4: Draw T=10 stratified subsamples ═══
        print("\n=== Step 4.4: Drawing Subsamples ===")

        # Load Tier D population into pandas for sampling
        tier_d_df = con.execute(f"""
            SELECT f.*, e.gdp_per_capita_ppp, e.hdi, e.pct_christian,
                   e.govt_restrictions_index, e.social_hostilities_index,
                   e.lds_membership, e.lds_members_per_capita, e.gepi,
                   e.pct_relig_important, e.religious_diversity_index
            FROM users_features f
            LEFT JOIN country_enrichment e ON f.iso3_code = e.iso3_code
            WHERE {tier_d_sql}
        """).df()

        log_qc("4.4", "tier_d_loaded", len(tier_d_df))

        # Create stratification variable: country_cluster × region
        tier_d_df["stratum"] = tier_d_df["country_cluster"].fillna("Unknown") + "|" + tier_d_df["USER_WORLD_REGION"].fillna("Unknown")

        strata_counts = tier_d_df["stratum"].value_counts()
        log_qc("4.4", "distinct_strata", len(strata_counts))

        # Pool tiny strata (< FLOOR) into "Other"
        small_strata = strata_counts[strata_counts < FLOOR].index.tolist()
        if small_strata:
            tier_d_df.loc[tier_d_df["stratum"].isin(small_strata), "stratum"] = "Other|Pooled"
            log_qc("4.4", "strata_pooled", len(small_strata))

        strata_final = tier_d_df["stratum"].value_counts()
        log_qc("4.4", "final_strata", len(strata_final))

        # Clear any partial registry entries from prior failed runs
        con.execute("DELETE FROM experiment_registry WHERE phase = 'phase4'")

        # Draw subsamples
        for t in range(1, T + 1):
            seed = BASE_SEED + t
            rng = np.random.RandomState(seed)

            # Proportional allocation with floor
            samples = []
            total_pop = len(tier_d_df)
            for stratum, count in strata_final.items():
                n_draw = max(FLOOR, int(round(count / total_pop * N_PER)))
                n_draw = min(n_draw, count)
                stratum_df = tier_d_df[tier_d_df["stratum"] == stratum]
                samples.append(stratum_df.sample(n=n_draw, random_state=rng))

            subsample = pd.concat(samples, ignore_index=True)

            # Trim to target size if over
            if len(subsample) > N_PER + 100:
                subsample = subsample.sample(n=N_PER, random_state=rng).reset_index(drop=True)

            # ═══ Step 4.5: Train/test split ═══
            # Stratified by persist_tertile
            subsample["split"] = "test"
            for tertile in subsample["persist_tertile"].dropna().unique():
                mask = subsample["persist_tertile"] == tertile
                tertile_idx = subsample[mask].index.tolist()
                n_train = int(len(tertile_idx) * 0.7)
                train_idx = rng.choice(tertile_idx, size=n_train, replace=False)
                subsample.loc[train_idx, "split"] = "train"
            # Handle null persist_tertile (shouldn't exist in Tier D, but just in case)
            null_mask = subsample["persist_tertile"].isna()
            if null_mask.sum() > 0:
                null_idx = subsample[null_mask].index.tolist()
                n_train = int(len(null_idx) * 0.7)
                train_idx = rng.choice(null_idx, size=n_train, replace=False)
                subsample.loc[train_idx, "split"] = "train"

            n_train = (subsample["split"] == "train").sum()
            n_test = (subsample["split"] == "test").sum()

            # ═══ Step 4.6: Export Parquet ═══
            out_path = SUBSAMPLE_DIR / f"subsample_{t:02d}.parquet"
            subsample.drop(columns=["stratum"], errors="ignore").to_parquet(out_path, index=False)

            # ═══ Step 4.7: Log metadata ═══
            persist_rate = (subsample["persist_median"] == 1).mean() * 100 if "persist_median" in subsample.columns else None
            mean_tenure = subsample["tenure_days"].mean()

            log_qc("4.4", f"subsample_{t:02d}", f"n={len(subsample)}, train={n_train}, test={n_test}, seed={seed}")

            # Register in DB
            con.execute("""
                INSERT INTO experiment_registry (experiment_id, phase, subsample_id, seed, n_rows, n_train, n_test, exclusions, parameters)
                VALUES (?, 'phase4', ?, ?, ?, ?, ?, 'MNAR + tenure<31 + Tier D filter', ?)
            """, [t, t, int(seed), int(len(subsample)), int(n_train), int(n_test),
                  json.dumps({"persist_rate": round(float(persist_rate), 1) if persist_rate else None,
                              "mean_tenure": round(float(mean_tenure), 1),
                              "n_strata": int(len(strata_final))})])

            print(f"  Subsample {t:02d}: n={len(subsample):,} (train={n_train}, test={n_test}), seed={seed}")

        # Verify all parquet files
        print("\n=== Step 4.6: Verify Exports ===")
        for t in range(1, T + 1):
            p = SUBSAMPLE_DIR / f"subsample_{t:02d}.parquet"
            df_check = pd.read_parquet(p)
            log_qc("4.6", f"verify_{t:02d}", f"{len(df_check)} rows, {len(df_check.columns)} cols")

        # Persist QC log
        for entry in qc_log:
            con.execute("""
                INSERT INTO qc_log (step, metric, value, note, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, [entry["step"], entry["metric"], str(entry["value"]), entry.get("note", ""),
                  entry["timestamp"]])

        # Write report
        report = [
            "# Phase 4: Subsampling Report",
            f"\n**Generated**: {datetime.now().isoformat()}",
            f"**Tier D Population**: {tier_d_count:,} users ({tier_d_count/total_raw*100:.1f}%)",
            f"**Subsamples**: T={T}, n≈{N_PER} each",
            f"**Stratification**: country_cluster × region, floor={FLOOR}",
            "\n---\n",
            "## QC Log\n",
            "| Step | Metric | Value | Note |",
            "|------|--------|-------|------|",
        ]
        for entry in qc_log:
            val = str(entry["value"])[:80]
            report.append(f"| {entry['step']} | {entry['metric']} | {val} | {entry.get('note', '')} |")

        (OUTPUT_DIR / "subsampling_report.md").write_text("\n".join(report))
        (OUTPUT_DIR / "qc_log.json").write_text(json.dumps(qc_log, indent=2, default=str))

        print(f"\n=== Phase 4 Complete ===")
        print(f"Tier D population: {tier_d_count:,}")
        print(f"Subsamples: {T} × ~{N_PER} exported to {SUBSAMPLE_DIR}")

    finally:
        con.close()


if __name__ == "__main__":
    main()
