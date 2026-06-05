# Methodology Report: Pre-Clustering Data Assessment

**Date**: 2026-03-25
**Dataset**: FamilySearch User Segmentation (7.6M accounts, 33 columns)
**Sample**: 250,000 stratified sample (Parquet cache)
**Purpose**: Establish sound methodology for handling tenure bias, missingness, feature engineering, and external enrichment prior to clustering analysis.

---

## 0. Data Infrastructure: Database-First Architecture

### The Case for a Database

The analysis pipeline involves multiple data operations that compound in cost when performed on flat files:

1. **Raw data** (7.6M rows, 33 cols, 1.5GB CSV) — too large for in-memory exploration without sampling
2. **Engineered features** (20+ derived columns per user) — computed once, queried many times
3. **External enrichment** (country-level covariates from 6+ sources) — joined to every user record
4. **Composite subsamples** (T=5 draws of n=30,000 with stratification logic) — reproducible draws with recorded weights
5. **Clustering results** (labels, centroids, metrics per run) — persisted across experiments
6. **Parquet exports** (for dashboard consumption) — generated from materialized views

Performing all of this through pandas DataFrames in memory creates three problems: (a) the 1.5GB raw data must be re-loaded on every notebook/dashboard restart, (b) feature engineering must be re-computed on every session, and (c) subsample draws are not reproducible unless seeds AND the exact data state are preserved. A database solves all three by making the computed state persistent, queryable, and versionable.

### Recommended Architecture: DuckDB (Embedded Analytical Database)

**Why DuckDB over PostgreSQL**: The analysis is single-user, read-heavy, and analytical (OLAP). DuckDB is an embedded columnar database that:
- Reads Parquet and CSV natively (zero-ETL for initial load)
- Runs analytical SQL 10-100x faster than pandas for aggregations
- Requires no server process (single file, like SQLite but columnar)
- Integrates natively with pandas and Streamlit via `duckdb.sql().df()`
- Supports window functions, CTEs, and COPY TO PARQUET for export

**Why not PostgreSQL**: Would work well (and we have one running for Jarvis) but adds server dependency, requires connection management in the dashboard, and is overkill for a single-user analytical workload. If the project scales to multi-user or production deployment, PostgreSQL is the natural upgrade path.

### Database Schema

```sql
-- ═══════════════════════════════════════════════════════════
-- LAYER 1: RAW DATA (immutable, loaded once)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE raw_users AS
SELECT * FROM read_csv_auto('data/raw/users.csv');
-- 7.6M rows, 33 columns
-- This is the single source of truth. Never modified.

-- ═══════════════════════════════════════════════════════════
-- LAYER 2: CLEANED DATA (deterministic transforms)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE users_cleaned AS
SELECT
    USER_ID,
    ACCOUNT_CREATE_DATE,
    ACCOUNT_TYPE,
    -- Age: clip to 0-110
    LEAST(GREATEST(USER_CURRENT_AGE, 0), 110) AS user_age,
    COUNTRY,
    USER_WORLD_REGION,
    USER_AREA_NAME,
    -- Province/City: convert 'Unknown'/'Redacted'/'-' to NULL (retained for Member-only geographic analysis)
    NULLIF(NULLIF(NULLIF(PROVINCE, 'Unknown'), 'Redacted'), '-') AS province,
    NULLIF(NULLIF(NULLIF(CITY, 'Unknown'), 'Redacted'), '-') AS city,

    -- Date milestones: clip negative days-to-first to 0
    EARLIEST_LOGIN_DATE,
    GREATEST(0, DATEDIFF('day', ACCOUNT_CREATE_DATE, EARLIEST_LOGIN_DATE)) AS days_to_first_login,
    EARLIEST_TREE_EDIT_DATE,
    GREATEST(0, DATEDIFF('day', ACCOUNT_CREATE_DATE, EARLIEST_TREE_EDIT_DATE)) AS days_to_first_tree_edit,
    EARLIEST_NAME_CONTRIBUTOR_DATE,
    GREATEST(0, DATEDIFF('day', ACCOUNT_CREATE_DATE, EARLIEST_NAME_CONTRIBUTOR_DATE)) AS days_to_first_name,
    EARLIEST_SOURCE_CONTRIBUTOR_DATE,
    GREATEST(0, DATEDIFF('day', ACCOUNT_CREATE_DATE, EARLIEST_SOURCE_CONTRIBUTOR_DATE)) AS days_to_first_source,

    -- Activity counts: null block → exclude flag, zeros preserved
    CASE WHEN DAYS_LOGGING_IN IS NULL THEN TRUE ELSE FALSE END AS is_null_activity_block,
    COALESCE(DAYS_LOGGING_IN, 0) AS days_logging_in,
    COALESCE(TREE_EDITS, 0) AS tree_edits,
    COALESCE(SOURCES_ADDED, 0) AS sources_added,
    COALESCE(MEMORIES_ADDED, 0) AS memories_added,
    COALESCE(GET_INVOLVED_ITEMS_REVIEWED, 0) AS get_involved_items,
    COALESCE(RECORD_EDITS, 0) AS record_edits,

    -- Name columns: null → 0 (semantically correct)
    COALESCE(TOTAL_NAMES_ADDED, 0) AS total_names_added,
    COALESCE(DECEASED_NAMES_ADDED, 0) AS deceased_names_added,
    COALESCE(LIVING_NAMES_ADDED, 0) AS living_names_added,
    COALESCE(NOVEL_NAMES_ADDED, 0) AS novel_names_added,
    COALESCE(QUALIFIED_NAMES_ADDED, 0) AS qualified_names_added,

    -- Tenure
    GREATEST(1, DATEDIFF('day', ACCOUNT_CREATE_DATE, CURRENT_DATE)) AS tenure_days

FROM raw_users
WHERE ACCOUNT_CREATE_DATE IS NOT NULL;

-- ═══════════════════════════════════════════════════════════
-- LAYER 3: ENGINEERED FEATURES (derived variables)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE users_features AS
SELECT
    c.*,

    -- Tenure-normalized rates (per week)
    c.days_logging_in / GREATEST(c.tenure_days / 7.0, 1) AS logins_per_week,
    c.tree_edits / GREATEST(c.tenure_days / 7.0, 1) AS tree_edits_per_week,
    c.sources_added / GREATEST(c.tenure_days / 7.0, 1) AS sources_per_week,
    c.memories_added / GREATEST(c.tenure_days / 7.0, 1) AS memories_per_week,
    c.total_names_added / GREATEST(c.tenure_days / 7.0, 1) AS names_per_week,
    c.get_involved_items / GREATEST(c.tenure_days / 7.0, 1) AS get_involved_per_week,
    c.record_edits / GREATEST(c.tenure_days / 7.0, 1) AS record_edits_per_week,

    -- Log-transformed counts
    LN(1 + c.days_logging_in) AS days_logging_in_log,
    LN(1 + c.tree_edits) AS tree_edits_log,
    LN(1 + c.sources_added) AS sources_added_log,
    LN(1 + c.total_names_added) AS total_names_added_log,

    -- Binary activity flags
    CASE WHEN c.days_logging_in > 0 THEN 1 ELSE 0 END AS has_logged_in,
    CASE WHEN c.tree_edits > 0 THEN 1 ELSE 0 END AS has_tree_edits,
    CASE WHEN c.sources_added > 0 THEN 1 ELSE 0 END AS has_sources,
    CASE WHEN c.memories_added > 0 THEN 1 ELSE 0 END AS has_memories,
    CASE WHEN c.get_involved_items > 0 THEN 1 ELSE 0 END AS has_get_involved,
    CASE WHEN c.record_edits > 0 THEN 1 ELSE 0 END AS has_record_edits,
    CASE WHEN c.total_names_added > 0 THEN 1 ELSE 0 END AS has_names,

    -- Activity breadth (count of activity types used)
    (CASE WHEN c.tree_edits > 0 THEN 1 ELSE 0 END
     + CASE WHEN c.sources_added > 0 THEN 1 ELSE 0 END
     + CASE WHEN c.memories_added > 0 THEN 1 ELSE 0 END
     + CASE WHEN c.get_involved_items > 0 THEN 1 ELSE 0 END
     + CASE WHEN c.record_edits > 0 THEN 1 ELSE 0 END
     + CASE WHEN c.total_names_added > 0 THEN 1 ELSE 0 END
    ) AS n_activity_types,

    -- Engagement depth ratios
    CASE WHEN c.total_names_added > 0
         THEN c.deceased_names_added * 1.0 / c.total_names_added
         ELSE 0 END AS pct_deceased_names,
    CASE WHEN c.total_names_added > 0
         THEN c.novel_names_added * 1.0 / c.total_names_added
         ELSE 0 END AS pct_novel_names,

    -- Login consistency (fraction of tenure with a login)
    LEAST(1.0, c.days_logging_in * 1.0 / GREATEST(c.tenure_days, 1)) AS login_consistency,

    -- Tenure weight (log-scaled observation window; used as sample weight in clustering — Section 1)
    LN(GREATEST(c.tenure_days / 7.0, 1)) AS tenure_weight,

    -- Age group (decade bins; age=0 excluded as missing in Layer 2; see Section 3 binning rationale)
    CASE
        WHEN c.user_age <= 19 THEN '8-19'
        WHEN c.user_age <= 29 THEN '20-29'
        WHEN c.user_age <= 39 THEN '30-39'
        WHEN c.user_age <= 49 THEN '40-49'
        WHEN c.user_age <= 59 THEN '50-59'
        WHEN c.user_age <= 69 THEN '60-69'
        WHEN c.user_age <= 79 THEN '70-79'
        ELSE '80+'
    END AS age_group

FROM users_cleaned c;

-- Index for fast lookups
CREATE INDEX idx_users_features_country ON users_features(COUNTRY);
CREATE INDEX idx_users_features_region ON users_features(USER_WORLD_REGION);
CREATE INDEX idx_users_features_type ON users_features(ACCOUNT_TYPE);

-- ═══════════════════════════════════════════════════════════
-- LAYER 4: EXTERNAL ENRICHMENT (country-level covariates)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE country_enrichment (
    iso3_code           VARCHAR(3) PRIMARY KEY,
    country_name        VARCHAR NOT NULL,
    -- World Bank / UN
    gdp_per_capita_ppp  FLOAT,
    internet_pct        FLOAT,
    mobile_per_100      FLOAT,
    hdi_score           FLOAT,
    education_index     FLOAT,
    -- Religiosity
    pct_religious       FLOAT,
    pct_christian       FLOAT,
    religious_diversity FLOAT,
    -- LDS-specific
    lds_temples         INTEGER,
    lds_membership      INTEGER,
    lds_members_per_capita FLOAT,
    -- Digital / genealogy
    genealogy_search_index FLOAT,
    -- Composites
    digital_readiness   FLOAT,
    lds_intensity       FLOAT,
    gepi_score          FLOAT,    -- Genealogy Engagement Propensity Index
    -- Metadata
    data_year           INTEGER,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE country_name_map (
    fs_country_name     VARCHAR PRIMARY KEY,  -- as in FamilySearch data
    iso3_code           VARCHAR(3) REFERENCES country_enrichment(iso3_code)
);

-- Materialized enriched users view
CREATE TABLE users_enriched AS
SELECT
    f.*,
    e.gdp_per_capita_ppp,
    e.internet_pct,
    e.hdi_score,
    e.education_index,
    e.pct_religious,
    e.lds_temples,
    e.lds_members_per_capita,
    e.digital_readiness,
    e.gepi_score
FROM users_features f
LEFT JOIN country_name_map m ON f.COUNTRY = m.fs_country_name
LEFT JOIN country_enrichment e ON m.iso3_code = e.iso3_code;

-- ═══════════════════════════════════════════════════════════
-- LAYER 5: SUBSAMPLES (reproducible draws with weights)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE subsample_registry (
    subsample_id        INTEGER PRIMARY KEY,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    n_target            INTEGER NOT NULL,      -- requested size
    n_actual            INTEGER NOT NULL,      -- actual drawn
    m_floor             INTEGER NOT NULL,      -- per-country minimum
    seed                INTEGER NOT NULL,      -- random seed
    description         VARCHAR,
    excludes_null_block BOOLEAN DEFAULT TRUE,
    excludes_lt30d      BOOLEAN DEFAULT TRUE
);

CREATE TABLE subsample_members (
    subsample_id        INTEGER REFERENCES subsample_registry(subsample_id),
    user_id             INTEGER NOT NULL,
    country             VARCHAR NOT NULL,
    sampling_weight     FLOAT NOT NULL,        -- N_h / n_h
    stratum_type        VARCHAR NOT NULL,      -- 'census' or 'sampled'
    PRIMARY KEY (subsample_id, user_id)
);

-- ═══════════════════════════════════════════════════════════
-- LAYER 6: CLUSTERING RESULTS (experiment tracking)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE clustering_experiments (
    experiment_id       INTEGER PRIMARY KEY,
    subsample_id        INTEGER REFERENCES subsample_registry(subsample_id),
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    algorithm           VARCHAR NOT NULL,       -- 'kmeans', 'gmm', 'hdbscan'
    k                   INTEGER,
    scaler              VARCHAR DEFAULT 'robust',
    feature_set         VARCHAR,                -- comma-separated feature names
    n_features          INTEGER,
    -- Quality metrics
    silhouette          FLOAT,
    calinski_harabasz   FLOAT,
    davies_bouldin      FLOAT,
    bic                 FLOAT,                  -- GMM only
    aic                 FLOAT,                  -- GMM only
    -- Stability (from clusterboot)
    mean_jaccard        FLOAT,
    min_jaccard         FLOAT,
    n_stable_clusters   INTEGER,               -- Jaccard >= 0.75
    bootstrap_r         INTEGER,
    -- Metadata
    notes               VARCHAR
);

CREATE TABLE cluster_assignments (
    experiment_id       INTEGER REFERENCES clustering_experiments(experiment_id),
    user_id             INTEGER NOT NULL,
    cluster_label       INTEGER NOT NULL,
    probability         FLOAT,                  -- GMM posterior probability
    PRIMARY KEY (experiment_id, user_id)
);

CREATE TABLE cluster_profiles (
    experiment_id       INTEGER REFERENCES clustering_experiments(experiment_id),
    cluster_label       INTEGER NOT NULL,
    feature_name        VARCHAR NOT NULL,
    mean_value          FLOAT,
    median_value        FLOAT,
    std_value           FLOAT,
    PRIMARY KEY (experiment_id, cluster_label, feature_name)
);

-- ═══════════════════════════════════════════════════════════
-- LAYER 7: USER-DEFINED DERIVED FEATURES (from Feature Lab)
-- ═══════════════════════════════════════════════════════════

CREATE TABLE derived_feature_registry (
    feature_id          INTEGER PRIMARY KEY,
    feature_name        VARCHAR NOT NULL UNIQUE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    transform_type      VARCHAR,                -- 'log1p', 'ratio', 'bin', etc.
    source_columns      VARCHAR,                -- comma-separated source columns
    description         VARCHAR,
    sql_expression      VARCHAR                 -- reproducible SQL definition
);

CREATE TABLE derived_feature_values (
    feature_id          INTEGER REFERENCES derived_feature_registry(feature_id),
    user_id             INTEGER NOT NULL,
    value               FLOAT,
    PRIMARY KEY (feature_id, user_id)
);
```

