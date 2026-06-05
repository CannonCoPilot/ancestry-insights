"""Phase 1: Data Infrastructure & QC
Loads raw CSV into DuckDB, applies cleaning, builds crosswalk, creates tracking tables.
Run once. Outputs: data/familysearch.duckdb, outputs/phase1/qc_report.md
"""
import duckdb
import pycountry
import json
import os
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "familysearch.duckdb"
CSV_PATH = PROJECT_ROOT / "data" / "raw" / "users.csv"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "phase1"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ACTIVITY_COLS = [
    "DAYS_LOGGING_IN", "SOURCES_ADDED", "DAYS_ADDING_SOURCES",
    "MEMORIES_ADDED", "DAYS_ADDING_MEMORIES",
    "GET_INVOLVED_ITEMS_REVIEWED", "DAYS_REVIEWING_GET_INVOLVED_ITEMS",
    "RECORD_EDITS", "DAYS_EDITING_RECORDS",
    "TREE_EDITS", "DAYS_EDITING_TREES",
]

qc_log = []

def log_qc(step: str, metric: str, value, note: str = ""):
    entry = {"step": step, "metric": metric, "value": value, "note": note,
             "timestamp": datetime.now().isoformat()}
    qc_log.append(entry)
    print(f"  [{step}] {metric} = {value}  {note}")


def step_1_1_load_raw(con):
    """Load raw CSV into users_raw table."""
    print("\n=== Step 1.1: Load Raw CSV ===")
    con.execute("DROP TABLE IF EXISTS users_raw")
    con.execute(f"""
        CREATE TABLE users_raw AS
        SELECT * FROM read_csv_auto('{CSV_PATH}', header=true, sample_size=100000)
    """)
    row_count = con.execute("SELECT COUNT(*) FROM users_raw").fetchone()[0]
    col_count = len(con.execute("DESCRIBE users_raw").fetchall())
    log_qc("1.1", "raw_row_count", row_count)
    log_qc("1.1", "raw_col_count", col_count)

    if row_count != 7625105:
        log_qc("1.1", "WARNING", f"Expected 7625105, got {row_count}", "Row count mismatch")
    if col_count != 33:
        log_qc("1.1", "WARNING", f"Expected 33, got {col_count}", "Column count mismatch")

    # Log column names and types
    cols = con.execute("DESCRIBE users_raw").fetchall()
    for name, dtype, *_ in cols:
        log_qc("1.1", f"col_type:{name}", dtype)

    return row_count, col_count


def step_1_2_age_cleaning(con):
    """Flag age=0 and out-of-range ages."""
    print("\n=== Step 1.2: Age Cleaning ===")
    # Count each category before cleaning
    age_0 = con.execute("SELECT COUNT(*) FROM users_raw WHERE USER_CURRENT_AGE = 0").fetchone()[0]
    age_lt8 = con.execute("SELECT COUNT(*) FROM users_raw WHERE USER_CURRENT_AGE > 0 AND USER_CURRENT_AGE < 8").fetchone()[0]
    age_gt110 = con.execute("SELECT COUNT(*) FROM users_raw WHERE USER_CURRENT_AGE > 110").fetchone()[0]
    age_neg = con.execute("SELECT COUNT(*) FROM users_raw WHERE USER_CURRENT_AGE < 0").fetchone()[0]

    log_qc("1.2", "age_eq_0", age_0, "Will be set to NULL (system default)")
    log_qc("1.2", "age_1_to_7", age_lt8, "Will be set to NULL (below min account age 8)")
    log_qc("1.2", "age_gt_110", age_gt110, "Will be clipped to 110")
    log_qc("1.2", "age_negative", age_neg, "Will be set to NULL")
    log_qc("1.2", "total_age_nullified", age_0 + age_lt8 + age_neg)


