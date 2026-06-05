<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/scikit--learn-1.3+-F7931E?style=for-the-badge&logo=scikitlearn&logoColor=white" alt="scikit-learn">
  <img src="https://img.shields.io/badge/DuckDB-Analytical_DB-FFF000?style=for-the-badge&logo=duckdb&logoColor=black" alt="DuckDB">
  <img src="https://img.shields.io/badge/Streamlit-Dashboard-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit">
  <img src="https://img.shields.io/badge/Plotly-Interactive_Viz-3F4F75?style=for-the-badge&logo=plotly&logoColor=white" alt="Plotly">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
</p>

# Ancestry Insights

**Machine learning user segmentation analysis on 7.6 million genealogy records -- behavioral clustering, interactive dashboards, and data-driven insights at scale.**

---

## What Makes This Interesting

This is not a toy clustering exercise on a clean Kaggle dataset. The raw data is 7.6M user records with structurally missing data blocks, heavy-tailed distributions, and severe tenure bias (users observed for 1 day vs. 365 days in the same table). The interesting engineering decisions are in how these problems are solved before any model touches the data:

- **Tenure-normalized feature engineering** -- raw activity counts are meaningless when observation windows vary 365x. Every behavioral feature is rate-adjusted (per-week, per-90-day-window, log-transformed) before clustering.
- **MNAR detection and handling** -- 11 activity columns go null as a block (Missing Not At Random). These are not imputed; they are detected, flagged, and excluded from the clustering population with explicit justification.
- **Custom composite index (GEPI)** -- no published index combines economic development, religiosity, and digital access for genealogy engagement prediction. A Genealogy Engagement Propensity Index was constructed from World Bank, UN HDI, and Pew Research data, validated against observed registration rates.
- **Stratified bootstrap stability** -- every clustering result is validated across T=10 stratified subsamples with Cochran floor guarantees per stratum. The reported metrics are medians with IQR, not single-run numbers.
- **Supervised-unsupervised fusion** -- discriminant analysis (LDA/RF) identifies which features predict persistence; unsupervised clustering (K-Means/GMM/HDBSCAN) discovers natural structure. The overlay between the two reveals which behavioral clusters have actionable retention profiles.

---

## Architecture

```
                    7.6M raw records (CSV, 33 columns)
                              |
                    +---------v----------+
                    |  DuckDB 7-Layer DB |
                    |  (familysearch.db) |
                    +---------+----------+
                              |
          +-------------------+-------------------+
          |                   |                   |
  +-------v-------+  +-------v-------+  +-------v--------+
  | Layer 1: Raw  |  | Layer 4:      |  | Layer 7:       |
  | Layer 2: Clean|  | External      |  | Cluster        |
  | Layer 3: Feat.|  | Enrichment    |  | Assignments    |
  +-------+-------+  +-------+-------+  +-------+--------+
          |                   |                   |
          +-------------------+-------------------+
                              |
              +---------------+---------------+
              |               |               |
      +-------v------+ +-----v------+ +------v-------+
      | Phase 4:     | | Phase 5:   | | Phase 6-7:   |
      | Subsampling  | | LDA / RF   | | K-Means, GMM |
      | T=10 x 5,000 | | Feature    | | HDBSCAN, PCA |
      | Stratified   | | Importance | | Factor Anal. |
      +--------------+ +-----+------+ +------+-------+
                              |               |
                      +-------v---------------v-------+
                      |     Phase 7b: Deep Dive       |
                      |  Bootstrap stability, biplots |
                      |  Radar profiles, silhouette   |
                      +---------------+---------------+
                                      |
                    +-----------------+-----------------+
                    |                                   |
            +-------v--------+               +---------v--------+
            | Streamlit v2   |               | PowerPoint Deck  |
            | 8-page         |               | Executive Summary|
            | dashboard      |               | (python-pptx)    |
            +----------------+               +------------------+
```

---

## Key Technical Features

### 7-Layer DuckDB Architecture
The database schema separates concerns by transformation stage: raw immutable data, deterministic cleaning, engineered features, external enrichment, country crosswalk, subsample partitions, and cluster assignments. Each layer is reproducible from the one above it. No pandas-in-memory recomputation on restart.

### 4-Construct Feature Engineering
25+ derived features organized into four behavioral constructs -- **Velocity** (time-to-first-action milestones), **Volume** (tenure-normalized activity rates), **Sequencing** (engagement funnel progression), and **Persistence** (sustained engagement indicators). Feature selection via Random Forest importance with collinearity deduplication.

