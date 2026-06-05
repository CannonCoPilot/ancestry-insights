"""Phase 3: External Data Enrichment
Downloads country-level covariates, builds country_enrichment table, computes GEPI.
Run once after Phase 1 (needs country_crosswalk). Can run parallel with Phase 2.
Outputs: country_enrichment table in DuckDB, outputs/phase3/ reports.
"""
import duckdb
import json
import pandas as pd
import warnings
from pathlib import Path
from datetime import datetime
from io import StringIO

warnings.filterwarnings("ignore", category=FutureWarning)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "familysearch.duckdb"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "phase3"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

qc_log = []

def log_qc(step: str, metric: str, value, note: str = ""):
    entry = {"step": step, "metric": metric, "value": value, "note": note,
             "timestamp": datetime.now().isoformat()}
    qc_log.append(entry)
    print(f"  [{step}] {metric} = {value}  {note}")


def step_3_1_world_bank():
    """Download World Bank WDI indicators via wbgapi."""
    print("\n=== Step 3.1: World Bank WDI ===")
    try:
        import wbgapi as wb

        indicators = {
            "NY.GDP.PCAP.PP.CD": "gdp_per_capita_ppp",
            "IT.NET.USER.ZS": "internet_pct",
            "IT.CEL.SETS.P2": "mobile_per_100",
            "SE.TER.ENRR": "tertiary_enrollment",
            "SP.POP.TOTL": "population",
        }

        # Fetch each indicator separately with mrv=5, take most recent non-null value
        # (mrv=1 often returns the current year which has no data yet)
        frames = []
        for code, name in indicators.items():
            records = list(wb.data.fetch(code, mrv=5))
            if records:
                rdf = pd.DataFrame(records)
                rdf = rdf[rdf["aggregate"] == False]  # Exclude regional aggregates
                rdf = rdf.sort_values("time", ascending=False)
                rdf = rdf.dropna(subset=["value"])
                rdf = rdf.drop_duplicates(subset=["economy"], keep="first")
                rdf = rdf[["economy", "value"]].rename(columns={"economy": "iso3_code", "value": name})
                frames.append(rdf)
                log_qc("3.1", f"wdi_{name}_coverage", len(rdf))

        if frames:
            df = frames[0]
            for f in frames[1:]:
                df = df.merge(f, on="iso3_code", how="outer")
            log_qc("3.1", "wdi_countries", len(df))
            return df
        else:
            log_qc("3.1", "WARNING", "No WDI data fetched")
            return pd.DataFrame()

    except Exception as e:
        log_qc("3.1", "ERROR", str(e))
        print(f"  World Bank download failed: {e}")
        return pd.DataFrame()