def step_1_3_province_city_sentinels(con):
    """Count sentinel values in Province and City."""
    print("\n=== Step 1.3: Province/City Sentinel Detection ===")
    for col in ["PROVINCE", "CITY"]:
        for sentinel in ["Unknown", "Redacted", "-"]:
            n = con.execute(f"SELECT COUNT(*) FROM users_raw WHERE TRIM({col}) = '{sentinel}'").fetchone()[0]
            if n > 0:
                log_qc("1.3", f"{col}_sentinel:{sentinel}", n)
        empty = con.execute(f"SELECT COUNT(*) FROM users_raw WHERE TRIM({col}) = '' OR {col} IS NULL").fetchone()[0]
        if empty > 0:
            log_qc("1.3", f"{col}_empty_or_null", empty)


def step_1_4_mnar_detection(con):
    """Identify MNAR block: all 11 activity columns NULL simultaneously."""
    print("\n=== Step 1.4: MNAR Block Detection ===")
    # Build the WHERE clause: all 11 activity cols IS NULL
    null_conditions = " AND ".join([f"{col} IS NULL" for col in ACTIVITY_COLS])
    mnar_count = con.execute(f"SELECT COUNT(*) FROM users_raw WHERE {null_conditions}").fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM users_raw").fetchone()[0]
    mnar_pct = mnar_count / total * 100

    log_qc("1.4", "mnar_block_count", mnar_count)
    log_qc("1.4", "mnar_block_pct", round(mnar_pct, 2))

    # Verify it's truly block-or-nothing: no partial nulls
    any_null = " OR ".join([f"{col} IS NULL" for col in ACTIVITY_COLS])
    any_null_count = con.execute(f"SELECT COUNT(*) FROM users_raw WHERE ({any_null})").fetchone()[0]
    log_qc("1.4", "any_activity_null_count", any_null_count, "Should equal mnar_block_count if block-or-nothing")

    if any_null_count != mnar_count:
        log_qc("1.4", "WARNING", f"Partial nulls exist: {any_null_count - mnar_count} rows", "NOT pure block missingness")


def step_1_5_tenure(con):
    """Compute reference date and tenure."""
    print("\n=== Step 1.5: Tenure Computation ===")
    # Infer reference date from max of all date columns
    date_cols = [
        "ACCOUNT_CREATE_DATE", "EARLIEST_LOGIN_DATE", "EARLIEST_TREE_EDIT_DATE",
        "EARLIEST_NAME_CONTRIBUTOR_DATE", "EARLIEST_SOURCE_CONTRIBUTOR_DATE",
        "EARLIEST_MEMORY_CONTRIBUTOR_DATE", "EARLIEST_GET_INVOLVED_USAGE_DATE",
        "EARLIEST_RECORD_EDIT_DATE",
    ]
    max_dates = []
    for dc in date_cols:
        try:
            val = con.execute(f"SELECT MAX(CAST({dc} AS DATE)) FROM users_raw").fetchone()[0]
            if val:
                max_dates.append(val)
        except Exception:
            pass

    reference_date = max(max_dates) if max_dates else None
    log_qc("1.5", "reference_date", str(reference_date))
    log_qc("1.5", "max_dates_by_col", {dc: str(v) for dc, v in zip(date_cols, max_dates)})

    return reference_date