### Multi-Algorithm Clustering Comparison
Systematic evaluation of K-Means, Gaussian Mixture Models, and HDBSCAN across 6 feature set configurations, 4 rotation methods (PCA, Varimax, ICA, Factor Analysis), and 3 scaling strategies. Optimization target: silhouette score multiplied by Cramer's V (cluster-persistence association) at k=5.

### External Data Enrichment Pipeline
Automated ingestion from World Bank WDI (5 indicators), UN HDI, and Pew Research Center (religious composition for 201 countries, government restrictions for 198). Country-to-ISO3 crosswalk handles FamilySearch's non-standard country names with manual overrides.

### Interactive 8-Page Dashboard
Streamlit multi-page app with custom FamilySearch-inspired branding, interactive Plotly visualizations, and live DuckDB queries. Pages span the full analysis lifecycle: data quality audit, EDA, feature engineering explorer, interactive clustering lab, segment profiling, and business insights.

---

## Project Metrics

| Metric | Value |
|---|---|
| Raw records | 7,625,105 |
| Raw columns | 33 |
| Engineered features | 25+ |
| External data sources | 3 (World Bank, UN, Pew) |
| Country enrichment coverage | 201 countries |
| Clustering algorithms | 3 (K-Means, GMM, HDBSCAN) |
| Dimensionality reduction methods | 4 (PCA, Factor Analysis, ICA, LDA) |
| Bootstrap subsamples | T=10 x 5,000 stratified |
| Dashboard pages | 8 |
| Visualizations generated | 147 |
| Analysis reports generated | 26 |
| Pipeline phases | 7 (+ 3 sub-phases) |
| Python source files | 22 |
| Lines of code (pipeline) | ~7,000 |
| Lines of code (dashboard) | ~2,000 |

---

## Tech Stack

| Layer | Tools |
|---|---|
| **Data Storage** | DuckDB (embedded columnar OLAP), Parquet exports |
| **Data Processing** | pandas, NumPy, PyArrow |
| **Machine Learning** | scikit-learn (K-Means, GMM, LDA, RF, PCA), hdbscan, umap-learn |
| **Statistical Analysis** | SciPy (chi-squared, partial correlation, curve fitting), bootstrap validation |
| **Visualization** | Plotly (interactive), Matplotlib, Seaborn |
| **Dashboard** | Streamlit (multi-page, custom theming) |
| **External Data** | World Bank API (wbgapi), Pew Research (pyreadstat/SPSS), UN HDI |
| **Reporting** | python-pptx (automated executive slide deck) |

---

## Repository Structure

```
ancestry-insights/
  src/                    # Analysis pipeline (22 modules, ~7K LOC)
    phase1_infrastructure.py    # CSV ingest, QC, DuckDB schema
    phase2_features.py          # Feature engineering (4 constructs)
    phase3_enrichment.py        # World Bank + UN enrichment
    phase3_pew_integration.py   # Pew religiosity data
    phase4_subsampling.py       # Stratified bootstrap draws
    phase5_classification.py    # LDA / RF discriminant analysis
    phase6_clustering.py        # K-Means, GMM clustering
    phase7_cluster_optimization.py  # Rotation + weighting grid search
    phase7b_deep_dive.py        # Publication-quality profiling
    final_analysis.py           # End-to-end factorial design
    build_slide_deck.py         # Automated PowerPoint generation
  dashboard_v2/           # Streamlit app (8 pages, ~2K LOC)
    Home.py                     # Landing page with dataset summary
    pages/                      # Workflow, Data Quality, EDA, Feature Lab,
                                # Clustering Lab, Segment Profiles, Insights, About
    components/                 # Branding, charts, metrics
  docs/                   # Methodology, literature review, hypothesis pipeline
  outputs/                # 147 figures, 26 reports across 18 subdirectories
  screenshots/            # Dashboard captures
```

---

## Getting Started

```bash
# Clone and set up environment
git clone https://github.com/<your-username>/ancestry-insights.git
cd ancestry-insights
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the analysis pipeline (phases are sequential)
python src/phase1_infrastructure.py    # Requires data/raw/users.csv
python src/phase2_features.py
python src/phase3_enrichment.py
# ... phases 4-7

# Launch the dashboard
./run_dashboard.sh
# Open http://localhost:8501
```

> **Note**: The raw dataset (7.6M records) is not included in this repository. The pipeline scripts, dashboard, methodology documentation, and all generated outputs are fully available for review.

---

## License

MIT License. See [LICENSE](LICENSE) for details.

---

<p align="center">
  <i>From 7.6 million rows of behavioral data to actionable user segments -- built with statistical rigor, not just algorithms.</i>
</p>
