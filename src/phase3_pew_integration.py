"""Phase 3 Supplement: Integrate Pew Research datasets into country_enrichment.
Adds Religious Composition (201 countries), Restrictions (198), and Global Attitudes (24).
Run after phase3_enrichment.py.
"""
import duckdb
import pandas as pd
import pyreadstat
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "familysearch.duckdb"
PEW_DIR = PROJECT_ROOT / "data" / "external" / "pew"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "phase3"

qc_log = []

def log_qc(step, metric, value, note=""):
    entry = {"step": step, "metric": metric, "value": value, "note": note,
             "timestamp": datetime.now().isoformat()}
    qc_log.append(entry)
    print(f"  [{step}] {metric} = {value}  {note}")


def build_pew_name_crosswalk(con):
    """Build a mapping from Pew country names to our ISO3 codes via the FS crosswalk."""
    fs_xwalk = con.execute("SELECT fs_country_name, iso3_code FROM country_crosswalk WHERE iso3_code IS NOT NULL").df()

    # Manual overrides for Pew naming differences
    pew_to_fs = {
        "UK": "United Kingdom",
        "U.K.": "United Kingdom",
        "United States": "United States",
        "U.S.": "United States",
        "USA": "United States",
        "South Korea": "South Korea",
        "North Korea": "North Korea",
        "Czech Republic": "Czech Republic",
        "Czechia": "Czech Republic",
        "Bosnia-Herzegovina": "Bosnia and Herzegovina",
        "Bosnia and Herzegovina": "Bosnia and Herzegovina",
        "Palestinian territories": "Palestine",
        "Palestinian Territories": "Palestine",
        "Ivory Coast": "Cote d'Ivoire",
        "Côte d'Ivoire": "Cote d'Ivoire",
        "Democratic Republic of the Congo": "D.R. Congo",
        "DR Congo": "D.R. Congo",
        "Republic of the Congo": "Congo",
        "Timor-Leste": "East Timor",
        "Burma (Myanmar)": "Myanmar",
        "Burma": "Myanmar",
        "Swaziland": "Eswatini",
        "Cape Verde": "Cabo Verde",
        "Macau": "Macau",
        "Hong Kong": "Hong Kong",
        "Brunei": "Brunei",
        "Vatican City": "Vatican City",
        "Taiwan": "Taiwan",
        "Russia": "Russia",
        "Vietnam": "Vietnam",
        "Laos": "Laos",
        "Bolivia": "Bolivia",
        "Venezuela": "Venezuela",
        "Iran": "Iran",
        "Syria": "Syria",
        "Moldova": "Moldova",
        "Tanzania": "Tanzania",
        "Turkiye": "Turkey",
        "Turkey": "Turkey",
    }

    # Build Pew name → ISO3 lookup
    fs_name_to_iso3 = dict(zip(fs_xwalk["fs_country_name"], fs_xwalk["iso3_code"]))

    def resolve(pew_name):
        """Resolve a Pew country name to ISO3 via FS crosswalk."""
        # Direct match
        if pew_name in fs_name_to_iso3:
            return fs_name_to_iso3[pew_name]
        # Manual override
        if pew_name in pew_to_fs:
            fs_name = pew_to_fs[pew_name]
            return fs_name_to_iso3.get(fs_name)
        # Strip and retry
        stripped = pew_name.strip()
        if stripped in fs_name_to_iso3:
            return fs_name_to_iso3[stripped]
        return None

    return resolve