def step_1_6_country_crosswalk(con):
    """Build ISO-3166 alpha-3 crosswalk for all observed country names."""
    print("\n=== Step 1.6: Country Crosswalk ===")
    countries = [r[0] for r in con.execute("SELECT DISTINCT COUNTRY FROM users_raw ORDER BY COUNTRY").fetchall()]
    log_qc("1.6", "distinct_countries", len(countries))

    # Build pycountry lookup index
    name_to_iso3 = {}

    # First pass: exact name match
    for c in pycountry.countries:
        name_to_iso3[c.name.lower()] = c.alpha_3
        if hasattr(c, 'common_name'):
            name_to_iso3[c.common_name.lower()] = c.alpha_3
        if hasattr(c, 'official_name'):
            name_to_iso3[c.official_name.lower()] = c.alpha_3

    # Manual overrides for FamilySearch-specific names
    manual_map = {
        "D.R. Congo": "COD",
        "DR Congo": "COD",
        "Congo (Kinshasa)": "COD",
        "Congo (Brazzaville)": "COG",
        "Republic of the Congo": "COG",
        "Ivory Coast": "CIV",
        "Cote d'Ivoire": "CIV",
        "Côte d'Ivoire": "CIV",
        "South Korea": "KOR",
        "North Korea": "PRK",
        "Russia": "RUS",
        "Taiwan": "TWN",
        "Vietnam": "VNM",
        "Viet Nam": "VNM",
        "Bolivia": "BOL",
        "Venezuela": "VEN",
        "Iran": "IRN",
        "Syria": "SYR",
        "Laos": "LAO",
        "Moldova": "MDA",
        "Tanzania": "TZA",
        "Palestine": "PSE",
        "Palestinian Territories": "PSE",
        "Macau": "MAC",
        "Macao": "MAC",
        "Hong Kong": "HKG",
        "Brunei": "BRN",
        "Burma": "MMR",
        "Myanmar": "MMR",
        "Czech Republic": "CZE",
        "Czechia": "CZE",
        "Macedonia": "MKD",
        "North Macedonia": "MKD",
        "Swaziland": "SWZ",
        "Eswatini": "SWZ",
        "Cape Verde": "CPV",
        "Cabo Verde": "CPV",
        "Timor-Leste": "TLS",
        "East Timor": "TLS",
        "Vatican City": "VAT",
        "Holy See": "VAT",
        "Micronesia": "FSM",
        "Federated States of Micronesia": "FSM",
        "Reunion": "REU",
        "Réunion": "REU",
        "Curacao": "CUW",
        "Curaçao": "CUW",
        "Sint Maarten": "SXM",
        "Saint Martin": "MAF",
        "St. Martin": "MAF",
        "U.S. Virgin Islands": "VIR",
        "US Virgin Islands": "VIR",
        "British Virgin Islands": "VGB",
        "Turks and Caicos": "TCA",
        "Turks and Caicos Islands": "TCA",
        "Cayman Islands": "CYM",
        "Falkland Islands": "FLK",
        "Faroe Islands": "FRO",
        "French Guiana": "GUF",
        "French Polynesia": "PYF",
        "New Caledonia": "NCL",
        "Martinique": "MTQ",
        "Guadeloupe": "GLP",
        "Mayotte": "MYT",
        "Saint Barthelemy": "BLM",
        "Saint Barthélemy": "BLM",
        "Wallis and Futuna": "WLF",
        "Saint Pierre and Miquelon": "SPM",
        "Bermuda": "BMU",
        "Aruba": "ABW",
        "Guam": "GUM",
        "American Samoa": "ASM",
        "Northern Mariana Islands": "MNP",
        "Puerto Rico": "PRI",
        "Kosovo": "XKX",
        "Bonaire": "BES",
        "Caribbean Netherlands": "BES",
        "Channel Islands": "GBR",  # Jersey/Guernsey — Crown Dependencies, no ISO3; map to GBR
        "St. Helena": "SHN",
        "St. Kitts and Nevis": "KNA",
        "St. Lucia": "LCA",
        "St. Pierre and Miquelon": "SPM",
        "St. Vincent and the Grenadines": "VCT",
        "Turkey": "TUR",  # pycountry uses "Türkiye" since 2022
        "U.S. Minor Outlying Islands": "UMI",
        "Christmas Island": "CXR",
        "Cocos Islands": "CCK",
        "Cook Islands": "COK",
        "Norfolk Island": "NFK",
        "Niue": "NIU",
        "Tokelau": "TKL",
        "Pitcairn": "PCN",
        "Svalbard": "SJM",
        "Unknown": None,
        "-": None,
    }

    matched = {}
    unmatched = []

    for country in countries:
        # Try manual map first (case-sensitive)
        if country in manual_map:
            matched[country] = manual_map[country]
            continue

        # Try exact lowercase match
        lower = country.lower().strip()
        if lower in name_to_iso3:
            matched[country] = name_to_iso3[lower]
            continue

        # Try fuzzy: remove common prefixes/suffixes
        cleaned = lower.replace("the ", "").replace(" islands", "").replace(" island", "").strip()
        if cleaned in name_to_iso3:
            matched[country] = name_to_iso3[cleaned]
            continue

        # Try pycountry fuzzy_search
        try:
            results = pycountry.countries.search_fuzzy(country)
            if results:
                matched[country] = results[0].alpha_3
                continue
        except LookupError:
            pass

        unmatched.append(country)

    log_qc("1.6", "matched_countries", len([k for k, v in matched.items() if v is not None]))
    log_qc("1.6", "null_mapped", len([k for k, v in matched.items() if v is None]))
    log_qc("1.6", "unmatched_countries", len(unmatched))

    if unmatched:
        log_qc("1.6", "unmatched_list", unmatched)

    # Create crosswalk table
    con.execute("DROP TABLE IF EXISTS country_crosswalk")
    con.execute("""
        CREATE TABLE country_crosswalk (
            fs_country_name TEXT PRIMARY KEY,
            iso3_code TEXT,
            match_method TEXT
        )
    """)

    for country, iso3 in matched.items():
        method = "manual" if country in manual_map else "pycountry"
        con.execute("INSERT INTO country_crosswalk VALUES (?, ?, ?)", [country, iso3, method])
    for country in unmatched:
        con.execute("INSERT INTO country_crosswalk VALUES (?, NULL, 'unmatched')", [country])

    # Verify
    total_xwalk = con.execute("SELECT COUNT(*) FROM country_crosswalk").fetchone()[0]
    null_iso3 = con.execute("SELECT COUNT(*) FROM country_crosswalk WHERE iso3_code IS NULL").fetchone()[0]
    log_qc("1.6", "crosswalk_total_rows", total_xwalk)
    log_qc("1.6", "crosswalk_null_iso3", null_iso3, "Includes 'Unknown' and unmatched")

    return unmatched