def step_3_2_un_hdi():
    """Download UN HDI composite index via direct CSV."""
    print("\n=== Step 3.2: UN HDI ===")
    try:
        import urllib.request
        url = "https://hdr.undp.org/sites/default/files/2025_HDR/HDR25_Composite_indices_complete_time_series.csv"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research; FamilySearch analysis)"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw_bytes = resp.read()
        # Try utf-8 first, fall back to latin-1
        for encoding in ["utf-8-sig", "utf-8", "latin-1"]:
            try:
                csv_text = raw_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        df = pd.read_csv(StringIO(csv_text))

        # The CSV has columns like 'iso3', 'country', 'hdi_2023', 'hdi_2022', etc.
        # Find the most recent HDI column
        hdi_cols = [c for c in df.columns if c.startswith("hdi_") and c[4:].isdigit()]
        if not hdi_cols:
            # Try alternate naming
            hdi_cols = [c for c in df.columns if "hdi" in c.lower() and any(str(y) in c for y in range(2020, 2026))]

        if hdi_cols:
            hdi_cols_sorted = sorted(hdi_cols, key=lambda c: int(c.split("_")[-1]) if c.split("_")[-1].isdigit() else 0, reverse=True)
            most_recent = hdi_cols_sorted[0]
            log_qc("3.2", "hdi_most_recent_col", most_recent)
        else:
            log_qc("3.2", "WARNING", "No HDI year columns found")
            log_qc("3.2", "available_columns", str(df.columns.tolist()[:20]))
            return pd.DataFrame()

        # Find iso3 column
        iso3_col = None
        for candidate in ["iso3", "ISO3", "iso_code", "country_code"]:
            if candidate in df.columns:
                iso3_col = candidate
                break
        if iso3_col is None:
            # Check if there's a column with 3-char codes
            for col in df.columns:
                sample = df[col].dropna().head(10)
                if sample.str.len().eq(3).all() and sample.str.isalpha().all():
                    iso3_col = col
                    break

        if iso3_col is None:
            log_qc("3.2", "WARNING", "No ISO3 column found")
            log_qc("3.2", "columns", str(df.columns.tolist()[:15]))
            return pd.DataFrame()

        # Also grab education index and life expectancy if available
        edu_cols = [c for c in df.columns if "eys_" in c or "education" in c.lower()]
        le_cols = [c for c in df.columns if "le_" in c and c.split("_")[-1].isdigit()]

        result = df[[iso3_col, most_recent]].copy()
        result = result.rename(columns={iso3_col: "iso3_code", most_recent: "hdi"})

        # Add education index (expected years of schooling) if available
        if edu_cols:
            edu_sorted = sorted(edu_cols, reverse=True)
            result["education_index"] = df[edu_sorted[0]]
            log_qc("3.2", "education_col", edu_sorted[0])

        # Add life expectancy if available
        if le_cols:
            le_sorted = sorted(le_cols, reverse=True)
            result["life_expectancy"] = df[le_sorted[0]]
            log_qc("3.2", "life_exp_col", le_sorted[0])

        result = result.dropna(subset=["hdi"])
        result["hdi"] = pd.to_numeric(result["hdi"], errors="coerce")
        result = result.dropna(subset=["hdi"])

        log_qc("3.2", "hdi_countries", len(result))
        log_qc("3.2", "hdi_range", f"{result['hdi'].min():.3f} - {result['hdi'].max():.3f}")

        return result

    except Exception as e:
        log_qc("3.2", "ERROR", str(e))
        print(f"  UN HDI download failed: {e}")
        return pd.DataFrame()


def step_3_3_itu():
    """Attempt to download ITU IDI data."""
    print("\n=== Step 3.3: ITU IDI ===")
    try:
        url = "https://www.itu.int/en/ITU-D/Statistics/Documents/IDI/IDIDataset.xlsx"
        df = pd.read_excel(url, engine="openpyxl")
        log_qc("3.3", "itu_rows", len(df))
        log_qc("3.3", "itu_columns", str(df.columns.tolist()[:10]))
        # Parse would need inspection of actual sheet structure
        return df
    except Exception as e:
        log_qc("3.3", "DEFERRED", str(e), "ITU Excel download failed or format changed; using WDI internet_pct as substitute")
        return pd.DataFrame()


def step_3_4_pew():
    """Pew religiosity — requires account; defer with documentation."""
    print("\n=== Step 3.4: Pew Religiosity ===")
    log_qc("3.4", "DEFERRED", "Requires free account at pewresearch.org + SPSS download",
            "36-country coverage only. Can be added in Phase 3 iteration 2.")
    return pd.DataFrame()


