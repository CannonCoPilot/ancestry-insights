"""Phase 2 Completion: Milestone sequence encoding + persistence dichotomization.
Fixes the slow row-by-row UPDATE with a temp table + JOIN approach.
Run after phase2_features.py created users_features (SQL features done).
"""
import duckdb
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "familysearch.duckdb"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "phase2"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

qc_log = []

def log_qc(step, metric, value, note=""):
    entry = {"step": step, "metric": metric, "value": value, "note": note,
             "timestamp": datetime.now().isoformat()}
    qc_log.append(entry)
    print(f"  [{step}] {metric} = {value}  {note}")


def main():
    print("Phase 2 Completion: Sequence Encoding + Dichotomization")
    con = duckdb.connect(str(DB_PATH))

    try:
        total = con.execute("SELECT COUNT(*) FROM users_features").fetchone()[0]
        print(f"users_features: {total:,} rows")

        # ═══════════════════════════════════════════════════
        # STEP 2.7: MILESTONE SEQUENCE ENCODING (temp table approach)
        # ═══════════════════════════════════════════════════
        print("\n=== Step 2.7: Milestone Sequence Encoding (optimized) ===")

        # Use DuckDB SQL to compute the sequence directly
        # Strategy: UNPIVOT date columns, filter non-null, order by date, aggregate into string
        # Only process rows that have at least one milestone date (skips MNAR + zero-activity)
        con.execute("""
            CREATE OR REPLACE TEMP TABLE milestone_dates AS
            SELECT USER_ID, milestone, milestone_date
            FROM (
                SELECT USER_ID,
                    earliest_login_date AS L,
                    earliest_tree_edit_date AS T,
                    earliest_name_date AS N,
                    earliest_source_date AS S,
                    earliest_memory_date AS M,
                    earliest_record_edit_date AS R,
                    earliest_get_involved_date AS G
                FROM users_features
                WHERE is_mnar = FALSE
                  AND (earliest_login_date IS NOT NULL
                       OR earliest_tree_edit_date IS NOT NULL
                       OR earliest_name_date IS NOT NULL)
            ) UNPIVOT (
                milestone_date FOR milestone IN (L, T, N, S, M, R, G)
            )
            WHERE milestone_date IS NOT NULL
        """)

        unpivot_count = con.execute("SELECT COUNT(*) FROM milestone_dates").fetchone()[0]
        log_qc("2.7", "unpivoted_milestone_rows", unpivot_count)

        # Order milestones per user and concatenate
        con.execute("""
            CREATE OR REPLACE TEMP TABLE user_sequences AS
            SELECT USER_ID,
                   STRING_AGG(milestone, '>' ORDER BY milestone_date, milestone) AS milestone_sequence
            FROM milestone_dates
            GROUP BY USER_ID
        """)

        seq_count = con.execute("SELECT COUNT(*) FROM user_sequences").fetchone()[0]
        log_qc("2.7", "users_with_sequences", seq_count)

        # Update the main table via a JOIN (fast — no row-by-row)
        # First reset any partially written sequences from the killed run
        con.execute("UPDATE users_features SET milestone_sequence = NULL")

        con.execute("""
            UPDATE users_features f
            SET milestone_sequence = s.milestone_sequence
            FROM user_sequences s
            WHERE f.USER_ID = s.USER_ID
        """)

        # Set empty string for users with no milestones
        con.execute("""
            UPDATE users_features
            SET milestone_sequence = ''
            WHERE milestone_sequence IS NULL
        """)

        # Verify
        populated = con.execute("SELECT COUNT(*) FROM users_features WHERE milestone_sequence != ''").fetchone()[0]
        empty = con.execute("SELECT COUNT(*) FROM users_features WHERE milestone_sequence = ''").fetchone()[0]
        log_qc("2.7", "sequences_populated", populated)
        log_qc("2.7", "sequences_empty", empty, "Users with no milestone dates")

        # Top 20 sequences
        top_seqs = con.execute("""
            SELECT milestone_sequence, COUNT(*) as n
            FROM users_features
            WHERE milestone_sequence != ''
            GROUP BY milestone_sequence
            ORDER BY n DESC
            LIMIT 20
        """).fetchall()

        distinct = con.execute("SELECT COUNT(DISTINCT milestone_sequence) FROM users_features WHERE milestone_sequence != ''").fetchone()[0]
        log_qc("2.7", "distinct_sequences", distinct)
        for seq, ct in top_seqs:
            log_qc("2.7", f"seq:{seq}", ct, f"{ct/total*100:.1f}%")

        # Clean up temp tables
        con.execute("DROP TABLE IF EXISTS milestone_dates")
        con.execute("DROP TABLE IF EXISTS user_sequences")

        # ═══════════════════════════════════════════════════
        # STEP 2.14: PERSISTENCE DICHOTOMIZATION
        # ═══════════════════════════════════════════════════
        print("\n=== Step 2.14: Persistence Dichotomization ===")

        non_mnar = con.execute("SELECT COUNT(*) FROM users_features WHERE is_mnar = FALSE").fetchone()[0]

        # Median split on persistence_c
        median_c = con.execute("SELECT MEDIAN(persistence_c) FROM users_features WHERE is_mnar = FALSE").fetchone()[0]
        log_qc("2.14", "persistence_c_median", round(median_c, 6))

        # Add columns if they don't exist
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

        # Tertile split
        t33 = con.execute("SELECT PERCENTILE_CONT(0.333) WITHIN GROUP (ORDER BY persistence_c) FROM users_features WHERE is_mnar = FALSE").fetchone()[0]
        t67 = con.execute("SELECT PERCENTILE_CONT(0.667) WITHIN GROUP (ORDER BY persistence_c) FROM users_features WHERE is_mnar = FALSE").fetchone()[0]
        log_qc("2.14", "persistence_c_p33", round(t33, 6))
        log_qc("2.14", "persistence_c_p67", round(t67, 6))

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
            dist = con.execute(f"""
                SELECT {method}, COUNT(*) FROM users_features
                WHERE {method} IS NOT NULL GROUP BY {method} ORDER BY {method}
            """).fetchall()
            for val, ct in dist:
                log_qc("2.14", f"{method}:{val}", ct, f"{ct/non_mnar*100:.1f}%")

        # Persistence correlations
        corr = con.execute("""
            SELECT CORR(persistence_a, persistence_b),
                   CORR(persistence_a, persistence_c),
                   CORR(persistence_b, persistence_c)
            FROM users_features WHERE is_mnar = FALSE
        """).fetchone()
        log_qc("2.13", "corr_A_B", round(corr[0], 4) if corr[0] else None)
        log_qc("2.13", "corr_A_C", round(corr[1], 4) if corr[1] else None)
        log_qc("2.13", "corr_B_C", round(corr[2], 4) if corr[2] else None)

        # ═══════════════════════════════════════════════════
        # STEP 2.15: VALIDATION
        # ═══════════════════════════════════════════════════
        print("\n=== Step 2.15: Final Validation ===")

        col_count = len(con.execute("DESCRIBE users_features").fetchall())
        row_count = con.execute("SELECT COUNT(*) FROM users_features").fetchone()[0]
        log_qc("2.15", "final_columns", col_count)
        log_qc("2.15", "final_rows", row_count)
        log_qc("2.15", "rows_preserved", row_count == total)

        # Key distributions
        stats = con.execute("""
            SELECT
                AVG(days_to_first_login), MEDIAN(days_to_first_login),
                AVG(activation_speed),
                AVG(logins_per_week), AVG(tree_edits_per_week), AVG(names_per_week),
                AVG(activity_breadth),
                AVG(persistence_a), AVG(persistence_b), AVG(persistence_c),
                MIN(persistence_c), MAX(persistence_c)
            FROM users_features WHERE is_mnar = FALSE
        """).fetchone()
        names = ["avg_days_to_first_login", "med_days_to_first_login", "avg_activation_speed",
                 "avg_logins_pw", "avg_tree_edits_pw", "avg_names_pw", "avg_breadth",
                 "avg_persist_a", "avg_persist_b", "avg_persist_c", "min_persist_c", "max_persist_c"]
        for n, v in zip(names, stats):
            log_qc("2.15", n, round(v, 4) if v is not None else None)

        # Funnel stage distribution
        funnel = con.execute("""
            SELECT funnel_stage, COUNT(*) FROM users_features WHERE is_mnar = FALSE
            GROUP BY funnel_stage ORDER BY funnel_stage
        """).fetchall()
        for stage, ct in funnel:
            log_qc("2.15", f"funnel:{stage}", ct, f"{ct/non_mnar*100:.1f}%")

        # Country cluster distribution
        clusters = con.execute("""
            SELECT country_cluster, COUNT(*) FROM users_features
            GROUP BY country_cluster ORDER BY COUNT(*) DESC
        """).fetchall()
        for cluster, ct in clusters:
            log_qc("2.15", f"cluster:{cluster}", ct, f"{ct/total*100:.1f}%")

        # Persist to DB
        for entry in qc_log:
            con.execute("""
                INSERT INTO qc_log (step, metric, value, note, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, [entry["step"], entry["metric"], str(entry["value"]), entry.get("note", ""),
                  entry["timestamp"]])

        # Write reports
        report = [
            "# Phase 2: Feature Engineering Report",
            f"\n**Generated**: {datetime.now().isoformat()}",
            f"**Table**: users_features ({row_count:,} rows, {col_count} columns)",
            "\n---\n",
            "## QC Log\n",
            "| Step | Metric | Value | Note |",
            "|------|--------|-------|------|",
        ]
        for entry in qc_log:
            val = str(entry["value"])[:80]
            report.append(f"| {entry['step']} | {entry['metric']} | {val} | {entry.get('note', '')} |")

        (OUTPUT_DIR / "feature_report.md").write_text("\n".join(report))
        (OUTPUT_DIR / "qc_log.json").write_text(json.dumps(qc_log, indent=2, default=str))

        print(f"\n=== Phase 2 Complete ===")
        print(f"users_features: {row_count:,} rows, {col_count} columns")
        print(f"Reports: {OUTPUT_DIR}")

    finally:
        con.close()


if __name__ == "__main__":
    main()