### Data Flow Diagram

```
                                    ┌─────────────┐
                                    │  Raw CSV     │
                                    │  (1.5GB)     │
                                    └──────┬───────┘
                                           │ COPY INTO (once)
                                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                        DuckDB (data.duckdb)                      │
│                                                                  │
│  Layer 1: raw_users ─────────────────────────────── 7.6M rows    │
│       │                                                          │
│       │ deterministic SQL transforms                             │
│       ▼                                                          │
│  Layer 2: users_cleaned ─────────────────────────── 7.6M rows    │
│       │  (nulls handled, ages clipped, dates derived)            │
│       │                                                          │
│       │ tenure-normalize, log, flags, ratios                     │
│       ▼                                                          │
│  Layer 3: users_features ────────────────────────── 7.6M rows    │
│       │  (+25 engineered columns = 58 total)                     │
│       │                                                          │
│       ├──── JOIN country_enrichment ──────────────── Layer 4     │
│       │     (GDP, HDI, LDS temples, GEPI)                        │
│       ▼                                                          │
│  Layer 4: users_enriched ────────────────────────── 7.6M rows    │
│       │  (+10 country covariates = 68 total)                     │
│       │                                                          │
│       │ composite allocation (m=30, seed=S)                      │
│       ▼                                                          │
│  Layer 5: subsample_members ─────────────────────── 30K rows     │
│       │  (with weights, stratum_type, subsample_id)              │
│       │                                                          │
│       │ scale → cluster → evaluate                               │
│       ▼                                                          │
│  Layer 6: clustering_experiments ────────────────── per-run      │
│           cluster_assignments                                    │
│           cluster_profiles                                       │
│                                                                  │
│  Layer 7: derived_feature_values ────────────────── user-created │
│           (from Feature Lab UI)                                  │
│                                                                  │
│  EXPORT TO:                                                      │
│  ├── data/samples/subsample_N.parquet (dashboard consumption)    │
│  └── outputs/experiment_N.json (experiment metadata)             │
└──────────────────────────────────────────────────────────────────┘
```

### Why This Architecture

| Concern | Flat File (current) | DuckDB (proposed) |
|---------|-------------------|-------------------|
| Initial load | 60-90s (pandas read_csv) | 10-15s (COPY INTO, once) |
| Subsequent access | 5-10s (read parquet) | <1s (table already loaded) |
| Feature engineering | Recomputed every session | Materialized once, queried instantly |
| Enrichment join | Manual pandas merge | SQL LEFT JOIN on materialized table |
| Subsample draws | Custom Python + seed management | SQL + registry table = reproducible |
| Experiment tracking | Session state (lost on restart) | Persistent table (survives restarts) |
| Dashboard integration | `pd.read_parquet()` | `duckdb.sql("SELECT...").df()` |
| Storage | ~500MB parquet per sample | Single file, ~2GB total |
| Dependencies | None (pandas only) | `pip install duckdb` (~20MB) |

### Implementation Plan

1. **Phase 0a**: `pip install duckdb` + create `data/data.duckdb`
2. **Phase 0b**: Load raw CSV into `raw_users` table (one-time, ~2 min for 7.6M rows)
3. **Phase 0c**: Run Layers 2-3 SQL (users_cleaned, users_features) — deterministic, takes ~30s
4. **Phase 0d**: Create Layer 4 tables (country_enrichment schema ready, data populated when available)
5. **Phase 0e**: Update dashboard `data_loader.py` to read from DuckDB instead of Parquet
6. **Phase 0f**: Update Feature Lab to write derived features to Layer 7 tables
7. **Phase 0g**: Update Clustering Lab to write results to Layer 6 tables

### Migration Path

The Parquet-based workflow continues to work in parallel. DuckDB can read existing Parquet files via `read_parquet()`, so the migration is incremental — no big-bang cutover needed. The dashboard can fall back to Parquet if DuckDB is unavailable.

### Note on PostgreSQL

If the project later requires multi-user access, API-based serving, or integration with other systems, the schema above is 100% portable to PostgreSQL. DuckDB SQL is PostgreSQL-compatible for all DDL and DML used here. The migration would be: `pg_dump`-style export from DuckDB → `psql` import to PostgreSQL → update connection string in `data_loader.py`.

---

## 1. Tenure Bias: Account Age and Signal Quality

### Question
Does account recency reduce signal quality? Should newer accounts be weighted differently or excluded?

### Empirical Findings

**Raw activity increases with tenure** (as expected — more time = more activity):

| Tenure | Mean Logins | Mean Tree Edits | Mean Sources |
|--------|------------|----------------|-------------|
| 31-90d | 1.3 | 13.8 | 1.5 |
| 91-180d | 2.2 | 13.9 | 2.4 |
| 181-270d | 4.1 | 17.8 | 5.3 |
| 271-365d | 4.9 | 20.5 | 5.8 |
| 365+d | 5.1 | 21.7 | 7.8 |

**But tenure-normalized RATES tell a different story** — newest users are the *most* active per unit time:

| Tenure | Logins/wk | Tree Edits/wk | Names/wk |
|--------|----------|---------------|---------|
| 31-90d | 0.094 | 0.996 | 0.282 |
| 91-180d | 0.100 | 0.651 | 0.195 |
| 181-270d | 0.115 | 0.503 | 0.133 |
| 271-365d | 0.097 | 0.406 | 0.101 |
| 365+d | 0.080 | 0.339 | 0.077 |

**Coefficient of variation (noise) INCREASES with tenure**, contradicting the initial hypothesis:

| Tenure | CV (Logins) | CV (Tree Edits) | CV (Names) |
|--------|------------|-----------------|-----------|
| 31-90d | 0.69 | 2.15 | 1.45 |
| 91-180d | 1.89 | 5.88 | 2.40 |
| 271-365d | 3.14 | 16.72 | 7.04 |

### Interpretation

The intuition that "newer accounts are noisier" is **empirically wrong** for this dataset. Older accounts have *higher* CV because a small number of power users accumulate extreme values over time, inflating variance. Newer accounts have more homogeneous (and paradoxically cleaner) rate distributions.

### Recommendation