def process_religious_composition(resolve_fn):
    """Process Religious Composition 2020 dataset."""
    print("\n=== Religious Composition 2020 ===")
    pct = pd.read_csv(
        PEW_DIR / "Religious-Composition-2010-2020-dataset" /
        "Religious Composition 2010-2020 dataset" /
        "Religious Composition 2010-2020 (percentages).csv"
    )
    comp = pct[(pct["Level"] == 1) & (pct["Year"] == 2020)].copy()

    div = pd.read_csv(
        PEW_DIR / "Religious-Composition-2010-2020-dataset" /
        "Religious Composition 2010-2020 dataset" /
        "Religious Composition 2010-2020 (diversity statistics).csv"
    )
    div_2020 = div[(div["Level"] == 1) & (div["Year"] == 2020)][["Country", "RDI_score"]].copy()

    comp = comp.merge(div_2020, on="Country", how="left")
    comp["iso3_code"] = comp["Country"].map(resolve_fn)

    matched = comp["iso3_code"].notna().sum()
    log_qc("3.4a", "composition_countries", len(comp))
    log_qc("3.4a", "composition_matched", matched)
    log_qc("3.4a", "composition_unmatched", len(comp) - matched)

    unmatched = comp[comp["iso3_code"].isna()]["Country"].tolist()
    if unmatched:
        log_qc("3.4a", "unmatched_names", str(unmatched[:15]))

    result = comp[comp["iso3_code"].notna()][
        ["iso3_code", "Christians", "Muslims", "Religiously_unaffiliated", "RDI_score"]
    ].copy()
    result = result.rename(columns={
        "Christians": "pct_christian",
        "Muslims": "pct_muslim",
        "Religiously_unaffiliated": "pct_unaffiliated",
        "RDI_score": "religious_diversity_index",
    })

    return result


def process_restrictions(resolve_fn):
    """Process Religious Restrictions 2022 dataset."""
    print("\n=== Religious Restrictions 2022 ===")
    restr = pd.read_csv(
        PEW_DIR / "Global-Restrictions-on-Religion-2007-2022-Dataset" /
        "PublicDataset_ReligiousRestrictions_2007to2022.csv",
        low_memory=False,
    )
    r2022 = restr[restr["Question_Year"] == 2022][["Ctry_EditorialName", "GRI", "SHI"]].copy()
    r2022["iso3_code"] = r2022["Ctry_EditorialName"].map(resolve_fn)

    matched = r2022["iso3_code"].notna().sum()
    log_qc("3.4b", "restrictions_countries", len(r2022))
    log_qc("3.4b", "restrictions_matched", matched)

    unmatched = r2022[r2022["iso3_code"].isna()]["Ctry_EditorialName"].tolist()
    if unmatched:
        log_qc("3.4b", "unmatched_names", str(unmatched[:15]))

    result = r2022[r2022["iso3_code"].notna()][["iso3_code", "GRI", "SHI"]].copy()
    result = result.rename(columns={
        "GRI": "govt_restrictions_index",
        "SHI": "social_hostilities_index",
    })

    return result


def process_global_attitudes(resolve_fn):
    """Process Global Attitudes Spring 2025 microdata → country-level aggregates."""
    print("\n=== Global Attitudes Spring 2025 ===")
    ga_df, meta = pyreadstat.read_sav(
        str(PEW_DIR / "Pew-Research-Center-Global-Attitudes-Spring-2025-Public" /
            "Pew Research Center Global Attitudes Spring 2025 Dataset.sav")
    )
    country_labels = meta.variable_value_labels["country"]
    ga_df["country_name"] = ga_df["country"].map(country_labels)

    # Compute country-level religiosity scores (excluding DK/Refused = 8, 9)
    valid = ga_df[~ga_df["religion_import"].isin([8, 9])].copy()
    valid["relig_important"] = valid["religion_import"].isin([1, 2]).astype(int)
    valid["relig_very_important"] = (valid["religion_import"] == 1).astype(int)
    valid["prays_daily"] = valid["pray_freq"].isin([1, 2]).astype(int)
    valid["god_moral"] = (valid["believe_god"] == 2).astype(int)

    agg = valid.groupby("country_name").agg(
        pew_n_respondents=("relig_important", "count"),
        pct_relig_important=("relig_important", "mean"),
        pct_relig_very_important=("relig_very_important", "mean"),
        pct_prays_daily=("prays_daily", "mean"),
        pct_god_necessary_morality=("god_moral", "mean"),
    ).reset_index()

    # Convert to percentages
    for col in ["pct_relig_important", "pct_relig_very_important", "pct_prays_daily", "pct_god_necessary_morality"]:
        agg[col] = (agg[col] * 100).round(2)

    agg["iso3_code"] = agg["country_name"].map(resolve_fn)

    matched = agg["iso3_code"].notna().sum()
    log_qc("3.4c", "attitudes_countries", len(agg))
    log_qc("3.4c", "attitudes_matched", matched)

    unmatched = agg[agg["iso3_code"].isna()]["country_name"].tolist()
    if unmatched:
        log_qc("3.4c", "unmatched_names", str(unmatched))

    result = agg[agg["iso3_code"].notna()].drop(columns=["country_name"])
    return result