def step_3_5_lds_stats():
    """Download LDS Church statistics from GitHub community CSV."""
    print("\n=== Step 3.5: LDS Church Statistics ===")
    try:
        url = "https://github.com/LatterDataSaint/All-LDS-Facts-and-Statistics-Pages/raw/main/lds_fs_countries_20120213-to-20250803.csv"
        df = pd.read_csv(url, low_memory=False)

        log_qc("3.5", "lds_raw_rows", len(df))
        log_qc("3.5", "lds_columns", str(df.columns.tolist()[:15]))

        # Get most recent snapshot per country
        # The CSV typically has columns like: country, date, membership, congregations, stakes, temples, etc.
        date_col = None
        for candidate in ["date", "Date", "snapshot_date", "scrape_date", "timestamp"]:
            if candidate in df.columns:
                date_col = candidate
                break

        country_col = None
        for candidate in ["country", "Country", "country_name"]:
            if candidate in df.columns:
                country_col = candidate
                break

        if country_col is None:
            log_qc("3.5", "WARNING", f"No country column found. Cols: {df.columns.tolist()[:10]}")
            return pd.DataFrame()

        membership_col = None
        for candidate in ["membership", "Membership", "members", "Members", "total_membership",
                          "Total Church Membership"]:
            if candidate in df.columns:
                membership_col = candidate
                break

        congregations_col = None
        for candidate in ["congregations", "Congregations", "wards_branches"]:
            if candidate in df.columns:
                congregations_col = candidate
                break

        temples_col = None
        for candidate in ["temples", "Temples", "operating_temples"]:
            if candidate in df.columns:
                temples_col = candidate
                break

        stakes_col = None
        for candidate in ["stakes", "Stakes"]:
            if candidate in df.columns:
                stakes_col = candidate
                break

        population_col = None
        for candidate in ["population", "Population"]:
            if candidate in df.columns:
                population_col = candidate
                break

        log_qc("3.5", "detected_cols", {
            "country": country_col, "date": date_col,
            "membership": membership_col, "congregations": congregations_col,
            "temples": temples_col, "stakes": stakes_col, "population": population_col
        })

        # Get most recent row per country
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df = df.sort_values(date_col, ascending=False).drop_duplicates(subset=[country_col], keep="first")
        else:
            df = df.drop_duplicates(subset=[country_col], keep="last")

        # Build result
        result = pd.DataFrame({"country_name": df[country_col]})
        if membership_col:
            result["lds_membership"] = pd.to_numeric(df[membership_col].astype(str).str.replace(",", ""), errors="coerce")
        if congregations_col:
            result["lds_congregations"] = pd.to_numeric(df[congregations_col].astype(str).str.replace(",", ""), errors="coerce")
        if temples_col:
            result["lds_temples"] = pd.to_numeric(df[temples_col].astype(str).str.replace(",", ""), errors="coerce")
        if stakes_col:
            result["lds_stakes"] = pd.to_numeric(df[stakes_col].astype(str).str.replace(",", ""), errors="coerce")
        if population_col:
            result["lds_country_pop"] = pd.to_numeric(df[population_col].astype(str).str.replace(",", ""), errors="coerce")

        result = result.dropna(subset=["country_name"])
        log_qc("3.5", "lds_countries", len(result))
        if "lds_membership" in result.columns:
            log_qc("3.5", "lds_total_membership", int(result["lds_membership"].sum()))
            log_qc("3.5", "lds_countries_with_members", int((result["lds_membership"] > 0).sum()))

        return result

    except Exception as e:
        log_qc("3.5", "ERROR", str(e))
        print(f"  LDS stats download failed: {e}")
        return pd.DataFrame()


def step_3_6_google_trends():
    """Google Trends — defer with documentation."""
    print("\n=== Step 3.6: Google Trends ===")
    log_qc("3.6", "DEFERRED", "pytrends archived Apr 2025; official API closed-alpha",
            "Manual export from trends.google.com possible but deferred for proof-of-concept.")
    return pd.DataFrame()


def step_3_7_build_enrichment(con, wdi_df, hdi_df, lds_df):
    """Build country_enrichment table by joining all sources on ISO3."""
    print("\n=== Step 3.7: Build country_enrichment table ===")

    # Start with the crosswalk as the base
    crosswalk = con.execute("SELECT fs_country_name, iso3_code FROM country_crosswalk WHERE iso3_code IS NOT NULL").df()
    log_qc("3.7", "crosswalk_countries", len(crosswalk))

    # Get unique ISO3 codes from crosswalk
    base = crosswalk[["iso3_code"]].drop_duplicates().copy()
    base = base[base["iso3_code"].notna()].reset_index(drop=True)
    log_qc("3.7", "unique_iso3_codes", len(base))

    # Join WDI
    if not wdi_df.empty and "iso3_code" in wdi_df.columns:
        wdi_cols = [c for c in wdi_df.columns if c != "iso3_code"]
        base = base.merge(wdi_df[["iso3_code"] + wdi_cols], on="iso3_code", how="left")
        for col in wdi_cols:
            n = base[col].notna().sum()
            log_qc("3.7", f"joined_wdi_{col}", n, f"{n/len(base)*100:.1f}%")

    # Join HDI
    if not hdi_df.empty and "iso3_code" in hdi_df.columns:
        hdi_cols = [c for c in hdi_df.columns if c != "iso3_code"]
        base = base.merge(hdi_df[["iso3_code"] + hdi_cols], on="iso3_code", how="left")
        for col in hdi_cols:
            n = base[col].notna().sum()
            log_qc("3.7", f"joined_hdi_{col}", n, f"{n/len(base)*100:.1f}%")

    # Join LDS (needs country name → ISO3 crosswalk)
    if not lds_df.empty and "country_name" in lds_df.columns:
        # Map LDS country names to ISO3 via our crosswalk
        lds_merged = lds_df.merge(crosswalk, left_on="country_name", right_on="fs_country_name", how="inner")
        lds_cols = [c for c in lds_df.columns if c != "country_name"]
        if "iso3_code" in lds_merged.columns and len(lds_merged) > 0:
            lds_agg = lds_merged.groupby("iso3_code")[lds_cols].first().reset_index()
            base = base.merge(lds_agg, on="iso3_code", how="left")
            for col in lds_cols:
                if col in base.columns:
                    n = base[col].notna().sum()
                    log_qc("3.7", f"joined_lds_{col}", n, f"{n/len(base)*100:.1f}%")

        # Compute LDS density if we have both membership and population
        if "lds_membership" in base.columns:
            pop_col = "lds_country_pop" if "lds_country_pop" in base.columns else "population"
            if pop_col in base.columns:
                base["lds_members_per_capita"] = base["lds_membership"] / base[pop_col].clip(lower=1)
                n = base["lds_members_per_capita"].notna().sum()
                log_qc("3.7", "lds_density_coverage", n)

    # Write to DuckDB
    con.execute("DROP TABLE IF EXISTS country_enrichment")
    con.register("_enrichment_df", base)
    con.execute("CREATE TABLE country_enrichment AS SELECT * FROM _enrichment_df")
    con.unregister("_enrichment_df")

    row_count = con.execute("SELECT COUNT(*) FROM country_enrichment").fetchone()[0]
    col_count = len(con.execute("DESCRIBE country_enrichment").fetchall())
    log_qc("3.7", "enrichment_rows", row_count)
    log_qc("3.7", "enrichment_cols", col_count)

    return base