def step_1_7_create_users_clean(con, reference_date):
    """Create users_clean with all transformations applied."""
    print("\n=== Step 1.7: Create users_clean ===")

    # Build MNAR detection clause
    null_conditions = " AND ".join([f"r.{col} IS NULL" for col in ACTIVITY_COLS])

    con.execute("DROP TABLE IF EXISTS users_clean")
    con.execute(f"""
        CREATE TABLE users_clean AS
        SELECT
            r.USER_ID,
            CAST(r.ACCOUNT_CREATE_DATE AS DATE) AS account_create_date,
            r.ACCOUNT_TYPE,

            -- Age: NULL for 0, <8, >110, negative
            CASE
                WHEN r.USER_CURRENT_AGE <= 0 THEN NULL
                WHEN r.USER_CURRENT_AGE < 8 THEN NULL
                WHEN r.USER_CURRENT_AGE > 110 THEN 110
                ELSE r.USER_CURRENT_AGE
            END AS user_age,

            -- Geography: keep raw
            r.COUNTRY,
            -- Province/City: sentinel -> NULL
            CASE WHEN TRIM(r.PROVINCE) IN ('Unknown', 'Redacted', '-', '') THEN NULL ELSE r.PROVINCE END AS province,
            CASE WHEN TRIM(r.CITY) IN ('Unknown', 'Redacted', '-', '') THEN NULL ELSE r.CITY END AS city,
            r.USER_WORLD_REGION,
            r.USER_AREA_NAME,

            -- ISO3 from crosswalk
            xw.iso3_code,

            -- Date milestones (cast to DATE)
            CAST(r.EARLIEST_LOGIN_DATE AS DATE) AS earliest_login_date,
            CAST(r.EARLIEST_NAME_CONTRIBUTOR_DATE AS DATE) AS earliest_name_date,
            CAST(r.EARLIEST_SOURCE_CONTRIBUTOR_DATE AS DATE) AS earliest_source_date,
            CAST(r.EARLIEST_MEMORY_CONTRIBUTOR_DATE AS DATE) AS earliest_memory_date,
            CAST(r.EARLIEST_GET_INVOLVED_USAGE_DATE AS DATE) AS earliest_get_involved_date,
            CAST(r.EARLIEST_RECORD_EDIT_DATE AS DATE) AS earliest_record_edit_date,
            CAST(r.EARLIEST_TREE_EDIT_DATE AS DATE) AS earliest_tree_edit_date,

            -- Activity counts (keep as-is; NULLs preserved for MNAR block)
            r.DAYS_LOGGING_IN,
            r.SOURCES_ADDED,
            r.DAYS_ADDING_SOURCES,
            r.MEMORIES_ADDED,
            r.DAYS_ADDING_MEMORIES,
            r.GET_INVOLVED_ITEMS_REVIEWED,
            r.DAYS_REVIEWING_GET_INVOLVED_ITEMS,
            r.RECORD_EDITS,
            r.DAYS_EDITING_RECORDS,
            r.TREE_EDITS,
            r.DAYS_EDITING_TREES,

            -- Name counts (keep as-is)
            r.DAYS_ADDING_NAMES,
            r.TOTAL_NAMES_ADDED,
            r.DECEASED_NAMES_ADDED,
            r.LIVING_NAMES_ADDED,
            r.NOVEL_NAMES_ADDED,
            r.QUALIFIED_NAMES_ADDED,

            -- MNAR flag (all 11 activity cols NULL)
            CASE WHEN {null_conditions} THEN TRUE ELSE FALSE END AS is_mnar,

            -- Tenure
            DATE '{reference_date}' - CAST(r.ACCOUNT_CREATE_DATE AS DATE) AS tenure_days,
            (DATE '{reference_date}' - CAST(r.ACCOUNT_CREATE_DATE AS DATE)) / 7.0 AS tenure_weeks

        FROM users_raw r
        LEFT JOIN country_crosswalk xw ON r.COUNTRY = xw.fs_country_name
    """)

    clean_count = con.execute("SELECT COUNT(*) FROM users_clean").fetchone()[0]
    raw_count = con.execute("SELECT COUNT(*) FROM users_raw").fetchone()[0]
    log_qc("1.7", "users_clean_rows", clean_count)
    log_qc("1.7", "row_count_match", clean_count == raw_count)

    # Verify key transformations
    age_nulls = con.execute("SELECT COUNT(*) FROM users_clean WHERE user_age IS NULL").fetchone()[0]
    age_min = con.execute("SELECT MIN(user_age) FROM users_clean WHERE user_age IS NOT NULL").fetchone()[0]
    age_max = con.execute("SELECT MAX(user_age) FROM users_clean WHERE user_age IS NOT NULL").fetchone()[0]
    mnar_ct = con.execute("SELECT COUNT(*) FROM users_clean WHERE is_mnar = TRUE").fetchone()[0]
    prov_null = con.execute("SELECT COUNT(*) FROM users_clean WHERE province IS NULL").fetchone()[0]
    city_null = con.execute("SELECT COUNT(*) FROM users_clean WHERE city IS NULL").fetchone()[0]
    iso3_null = con.execute("SELECT COUNT(*) FROM users_clean WHERE iso3_code IS NULL").fetchone()[0]
    tenure_neg = con.execute("SELECT COUNT(*) FROM users_clean WHERE tenure_days < 0").fetchone()[0]

    log_qc("1.7", "age_nulls", age_nulls)
    log_qc("1.7", "age_min", age_min, "Should be >= 8")
    log_qc("1.7", "age_max", age_max, "Should be <= 110")
    log_qc("1.7", "mnar_flagged", mnar_ct)
    log_qc("1.7", "province_null", prov_null)
    log_qc("1.7", "city_null", city_null)
    log_qc("1.7", "iso3_null", iso3_null, "Includes 'Unknown' country")
    log_qc("1.7", "tenure_negative", tenure_neg, "Should be 0")