1. **Tenure normalization is mandatory** — use per-week rates, not raw counts, as clustering features. This eliminates the accumulation confound.
2. **Do NOT exclude newer accounts** — they have valid, if brief, behavioral signal. The per-week rates are well-defined even for 31-day accounts.
3. **Exclude the 0-30 day bucket** — the 0-30d bucket has zero observations with activity data (all null). These accounts are too new to have been captured by the data pipeline.
4. **Apply `log(tenure_weeks)` weighting.** Even after tenure normalization, per-week rates from a 5-week observation window are inherently noisier than rates from a 200-week window — the longer-tenured account has had more opportunities for its rate to converge toward its true behavioral mean. A `log(tenure_weeks)` weight provides a smooth, diminishing-returns correction: it upweights longer-tenured accounts modestly (log is concave, so going from 5→50 weeks matters more than 500→5000) without discarding or heavily penalizing recent accounts. This weight is computed as a feature column (`tenure_weight = LN(tenure_days / 7.0)`) and applied as a sample weight during clustering (weighted K-Means, or as a prior in GMM), not as a row filter.

**References**:
- Fader, Hardie & Lee (2005), "Counting Your Customers" the Easy Way — canonical work on tenure-normalized behavioral analysis in customer analytics. *Marketing Science*.
- Aggarwal & Reddy (2014), *Data Clustering: Algorithms and Applications* — weighted clustering formulations (Ch. 7).

---

## 2. Longitudinal Conversion Feasibility

### Question
Can we convert the cross-sectional snapshot into longitudinal (time-series) data for trend-based clustering?

### Empirical Findings

**Available temporal anchors** (date columns with non-null coverage):

| Date Column | Coverage | Median Days-to-First |
|-------------|---------|---------------------|
| EARLIEST_LOGIN_DATE | 84.3% | 19 days |
| EARLIEST_TREE_EDIT_DATE | 53.0% | 8 days |
| EARLIEST_NAME_CONTRIBUTOR_DATE | 51.9% | 7 days |
| EARLIEST_SOURCE_CONTRIBUTOR_DATE | 8.4% | 5 days |
| EARLIEST_MEMORY_CONTRIBUTOR_DATE | 2.5% | 12 days |
| EARLIEST_GET_INVOLVED_USAGE_DATE | 0.6% | 43 days |
| EARLIEST_RECORD_EDIT_DATE | 0.6% | 14 days |

**Activity sequencing is highly consistent**:
- Login before tree edit: 98.7% of users
- Tree edit before source: 98.5% of users

### Assessment

**True longitudinal data is NOT available.** The dataset provides only:
- Account creation date
- *Earliest* date for each activity type (first occurrence only)
- Cumulative counts (no per-day or per-week breakdowns)

We have **milestone timestamps** (when did the user first do X?) but not **trajectory data** (how did behavior change over weeks/months?).

### What IS Possible: Pseudo-Longitudinal Features

We can derive a **behavioral onboarding funnel** from the milestone timestamps:

1. **Days-to-first-login** — activation latency
2. **Days-to-first-tree-edit** — first contribution latency
3. **Days-to-first-source** — deeper engagement latency
4. **Activity sequence order** — which activity came first?
5. **Activation velocity** — how quickly did they reach N activity types?
6. **Early vs late contributor** — binary: first contribution within 7 days of account creation?

These pseudo-longitudinal features capture the *tempo* of user onboarding without requiring true time-series data.

### Viable Modeling Approaches for Pseudo-Longitudinal Data

The milestone timestamps support several analytical methods beyond standard cross-sectional clustering. These are ordered from simplest (included by default) to most specialized (optional enrichments).

**1. Cross-sectional clustering with temporal features (default).** Treat derived latency/velocity features as additional columns in the standard clustering feature matrix alongside rate and count features. Days-to-first-X, activation velocity, and funnel depth enter K-Means/GMM/HDBSCAN directly. This is the baseline approach and requires no additional tooling.

**2. Funnel stage classification → within-stage clustering.** First classify each user into a discrete funnel stage based on which milestones they have reached:

| Stage | Criteria | Expected % |
|-------|----------|-----------|
| 0 — Registered only | No login date | ~16% |
| 1 — Logged in | Login but no contributions | ~30% |
| 2 — Browsed/light use | Tree edits but no sources | ~25% |
| 3 — Contributor | Sources or names added | ~20% |
| 4 — Deep contributor | 3+ activity types with contributions | ~9% |

Then cluster *within* each stage on behavioral intensity (rates, consistency, breadth). This avoids mixing "never logged in" users with "power editors" in the same feature space, which can dominate cluster formation. The stage variable itself can also serve as a post-hoc segment descriptor.

**3. Survival/hazard modeling (optional).** Treat each activity milestone as a time-to-event outcome and fit Cox proportional hazard or accelerated failure time (AFT) models. This answers: *what predicts whether and how quickly a user reaches their first tree edit (or source contribution, etc.)?* Users who never reached a milestone are right-censored — handled naturally by survival methods. Output — predicted hazard scores or survival quantiles per user — can become additional clustering inputs, enriching the feature space with "propensity to engage" scores that the raw latency features alone cannot capture (because they are undefined for censored users).

**4. Latent class analysis (optional).** A model-based approach that discovers discrete subgroups from a mixture of categorical (which milestones reached: Y/N) and continuous (days-to-milestone) indicators simultaneously. Conceptually similar to GMM but designed for mixed-type data. Well-suited to the milestone pattern where each user has a binary vector of "reached milestone Y/N" plus continuous latency values for those they did reach. Implementations: `poLCA` (R), `stepMix` (Python).

**5. Sequence analysis via Optimal Matching (optional).** Encode each user's milestone order as a short categorical sequence (e.g., `Login → TreeEdit → Source` vs `Login → Names → TreeEdit`). Optimal Matching (Abbott & Tsay 2000) computes pairwise dissimilarity between sequences based on edit distance (insertions, deletions, substitutions with domain-informed costs). Hierarchical clustering on the resulting distance matrix identifies groups with similar onboarding *paths* regardless of speed. This captures behavioral ordering patterns that latency features miss — two users may reach the same milestones at the same speed but in different orders, reflecting different motivations.

### Approaches That Require True Longitudinal Data (NOT viable)

The following methods require repeated measurements at regular intervals and **cannot** be applied to this dataset:

- **Dynamic Time Warping (DTW) / temporal k-means** — need time series of observations per user
- **Hidden Markov Models (HMM)** — need state transition sequences over time
- **Recurrent neural networks / LSTMs** — need sequential observation vectors
- **Change-point detection** — needs a time series within which to detect regime shifts

### Recommendation