def step_3_8_gepi(con, enrichment_df):
    """Compute GEPI composite score."""
    print("\n=== Step 3.8: GEPI Composite ===")

    gepi_components = []
    for col in ["gdp_per_capita_ppp", "internet_pct", "hdi", "lds_members_per_capita"]:
        if col in enrichment_df.columns:
            gepi_components.append(col)

    log_qc("3.8", "gepi_components_available", len(gepi_components))
    log_qc("3.8", "gepi_components", gepi_components)

    if len(gepi_components) < 3:
        log_qc("3.8", "SKIPPED", "Fewer than 3 components available")
        return

    # Standardize each component to z-scores
    z_df = enrichment_df[["iso3_code"] + gepi_components].copy()
    for col in gepi_components:
        mean = z_df[col].mean()
        std = z_df[col].std()
        if std > 0:
            z_df[f"z_{col}"] = (z_df[col] - mean) / std
        else:
            z_df[f"z_{col}"] = 0

    # GEPI = mean of available z-scores (require at least 3 non-null)
    z_cols = [f"z_{c}" for c in gepi_components]
    z_df["gepi"] = z_df[z_cols].mean(axis=1)
    z_df["gepi_n_components"] = z_df[z_cols].notna().sum(axis=1)
    z_df.loc[z_df["gepi_n_components"] < 3, "gepi"] = None

    n_gepi = z_df["gepi"].notna().sum()
    log_qc("3.8", "gepi_countries", n_gepi)
    if n_gepi > 0:
        log_qc("3.8", "gepi_range", f"{z_df['gepi'].min():.3f} to {z_df['gepi'].max():.3f}")

    # Update enrichment table with GEPI
    try:
        con.execute("ALTER TABLE country_enrichment ADD COLUMN gepi DOUBLE")
    except Exception:
        pass
    for _, row in z_df[z_df["gepi"].notna()].iterrows():
        con.execute("UPDATE country_enrichment SET gepi = ? WHERE iso3_code = ?",
                     [float(row["gepi"]), row["iso3_code"]])

    log_qc("3.8", "gepi_written_to_db", n_gepi)