def step_1_8_tracking_tables(con):
    """Create experiment registry and QC log tables."""
    print("\n=== Step 1.8: Tracking Tables ===")
    con.execute("DROP TABLE IF EXISTS experiment_registry")
    con.execute("""
        CREATE TABLE experiment_registry (
            experiment_id INTEGER PRIMARY KEY,
            phase TEXT,
            subsample_id INTEGER,
            seed INTEGER,
            n_rows INTEGER,
            n_train INTEGER,
            n_test INTEGER,
            exclusions TEXT,
            parameters TEXT,
            commit_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    con.execute("DROP TABLE IF EXISTS qc_log")
    con.execute("DROP SEQUENCE IF EXISTS qc_seq")
    con.execute("CREATE SEQUENCE qc_seq START 1")
    con.execute("""
        CREATE TABLE qc_log (
            id INTEGER PRIMARY KEY DEFAULT nextval('qc_seq'),
            step TEXT,
            metric TEXT,
            value TEXT,
            note TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    log_qc("1.8", "experiment_registry", "created")
    log_qc("1.8", "qc_log", "created")


def step_1_9_qc_summary(con):
    """Run comprehensive QC queries and write to qc_log."""
    print("\n=== Step 1.9: QC Summary ===")

    # Total rows
    total = con.execute("SELECT COUNT(*) FROM users_clean").fetchone()[0]
    log_qc("1.9", "total_rows", total)

    # NULL rates per column
    cols = [r[0] for r in con.execute("DESCRIBE users_clean").fetchall()]
    for col in cols:
        null_ct = con.execute(f"SELECT COUNT(*) FROM users_clean WHERE {col} IS NULL").fetchone()[0]
        null_pct = round(null_ct / total * 100, 2)
        if null_pct > 0:
            log_qc("1.9", f"null_pct:{col}", null_pct)

    # MNAR
    mnar = con.execute("SELECT COUNT(*) FROM users_clean WHERE is_mnar = TRUE").fetchone()[0]
    log_qc("1.9", "mnar_pct", round(mnar / total * 100, 2))

    # Tenure distribution
    tenure_stats = con.execute("""
        SELECT MIN(tenure_days), MEDIAN(tenure_days), MAX(tenure_days),
               AVG(tenure_days), COUNT(*) FILTER (WHERE tenure_days < 0)
        FROM users_clean
    """).fetchone()
    log_qc("1.9", "tenure_min", tenure_stats[0])
    log_qc("1.9", "tenure_median", tenure_stats[1])
    log_qc("1.9", "tenure_max", tenure_stats[2])
    log_qc("1.9", "tenure_mean", round(tenure_stats[3], 1))
    log_qc("1.9", "tenure_negative_count", tenure_stats[4])

    # Age distribution
    age_stats = con.execute("""
        SELECT MIN(user_age), MEDIAN(user_age), MAX(user_age), AVG(user_age), COUNT(*) FILTER (WHERE user_age IS NULL)
        FROM users_clean
    """).fetchone()
    log_qc("1.9", "age_min", age_stats[0])
    log_qc("1.9", "age_median", age_stats[1])
    log_qc("1.9", "age_max", age_stats[2])
    log_qc("1.9", "age_mean", round(age_stats[3], 1) if age_stats[3] else None)
    log_qc("1.9", "age_null_count", age_stats[4])

    # Country count
    n_countries = con.execute("SELECT COUNT(DISTINCT COUNTRY) FROM users_clean").fetchone()[0]
    log_qc("1.9", "distinct_countries", n_countries)

    # Account type
    acct_types = con.execute("SELECT ACCOUNT_TYPE, COUNT(*) FROM users_clean GROUP BY ACCOUNT_TYPE").fetchall()
    for atype, ct in acct_types:
        log_qc("1.9", f"account_type:{atype}", ct)

    # Region distribution
    regions = con.execute("SELECT USER_WORLD_REGION, COUNT(*) FROM users_clean GROUP BY USER_WORLD_REGION ORDER BY COUNT(*) DESC").fetchall()
    for region, ct in regions:
        log_qc("1.9", f"region:{region}", ct)

    # ISO3 crosswalk coverage
    iso3_coverage = con.execute("SELECT COUNT(*) FROM users_clean WHERE iso3_code IS NOT NULL").fetchone()[0]
    log_qc("1.9", "iso3_coverage_pct", round(iso3_coverage / total * 100, 2))

    # Write QC log to database
    for entry in qc_log:
        con.execute("""
            INSERT INTO qc_log (step, metric, value, note, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, [entry["step"], entry["metric"], str(entry["value"]), entry.get("note", ""),
              entry["timestamp"]])


def write_qc_report():
    """Write QC report markdown file."""
    report_path = OUTPUT_DIR / "qc_report.md"
    lines = [
        "# Phase 1: QC Report",
        f"\n**Generated**: {datetime.now().isoformat()}",
        f"**Database**: `{DB_PATH}`",
        f"**Source**: `{CSV_PATH}`",
        "\n---\n",
        "## QC Log\n",
        "| Step | Metric | Value | Note |",
        "|------|--------|-------|------|",
    ]
    for entry in qc_log:
        val = str(entry["value"])
        if len(val) > 80:
            val = val[:77] + "..."
        lines.append(f"| {entry['step']} | {entry['metric']} | {val} | {entry.get('note', '')} |")

    report_path.write_text("\n".join(lines))
    print(f"\nQC report written to {report_path}")


def main():
    print(f"Phase 1: Data Infrastructure & QC")
    print(f"Database: {DB_PATH}")
    print(f"Source CSV: {CSV_PATH}")

    # Remove old DB if exists
    if DB_PATH.exists():
        DB_PATH.unlink()
        print("Removed existing database.")

    con = duckdb.connect(str(DB_PATH))

    try:
        # Step 1.1: Load raw
        row_count, col_count = step_1_1_load_raw(con)

        # Step 1.2: Age cleaning analysis
        step_1_2_age_cleaning(con)

        # Step 1.3: Province/City sentinels
        step_1_3_province_city_sentinels(con)

        # Step 1.4: MNAR detection
        step_1_4_mnar_detection(con)

        # Step 1.5: Reference date and tenure
        reference_date = step_1_5_tenure(con)

        # Step 1.6: Country crosswalk
        unmatched = step_1_6_country_crosswalk(con)

        # Step 1.7: Create users_clean
        step_1_7_create_users_clean(con, reference_date)

        # Step 1.8: Tracking tables
        step_1_8_tracking_tables(con)

        # Step 1.9: QC summary
        step_1_9_qc_summary(con)

        # Write report
        write_qc_report()

        # Save QC log as JSON too
        json_path = OUTPUT_DIR / "qc_log.json"
        json_path.write_text(json.dumps(qc_log, indent=2, default=str))
        print(f"QC log JSON written to {json_path}")

        # Final database stats
        tables = con.execute("SHOW TABLES").fetchall()
        print(f"\n=== Phase 1 Complete ===")
        print(f"Database: {DB_PATH} ({DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)")
        print(f"Tables: {[t[0] for t in tables]}")

        if unmatched:
            print(f"\n⚠ UNMATCHED COUNTRIES ({len(unmatched)}): {unmatched}")
            print("These need manual ISO3 mapping.")

    finally:
        con.close()


if __name__ == "__main__":
    main()
