"""Phase 2: Feature Engineering
Derives Velocity, Volume, Sequencing, and Persistence features from users_clean.
Run once after Phase 1. Outputs: users_features table in DuckDB, outputs/phase2/ reports.
"""
import duckdb
import json
import numpy as np
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "familysearch.duckdb"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "phase2"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# The 11 activity columns that define the MNAR block
ACTIVITY_COLS = [
    "DAYS_LOGGING_IN", "SOURCES_ADDED", "DAYS_ADDING_SOURCES",
    "MEMORIES_ADDED", "DAYS_ADDING_MEMORIES",
    "GET_INVOLVED_ITEMS_REVIEWED", "DAYS_REVIEWING_GET_INVOLVED_ITEMS",
    "RECORD_EDITS", "DAYS_EDITING_RECORDS",
    "TREE_EDITS", "DAYS_EDITING_TREES",
]

# Countries in each cluster (from methodology report Section 4)
CLUSTER_HIGH_LDS = [
    "Mexico", "Brazil", "Chile", "Peru", "Argentina", "Philippines",
    "Colombia", "Ecuador", "Bolivia", "Guatemala", "Honduras",
    "El Salvador", "Nicaragua", "Costa Rica", "Panama",
    "Dominican Republic", "Paraguay", "Uruguay", "Venezuela",
]
CLUSTER_MOD_LOW_LDS = [
    "United Kingdom", "Germany", "France", "Australia", "Canada",
    "Italy", "Spain", "Portugal", "Ireland", "New Zealand",
    "Sweden", "Norway", "Denmark", "Finland", "Netherlands",
    "Belgium", "Switzerland", "Austria",
]
CLUSTER_LOW_HIGH_DEV = [
    "Japan", "South Korea", "Taiwan", "Singapore",
]
CLUSTER_LOW_DEVELOPING = [
    "Egypt", "India", "Nigeria", "Indonesia", "Pakistan",
    "Bangladesh", "Ghana", "Kenya", "South Africa",
]

qc_log = []

def log_qc(step: str, metric: str, value, note: str = ""):
    entry = {"step": step, "metric": metric, "value": value, "note": note,
             "timestamp": datetime.now().isoformat()}
    qc_log.append(entry)
    print(f"  [{step}] {metric} = {value}  {note}")