def step_3_9_coverage_report(con):
    """Generate coverage validation report."""
    print("\n=== Step 3.9: Coverage Validation ===")

    # Get all enrichment columns
    cols = [r[0] for r in con.execute("DESCRIBE country_enrichment").fetchall() if r[0] != "iso3_code"]

    # Count non-null per column
    report_lines = [
        "# Phase 3: External Enrichment Coverage Report",
        f"\n**Generated**: {datetime.now().isoformat()}",
        "\n---\n",
        "## Column Coverage\n",
        "| Column | Non-NULL | % Coverage |",
        "|--------|---------|-----------|",
    ]

    total = con.execute("SELECT COUNT(*) FROM country_enrichment").fetchone()[0]
    for col in cols:
        n = con.execute(f"SELECT COUNT(*) FROM country_enrichment WHERE {col} IS NOT NULL").fetchone()[0]
        pct = n / total * 100 if total > 0 else 0
        report_lines.append(f"| {col} | {n} | {pct:.1f}% |")
        log_qc("3.9", f"coverage:{col}", n, f"{pct:.1f}%")

    # Cross-reference with FamilySearch user data
    report_lines.extend([
        "\n## User-Level Coverage\n",
        "How many FamilySearch users can be enriched?\n",
    ])

    # Count users whose iso3_code matches an enrichment row
    if "users_features" in [r[0] for r in con.execute("SHOW TABLES").fetchall()]:
        source_table = "users_features"
    else:
        source_table = "users_clean"

    user_total = con.execute(f"SELECT COUNT(*) FROM {source_table}").fetchone()[0]
    user_enriched = con.execute(f"""
        SELECT COUNT(*) FROM {source_table} u
        JOIN country_enrichment e ON u.iso3_code = e.iso3_code
    """).fetchone()[0]
    log_qc("3.9", "users_enrichable", user_enriched, f"{user_enriched/user_total*100:.1f}%")

    for col in ["gdp_per_capita_ppp", "hdi", "lds_membership", "gepi"]:
        if col in cols:
            n = con.execute(f"""
                SELECT COUNT(*) FROM {source_table} u
                JOIN country_enrichment e ON u.iso3_code = e.iso3_code
                WHERE e.{col} IS NOT NULL
            """).fetchone()[0]
            log_qc("3.9", f"users_with_{col}", n, f"{n/user_total*100:.1f}%")

    report_lines.append(f"\n| Metric | Count | % of {user_total:,} users |")
    report_lines.append("|--------|-------|---------|")
    report_lines.append(f"| Has any enrichment | {user_enriched:,} | {user_enriched/user_total*100:.1f}% |")

    # Deferred sources
    report_lines.extend([
        "\n## Deferred Sources\n",
        "| Source | Reason | Impact |",
        "|--------|--------|--------|",
        "| Pew Religiosity | Requires free account + SPSS download | 36-country coverage only |",
        "| Google Trends | pytrends archived; official API closed-alpha | Genealogy interest proxy unavailable |",
        "| ITU IDI | Excel download may have changed format | WDI internet_pct used as substitute |",
    ])

    (OUTPUT_DIR / "coverage_report.md").write_text("\n".join(report_lines))
    log_qc("3.9", "report_written", str(OUTPUT_DIR / "coverage_report.md"))


def main():
    print("Phase 3: External Data Enrichment")

    # Steps 3.1-3.6: Download external data (parallel-safe, no DB writes)
    wdi_df = step_3_1_world_bank()
    hdi_df = step_3_2_un_hdi()
    step_3_3_itu()  # Likely deferred
    step_3_4_pew()  # Deferred
    lds_df = step_3_5_lds_stats()
    step_3_6_google_trends()  # Deferred

    # Steps 3.7-3.10: Build enrichment table (needs DB)
    con = duckdb.connect(str(DB_PATH))
    try:
        enrichment_df = step_3_7_build_enrichment(con, wdi_df, hdi_df, lds_df)
        step_3_8_gepi(con, enrichment_df)
        step_3_9_coverage_report(con)

        # Persist QC log
        for entry in qc_log:
            con.execute("""
                INSERT INTO qc_log (step, metric, value, note, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, [entry["step"], entry["metric"], str(entry["value"]), entry.get("note", ""),
                  entry["timestamp"]])

        # Write JSON log
        (OUTPUT_DIR / "qc_log.json").write_text(json.dumps(qc_log, indent=2, default=str))

        # Summary
        enrichment_count = con.execute("SELECT COUNT(*) FROM country_enrichment").fetchone()[0]
        enrichment_cols = len(con.execute("DESCRIBE country_enrichment").fetchall())
        print(f"\n=== Phase 3 Complete ===")
        print(f"country_enrichment: {enrichment_count} countries, {enrichment_cols} columns")
        print(f"Reports: {OUTPUT_DIR}")

    finally:
        con.close()


if __name__ == "__main__":
    main()