1. **Derive onboarding funnel features** from the milestone dates (days-to-first-X for each activity type).
2. **Create an "activation speed" composite** — e.g., average days-to-first across all activities the user eventually performed.
3. **Classify users into funnel stages** (0-4) as both a feature and a potential stratification variable.
4. **Do NOT attempt true time-series methods** (DTW, HMM, LSTM, change-point) — the data resolution is insufficient.
5. **Optional enrichments** (Phase 5, exploratory): survival modeling for engagement propensity scores, latent class analysis for mixed-type milestone patterns, or sequence analysis for onboarding path typologies. These should be attempted only after the baseline clustering (approach #1) is validated and stable.
6. **For future work**: recommend FamilySearch capture weekly/monthly activity snapshots to enable true longitudinal analysis.

**References**:
- Buckinx & Van den Poel (2005), "Customer base analysis: partial defection of behaviourally loyal clients in a non-contractual FMCG setting." *European Journal of Operational Research*.
- Abbott & Tsay (2000), "Sequence Analysis and Optimal Matching Methods in Sociology." *Sociological Methods & Research*.
- Vermunt & Magidson (2002), "Latent Class Cluster Analysis." In *Applied Latent Class Analysis*, Cambridge University Press.

---

## 3. Age x Engagement Interaction

### Age Binning Design Rationale

The original 7-bin scheme (0-17, 18-25, 26-35, 36-45, 46-55, 56-65, 66+) reflected two conventions from public reporting: a legal-minor boundary at 18 and a privacy-motivated 66+ catch-all used in census and public health contexts to reduce re-identification risk for elderly populations. Neither convention is appropriate here:

1. **Internal use removes the privacy justification.** The 66+ convention (CDC, Eurostat) protects against re-identification in published demographic tables. For an internal segmentation analysis on 7.6M accounts, this protection is unnecessary and actively harmful — it collapses 44 years of age range into a single bin, obscuring behavioral variation in the 60s, 70s, and beyond.

2. **Decade bins are adopted as the default resolution**, yielding 8 bins (8-19 through 70-79, plus 80+). This provides sufficient granularity to detect engagement gradients across the age spectrum while maintaining interpretable, consistently sized bins in the population-dense middle range (20-69). The first bin spans 8-19 because the minimum account age is 8 and no users aged 1-7 exist (see point 4).

3. **The 80+ open-ended bin reflects a priori behavioral reasoning, not a statistical convenience.** Behavioral demographics are not uniformly distributed across fixed-width age brackets. Digital engagement rates are expected to plateau and decline beyond a certain age horizon due to biological and technological factors (health constraints, digital literacy barriers, reduced mobility). Prior empirical findings in this dataset confirm that engagement peaks in the 50s-60s and declines thereafter. Over-binning this already-underrepresented tail (80-89, 90-99, 100-110 individually) would:
   - **Artificially fragment a behaviorally homogeneous stratum.** If engagement is flat-to-declining above 80, subdividing by decade produces bins that differ primarily in sample size, not in behavior.
   - **Weaken statistical signal.** Each additional narrow bin in a sparse tail reduces per-bin sample size, inflating variance in bin-level estimates (means, rates, proportions). For a ~30K subsample, the 80-89 bin might yield ~600 users, 90-99 ~190, and 100-110 ~40 — the latter too few to support reliable cluster profiling or Kruskal-Wallis testing.
   - **Distort representation in downstream analysis.** Country-stratified subsampling already down-weights rare populations. Further splitting the elderly tail compounds the underrepresentation, making any behavioral signal from this group statistically weaker and more susceptible to noise.

4. **Age=0 is flagged as missing; the first bin is 8-19.** FamilySearch requires a minimum age of 8 to create an account. Empirical inspection confirms zero users aged 1-8 in the dataset. The 757 accounts with age=0 (0.3%) are system defaults or data entry errors — these are set to NULL in Phase 2 cleaning and excluded from age-based analysis. The youngest real users are age 9 (n=100), which merge naturally into an 8-19 bin. The within-bin age distribution shows a sharp enrollment ramp: 100 (age 9) → 186 (age 11) → 906 (age 13) → 4,372 (age 14) → 8,585 (age 15), consistent with LDS youth program participation starting around age 13-14.

**Final scheme: 8 bins** — `8-19, 20-29, 30-39, 40-49, 50-59, 60-69, 70-79, 80+` (age=0 excluded as missing)

### Empirical Findings

*Computed on 250K stratified sample. Age=0 (757 accounts, 0.3%) excluded as missing — see binning rationale point 4.*

| Age Group | n | % | Login Rate/wk | Tree Edit Rate/wk | Source Rate/wk | Activity Breadth |
|-----------|---|---|-------------|-------------------|---------------|-----------------|
| 8-19 | 49,120 | 19.7% | 0.184 | 1.154 | 0.070 | 1.32 |
| 20-29 | 71,170 | 28.6% | 0.154 | 1.013 | 0.161 | 1.03 |
| 30-39 | 45,001 | 18.1% | 0.199 | 1.214 | 0.237 | 1.07 |
| 40-49 | 32,763 | 13.1% | 0.245 | 1.546 | 0.447 | 1.12 |
| 50-59 | 22,813 | 9.2% | 0.262 | 1.650 | 0.552 | 1.09 |
| 60-69 | 16,601 | 6.7% | 0.269 | 1.375 | 0.271 | 1.02 |
| 70-79 | 8,552 | 3.4% | 0.271 | 1.279 | 0.390 | 0.94 |
| 80+ | 3,223 | 1.3% | 0.227 | 0.773 | 0.107 | 0.78 |

### Key Patterns

1. **Youth breadth anomaly (8-19)**: Highest activity breadth (1.32) despite below-average login frequency (0.184/wk) — consistent with burst activity during church-directed youth programs. Within-bin age distribution shows a sharp enrollment ramp at 13-14, confirming the LDS youth program signal. These users do more *types* of activity per visit but visit less frequently.
2. **Login rate gradient (20-79)**: Login rates increase monotonically from 0.154/wk (20-29) to 0.271/wk (70-79) — a 1.76x increase across 6 decades. This confirms that older users who remain active are *more* engaged per unit time, not less.
3. **Tree edit and source peaks at 50-59**: Tree edit rate peaks at 1.650/wk, source contributions at 0.552/wk — the "genealogist sweet spot" is sharper than previously estimated (old scheme showed 46-55). Users in their 50s contribute at nearly 2x the rate of 20-somethings.
4. **80+ decline confirms behavioral plateau**: All metrics decline for 80+ (login rate drops 16% from 70-79, tree edits drop 40%, activity breadth drops to 0.78). This validates the a priori reasoning for collapsing the tail — the 80+ group is behaviorally distinct from 60-79 but internally homogeneous enough that further subdivision would not reveal meaningful substructure.
5. **20-29 is the engagement trough**: Lowest login rate (0.154/wk), lowest activity breadth among working-age groups (1.03). This cohort likely represents casual sign-ups with low sustained interest — a key segment for targeted re-engagement.

### Recommendation

1. **Include age as a clustering feature** but also create **age x engagement interactions**:
   - `age_engagement_index = age_group_median * logins_per_week` (captures the age-engagement interaction)
   - `youth_burst_flag = 1 if age <= 19 and n_activity_types >= 2` (captures the youth program pattern)
2. **Consider age-stratified clustering** — run separate models for youth (8-19), working-age (20-59), and senior (60+) to avoid age dominating the segmentation.

---

## 4. Country Variable: Exploiting 215-Country Granularity

### Empirical Findings

- **215 unique countries**, 0% missing (87 "Unknown" values = 0.03%)
- **Top 5 countries = 57.9%** of all users (US, Brazil, Mexico, Philippines, Argentina)
- **122 countries have <100 users** — too sparse for per-country analysis
- **Bottom 100 countries = 0.6%** of data

**Engagement varies significantly by country** (mean logins):
- Mexico: 4.99 (highest among top 10)
- US: 4.04
- Brazil: 3.77
- Philippines: 2.37
- UK: 2.41

### Country Cluster Design

Rather than using the 7-value `USER_WORLD_REGION` (too coarse) or 215 raw countries (too sparse in the tail), we define a priori country clusters informed by three dimensions: **engagement level** (empirical), **LDS institutional presence** (external), and **development level** (external). These clusters serve as a categorical feature for profiling and as a stratification variable, not as clustering inputs (to avoid ecological fallacy — see Section 5, Finding 5.2 in the literature review).

**Note on LDS data availability**: The LDS institutional presence dimension (temple counts, membership per capita, stake density) depends on being able to access and aggregate data from Church Newsroom statistical reports and the ARDA World Religion dataset. These are publicly available but not in a single downloadable table — manual collection or web scraping may be required. If LDS data proves inaccessible or incomplete, the cluster assignments should be based on engagement level and development level alone, with LDS presence treated as a qualitative label rather than a quantitative input. See Section 5 (External Data Enrichment) for the full dataset inventory and access notes.

#### Proposed Country Clusters

*Engagement statistics computed on 250K sample, tenure-normalized.*

| Cluster | Countries | n | % | Login/wk | Tree Edit/wk | Breadth |
|---------|-----------|---|---|---------|-------------|---------|
| **High-eng, High-LDS** | US (UT/ID), Mexico, Brazil, Chile, Peru, Argentina, Philippines | ~150K | ~60% | 0.212 | 1.146 | 1.18 |
| **Mod/High-eng, Low-LDS** | US (Other), UK, Germany, France, Australia, Canada | ~90K | ~36% | — | — | — |
| **Low-eng, High-dev** | Netherlands, Japan, South Korea | ~2.8K | ~1.1% | 0.182 | 0.846 | 0.74 |
| **Low-eng, Developing** | Egypt, India, Nigeria | ~4.2K | ~1.7% | 0.205 | 1.441 | 0.99 |
| **Micro-countries** | All countries with <100 users (122 countries) | ~3.0K | ~1.2% | 0.232 | 1.218 | — |

*Note: Mod/High-eng Low-LDS stats will be recomputed after US split is applied. Current stats for the 5 non-US countries in this group: Login/wk 0.169, Tree Edit/wk 1.362, Breadth 0.96.*

#### US Split: LDS Heartland vs Rest of Country

The United States (26.2% of all users) is not behaviorally homogeneous. The LDS heartland (Utah, Idaho) has fundamentally different user composition and engagement patterns than the rest of the country, warranting a sub-country split.

**Available proxies for US sub-geography**:

| Variable | Coverage (US) | UT/ID identifiable? | Notes |
|----------|--------------|---------------------|-------|
| `PROVINCE` | 3.7% non-Unknown | Yes (863 UT, 207 ID) | But: 100% of known-province users are Members |
| `USER_AREA_NAME` | 100% | Yes ("Utah Area" = 876) | Also confounded: Utah Area = 100% Member |

**Critical confound**: PROVINCE availability is a near-perfect proxy for ACCOUNT_TYPE in the US subset. All 2,430 US users with known PROVINCE are Member accounts (100.0%); all 63,014 with Unknown PROVINCE are Public accounts (0.0% Member). The UT/ID engagement premium (~2x login rate, ~2x tree edits) may be partially or entirely explained by the Member status confound documented in Section 9, not by geography alone.

| US Subset | n | Login/wk | Tree Edit/wk | Breadth | % Member |
|-----------|---|---------|-------------|---------|----------|
| UT/ID (PROVINCE) | 1,070 | 0.415 | 2.630 | 2.18 | 100% |
| Other known state | 1,360 | 0.526 | 2.873 | 2.24 | 100% |
| Unknown province | 63,014 | 0.224 | 1.296 | 1.05 | 0% |
| **Utah Area** (USER_AREA_NAME) | 876 | 0.389 | 2.510 | 2.17 | 100% |
| Non-Utah Area | 64,568 | 0.231 | 1.334 | 1.08 | 2.4% |

**Recommended split approach**: Use `USER_AREA_NAME = 'Utah Area'` as the proxy (100% coverage, no missing data). Assign "Utah Area" users to the **High-eng, High-LDS** cluster alongside Mexico, Brazil, etc. Assign remaining US users to **Mod/High-eng, Low-LDS** alongside UK, Canada, etc. Document the Member confound — the split still captures a real population difference (LDS-heartland Members with mission-driven engagement), but downstream interpretation should note that geography and account type are not separable in this subset.

### Recommendation

1. **Drop `USER_WORLD_REGION`** as a feature (too coarse).
2. **Derive `country_engagement_cluster`** using the 5 a priori clusters above, with the US split via `USER_AREA_NAME`.
3. **Validate clusters empirically**: after assignment, run Kruskal-Wallis on engagement metrics across clusters to confirm behavioral separation. If any two clusters are not statistically distinguishable, merge them.
4. **Join external data** (see Section 5) to create richer country-level features for the non-micro clusters.
5. **Do NOT drop "Unknown" country** — 87 records is negligible (0.03%), but no reason to exclude valid behavioral data just because geography is missing. Assign to Micro-countries bin.
6. **Retain Province/City with NULL conversion** — convert "Unknown", "Redacted", and "-" values to NULL (97%+ of rows). These columns are **exclusively populated for Member accounts** (100% of non-null Province/City rows are Members; 0% of Public accounts have geographic data). They are unsuitable as general clustering features — including them would leak the Member/Public distinction into the feature space, producing segments that merely rediscover account type. However, they are retained for optional Member-only geographic comparisons (e.g., engagement differences between Utah Valley and Latin American LDS cities).

---

## 5. External Data Enrichment

### Recommended Datasets

| Dataset | Source | Key Variables | Join Key | Update Freq | URL |
|---------|--------|--------------|----------|-------------|-----|
| World Bank WDI | World Bank Open Data | GDP/capita (PPP), internet users %, mobile subscriptions, education enrollment | ISO3 country code | Annual | data.worldbank.org |
| UN HDI | UNDP | Human Development Index, life expectancy, education index, GNI/capita | ISO3 | Annual | hdr.undp.org |
| ITU Digital Development | ITU | ICT Development Index, broadband penetration, digital skills | ISO3 | Annual | itu.int/en/ITU-D/Statistics |
| Pew Religiosity | Pew Research | % religious, % pray daily, importance of religion, religious diversity | Country name | Irregular (2015, 2018) | pewresearch.org/religion |
| LDS Church Statistics | Church Newsroom | Temples (operating + announced), membership, missions, stakes | Country name | Annual | newsroom.churchofjesuschrist.org |
| Genealogy Interest Index | Google Trends | Search volume for "genealogy", "family tree", "ancestry" by country | Country name | Monthly | trends.google.com |

### Data Availability Validation (2026-03-25)

Each source was validated for programmatic access, format, join key readiness, and estimated acquisition effort.

| Source | Verdict | Acquisition Method | Format | ISO3 Native? | Registration | Est. Time |
|--------|---------|-------------------|--------|-------------|-------------|-----------|
| **World Bank WDI** | **EASY** | `wbgapi` Python library (v1.0.14). Single call: `wb.data.DataFrame(['NY.GDP.PCAP.PP.CD', 'IT.NET.USER.ZS', 'IT.CEL.SETS.P2', 'SE.TER.ENRR'], mrv=5)` returns all indicators as a DataFrame. No API key required. | DataFrame | Yes | None | <5 min |
| **UN HDI** | **EASY** | Direct CSV download — `pd.read_csv('https://hdr.undp.org/sites/default/files/2025_HDR/HDR25_Composite_indices_complete_time_series.csv')`. No login required. Contains HDI, education index, GNI/capita, life expectancy (1990-2023, 193 countries). | CSV | Yes (`iso3` col) | None | <2 min |
| **ITU IDI** | **MODERATE** | Direct Excel download: `https://www.itu.int/en/ITU-D/Statistics/Documents/IDI/IDIDataset.xlsx`. Need to inspect sheet structure and filter out regional aggregates. Data year is 2022 (2-year lag). ~185 economies. | .xlsx | Yes (verify) | None | ~20 min |
| **Pew Religiosity** | **MODERATE** | Free account required at pewresearch.org. Download Spring 2024 Global Attitudes SPSS file (.sav), read with `pandas.read_spss()` or `pyreadstat`. Must aggregate microdata by country. **Critical coverage gap**: behavioral religiosity (prayer, importance) covers only **36 countries**; religious composition (% Christian/Muslim) available for **201 countries** via separate dataset. ~150 countries will be null on behavioral metrics. | SPSS (.sav) | No (crosswalk) | Free account | ~45 min |
| **LDS Church Stats** | **MODERATE** | No official bulk download exists — only individual country web pages. **GitHub workaround**: community CSV at `https://github.com/LatterDataSaint/All-LDS-Facts-and-Statistics-Pages` covers ~170 countries (2012-2025) with membership, congregations, stakes, missions, temples, FamilySearch centers. Requires country name → ISO3 crosswalk via `pycountry`. | CSV (GitHub) | No (name crosswalk) | None | ~30 min |
| **Google Trends** | **HARD** | `pytrends` Python library was **archived April 2025** (persistent 429 errors). Official Google Trends API launched July 2025 but remains in **closed alpha** (waitlist only). Pragmatic path: manual export from trends.google.com UI — set each of 3 keywords ("genealogy", "family tree", "ancestry") to Worldwide / Past 5 years / "Interest by subregion" tab → download CSV. Uses ISO 3166-1 alpha-2 codes (need ISO2→3 crosswalk). Alternative: paid SerpApi subscription (~$50-250/mo). | CSV (manual) | No (ISO2→3) | None (manual) | ~45 min |

**Recommended acquisition order**: World Bank → UN HDI → ITU → LDS (GitHub) → Pew → Google Trends. The first three are friction-free and provide the core development/digital variables. LDS and Pew add the religiosity dimension with moderate effort. Google Trends is lowest priority — a "nice to have" genealogy interest proxy that can be deferred if manual export is impractical.

**ISO3 crosswalk strategy**: World Bank and UN HDI use ISO3 natively. ITU likely does (verify after download). For Pew, LDS, and Google Trends, use `pycountry` (Python library) to map country names → ISO3 and ISO2 → ISO3 respectively. Build the crosswalk once as a reusable lookup table (`country_name_map` in the DuckDB schema, Phase 1 step 1c).

### Proposed Enrichment Schema

```sql
CREATE TABLE country_enrichment (
    iso3_code       CHAR(3) PRIMARY KEY,
    country_name    TEXT NOT NULL,
    -- World Bank / UN indicators
    gdp_per_capita_ppp  FLOAT,     -- World Bank, most recent year
    internet_pct        FLOAT,     -- % population using internet
    mobile_per_100      FLOAT,     -- Mobile subscriptions per 100 people
    hdi_score           FLOAT,     -- UN Human Development Index (0-1)
    education_index     FLOAT,     -- UN education sub-index (0-1)
    -- Religiosity
    pct_religious       FLOAT,     -- Pew: % saying religion is important
    pct_christian       FLOAT,     -- Pew: % Christian
    religious_diversity FLOAT,     -- Pew: Religious Diversity Index (0-10)
    -- LDS-specific
    lds_temples         INT,       -- Operating + under construction
    lds_membership      INT,       -- Reported membership
    lds_stakes          INT,       -- Number of stakes (organizational units)
    lds_members_per_capita FLOAT,  -- Membership / population
    -- Digital / genealogy
    genealogy_search_index FLOAT,  -- Google Trends relative search volume
    -- Derived composites
    digital_readiness_score FLOAT, -- Composite: internet_pct * hdi_score * education_index
    lds_intensity_score     FLOAT, -- Composite: lds_members_per_capita * lds_temples_per_million
    -- Metadata
    data_year       INT,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Country name mapping (FamilySearch names may differ from ISO standard)
CREATE TABLE country_name_map (
    fs_country_name TEXT PRIMARY KEY,  -- As it appears in FamilySearch data
    iso3_code       CHAR(3) REFERENCES country_enrichment(iso3_code)
);
```

### ETL Pipeline (Proposed)

```
┌────────────────┐     ┌──────────────────┐     ┌───────────────────┐
│ World Bank API │────▶│                  │────▶│                   │
│ UN HDI CSV     │     │  Python ETL      │     │ country_enrichment│
│ Pew Tables     │────▶│  (pandas + API)  │────▶│ (PostgreSQL)      │
│ LDS Newsroom   │     │                  │     │                   │
│ Google Trends  │────▶│  Normalize,      │     │ + country_name_map│
└────────────────┘     │  validate,       │     └────────┬──────────┘
                       │  composite scores│              │
                       └──────────────────┘              │ JOIN on country
                                                         ▼
                                              ┌───────────────────┐
                                              │ enriched_users    │
                                              │ (original 33 cols │
                                              │  + 12 country-    │
                                              │  level features)  │
                                              └───────────────────┘
```

---

## 6. Missingness Strategy

### Empirical Findings

**Three distinct missingness mechanisms identified:**

| Pattern | Columns | Rate | Mechanism | Evidence |
|---------|---------|------|-----------|----------|
| **Activity null block** | DAYS_LOGGING_IN through DAYS_EDITING_TREES (11 cols) | 10.2% | **MNAR (systematic)** | Block missingness (all-or-nothing); 99.9% Public accounts; only 1.3% have login dates; tenure similar to non-null. These are accounts the data pipeline never captured. |
| **Name columns** | DAYS_ADDING_NAMES through QUALIFIED_NAMES (6 cols) | 48.5% | **MAR (conditional)** | 100% agreement: null name cols = never added a name. This is meaningful zero, not missing data. |
| **Date columns** | EARLIEST_*_DATE (7 cols) | 0.6%-97.6% | **MAR (conditional)** | Null date = user never performed that activity. Coverage reflects activity rarity (Get Involved: 0.6% participation). |

### Recommendations

**Activity null block (10.2%):**
- **Option A (Recommended): Exclude** — These 25,500 users (in 250K sample) have no behavioral data. Including them as zeros would create a massive "phantom inactive" segment that doesn't represent genuine inactivity — it represents *untracked* users. Excluding them is the honest choice.
- **Option B: Flag and include** — Keep them but add a `DATA_PIPELINE_TRACKED = 0/1` flag. Use this flag as a clustering feature. Risk: they'll dominate the largest cluster, swamping real behavioral patterns.
- **Do NOT impute** — There's no basis for imputing activity values for users the pipeline never tracked.

**Name columns (48.5%):**
- **Impute as zero** — Null means "never added a name." Fill with 0 for counts, NaT for dates. This is semantically correct and preserves the full sample.

**Date columns (0.6%-97.6%):**
- **Derive days-to-first features** — Convert to numeric (days from account creation to first activity). Null = user never performed that activity = set to a large sentinel value (e.g., 9999) or leave as NaN and use only the binary "ever did it" flag in clustering.

**Province/City (97%+ Unknown):**
- **Convert to NULL** — "Unknown", "Redacted", and "-" values set to NULL. Columns retained for optional Member-only geographic analysis. **Critical finding**: Province/City data exists exclusively for Member accounts (100% of non-null rows). Must be excluded from clustering feature selection to avoid leaking account type into the model.

### Geographic Column Complementarity Analysis

The 5 geographic columns (COUNTRY, PROVINCE, CITY, USER_WORLD_REGION, USER_AREA_NAME) were analyzed for cross-column correlation and mutual information to assess whether a composite `geo_location` feature could recover sub-country granularity from partial data.

**Co-occurrence patterns** (250K sample):

| Pattern (Country/Province/City/Region/Area) | % of Users | Description |
|---------------------------------------------|-----------|-------------|
| Country + Region + Area only | **97.0%** | No Province, no City — coarse geo only |
| All 5 columns populated | **2.7%** | Full geo detail — but 100% Members |
| Partial (other combinations) | 0.3% | Edge cases (some City without Province, etc.) |

The columns form **two isolated tiers**, not a complementary hierarchy:

- **Tier 1 (universal, coarse)**: COUNTRY (100%), USER_WORLD_REGION (100%), USER_AREA_NAME (100%). Available for all users. COUNTRY is the finest resolution — WORLD_REGION and AREA_NAME are strictly coarser aggregations.
- **Tier 2 (Member-exclusive, fine-grained)**: PROVINCE (2.7%), CITY (2.9%). Available only for Member accounts. Where Province exists, City almost always exists too (99.3% overlap). These columns do not fill gaps in each other for the general population — they are jointly present or jointly absent.

**USER_AREA_NAME adds sub-country granularity only for the US.** For all other countries, AREA_NAME maps 1:1 to COUNTRY (e.g., "Philippines Area" = Philippines) or groups multiple countries into a single regional label (e.g., "Europe Central Area" = 34 countries including Italy, France, Germany). Only the US has 7 distinct AREA_NAME values:

| US AREA_NAME | n users | % of US |
|-------------|---------|---------|
| United States (general) | 63,022 | 96.3% |
| Utah Area | 876 | 1.3% |
| Central | 390 | 0.6% |
| Southwest | 390 | 0.6% |
| West | 370 | 0.6% |
| Northeast | 201 | 0.3% |
| Southeast | 195 | 0.3% |

**Composite `geo_location` feature assessment**: A "best available granularity" collapse was prototyped (City > Province > US sub-region > Country > Region). Result: it produces COUNTRY for 97% of users and city-level for 3% — functionally identical to using COUNTRY directly. The engineering effort does not justify the marginal gain. **Recommendation: do not engineer a composite `geo_location` feature.**

**What IS useful**: The `country_cluster` feature (Section 4) provides the right abstraction, reducing 215 countries to 5 behaviorally meaningful bins. For the US specifically, the `USER_AREA_NAME` split (Utah Area vs rest) is already incorporated into the country cluster design. Province/City remain available for targeted Member-only geographic comparisons but should not enter the general clustering feature space.

### Statistical Basis

The MNAR classification for the activity null block is supported by the demographic analysis: null-block users are disproportionately European (37.8% vs 20.6% baseline) and almost zero Members (0.1% vs 3.3%). This non-random pattern means imputation methods that assume MCAR/MAR (e.g., mean imputation, MICE) would produce biased results.

**Reference**: Rubin (1976), "Inference and Missing Data." *Biometrika*. The foundational taxonomy of MCAR/MAR/MNAR and its implications for valid inference.
**Reference**: van Buuren (2018), *Flexible Imputation of Missing Data*. Chapman & Hall. The modern standard for missingness strategy in applied statistics.

---

## 7. Additional Methodological Concerns

### 7.1 Extreme Right Skew and Outliers

**All activity metrics are massively right-skewed.** The top 1% of users contribute 30-60% of total activity volume. Standard k-means with Euclidean distance will be distorted by these outliers.

**Recommendation:**
- Apply `log1p()` transform to all count features before scaling
- Use `RobustScaler` (IQR-based) instead of `StandardScaler` (mean/std-based)
- Consider running clustering on both log-transformed and rank-transformed features and comparing stability

### 7.2 Multicollinearity

TREE_EDITS, SOURCES_ADDED, and TOTAL_NAMES_ADDED are highly correlated (r > 0.5). Including all three in clustering inflates the weight of "tree building" relative to other activity modes.

**Recommendation:**
- Use PCA to reduce the tree-building cluster (TREE_EDITS, SOURCES, NAMES) to 1-2 components
- OR select one representative per correlated group (e.g., TREE_EDITS for tree building, GET_INVOLVED for indexing)
- OR use UMAP/t-SNE for visualization but cluster in the original (high-dimensional) space

### 7.3 Dominant Inactive Segment

#### Relationship to MNAR Block (Section 6)

The MNAR null block (10.2%) and the "inactive segment" problem are **distinct issues** that must not be conflated:

- **MNAR block**: A data pipeline artifact — all 11 activity columns are NULL. No behavioral signal exists. These users are excluded entirely in Phase 4 subsampling (Section 6, Option A). This is a **data quality** decision.
- **Inactive segment**: A behavioral phenomenon — users the pipeline DID track but who show low or no engagement. This is a **segmentation design** question about how to prevent low-activity users from swamping the clustering.

After excluding the MNAR block, 89.8% of users remain (224,533 in the 250K sample). The question becomes: how should these tracked users be segmented before clustering?

#### The Login Count Threshold Is Misleading

The initial proposal was to split at "0-1 logins" vs "2+ logins." Empirical analysis reveals this threshold is **behaviorally invalid**:

**0-login users are NOT inactive.** Of 14,464 tracked users with DAYS_LOGGING_IN = 0:
- **87.4% made tree edits** (median 12 edits, max 19,402)
- **95.3% added names** (median 4.7 names)
- **97.8% have a tree edit date** — confirming actual platform activity
- Only 1.7% have a login date, suggesting these are **non-login contributors**: users who interact with FamilySearch through batch uploads, API integrations, or other channels not captured by the DAYS_LOGGING_IN metric. Classifying them as "inactive" would be a major analytical error.

**1-login users are split roughly 50/50.** Of 130,769 users with exactly 1 login:
- **47.6% (62,292) made at least one contribution** (tree edit, name, or source)
- **52.4% (68,477) browsed only** — logged in once, did nothing, never returned

#### Revised Activity Segmentation

Based on empirical activity profiles, the login-based binary split should be replaced with an **activity-based segmentation** that separates users by what they *did*, not just whether they logged in:

| Segment | n | % | Key Characteristics |
|---------|---|---|---------------------|
| **A: MNAR (untracked)** | 25,467 | 10.2% | Excluded in Phase 4. Pipeline artifact, not a behavioral group. |
| **B: Registered, no activity** | 81 | 0.0% | Tracked but zero on all metrics. Negligible — merge into segment D or exclude. |
| **C: Non-login contributor** | 14,383 | 5.8% | 0 logins but 87% have tree edits (median 12). Likely API/batch users. Behaviorally active — should NOT be classified as inactive. |
| **D: Single browse** | 68,477 | 27.4% | 1 login, no contributions. The true "looked and left" population. |
| **E: Single-session contributor** | 62,292 | 24.9% | 1 login + made contributions. Meaningful engagement in a single visit. |
| **F: Light user (2-5 logins)** | 54,891 | 22.0% | Multi-session, moderate engagement. |
| **G: Regular user (6-50 logins)** | 21,190 | 8.5% | Sustained engagement over time. |
| **H: Power user (51+ logins)** | 3,219 | 1.3% | Heavy, sustained contributors. |

**Demographic signatures differ across segments:**

| Segment | % Member | Mean Age | % Latin America | % North America |
|---------|---------|---------|----------------|----------------|
| C: Non-login contributor | 4.8% | 32.7 | 45.9% | 12.8% |
| D: Single browse | 0.2% | 35.1 | 34.2% | 30.2% |
| E: Single-session contributor | 2.8% | 30.4 | 46.6% | 21.4% |
| F: Light user | 4.4% | 37.7 | 37.4% | 36.4% |
| G: Regular user | 9.2% | 40.5 | 38.7% | 36.6% |
| H: Power user | 15.0% | 39.9 | 48.4% | 26.1% |

Key demographic patterns:
- **Member %** increases monotonically with engagement (0.2% → 15.0%)
- **Age** is youngest among single-session contributors (30.4) and oldest among regular users (40.5) — the youth program burst pattern from Section 3
- **Latin America** dominates non-login contributors (45.9%) and power users (48.4%) — a bimodal pattern suggesting distinct Latin American engagement modes
- **North America** increases with sustained engagement (12.8% → 36.6%) — consistent with the LDS heartland effect

#### Recommendation

1. **Exclude MNAR block** (Segment A) — data quality issue, not a behavioral segment (Section 6).
2. **Do NOT use a simple login threshold** to define "inactive." Instead, use **contribution-based activity classification**:
   - **Pre-clustering separation**: Remove segments C (non-login contributors) and D (single browse) from the main clustering input. Segment C should be analyzed separately — their non-login activity pattern suggests a fundamentally different user journey. Segment D has no behavioral features to cluster on.
   - **Cluster segments E through H** as the main analytical population (~58% of tracked users). These users have both login data AND contribution data, providing a rich feature space for segmentation.
3. **Report the full funnel**: "Of 7.6M users, 10.2% were excluded as untracked (MNAR), 5.8% are non-login contributors (analyzed separately), 27.4% are single-browse visitors (Segment 0); among the remaining 57% with login + contribution data, we find K behavioral segments."
4. **Optional**: Further segment the power users (H) and regular users (G) if silhouette analysis suggests sub-clusters exist. The 9.8% combined population may contain 2-3 distinct engagement profiles (e.g., genealogist deep-divers vs broad-but-shallow contributors).

**References**:
- Punj & Stewart (1983), "Cluster Analysis in Marketing Research: Review and Suggestions for Application." *Journal of Marketing Research*.
- Wedel & Kamakura (2000), *Market Segmentation: Conceptual and Methodological Foundations*. Springer — foundational text on pre-segmentation activity filtering before model-based clustering.

### 7.4 Cluster Stability and Validation

K-means results depend on random initialization. A single run may not represent the true structure.

**Recommendation:**
- Run each k with 10+ random initializations (MiniBatchKMeans `n_init=10`)
- Use **bootstrap stability analysis**: subsample 80% of data, re-cluster, measure Adjusted Rand Index between runs. Stable clusters should have ARI > 0.8.
- Compare K-Means vs GMM vs HDBSCAN — if segments are consistent across algorithms, they represent genuine structure rather than algorithmic artifacts.
- Use **gap statistic** in addition to silhouette and elbow for k selection.

**Reference**: Tibshirani, Walther & Hastie (2001), "Estimating the number of clusters in a data set via the gap statistic." *Journal of the Royal Statistical Society: Series B*.

### 7.5 The Member vs Public Confound

Members (3%) show 3x login rates and 37x Get Involved participation. This is such a strong signal that it may dominate clustering — creating a "Member cluster" and a "Public cluster" rather than behavioral segments.

**Recommendation:**
- **Include ACCOUNT_TYPE as a post-hoc descriptor** (for profiling), not as a clustering feature
- OR cluster Members and Public separately if the goal is behavioral segmentation within each group
- At minimum, report: "Segment X is 45% Member accounts vs 3% population average — this segment's behavior is driven by membership status, not purely by behavioral choice"

---

## 8. Recommended Pre-Clustering Pipeline

Based on all findings above:

```
Step 1: EXCLUDE
  - Remove 10.2% null-activity-block records (MNAR, pipeline artifact)
  - Remove 0-30 day tenure accounts (insufficient observation window)
  - Convert Province/City "Unknown"/"Redacted"/"-" to NULL (retain columns; exclude from clustering features)

Step 2: IMPUTE
  - Name columns: fill null with 0 (semantically correct)
  - Date columns: derive days-to-first, fill null with sentinel or binary flag

Step 3: ENGINEER
  - Tenure-normalize all activity counts (rates per week)
  - Log1p-transform skewed counts
  - Derive onboarding funnel features (days-to-first-X)
  - Create activity breadth (count of activity types used)
  - Create age x engagement interaction features
  - Join country-level enrichment (if available)
  - Derive behavioral country clusters (aggregate means, then k-means countries)

Step 4: SCALE
  - RobustScaler (IQR-based, outlier-resistant)

Step 5: REDUCE (optional)
  - PCA on correlated tree-building features to reduce multicollinearity

Step 6: CLUSTER (activity-based pre-segmentation + clustering)
  - Pre-filter: Exclude MNAR block (10.2%, Section 6) and single-browse visitors (27.4%, Segment D)
  - Separate: Non-login contributors (5.8%, Segment C) analyzed independently
  - Cluster: Segments E-H (single-session contributors through power users, ~58% of tracked)
  - K-Means on active users, k=4-7, evaluated by silhouette + gap statistic
  - Compare with GMM (handles non-spherical clusters) and HDBSCAN (arbitrary shapes)

Step 7: VALIDATE
  - Bootstrap stability (ARI > 0.8)
  - Kruskal-Wallis significance across all features
  - Cross-algorithm consistency
  - Profile segments with demographics (post-hoc, not as clustering input)
```

---

## 9. Detailed Column Profiles (All 33 Columns)

### Identity & Temporal Anchors

#### USER_ID (int64)
- **Role**: Unique identifier. No analytical value.
- **Quality**: 100% complete, 250K unique values (no duplicates).
- **Action**: Retain as index key. Exclude from clustering features.

#### ACCOUNT_CREATE_DATE (datetime)
- **Role**: Temporal anchor — all tenure calculations derive from this.
- **Quality**: 100% complete. Range: 2025-01-01 to 2025-12-30 (full year).
- **Distribution**: Approximately uniform across the year (accounts created continuously).
- **Action**: Use to compute `tenure_days`. Not a clustering feature itself, but the basis for all tenure-normalized rates.

### Demographics (5 columns)

#### ACCOUNT_TYPE (categorical, 2 values)
- **Distribution**: Public 97.0%, Member 3.0%.
- **Analytical significance**: Members show 3x login rates, 37x Get Involved participation. This is the single strongest demographic predictor of engagement.
- **Clustering decision**: **Exclude from clustering features** — use as post-hoc segment descriptor. If included, it will dominate and produce "Member vs Public" clusters rather than behavioral segments.
- **Derived features**: None needed (binary already).

#### USER_CURRENT_AGE (int64)
- **Distribution**: Mean 35.0, median 30, std 17.4. Right-skewed (skew 0.96). Range 0-110 (capped from original -1 to 150+).
- **Quality issues**: 757 ages = 0 (0.3%) — system defaults or data entry errors. FamilySearch minimum account age is 8; zero users aged 1-8 exist. Age=0 is set to NULL in Phase 2 cleaning.
- **Analytical significance**: Monotonic engagement gradient (20-79). Youth cohort (8-19, ~20%) shows distinct burst-activity pattern with sharp enrollment ramp at age 13-14 (LDS youth programs).
- **Derived features**: `AGE_GROUP` (8 bins: 8-19, 20-29, 30-39, 40-49, 50-59, 60-69, 70-79, 80+). The 80+ collapse reflects a priori expectation of behavioral plateau beyond that horizon. Full binning rationale in Section 3. Consider `age_engagement_interaction`.
- **Action**: Include raw age in clustering (already numeric). Add age group for stratification and profiling.

#### COUNTRY (categorical, 215 values)
- **Distribution**: Extreme long tail. Top 5 = 57.9% (US 26.2%, Brazil 20.7%, Mexico 4.7%, Philippines 3.2%, Argentina 3.1%). 122 countries have <100 users. 49 countries have <10 users. Bottom 107 countries cover 0.72%.
- **Quality**: 0% null. 87 "Unknown" values (0.03%).
- **Analytical significance**: Engagement varies significantly by country (Mexico 4.99 avg logins vs Philippines 2.37). Geography is a proxy for LDS presence, economic development, and digital infrastructure.
- **Derived features**: `country_engagement_cluster` (data-driven behavioral bins), external enrichment (GDP, HDI, LDS temples). See Section 4.
- **Action**: **Do NOT one-hot encode** (215 dummies would be catastrophic for clustering). Use data-driven country clusters or external enrichment composites. Province/City retained with NULL conversion but excluded from clustering (see Province/City profiles below).

#### PROVINCE (categorical, 614 values)
- **Distribution**: 97.3% "Unknown". Utah (0.3%), Idaho (0.1%) are the only meaningful US entries — clearly LDS heartland. International provinces include Lima, São Paulo, Veracruz. 465 values have <10 occurrences.
- **Critical finding**: Non-null Province data exists **exclusively for Member accounts** (100% of 6,768 non-Unknown rows are Members). Province availability is a perfect proxy for account type in this dataset.
- **Action**: Convert "Unknown" to NULL. **Exclude from clustering features** (would leak Member/Public distinction). Retain for optional Member-only geographic comparisons.

#### CITY (categorical, 3,179 values)
- **Distribution**: 96.8% "Unknown", 0.3% "Redacted", plus "-" junk values. 3,082 values have <10 occurrences. Top non-Unknown/Redacted cities: Kinshasa (51), Lehi (46), Fortaleza (39), Mexico City (35), Las Vegas (34). Utah Valley cities (Lehi, Orem, Provo, West Jordan, Spanish Fork) dominate US entries.
- **Critical finding**: Same as Province — non-null City data is **100% Member accounts**. City values encode "where LDS Members live," not general geographic coverage.
- **Action**: Convert "Unknown", "Redacted", "-" to NULL. **Exclude from clustering features**. Retain for optional Member-only geographic comparisons.

#### USER_WORLD_REGION (categorical, 7 values)
- **Distribution**: Latin America 38.7%, North America 27.9%, Europe 22.3%, Asia Pacific 7.1%, Middle East 2.4%, Africa 1.7%, Unknown 0.03%.
- **Analytical significance**: Coarse geographic grouping. Africa shows highest per-user tree edits (41 avg) despite smallest group size. Useful for stratification but too crude for clustering.
- **Action**: Use for stratified sampling and post-hoc profiling. Replace with data-driven country clusters for clustering input.

#### USER_AREA_NAME (categorical, 26 values)
- **Distribution**: LDS organizational areas (not geographic regions). "United States" 25.2%, "Brazil Area" 20.7%, "Europe Central Area" 15.2%.
- **Analytical significance**: This is an **LDS administrative geography** — reveals FamilySearch's organizational structure. More granular than WORLD_REGION (26 vs 7 values) and directly maps to LDS operational units.
- **Derived features**: Could create `area_engagement_mean` (mean engagement per area, then join back to individual users).
- **Action**: Consider as a stratification variable. Potentially more useful than WORLD_REGION for capturing LDS-specific geographic effects.

### Date Milestones (7 columns)

All date milestone columns share the same structure: the earliest date a user performed a specific activity type. Coverage ranges from 84.3% (login) to 0.6% (Get Involved, Record Edit).

**Critical quality finding**: Many dates are BEFORE account creation (93-98% of valid dates). This appears to be a systematic timezone or data pipeline artifact, not an error. The FamilySearch backend likely records UTC timestamps while account creation uses local time, or the "earliest" date reflects activity on linked accounts.

| Column | Coverage | Median Days-to-First | Negative Dates | Primary Derived Feature |
|--------|---------|---------------------|---------------|----------------------|
| EARLIEST_LOGIN_DATE | 84.3% | -1 (same day) | 98.3% | `DAYS_TO_FIRST_LOGIN` |
| EARLIEST_TREE_EDIT_DATE | 53.0% | -1 | 93.0% | `DAYS_TO_FIRST_TREE_EDIT` |
| EARLIEST_NAME_CONTRIBUTOR_DATE | 51.9% | -1 | 93.1% | `DAYS_TO_FIRST_NAME` |
| EARLIEST_SOURCE_CONTRIBUTOR_DATE | 8.4% | -1 | 62.2% | `DAYS_TO_FIRST_SOURCE` |
| EARLIEST_MEMORY_CONTRIBUTOR_DATE | 2.5% | 0 | 46.9% | `DAYS_TO_FIRST_MEMORY` |
| EARLIEST_GET_INVOLVED_USAGE_DATE | 0.6% | 0 | 49.5% | `DAYS_TO_FIRST_GET_INVOLVED` |
| EARLIEST_RECORD_EDIT_DATE | 0.6% | 0 | 47.0% | `DAYS_TO_FIRST_RECORD_EDIT` |

**Action**: Derive `days_to_first_X = max(0, (earliest_X_date - account_create_date).days)`. Clip negative to 0. Use as activation latency features. For columns with <5% coverage, use binary flag (ever_did_X) rather than latency.

### Activity Counts (11 columns)

All 11 activity count columns share the 10.2% MNAR null block (same rows missing for all). Among non-null records:

| Column | Zeros | Mean | Median | P99 | Max | Skew | Kurtosis | IQR Outlier % |
|--------|-------|------|--------|-----|-----|------|----------|--------------|
| DAYS_LOGGING_IN | 6.4% | 4.02 | 1 | 66 | 351 | 8.4 | 94 | 15.9% |
| TREE_EDITS | 47.1% | 18.4 | 2 | 168 | 41,792 | 99 | 12,166 | 6.4% |
| SOURCES_ADDED | 91.0% | 5.2 | 0 | 40 | 40,423 | 113 | 15,855 | 9.0% |
| DAYS_ADDING_SOURCES | 91.0% | 0.18 | 0 | 3 | 216 | 55 | 4,438 | 9.0% |
| MEMORIES_ADDED | 97.4% | 0.20 | 0 | 4 | 1,623 | 179 | 51,442 | 2.6% |
| DAYS_ADDING_MEMORIES | 97.4% | 0.05 | 0 | 1 | 115 | 81 | 11,684 | 2.6% |
| GET_INVOLVED_ITEMS | 99.4% | 4.1 | 0 | 0 | 111,370 | 222 | 57,737 | 0.6% |
| DAYS_GET_INVOLVED | 99.4% | 0.01 | 0 | 0 | 124 | 140 | 28,725 | 0.6% |
| RECORD_EDITS | 99.4% | 0.06 | 0 | 0 | 5,954 | 446 | 205,815 | 0.6% |
| DAYS_EDITING_RECORDS | 99.4% | 0.01 | 0 | 0 | 202 | 301 | 115,349 | 0.6% |
| DAYS_EDITING_TREES | 47.1% | 0.82 | 1 | 6 | 228 | 34 | 1,901 | 4.5% |

**Key observations**:
1. **Extreme right skew across all columns** (skewness 8 to 446). `log1p()` mandatory.
2. **Sparse activities**: Sources (91% zero), Memories (97.4% zero), Get Involved (99.4% zero), Record Edits (99.4% zero). These columns have almost no discriminative power in their raw form — binary flags (did/didn't) are more informative than counts.
3. **Count-days pairs are redundant**: SOURCES_ADDED and DAYS_ADDING_SOURCES have r=0.70; RECORD_EDITS and DAYS_EDITING_RECORDS have r=0.90. Use ONE from each pair (prefer the count, it has more variance).
4. **Max values are extreme**: GET_INVOLVED max=111,370 items (likely automated or institutional accounts). TREE_EDITS max=41,792. These outliers will distort any mean-based analysis.

**Action**:
- Null block (10.2%): EXCLUDE (MNAR, pipeline artifact)
- Zeros: retain (genuine inactivity)
- Transform: `log1p()` for counts, `binary flag` for sparse activities
- Select one from each count-days pair: TREE_EDITS (not DAYS_EDITING_TREES), SOURCES_ADDED (not DAYS_ADDING_SOURCES), etc.
- Tenure-normalize: `X_PER_WEEK = X / tenure_weeks`

### Name Columns (6 columns)

Name columns are **conditional** — only populated when `TOTAL_NAMES_ADDED >= 1` (48.5% null = 100% agreement with "never added a name").

| Column | Coverage | Mean (among contributors) | Median | P99 | Max | Skew |
|--------|---------|--------------------------|--------|-----|-----|------|
| DAYS_ADDING_NAMES | 51.5% | 1.34 | 1 | 5 | 155 | 34.5 |
| TOTAL_NAMES_ADDED | 51.5% | 8.21 | 5 | 59 | 7,135 | 75.8 |
| DECEASED_NAMES_ADDED | 51.5% | 3.41 | 1 | 29 | 7,128 | 104.1 |
| LIVING_NAMES_ADDED | 51.5% | 4.52 | 3 | 32 | 1,985 | 62.8 |
| NOVEL_NAMES_ADDED | 51.5% | 2.96 | 1 | 25 | 7,063 | 123.1 |
| QUALIFIED_NAMES_ADDED | 51.5% | 0.46 | 0 | 5 | 3,265 | 158.2 |

**Critical multicollinearity**: DECEASED_NAMES ↔ NOVEL_NAMES: r=0.983 (!). TOTAL_NAMES ↔ DECEASED: r=0.939. TOTAL_NAMES ↔ NOVEL: r=0.922. These are near-perfect correlations — the name subtypes are essentially counting the same things.

**Derived features**:
- `PCT_DECEASED_NAMES = DECEASED / TOTAL` — genealogy depth indicator (higher = researching deceased ancestors vs documenting living family)
- `PCT_NOVEL_NAMES = NOVEL / TOTAL` — discovery rate (adding new individuals vs editing existing)
- `HAS_NAMES` (binary) — contributed any names

**Action**:
- Fill nulls with 0 (semantically correct — never added names)
- Use TOTAL_NAMES_ADDED as the single count representative (others are sub-counts)
- Derive PCT_DECEASED_NAMES and PCT_NOVEL_NAMES as ratio features
- Drop LIVING_NAMES, DECEASED_NAMES, NOVEL_NAMES, QUALIFIED_NAMES individually (use ratios instead to avoid multicollinearity)

### Cross-Column Correlation Structure

**Three correlated blocks identified**:

1. **Tree-building block** (r > 0.5 across all pairs):
   TREE_EDITS, SOURCES_ADDED, TOTAL_NAMES_ADDED, DAYS_EDITING_TREES, DAYS_ADDING_NAMES, DAYS_ADDING_SOURCES
   → Reduce to 2-3 features via PCA or select representatives: `TREE_EDITS`, `SOURCES_ADDED`, `TOTAL_NAMES_ADDED`

2. **Name sub-type block** (r > 0.9):
   DECEASED_NAMES, NOVEL_NAMES, QUALIFIED_NAMES, TOTAL_NAMES
   → Reduce to 1 count (TOTAL_NAMES) + 2 ratios (PCT_DECEASED, PCT_NOVEL)

3. **Independent activities**:
   GET_INVOLVED_ITEMS (r < 0.08 with tree-building block)
   RECORD_EDITS (r < 0.05 with others)
   MEMORIES_ADDED (r < 0.05 with others)
   → Keep as independent features (binary flags due to sparsity)

**Activity co-occurrence**:
- Login + Tree edit: 42.4% (most common pair)
- Login + Sources: 7.4%
- Tree edit + Sources: 7.1%
- Tree edit + Memories: 2.2%
- All other pairs < 2%

**Implication**: Users who contribute at all tend to follow the sequence Login → Tree Edit → (optionally) Sources. Get Involved, Record Edits, and Memories are independent activity modes pursued by small, specialized subpopulations.

---

## 10. Subsampling Strategy

### Design Philosophy

Classical proportional stratified sampling preserves global population proportions but assigns zero observations to rare strata. Equal allocation gives every stratum the same power but distorts global cluster structure. The established solution from survey sampling theory is **composite allocation**: reserve a fixed "floor budget" of m seats per stratum to guarantee minimum representation, then allocate the remaining seats proportionally. This approach has formal precedent in Cochran (1977, Chapter 5A "partial stratification"), was formalized with box-constraint solvers by Brzezinski (2024, Statistics Canada RNABOX algorithm), and is standard practice in health informatics enrichment sampling (Kaplan et al., 2019, *JMIR Medical Informatics*).

### Recommended Parameters

| Parameter | Value | Justification |
|-----------|-------|---------------|
| **n** (subsample size) | **30,000** | Satisfies Dolnicar rule (100 x 17.5 features = 1,750 minimum); Qiu & Joe (10 x d x K = 1,050 minimum); fast for HDBSCAN (<50K); convergent for K-means |
| **m** (floor per country) | **30** | Minimum for stratum-level descriptive statistics; standard survey practice |
| **R** (stability trials) | **100** (exploratory) / **200** (reporting) | Per Hennig (2007): convergence by iteration 80-100; 200 for publication quality |
| **T** (independent subsamples) | **5** | Cross-subsample ARI validation; target ARI >= 0.70 |
| **Stability subsample fraction** | **80%** | Per Monti et al. (2003) consensus clustering protocol |
| **Jaccard stability threshold** | **>= 0.75** | Hennig (2007) validated threshold for "stable cluster" |

### Literature Basis for Sample Size

Three complementary guidelines converge:

1. **Dolnicar et al. (2014)**, *J. Travel Research*: 70-100 observations per feature for reliable market segmentation. With d=17.5 features: n >= 1,225-1,750.
2. **Qiu & Joe (2009)**, *J. Classification*: n >= 10 x d x K for stable covariance estimation. With d=17.5, K=6: n >= 1,050.
3. **Formann (1984)**: n >= 2^d as upper bound of caution. With d=15: n >= 32,768.
4. **HDBSCAN practical limit**: n <= 50,000 for fast iterative experiments (O(n^1.7) complexity).

The recommended n=30,000 satisfies all four constraints and runs in seconds for K-Means/GMM, <10s for HDBSCAN.

### Country Strata Classification

Based on the empirical country distribution (215 countries, 250K sample):

| Stratum Type | Countries | Users | Treatment |
|-------------|-----------|-------|-----------|
| **Census strata** (N_h < 30) | ~75 | ~700 | Take all — exhaustively sampled |
| **Floor + proportional** (N_h >= 30) | ~140 | ~249,300 | m=30 floor + proportional remainder |

### Composite Allocation Algorithm

```
Step 1: Classify strata
    S_census = {h : N_h < 30}          # ~75 countries, ~700 users
    S_sample = {h : N_h >= 30}         # ~140 countries

Step 2: Compute budgets
    n_census = sum(N_h for h in S_census)           # ~700
    floor_budget = m * |S_sample| = 30 * 140        # = 4,200
    variable_budget = n - floor_budget - n_census    # ≈ 25,100

Step 3: Allocate
    For each h in S_census:
        n_h = N_h                      # take all

    For each h in S_sample:
        n_h = m + round(variable_budget * N_h / sum(N_h for all h in S_sample))
        n_h = min(n_h, N_h)           # never exceed population

Step 4: Draw
    For each stratum: simple random sample without replacement of size n_h
    Record sampling weights: w_h = N_h / n_h
```

**Example allocations** (approximate, from 250K sample proportions):

| Country | Population (250K) | Floor | Proportional | Total n_h | Weight |
|---------|------------------|-------|-------------|-----------|--------|
| United States | 65,444 | 30 | 6,600 | 6,630 | 9.87 |
| Brazil | 51,676 | 30 | 5,210 | 5,240 | 9.86 |
| Mexico | 11,865 | 30 | 1,196 | 1,226 | 9.68 |
| Philippines | 8,021 | 30 | 809 | 839 | 9.56 |
| South Africa | 2,220 | 30 | 224 | 254 | 8.74 |
| Jamaica | 150 | 30 | 15 | 45 | 3.33 |
| Tonga | 8 | 8 | 0 | 8 (census) | 1.00 |

### Multi-Trial Stability Protocol

```
Phase 1 — Exploratory (fast iteration)
    Draw T=5 independent subsamples of n=30,000 each
    For each subsample:
        Run K-Means with K in {4,5,6,7,8}
        Run GMM with K in {4,5,6,7,8}
        Record silhouette, BIC/AIC, cluster sizes
    Select candidate K by consensus across T=5 trials

Phase 2 — Stability assessment
    On the best subsample (highest silhouette):
        Run clusterboot (Hennig 2007) with R=200 bootstrap iterations
        Record per-cluster Jaccard similarity
        Clusters with Jaccard >= 0.75: stable (keep)
        Clusters with Jaccard 0.60-0.75: borderline (investigate)
        Clusters with Jaccard < 0.60: unstable (merge or drop)

Phase 3 — Cross-subsample validation
    For each pair of T=5 subsamples:
        Compute ARI between cluster assignments on shared users
    Target: mean cross-subsample ARI >= 0.70

Phase 4 — Scale-up
    Assign all 7.6M users to nearest centroid (K-Means) or posterior (GMM)
    Validate country-level cluster proportions against domain expectations
    Apply sampling weights for any population-level inference
```

### Alternative: The Cube Method (Deville & Tillé, 2004)

For advanced applications, the cube method provides balanced sampling that simultaneously controls for multiple continuous auxiliary variables (tenure, age, feature usage rates) in addition to country stratification. It guarantees that the Horvitz-Thompson estimator of each auxiliary total equals the population total — stronger than stratified sampling alone.

**When to use**: If initial clustering experiments reveal that tenure or age confounds are driving cluster assignment (i.e., you get "young users" and "old users" clusters rather than behavioral segments), the cube method can produce subsamples that are exactly balanced on these confounders.

**Implementation**: R `sampling` package, `balancedSampling` package. Not yet available as a Python-native implementation for datasets of this scale.

**Reference**: Deville, J.-C., & Tillé, Y. (2004). "Efficient balanced sampling: The cube method." *Biometrika*, 91(4), 893-912.

### References for Subsampling Strategy

1. Cochran, W.G. (1977). *Sampling Techniques*, 3rd ed. Wiley. (Chapter 5A: partial stratification)
2. Brzezinski, M. (2024). "Recursive Neyman Algorithm for Optimum Sample Allocation under Box Constraints." *Statistics Canada Survey Methodology*.
3. Dolnicar, S., et al. (2014). "Required Sample Sizes for Data-Driven Market Segmentation." *J. Travel Research*, 53(3).
4. Qiu, W., & Joe, H. (2009). "Generation of Random Clusters with Specified Degree of Separation." *J. Classification*, 23(2).
5. Hennig, C. (2007). "Cluster-wise assessment of cluster stability." *Computational Statistics and Data Analysis*, 52(1), 258-271.
6. Monti, S., et al. (2003). "Consensus Clustering." *Machine Learning*, 52, 91-118.
7. von Luxburg, U. (2010). "Clustering Stability: An Overview." *Foundations and Trends in Machine Learning*, 2(3).
8. Liu, Y., et al. (2022). "Stability estimation for unsupervised clustering: A review." *WIREs Computational Statistics*.
9. Kaplan, C.P., et al. (2019). "Enrichment sampling for a multi-site patient survey." *JMIR Medical Informatics*.
10. Deville, J.-C., & Tillé, Y. (2004). "Efficient balanced sampling: The cube method." *Biometrika*, 91(4).

---

## Appendix A: Literature Review (Development, Religiosity, Digital Behavior)

See companion document: `docs/literature-review.md` — 25 references, 15 datasets, GEPI composite index proposal.

## Appendix B: Subsampling Literature

See Section 10 references (10 sources) and background research agent output for full findings on Cochran composite allocation, Hennig clusterboot, Monti consensus clustering, and Deville-Tillé cube method.

## Appendix C: Implementation Pipeline

See companion document: `docs/methods-pipeline.md` — 6 phases, 45 steps, ~5-8 hours end-to-end. Organized by data dependency (execution order), cross-referenced to this report's analytical sections.

---

*Methodology Report v1.3 — FamilySearch User Segmentation*
*10 analytical sections + 3 appendices*