def main():
    print("Phase 2: Feature Engineering")
    con = duckdb.connect(str(DB_PATH))

    try:
        total = con.execute("SELECT COUNT(*) FROM users_clean").fetchone()[0]
        print(f"Source: users_clean ({total:,} rows)")

        # ═══════════════════════════════════════════════════════════════
        # Build the full feature engineering SQL as a single CREATE TABLE
        # This is the most efficient approach for DuckDB — one pass over the data
        # ═══════════════════════════════════════════════════════════════

        print("\n=== Building users_features table (single-pass SQL) ===")
        con.execute("DROP TABLE IF EXISTS users_features")

        # Build country cluster CASE expression
        def sql_in_list(countries):
            return ", ".join([f"'{c}'" for c in countries])

        sql = f"""
        CREATE TABLE users_features AS
        SELECT
            c.*,

            -- ═══════════════════════════════════════════════════
            -- STEP 2.1: VELOCITY FEATURES
            -- Days between successive milestones (NULL if either date missing)
            -- ═══════════════════════════════════════════════════

            -- Account creation → first login
            CASE WHEN c.earliest_login_date IS NOT NULL
                 THEN GREATEST(0, c.earliest_login_date - c.account_create_date)
                 ELSE NULL END AS days_to_first_login,

            -- First login → first tree edit
            CASE WHEN c.earliest_login_date IS NOT NULL AND c.earliest_tree_edit_date IS NOT NULL
                 THEN GREATEST(0, c.earliest_tree_edit_date - c.earliest_login_date)
                 ELSE NULL END AS days_login_to_tree_edit,

            -- First login → first name contribution
            CASE WHEN c.earliest_login_date IS NOT NULL AND c.earliest_name_date IS NOT NULL
                 THEN GREATEST(0, c.earliest_name_date - c.earliest_login_date)
                 ELSE NULL END AS days_login_to_name,

            -- First tree edit → first source (Tier E only — sparse)
            CASE WHEN c.earliest_tree_edit_date IS NOT NULL AND c.earliest_source_date IS NOT NULL
                 THEN GREATEST(0, c.earliest_source_date - c.earliest_tree_edit_date)
                 ELSE NULL END AS days_tree_to_source,

            -- Account creation → first tree edit (composite velocity)
            CASE WHEN c.earliest_tree_edit_date IS NOT NULL
                 THEN GREATEST(0, c.earliest_tree_edit_date - c.account_create_date)
                 ELSE NULL END AS days_to_first_tree_edit,

            -- Account creation → first name
            CASE WHEN c.earliest_name_date IS NOT NULL
                 THEN GREATEST(0, c.earliest_name_date - c.account_create_date)
                 ELSE NULL END AS days_to_first_name,

            -- ═══════════════════════════════════════════════════
            -- STEP 2.2: ACTIVATION VELOCITY COMPOSITE
            -- Higher = faster activation. NULL if no login date.
            -- ═══════════════════════════════════════════════════

            CASE WHEN c.earliest_login_date IS NOT NULL
                 THEN 1.0 / (1.0 + GREATEST(0, c.earliest_login_date - c.account_create_date)
                      + COALESCE(GREATEST(0, c.earliest_tree_edit_date - c.earliest_login_date), 0))
                 ELSE NULL END AS activation_speed,

            -- ═══════════════════════════════════════════════════
            -- STEP 2.3: VOLUME FEATURES (tenure-normalized per-week rates)
            -- Only for the 3 primary activities with sufficient non-zero prevalence
            -- ═══════════════════════════════════════════════════

            COALESCE(c.DAYS_LOGGING_IN, 0) / GREATEST(c.tenure_weeks, 1.0) AS logins_per_week,
            COALESCE(c.TREE_EDITS, 0) / GREATEST(c.tenure_weeks, 1.0) AS tree_edits_per_week,
            COALESCE(c.TOTAL_NAMES_ADDED, 0) / GREATEST(c.tenure_weeks, 1.0) AS names_per_week,
            COALESCE(c.SOURCES_ADDED, 0) / GREATEST(c.tenure_weeks, 1.0) AS sources_per_week,

            -- Log1p transforms
            LN(1 + COALESCE(c.DAYS_LOGGING_IN, 0) / GREATEST(c.tenure_weeks, 1.0)) AS log_logins_pw,
            LN(1 + COALESCE(c.TREE_EDITS, 0) / GREATEST(c.tenure_weeks, 1.0)) AS log_tree_edits_pw,
            LN(1 + COALESCE(c.TOTAL_NAMES_ADDED, 0) / GREATEST(c.tenure_weeks, 1.0)) AS log_names_pw,
            LN(1 + COALESCE(c.SOURCES_ADDED, 0) / GREATEST(c.tenure_weeks, 1.0)) AS log_sources_pw,

            -- Log1p of raw counts (for complementary features)
            LN(1 + COALESCE(c.DAYS_LOGGING_IN, 0)) AS log_days_logging_in,
            LN(1 + COALESCE(c.TREE_EDITS, 0)) AS log_tree_edits,
            LN(1 + COALESCE(c.TOTAL_NAMES_ADDED, 0)) AS log_names_added,
            LN(1 + COALESCE(c.SOURCES_ADDED, 0)) AS log_sources_added,

            -- ═══════════════════════════════════════════════════
            -- STEP 2.4: VOLUME FEATURES (fixed 90-day window, prorated)
            -- Approximate: prorate total count to 90-day window
            -- ═══════════════════════════════════════════════════

            COALESCE(c.DAYS_LOGGING_IN, 0) * LEAST(90.0, c.tenure_days) / GREATEST(c.tenure_days, 1.0) AS logins_90d,
            COALESCE(c.TREE_EDITS, 0) * LEAST(90.0, c.tenure_days) / GREATEST(c.tenure_days, 1.0) AS tree_edits_90d,
            COALESCE(c.TOTAL_NAMES_ADDED, 0) * LEAST(90.0, c.tenure_days) / GREATEST(c.tenure_days, 1.0) AS names_90d,
            COALESCE(c.SOURCES_ADDED, 0) * LEAST(90.0, c.tenure_days) / GREATEST(c.tenure_days, 1.0) AS sources_90d,

            -- ═══════════════════════════════════════════════════
            -- STEP 2.5: BINARY ACTIVITY FLAGS
            -- ═══════════════════════════════════════════════════

            CASE WHEN COALESCE(c.DAYS_LOGGING_IN, 0) > 0 THEN 1 ELSE 0 END AS has_login,
            CASE WHEN COALESCE(c.TREE_EDITS, 0) > 0 THEN 1 ELSE 0 END AS has_tree_edits,
            CASE WHEN COALESCE(c.TOTAL_NAMES_ADDED, 0) > 0 THEN 1 ELSE 0 END AS has_names,
            CASE WHEN COALESCE(c.SOURCES_ADDED, 0) > 0 THEN 1 ELSE 0 END AS has_sources,
            CASE WHEN COALESCE(c.MEMORIES_ADDED, 0) > 0 THEN 1 ELSE 0 END AS has_memories,
            CASE WHEN COALESCE(c.RECORD_EDITS, 0) > 0 THEN 1 ELSE 0 END AS has_record_edits,
            CASE WHEN COALESCE(c.GET_INVOLVED_ITEMS_REVIEWED, 0) > 0 THEN 1 ELSE 0 END AS has_get_involved,

            -- ═══════════════════════════════════════════════════
            -- STEP 2.6: ACTIVITY BREADTH (Sequencing construct)
            -- Count of distinct activity types with any non-zero value
            -- ═══════════════════════════════════════════════════

            (CASE WHEN COALESCE(c.DAYS_LOGGING_IN, 0) > 0 THEN 1 ELSE 0 END
             + CASE WHEN COALESCE(c.TREE_EDITS, 0) > 0 THEN 1 ELSE 0 END
             + CASE WHEN COALESCE(c.TOTAL_NAMES_ADDED, 0) > 0 THEN 1 ELSE 0 END
             + CASE WHEN COALESCE(c.SOURCES_ADDED, 0) > 0 THEN 1 ELSE 0 END
             + CASE WHEN COALESCE(c.MEMORIES_ADDED, 0) > 0 THEN 1 ELSE 0 END
             + CASE WHEN COALESCE(c.RECORD_EDITS, 0) > 0 THEN 1 ELSE 0 END
             + CASE WHEN COALESCE(c.GET_INVOLVED_ITEMS_REVIEWED, 0) > 0 THEN 1 ELSE 0 END
            ) AS activity_breadth,

            -- ═══════════════════════════════════════════════════
            -- STEP 2.8: FUNNEL STAGE (0-4 based on furthest milestone)
            -- ═══════════════════════════════════════════════════

            CASE
                WHEN COALESCE(c.RECORD_EDITS, 0) > 0 OR COALESCE(c.GET_INVOLVED_ITEMS_REVIEWED, 0) > 0 THEN 4
                WHEN COALESCE(c.SOURCES_ADDED, 0) > 0 THEN 3
                WHEN COALESCE(c.TREE_EDITS, 0) > 0 OR COALESCE(c.TOTAL_NAMES_ADDED, 0) > 0 THEN 2
                WHEN COALESCE(c.DAYS_LOGGING_IN, 0) > 0 THEN 1
                ELSE 0
            END AS funnel_stage,

            -- ═══════════════════════════════════════════════════
            -- STEP 2.9: LOGIN CONSISTENCY
            -- ═══════════════════════════════════════════════════

            COALESCE(c.DAYS_LOGGING_IN, 0) / GREATEST(c.tenure_weeks, 1.0) AS login_consistency,

            -- ═══════════════════════════════════════════════════
            -- STEP 2.10: TENURE WEIGHT (log-scaled)
            -- ═══════════════════════════════════════════════════

            LN(1 + c.tenure_days) AS tenure_weight,

            -- ═══════════════════════════════════════════════════
            -- STEP 2.11: AGE GROUPS (8 bins, age=NULL stays NULL)
            -- ═══════════════════════════════════════════════════

            CASE
                WHEN c.user_age IS NULL THEN NULL
                WHEN c.user_age <= 19 THEN '8-19'
                WHEN c.user_age <= 29 THEN '20-29'
                WHEN c.user_age <= 39 THEN '30-39'
                WHEN c.user_age <= 49 THEN '40-49'
                WHEN c.user_age <= 59 THEN '50-59'
                WHEN c.user_age <= 69 THEN '60-69'
                WHEN c.user_age <= 79 THEN '70-79'
                ELSE '80+'
            END AS age_group,

            -- ═══════════════════════════════════════════════════
            -- STEP 2.12: COUNTRY CLUSTER (5 clusters + US split)
            -- ═══════════════════════════════════════════════════

            CASE
                WHEN c.COUNTRY = 'United States' AND c.USER_AREA_NAME = 'Utah Area'
                    THEN 'High-LDS-US-Utah'
                WHEN c.COUNTRY = 'United States'
                    THEN 'Mod-Eng-US-Other'
                WHEN c.COUNTRY IN ({sql_in_list(CLUSTER_HIGH_LDS)})
                    THEN 'High-LDS-International'
                WHEN c.COUNTRY IN ({sql_in_list(CLUSTER_MOD_LOW_LDS)})
                    THEN 'Mod-Eng-Low-LDS'
                WHEN c.COUNTRY IN ({sql_in_list(CLUSTER_LOW_HIGH_DEV)})
                    THEN 'Low-Eng-High-Dev'
                WHEN c.COUNTRY IN ({sql_in_list(CLUSTER_LOW_DEVELOPING)})
                    THEN 'Low-Eng-Developing'
                ELSE 'Micro-Other'
            END AS country_cluster,

            -- ═══════════════════════════════════════════════════
            -- STEP 2.13: PERSISTENCE SCORES (3 definitions)
            -- ═══════════════════════════════════════════════════

            -- Definition A: Login Consistency Ratio
            COALESCE(c.DAYS_LOGGING_IN, 0) / GREATEST(c.tenure_weeks, 1.0) AS persistence_a,

            -- Definition B: Activity Spread Index
            -- activity_span = MAX(dates) - MIN(dates), divided by tenure
            CASE WHEN GREATEST(
                    COALESCE(c.earliest_login_date, c.account_create_date),
                    COALESCE(c.earliest_tree_edit_date, c.account_create_date),
                    COALESCE(c.earliest_name_date, c.account_create_date),
                    COALESCE(c.earliest_source_date, c.account_create_date)
                 ) > LEAST(
                    COALESCE(c.earliest_login_date, DATE '2099-12-31'),
                    COALESCE(c.earliest_tree_edit_date, DATE '2099-12-31'),
                    COALESCE(c.earliest_name_date, DATE '2099-12-31'),
                    COALESCE(c.earliest_source_date, DATE '2099-12-31')
                 )
                 THEN (
                    GREATEST(
                        COALESCE(c.earliest_login_date, c.account_create_date),
                        COALESCE(c.earliest_tree_edit_date, c.account_create_date),
                        COALESCE(c.earliest_name_date, c.account_create_date),
                        COALESCE(c.earliest_source_date, c.account_create_date)
                    ) - LEAST(
                        COALESCE(c.earliest_login_date, DATE '2099-12-31'),
                        COALESCE(c.earliest_tree_edit_date, DATE '2099-12-31'),
                        COALESCE(c.earliest_name_date, DATE '2099-12-31'),
                        COALESCE(c.earliest_source_date, DATE '2099-12-31')
                    )
                 ) * 1.0 / GREATEST(c.tenure_days, 1)
                 ELSE 0.0
            END AS persistence_b,

            -- Definition C: Composite Survival Score (recommended)
            -- w1=1/3 login_consistency + w2=1/3 recency + w3=1/3 breadth
            (
                -- w1: login consistency (same as persistence_a, capped at 1)
                LEAST(1.0, COALESCE(c.DAYS_LOGGING_IN, 0) / GREATEST(c.tenure_weeks, 1.0)) / 3.0
                -- w2: recency = 1 - (days_since_last_milestone / tenure_days)
                + CASE WHEN GREATEST(
                        COALESCE(c.earliest_login_date, c.account_create_date),
                        COALESCE(c.earliest_tree_edit_date, c.account_create_date),
                        COALESCE(c.earliest_name_date, c.account_create_date),
                        COALESCE(c.earliest_source_date, c.account_create_date)
                    ) > c.account_create_date
                    THEN (1.0 - (DATE '2026-03-18' - GREATEST(
                        COALESCE(c.earliest_login_date, c.account_create_date),
                        COALESCE(c.earliest_tree_edit_date, c.account_create_date),
                        COALESCE(c.earliest_name_date, c.account_create_date),
                        COALESCE(c.earliest_source_date, c.account_create_date)
                    )) * 1.0 / GREATEST(c.tenure_days, 1)) / 3.0
                    ELSE 0.0
                  END
                -- w3: activity breadth (out of 7, normalized)
                + (CASE WHEN COALESCE(c.DAYS_LOGGING_IN, 0) > 0 THEN 1 ELSE 0 END
                   + CASE WHEN COALESCE(c.TREE_EDITS, 0) > 0 THEN 1 ELSE 0 END
                   + CASE WHEN COALESCE(c.TOTAL_NAMES_ADDED, 0) > 0 THEN 1 ELSE 0 END
                   + CASE WHEN COALESCE(c.SOURCES_ADDED, 0) > 0 THEN 1 ELSE 0 END
                   + CASE WHEN COALESCE(c.MEMORIES_ADDED, 0) > 0 THEN 1 ELSE 0 END
                   + CASE WHEN COALESCE(c.RECORD_EDITS, 0) > 0 THEN 1 ELSE 0 END
                   + CASE WHEN COALESCE(c.GET_INVOLVED_ITEMS_REVIEWED, 0) > 0 THEN 1 ELSE 0 END
                  ) / 7.0 / 3.0
            ) AS persistence_c

        FROM users_clean c
        """

        con.execute(sql)
        feat_count = con.execute("SELECT COUNT(*) FROM users_features").fetchone()[0]
        log_qc("2.0", "users_features_rows", feat_count)
        log_qc("2.0", "row_match", feat_count == total)

        # ═══════════════════════════════════════════════════
        # STEP 2.7: MILESTONE SEQUENCE ENCODING (post-hoc, needs Python)
        # DuckDB SQL can't easily sort variable-length date lists into ordered strings
        # ═══════════════════════════════════════════════════
        print("\n=== Step 2.7: Milestone Sequence Encoding ===")

        # Add the column
        try:
            con.execute("ALTER TABLE users_features ADD COLUMN milestone_sequence VARCHAR")
        except Exception:
            pass  # Column already exists from re-run

        # Process in batches for memory efficiency
        batch_size = 500_000
        offset = 0
        seq_counts = {}

        while offset < total:
            rows = con.execute(f"""
                SELECT USER_ID,
                       earliest_login_date, earliest_tree_edit_date, earliest_name_date,
                       earliest_source_date, earliest_memory_date, earliest_record_edit_date,
                       earliest_get_involved_date
                FROM users_features
                LIMIT {batch_size} OFFSET {offset}
            """).fetchall()

            updates = []
            for row in rows:
                uid = row[0]
                milestones = []
                codes = {
                    1: "L",  # login
                    2: "T",  # tree edit
                    3: "N",  # name
                    4: "S",  # source
                    5: "M",  # memory
                    6: "R",  # record edit
                    7: "G",  # get involved
                }
                for i, date_val in enumerate(row[1:], 1):
                    if date_val is not None:
                        milestones.append((date_val, codes[i]))

                milestones.sort(key=lambda x: x[0])
                seq = ">".join([m[1] for m in milestones])
                updates.append((seq, uid))

                seq_counts[seq] = seq_counts.get(seq, 0) + 1

            # Batch update
            con.executemany("UPDATE users_features SET milestone_sequence = ? WHERE USER_ID = ?", updates)
            offset += batch_size
            print(f"  Sequences encoded: {min(offset, total):,} / {total:,}")

        # Log top sequences
        top_seqs = sorted(seq_counts.items(), key=lambda x: -x[1])[:20]
        log_qc("2.7", "distinct_sequences", len(seq_counts))
        for seq, ct in top_seqs:
            label = seq if seq else "(empty)"
            log_qc("2.7", f"seq:{label}", ct, f"{ct/total*100:.1f}%")

        # ═══════════════════════════════════════════════════
        # STEP 2.14: PERSISTENCE DICHOTOMIZATION
        # ═══════════════════════════════════════════════════
        print("\n=== Step 2.14: Persistence Dichotomization ===")

        # Median split on persistence_c (excluding MNAR)
        median_c = con.execute("""
            SELECT MEDIAN(persistence_c) FROM users_features WHERE is_mnar = FALSE
        """).fetchone()[0]
        log_qc("2.14", "persistence_c_median", round(median_c, 4))

        # Add dichotomization columns
        for col_name in ["persist_median", "persist_tertile"]:
            try:
                con.execute(f"ALTER TABLE users_features ADD COLUMN {col_name} INTEGER")
            except Exception:
                pass

        # Median split
        con.execute(f"""
            UPDATE users_features
            SET persist_median = CASE
                WHEN is_mnar THEN NULL
                WHEN persistence_c >= {median_c} THEN 1
                ELSE 0
            END
        """)

        # Tertile split (for stratification)
        t33 = con.execute("SELECT PERCENTILE_CONT(0.333) WITHIN GROUP (ORDER BY persistence_c) FROM users_features WHERE is_mnar = FALSE").fetchone()[0]
        t67 = con.execute("SELECT PERCENTILE_CONT(0.667) WITHIN GROUP (ORDER BY persistence_c) FROM users_features WHERE is_mnar = FALSE").fetchone()[0]
        log_qc("2.14", "persistence_c_p33", round(t33, 4))
        log_qc("2.14", "persistence_c_p67", round(t67, 4))

        con.execute(f"""
            UPDATE users_features
            SET persist_tertile = CASE
                WHEN is_mnar THEN NULL
                WHEN persistence_c >= {t67} THEN 2
                WHEN persistence_c >= {t33} THEN 1
                ELSE 0
            END
        """)

        # Log class balance
        for method in ["persist_median", "persist_tertile"]:
            dist = con.execute(f"SELECT {method}, COUNT(*) FROM users_features WHERE {method} IS NOT NULL GROUP BY {method} ORDER BY {method}").fetchall()
            for val, ct in dist:
                log_qc("2.14", f"{method}:{val}", ct, f"{ct/(total - con.execute('SELECT COUNT(*) FROM users_features WHERE is_mnar').fetchone()[0])*100:.1f}%")

        # Persistence score correlations (A vs B vs C)
        corr = con.execute("""
            SELECT
                CORR(persistence_a, persistence_b) AS ab,
                CORR(persistence_a, persistence_c) AS ac,
                CORR(persistence_b, persistence_c) AS bc
            FROM users_features WHERE is_mnar = FALSE
        """).fetchone()
        log_qc("2.13", "corr_A_B", round(corr[0], 4) if corr[0] else None)
        log_qc("2.13", "corr_A_C", round(corr[1], 4) if corr[1] else None)
        log_qc("2.13", "corr_B_C", round(corr[2], 4) if corr[2] else None)

        # ═══════════════════════════════════════════════════
        # STEP 2.15: VALIDATION AND LOGGING
        # ═══════════════════════════════════════════════════
        print("\n=== Step 2.15: Validation ===")

        # Column count
        new_cols = con.execute("DESCRIBE users_features").fetchall()
        log_qc("2.15", "total_columns", len(new_cols))
        log_qc("2.15", "new_features_added", len(new_cols) - 37)  # 37 = users_clean cols

        # Verify no row loss
        final_count = con.execute("SELECT COUNT(*) FROM users_features").fetchone()[0]
        log_qc("2.15", "final_row_count", final_count)
        log_qc("2.15", "row_count_preserved", final_count == total)

        # Key feature distributions (non-MNAR only)
        stats_sql = """
            SELECT
                -- Velocity
                AVG(days_to_first_login) AS avg_dtfl,
                MEDIAN(days_to_first_login) AS med_dtfl,
                AVG(activation_speed) AS avg_aspeed,

                -- Volume
                AVG(logins_per_week) AS avg_lpw,
                AVG(tree_edits_per_week) AS avg_tepw,
                AVG(names_per_week) AS avg_npw,

                -- Sequencing
                AVG(activity_breadth) AS avg_breadth,

                -- Persistence
                AVG(persistence_a) AS avg_pa,
                AVG(persistence_b) AS avg_pb,
                AVG(persistence_c) AS avg_pc,
                MIN(persistence_c) AS min_pc,
                MAX(persistence_c) AS max_pc

            FROM users_features WHERE is_mnar = FALSE
        """
        stats = con.execute(stats_sql).fetchone()
        stat_names = ["avg_days_to_first_login", "med_days_to_first_login", "avg_activation_speed",
                      "avg_logins_pw", "avg_tree_edits_pw", "avg_names_pw",
                      "avg_activity_breadth",
                      "avg_persistence_a", "avg_persistence_b", "avg_persistence_c",
                      "min_persistence_c", "max_persistence_c"]
        for name, val in zip(stat_names, stats):
            log_qc("2.15", name, round(val, 4) if val is not None else None)

        # Funnel stage distribution
        funnel = con.execute("SELECT funnel_stage, COUNT(*) FROM users_features WHERE is_mnar = FALSE GROUP BY funnel_stage ORDER BY funnel_stage").fetchall()
        for stage, ct in funnel:
            non_mnar = total - con.execute("SELECT COUNT(*) FROM users_features WHERE is_mnar").fetchone()[0]
            log_qc("2.15", f"funnel_stage:{stage}", ct, f"{ct/non_mnar*100:.1f}%")

        # Country cluster distribution
        clusters = con.execute("SELECT country_cluster, COUNT(*) FROM users_features GROUP BY country_cluster ORDER BY COUNT(*) DESC").fetchall()
        for cluster, ct in clusters:
            log_qc("2.15", f"country_cluster:{cluster}", ct, f"{ct/total*100:.1f}%")

        # Age group distribution
        age_groups = con.execute("SELECT age_group, COUNT(*) FROM users_features GROUP BY age_group ORDER BY age_group").fetchall()
        for ag, ct in age_groups:
            log_qc("2.15", f"age_group:{ag}", ct)

        # Persist QC log to database
        for entry in qc_log:
            con.execute("""
                INSERT INTO qc_log (step, metric, value, note, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, [entry["step"], entry["metric"], str(entry["value"]), entry.get("note", ""),
                  entry["timestamp"]])

        # Write reports
        report_lines = [
            "# Phase 2: Feature Engineering Report",
            f"\n**Generated**: {datetime.now().isoformat()}",
            f"**Source**: users_clean ({total:,} rows)",
            f"**Output**: users_features ({len(new_cols)} columns)",
            "\n---\n",
            "## QC Log\n",
            "| Step | Metric | Value | Note |",
            "|------|--------|-------|------|",
        ]
        for entry in qc_log:
            val = str(entry["value"])
            if len(val) > 80:
                val = val[:77] + "..."
            report_lines.append(f"| {entry['step']} | {entry['metric']} | {val} | {entry.get('note', '')} |")

        (OUTPUT_DIR / "feature_report.md").write_text("\n".join(report_lines))
        (OUTPUT_DIR / "qc_log.json").write_text(json.dumps(qc_log, indent=2, default=str))

        print(f"\n=== Phase 2 Complete ===")
        print(f"users_features: {final_count:,} rows, {len(new_cols)} columns")
        print(f"New features added: {len(new_cols) - 37}")
        print(f"Reports: {OUTPUT_DIR}")

    finally:
        con.close()


if __name__ == "__main__":
    main()