def main():
    print("Phase 3 Supplement: Pew Research Integration")

    con = duckdb.connect(str(DB_PATH))

    try:
        resolve_fn = build_pew_name_crosswalk(con)

        # Process all three datasets
        comp_df = process_religious_composition(resolve_fn)
        restr_df = process_restrictions(resolve_fn)
        attitudes_df = process_global_attitudes(resolve_fn)

        # Merge all Pew data on ISO3
        pew_merged = comp_df.merge(restr_df, on="iso3_code", how="outer")
        pew_merged = pew_merged.merge(attitudes_df, on="iso3_code", how="outer")

        log_qc("3.4", "pew_merged_countries", len(pew_merged))
        for col in pew_merged.columns:
            if col != "iso3_code":
                n = pew_merged[col].notna().sum()
                log_qc("3.4", f"pew_{col}_coverage", n)

        # Add new columns to country_enrichment
        existing = con.execute("SELECT * FROM country_enrichment").df()
        log_qc("3.4", "existing_enrichment_cols", len(existing.columns))

        # Merge Pew data into existing enrichment
        updated = existing.merge(pew_merged, on="iso3_code", how="left")
        log_qc("3.4", "updated_enrichment_cols", len(updated.columns))

        # Write back
        con.execute("DROP TABLE IF EXISTS country_enrichment")
        con.register("_updated_df", updated)
        con.execute("CREATE TABLE country_enrichment AS SELECT * FROM _updated_df")
        con.unregister("_updated_df")

        final_count = con.execute("SELECT COUNT(*) FROM country_enrichment").fetchone()[0]
        final_cols = len(con.execute("DESCRIBE country_enrichment").fetchall())
        log_qc("3.4", "final_enrichment_rows", final_count)
        log_qc("3.4", "final_enrichment_cols", final_cols)

        # User-level coverage check
        total_users = con.execute("SELECT COUNT(*) FROM users_clean").fetchone()[0]
        for col in ["pct_christian", "govt_restrictions_index", "pct_relig_important"]:
            if col in updated.columns:
                n = con.execute(f"""
                    SELECT COUNT(*) FROM users_clean u
                    JOIN country_enrichment e ON u.iso3_code = e.iso3_code
                    WHERE e.{col} IS NOT NULL
                """).fetchone()[0]
                log_qc("3.4", f"users_with_{col}", n, f"{n/total_users*100:.1f}%")

        # Persist QC log
        for entry in qc_log:
            con.execute("""
                INSERT INTO qc_log (step, metric, value, note, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, [entry["step"], entry["metric"], str(entry["value"]), entry.get("note", ""),
                  entry["timestamp"]])

        # Write report
        report = [
            "# Phase 3 Supplement: Pew Research Integration",
            f"\n**Generated**: {datetime.now().isoformat()}",
            "\n---\n",
            "## QC Log\n",
            "| Step | Metric | Value | Note |",
            "|------|--------|-------|------|",
        ]
        for entry in qc_log:
            val = str(entry["value"])[:80]
            report.append(f"| {entry['step']} | {entry['metric']} | {val} | {entry.get('note', '')} |")

        (OUTPUT_DIR / "pew_integration_report.md").write_text("\n".join(report))
        (OUTPUT_DIR / "pew_qc_log.json").write_text(json.dumps(qc_log, indent=2, default=str))

        # Print final enrichment schema
        print(f"\n=== Integration Complete ===")
        print(f"country_enrichment: {final_count} countries, {final_cols} columns")
        cols = con.execute("DESCRIBE country_enrichment").fetchall()
        print("\nFinal schema:")
        for name, dtype, *_ in cols:
            n = con.execute(f"SELECT COUNT(*) FROM country_enrichment WHERE {name} IS NOT NULL").fetchone()[0]
            print(f"  {name:<35} {dtype:<10} {n:>4} non-null ({n/final_count*100:.0f}%)")

    finally:
        con.close()


if __name__ == "__main__":
    main()
