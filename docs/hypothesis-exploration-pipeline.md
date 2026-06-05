# Hypothesis Exploration Pipeline: FamilySearch User Persistence Analysis

**Date**: 2026-03-25
**Companion documents**: `docs/methodology-report.md` (analytical foundations), `docs/methods-pipeline.md` (original pipeline, superseded by this document)
**Purpose**: Hypothesis-driven pipeline to investigate whether user Persistence on FamilySearch is better predicted by behavioral engagement patterns (Velocity, Volume, Sequencing) or by demographic/contextual factors (age, country, culture, socioeconomic status).

---

## Table of Contents

1. [Definitions](#1-definitions) (includes 1.0 Data Density Assessment)
2. [The Hypothesis](#2-the-hypothesis)
3. [Pipeline Summary](#3-pipeline-summary)
4. [Phase 1: Data Infrastructure & QC](#phase-1-data-infrastructure--qc)
5. [Phase 2: Feature Engineering](#phase-2-feature-engineering)
6. [Phase 3: External Data Enrichment](#phase-3-external-data-enrichment)
7. [Phase 4: Subsampling & Data Partitioning](#phase-4-subsampling--data-partitioning)
8. [Phase 5: Supervised Classification](#phase-5-supervised-classification-discriminant-analysis)
9. [Phase 6: Unsupervised Clustering](#phase-6-unsupervised-clustering)
10. [Phase 7: Hypothesis Evaluation](#phase-7-hypothesis-evaluation)
11. [Phase 8: Reporting & Presentation](#phase-8-reporting--presentation)
12. [Dependencies](#dependencies)
13. [Important Notes](#important-notes)

---

## 1. Definitions

### 1.0 Data Density Assessment

A comprehensive assessment of data sparsity (see companion report: `reports/data-density-assessment.md`) established the following population tiers and analytical constraints:

**Population tiers** (250K sample, extrapolates to 7.6M):

| Tier | Description | n (sample) | % | Modeling Viability |
|------|-------------|-----------|---|-------------------|
| MNAR (untracked) | Pipeline artifact — all activity NULL | 25,467 | 10.2% | **Exclude** |
| Non-login contributor | 0 logins but 87% have tree edits | 14,129 | 5.7% | Analyze separately |
| Browse-only | Logged in, zero contributions | ~104,000 | 41.6% | One data point — **Segment 0** |
| **Tier D: Full constructs** | Login + tree edits + names + dates | **103,973** | **41.6%** | **Primary analytical population** |
| Tier E: Deep | Tier D + sources | 15,998 | 6.4% | Sensitivity analysis only |

**Activity column sparsity** constrains the constructs:

| Activity | % Active (>0) | Viable for rate features? |
|----------|--------------|--------------------------|
| Logins | 84.0% | Yes |
| Tree Edits | 47.5% | Yes |
| Names Added | 51.5% | Yes |
| Sources Added | 8.1% | Marginal (breadth count only) |
| Memories / Get Involved / Record Edits | 0.6-2.3% | No (binary flag only) |

**Geographic bias**: Europe has 2.3x the MNAR rate of Latin America (17.3% vs 7.6%). Latin America has the highest analytical yield (48.0%); Europe the lowest (34.6%). Subsampling must stratify by region.

**The 3-activity constraint**: All four constructs below operate on a feature space dominated by three activities — logins, tree edits, and names. The four rarer activities contribute to activity breadth (count of types) but cannot anchor temporal analysis or rate computation for most users.

### 1.1 Four Constructs

| Construct | Definition | Measurement | Feasible Milestones | Unit |
|-----------|-----------|-------------|---------------------|------|
| **Velocity** | Time between milestones: account creation to first login, first login to first tree edit, first tree edit to first name contribution. | Days between successive EARLIEST_*_DATE fields. Three primary transitions; a 4th (→ first source) is available for the 6.4% Tier E population. | Login → Tree Edit → Name (→ Source for Tier E) | Days (lower = faster) |
| **Volume** | Rate of contributions within a fixed observation window. Number of edits/additions per unit time within a standardized window. | Contributions per week within a 90-day window (default; test 60/120/180 as sensitivity). Computed for logins, tree edits, and names. Source/memory/get-involved/record rates are zero for >90% of users and are excluded from Volume features. | Logins, Tree Edits, Names | Contributions/week |
| **Sequencing** | The variety and order of completed milestone contributions. Captures breadth (how many of the 3 primary activity types a user has performed, range 0-3 for most users, 0-6 if counting binary flags for rare activities) and path (which of the 3 primary milestones came first). | Activity breadth count (0-6 using binary flags), primary milestone sequence string (e.g., `L→T→N`, `L→N→T`, `T→N→L`), and funnel stage (0-4). For the 3-milestone system, there are 6 possible orderings. The Optimal Matching approach remains viable on these short sequences. | 3 primary milestones (6 permutations) + breadth count (0-6) | Categorical / ordinal |
| **Persistence** | The target/classifier variable. A continuous survival-like score measuring long-term sustained activity, later dichotomized into Persistent vs Transient at an empirically determined threshold. | Composite of login consistency, recency of last milestone, and activity breadth (see Section 1.2). Recency uses `MAX(EARLIEST_*_DATE)` as proxy — not last session date. | All available dates | Continuous [0, ~1], then binary |

### 1.2 Persistence Operationalization

Three candidate definitions are proposed. All three will be computed; the recommended definition (C) will be used as the primary target variable, with A and B reported as sensitivity checks.

**Definition A: Login Consistency Ratio**

```
persistence_score_A = DAYS_LOGGING_IN / max(tenure_weeks, 1)
```

- Range: 0 to ~7 (daily loggers with short tenure), but typically 0-1 after normalization
- Captures: proportion of tenure weeks with at least one login
- Pros: Simple, directly observable, no derived features needed
- Cons: Penalizes newer accounts; ignores non-login activity (the 5.8% non-login contributors from methodology report Section 7.3)

**Definition B: Activity Spread Index**

```
activity_span = MAX(all EARLIEST_*_DATE values) - MIN(all EARLIEST_*_DATE values)
persistence_score_B = activity_span / max(tenure_days, 1)
```

- Range: 0 (all activity on one day) to ~1 (activity spread across full tenure)
- Pros: Captures temporal spread regardless of login count; works for non-login contributors
- Cons: Only uses first-occurrence dates, not ongoing activity; cannot distinguish \"active throughout\" from \"active at start and end but not middle\"

**Definition C: Composite Survival Score (Recommended)**

```
persistence_score_C = w1 * (DAYS_LOGGING_IN / max(tenure_weeks, 1))
                    + w2 * (1 - days_since_last_milestone / max(tenure_days, 1))
                    + w3 * (n_activity_types / 6)
```

Where:
- `days_since_last_milestone = reference_date - MAX(all EARLIEST_*_DATE values)`, clipped to `[0, tenure_days]`
- `n_activity_types` = count of distinct activity milestones achieved (out of 6: login, tree edit, person add, name add, source add, record attach)
- Weights `w1`, `w2`, `w3` = 1/3 each as starting point; optimize via discriminant loading if warranted
- Range: 0 (registered, never returned) to ~1 (frequent, recent, broad activity)

**Known limitation**: `days_since_last_milestone` measures time since the user's most recent *first occurrence* of an activity type — not time since their most recent activity overall. EARLIEST_*_DATE fields record when the user first performed each type of action, not their latest session. `MAX(EARLIEST_*)` is the best available proxy for recency of engagement, but conclusions should note that this is not strictly "time elapsed since last account activity." A user who achieved their last new milestone a year ago may still have been active yesterday on previously established activity types.

### 1.3 Persistence Dichotomization

After computing the continuous score, split into Persistent (1) vs Transient (0) using three methods:

| Method | Description | When to Prefer |
|--------|-------------|----------------|
| **Median split** | Score >= median → Persistent | Simple, balanced classes, good default |
| **ROC-optimal cutpoint** | Maximize (sensitivity + specificity) from preliminary logistic regression on the continuous score | When class balance is less important than discrimination |
| **Gaussian Mixture Model** | Fit 2-component GMM on score distribution; assign class by posterior probability | When the score has a natural bimodal structure |

Report results for all three thresholds. Adopt the one that produces the most stable classification across the T=10 subsamples (measured by cross-subsample agreement rate).

---

## 2. The Hypothesis

**H1 (Engagement-Driven Persistence)**: User Persistence is primarily predicted by behavioral engagement patterns — specifically Velocity (how quickly users progress through milestones), Volume (rate of contributions), and Sequencing (breadth and order of activities). If H1 holds, the discriminant function's loadings will be dominated by Velocity, Volume, and Sequencing features, with demographic/contextual variables contributing marginal additional predictive power.

**H0 (Context-Driven Persistence)**: User Persistence is primarily predicted by demographic and contextual factors — age, country cluster, and external enrichment variables (GDP, HDI, LDS presence). If H0 holds, contextual features will dominate the discriminant loadings, suggesting that *who* the user is matters more than *how* they engage.

**Note on ACCOUNT_TYPE exclusion**: Member vs Public account type is excluded from discriminant modeling. The engagement differential between Members and Public accounts is so large (3x login rates, 37x Get Involved participation) that including it would dominate the discriminant function, trivially classifying Persistence by account type rather than by the behavioral or contextual constructs under investigation. Instead, ACCOUNT_TYPE is reserved for downstream cross-validation: after the discriminant function is trained, its performance is assessed separately within Member and within Public populations to determine whether the same engagement→Persistence relationship holds across both groups.

**The Broader Question**: \"Should we expect that people of different cultures, ages, genders, education or wealth will differ greatly between themselves in matters of what captivates and holds their attention and motivation? Is engagement with the story of our family histories more greatly influenced by our circumstances or by how we approach that same engagement?\"

**Decision framework**:

| Outcome | Evidence Pattern | Implication |
|---------|-----------------|-------------|
| **H1 supported** | Block 4 AUC ≈ Block 6 AUC >> Block 5 AUC | Optimize onboarding velocity and contribution breadth |
| **H0 supported** | Block 5 AUC ≈ Block 6 AUC >> Block 4 AUC | Target specific demographic/geographic segments |
| **Mixed / interaction** | Block 6 AUC >> Block 4 AUC *and* Block 6 AUC >> Block 5 AUC | Tailor engagement strategy by context |

---

## 3. Pipeline Summary

| Phase | Name | Runs | Est. Duration | Key Output |
|-------|------|------|---------------|------------|
| 1 | Data Infrastructure & QC | Once | 30-45 min | DuckDB with clean tables |
| 2 | Feature Engineering | Once | 5-10 min | Velocity/Volume/Sequencing/Persistence features |
| 3 | External Enrichment | Once | 2-4 hours | Country-level covariates joined |
| 4 | Subsampling & Partitioning | Once | <5 min | T=10 x 5K subsamples with train/test splits |
| 5 | Supervised Classification | Iterative | 2-4 hours | Discriminant functions, block comparisons |
| 6 | Unsupervised Clustering | Iterative | 1-2 hours | K stable clusters with Persistence overlay |
| 7 | Hypothesis Evaluation | Once | 1-2 hours | H1 vs H0 verdict with evidence |
| 8 | Reporting & Presentation | Once | 2-3 hours | Committee-ready deliverable |

### Dependencies Graph

```
Phase 1 ──► Phase 2 ──► Phase 4 ──► Phase 5 ──► Phase 7 ──► Phase 8
                │                       │            │
                │                       ▼            │
                │                    Phase 6 ────────┘
                │
                └──► Phase 3 (parallel with Phase 2; joins at Phase 4)
```

---

## Phase 1: Data Infrastructure & QC

**Goal**: Load raw data into DuckDB, apply all cleaning rules from the methodology report, validate integrity, and establish experiment tracking infrastructure.

**Inputs**: Raw CSV file (`data/raw/*.csv`), ISO-3166 country codes reference

**Outputs**: Clean DuckDB database at `data/familysearch.duckdb` with tables `users_raw`, `users_clean`, `experiment_registry`, `qc_log`

**Cross-reference**: Implements methodology report Sections 0 (ethical/data context) and 6 (missing-data and QC)

**Dependencies**: None (entry point)

**Duration estimate**: 30-45 minutes

| Step | Action | Reference | Acceptance Criteria |
|------|--------|-----------|---------------------|
| 1.1 | Create DuckDB database and load raw CSV into `users_raw` table. Verify all 33 columns present with expected types. | Methodology 0.3 | Row count matches source CSV; 33 columns confirmed; no silent column drops |
| 1.2 | Apply age cleaning: set `AGE = NULL` where `AGE = 0` or `AGE < 8` or `AGE > 110`. Log counts for each rule. | Methodology 6.1 | Age distribution min >= 8, max <= 110; NULL count logged and matches expectation (~1-2% of rows) |
| 1.3 | Apply Province/City NULL conversion: set `PROVINCE = NULL` and `CITY = NULL` where values are 'Unknown', 'Redacted', '-', or empty strings. | Methodology 6.1 | No sentinel values remain in Province or City columns; Province ~97.3% NULL, City ~97.1% NULL |
| 1.4 | Flag MNAR block: create boolean column `is_mnar` = TRUE where all 11 activity columns (DAYS_LOGGING_IN through DAYS_EDITING_TREES) are simultaneously NULL. This is verified block-or-nothing missingness — no partial nulls exist. Record the percentage. | Methodology 6.2 | MNAR block flagged; percentage approximately 10.12% of total rows; `any_activity_null_count == mnar_block_count` (confirms pure block) |
| 1.5 | Compute tenure: `tenure_days = reference_date - ACCOUNT_CREATION_DATE` where `reference_date` = data extraction date (infer from MAX of all date columns or use a fixed date if documented). Create `tenure_weeks = tenure_days / 7.0`. | Methodology 2.1 | tenure_days >= 0 for all rows; no negative tenure; distribution inspected |
| 1.6 | Build ISO-3166 country crosswalk table: map all observed COUNTRY values to ISO-3166 alpha-3 codes. Flag unmatched values. Store as `country_crosswalk` table. | Methodology 3.1 | All countries mapped or explicitly flagged as unmatchable; coverage rate logged |
| 1.7 | Write clean data to `users_clean` table with all cleaning applied, MNAR flag, tenure columns, and country ISO3 code joined. | -- | `users_clean` row count = `users_raw` row count; all transformations applied |
| 1.8 | Create `experiment_registry` table (columns: experiment_id, subsample_id, seed, n_rows, exclusions, created_at) and `qc_log` table (columns: step, metric, value, timestamp). | -- | Tables exist and are writable |
| 1.9 | Run QC summary queries: total rows, NULL rates per column, MNAR %, tenure distribution (min/median/max), age distribution, country count, account type distribution. Write results to `qc_log`. | Methodology 6 | All metrics logged; no unexpected NULLs in required columns; distributions are plausible |

---

## Phase 2: Feature Engineering

**Goal**: Derive all Velocity, Volume, Sequencing, and Persistence features from the clean data.

**Inputs**: `users_clean` table from Phase 1

**Outputs**: `users_features` table with all derived columns appended

**Cross-reference**: Implements methodology report Sections 1 (tenure normalization), 2 (Volume), 3 (country clustering), 7 (segmentation), and new constructs defined in this document

**Dependencies**: Phase 1

**Duration estimate**: 5-10 minutes

| Step | Action | Reference | Acceptance Criteria |
|------|--------|-----------|---------------------|
| 2.1 | **Velocity features**: Compute onboarding latency for each milestone transition. `days_to_first_login = EARLIEST_LOGIN_DATE - ACCOUNT_CREATION_DATE`, `days_to_first_tree_edit = EARLIEST_TREE_PERSON_EDIT_DATE - EARLIEST_LOGIN_DATE`, `days_to_first_source = EARLIEST_SOURCE_ADDED_DATE - EARLIEST_TREE_PERSON_EDIT_DATE`, etc. Set to NULL if either date is missing. | Definition 1.1 | All velocity features >= 0 or NULL; no negative latencies; distribution inspected for outliers |
| 2.2 | **Activation velocity composite**: `activation_speed = 1 / (1 + days_to_first_login + COALESCE(days_to_first_tree_edit, 0))`. Produces a 0-1 score where higher = faster activation. | Definition 1.1 | Range [0, 1]; NULL only if days_to_first_login is NULL; median and IQR logged |
| 2.3 | **Volume features (tenure-normalized)**: Compute per-week rates for each activity count. `tree_edits_per_week = TREE_PERSON_EDITS / max(tenure_weeks, 1)`, etc. Apply log1p transform: `log_tree_edits_pw = log(1 + tree_edits_per_week)`. | Methodology 1 | Rates >= 0; log-transformed features computed; no Inf/NaN values |
| 2.4 | **Volume features (fixed-window)**: For the 90-day default window, compute contributions within the first 90 days of account creation. Use EARLIEST dates to determine if activity occurred within window; for counts, prorate if tenure < 90 days: `volume_90d = count * min(90, tenure_days) / max(tenure_days, 1)`. Note: this is approximate given we lack per-period counts. | Definition 1.1 | 90-day volume features computed; sensitivity variants (60/120/180) flagged for Phase 5 |
| 2.5 | **Binary activity flags**: For each milestone, create `has_X = 1` if the corresponding EARLIEST date or count > 0, else 0. Activities: login, tree_person_edit, tree_person_add, person_name_add, source_add, record_attach. | Methodology 7.3 | Exactly 6 binary flags; each is 0 or 1; sum matches activity breadth |
| 2.6 | **Activity breadth (Sequencing)**: `activity_breadth = has_login + has_tree_edit + has_tree_add + has_name_add + has_source_add + has_record_attach`. Range 0-6. | Definition 1.1 | Range [0, 6]; distribution matches expectation (mode likely at 0 or 1) |
| 2.7 | **Milestone sequence encoding (Sequencing)**: For each user, order the achieved milestones by their EARLIEST date and encode as a string. E.g., if login came first, then tree edit, then source: `\"L>T>S\"`. Use single-character codes: L=login, T=tree_edit, P=person_add, N=name_add, S=source_add, R=record_attach. NULL/missing milestones are omitted. | Definition 1.1 | String column populated; empty string for users with no milestones; top 20 most common sequences logged |
| 2.8 | **Funnel stage classification**: Assign each user to a funnel stage based on furthest milestone reached: 0=registered only, 1=logged in, 2=first tree edit, 3=first source, 4=record attachment. | Methodology 7.3 | Stages 0-4; distribution logged; monotonically increasing with activity breadth |
| 2.9 | **Login consistency**: `login_consistency = DAYS_LOGGING_IN / max(tenure_weeks, 1)`. | Definition 1.2A | >= 0; distribution inspected; outliers (>7, i.e., daily login with <1 week tenure) noted |
| 2.10 | **Tenure weight**: `tenure_weight = log(1 + tenure_days)`. Used as analytic weight in clustering and classification. | Methodology 1.2 | > 0 for all rows with tenure > 0; distribution logged |
| 2.11 | **Age groups**: Bin AGE into 8 groups: 8-19, 20-29, 30-39, 40-49, 50-59, 60-69, 70-79, 80+. NULL AGE remains NULL. | Methodology 6.1 | 8 bins + NULL; distribution matches raw age distribution |
| 2.12 | **Country cluster assignment**: Apply the 5-cluster schema from methodology report Section 3, with US split out as its own cluster. Clusters: (1) High-eng High-LDS (US), (2) High-eng High-LDS (non-US), (3) High-eng Low-LDS, (4) Mid-eng Developing, (5) Low-eng Developing, (6) Unclustered/Other. | Methodology 3.2 | Each non-NULL country assigned exactly one cluster; US is cluster 1; distribution logged |
| 2.13 | **Persistence score computation**: Compute all three definitions (A, B, C) per Section 1.2. | Definition 1.2 | Three continuous score columns; ranges verified; correlation between A, B, C logged (expect r > 0.5) |
| 2.14 | **Persistence dichotomization**: For Definition C (primary), compute median split, ROC-optimal cutpoint (from logistic regression of persistence_score_C on activity_breadth), and 2-component GMM. Create binary columns for each method. | Definition 1.3 | Three binary columns; class balance logged for each; cross-agreement rate between methods logged |
| 2.15 | Write all features to `users_features` table. Log feature count, NULL rates, and summary statistics for all new columns. | -- | Table exists with all original + derived columns; no accidental row loss; QC summary in `qc_log` |

---

## Phase 3: External Data Enrichment

**Goal**: Acquire, clean, and join country-level contextual variables from external sources to enable H0 testing.

**Inputs**: ISO-3166 country crosswalk from Phase 1, external data APIs/downloads

**Outputs**: `country_enrichment` table in DuckDB; coverage report

**Cross-reference**: Implements methodology report Section 4 (GEPI and external sources)

**Dependencies**: Phase 1 (country crosswalk). Can run in parallel with Phase 2.

**Duration estimate**: 2-4 hours (dominated by manual downloads and API rate limits)

| Step | Action | Reference | Acceptance Criteria |
|------|--------|-----------|---------------------|
| 3.1 | **World Bank WDI** (via `wbgapi` Python package): Download GDP per capita (NY.GDP.PCAP.CD), internet penetration (IT.NET.USER.ZS), education index proxy (SE.ADT.LITR.ZS). Use most recent available year. Store as `wdi_indicators`. | Methodology 4.1 | >= 180 countries with GDP; >= 170 with internet; coverage gaps logged |
| 3.2 | **UN HDI** (direct CSV from hdr.undp.org): Download Human Development Index composite. Parse into `hdi_data` table with ISO3 key. | Methodology 4.2 | >= 185 countries; HDI range [0.2, 1.0]; no duplicate countries |
| 3.3 | **ITU IDI** (Excel download from itu.int): Download ICT Development Index if available for recent year. Parse into `idi_data` table. | Methodology 4.3 | >= 170 countries or note if IDI discontinued (last published 2017); if unavailable, substitute ITU internet stats |
| 3.4 | **Pew religiosity data** (account required, SPSS format): Download religiosity composite from Pew Research Global Attitudes survey. Parse SPSS to CSV, extract country-level religiosity score. Note: 36-country coverage only. | Methodology 4.4 | 36 countries with religiosity scores; explicitly log the 179+ countries WITHOUT coverage |
| 3.5 | **LDS Church statistics** (GitHub CSV from church newsroom data): Download membership-by-country data. Compute `lds_density = members / population`. | Methodology 4.5 | >= 150 countries (many with 0 members); LDS density range [0, ~0.5]; US density verified ~2% |
| 3.6 | **Google Trends** (manual export or defer): If pursuing, export search interest for \"family tree\" or \"genealogy\" by country. If deferred, document as a gap and exclude from GEPI composite. | Methodology 4.6 | Either: data for >= 50 countries, or explicit deferral documented |
| 3.7 | **Build `country_enrichment` table**: Join all external sources on ISO3 code. Columns: iso3, gdp_per_capita, internet_pct, education_index, hdi, idi, pew_religiosity, lds_density, google_trends_index. | -- | One row per country; all sources joined; NULL where source lacks coverage |
| 3.8 | **GEPI composite** (if >= 4 of 6 sources available): Standardize each indicator to z-scores, compute `gepi = mean(z_gdp, z_internet, z_hdi, z_lds_density, ...)`. Only for countries with >= 4 non-NULL indicators. | Methodology 4.7 | GEPI computed where feasible; range approximately [-2, +2]; coverage count logged |
| 3.9 | **Coverage validation report**: For each of the 215 observed countries in the user data, report which external sources have data. Compute: total countries, countries with all sources, countries with >= 4, countries with < 4. | -- | Report generated; coverage gaps explicitly documented; decision logged on whether to proceed with partial enrichment |
| 3.10 | **Join enrichment to user data**: Left join `country_enrichment` to `users_features` on ISO3 code. Users from countries without enrichment retain NULLs in enrichment columns. | -- | Row count unchanged after join; enrichment columns added; NULL rate per enrichment column logged |

---

## Phase 4: Subsampling & Data Partitioning

**Goal**: Apply exclusions, segment the population, draw reproducible stratified subsamples, and create train/test splits.

**Inputs**: `users_features` table (with enrichment from Phase 3 if available)

**Outputs**: T=10 Parquet files with train/test splits; subsample registry

**Cross-reference**: Implements methodology report Section 5 (subsampling) and Section 7.3 (segmentation)

**Dependencies**: Phases 1, 2; Phase 3 (optional, for enrichment columns)

**Duration estimate**: < 5 minutes

| Step | Action | Reference | Acceptance Criteria |
|------|--------|-----------|---------------------|
| 4.1 | **Apply exclusions**: Remove rows where `is_mnar = TRUE` or `tenure_days < 31`. Log counts removed for each reason. | Methodology 6.2, 5.1 | MNAR block removed (~10.2%); short-tenure removed; remaining row count logged |
| 4.2 | **Activity-based pre-segmentation**: Assign each remaining user to a segment. Segment A: MNAR (already excluded). Segment B: Registered, no activity (`activity_breadth = 0 AND DAYS_LOGGING_IN = 0`). Segment C: Non-login contributors (`DAYS_LOGGING_IN = 0 AND activity_breadth > 0`). Segment D: Single-browse visitors (`DAYS_LOGGING_IN = 1 AND activity_breadth = 0`). Segments E-H: Remaining users, classified by activity level (E: 1-2 logins + minimal edits; F: moderate activity; G: regular contributors; H: power users). | Methodology 7.3 | All non-excluded users assigned exactly one segment; segment sizes logged; B excluded, C set aside, D labeled as Segment 0 |
| 4.3 | **Define analytical population**: **Tier D** (users with login + tree edits + names + all 3 milestone dates) = ~42% of tracked users (~3.2M at population scale). This is the primary analytical population for classification and clustering. Tier E (+ sources, 6.4%) available for sensitivity analysis. Segment C (non-login contributors, 5.7%) analyzed independently. Browse-only (37%) = Segment 0, descriptive profiling only. See `reports/data-density-assessment.md`. | Data Density Assessment | Analytical population ~42% of total; Tier D count logged; Segments C/D counts logged separately |
| 4.4 | **Draw T=10 stratified subsamples** from the Tier D analytical population. Each subsample: n=5,000. Stratify by `country_cluster` AND `USER_WORLD_REGION` with Cochran floor m=15 per stratum to counteract European underrepresentation (34.6% yield vs 48% for Latin America). Record seed for each subsample in `experiment_registry`. | Methodology 5.2 | 10 subsamples of ~5,000 each; each stratum has >= 15 rows or is pooled into \"Other\"; seeds recorded |
| 4.5 | **Train/test split within each subsample**: 70/30 stratified by persistence_score_C tertile. Record split indices. | -- | Each subsample has train (~3,500) and test (~1,500) partitions; tertile proportions approximately equal in both partitions |
| 4.6 | **Export Parquet files**: One file per subsample with train/test indicator column. Naming: `data/subsamples/subsample_{01-10}.parquet`. | -- | 10 Parquet files on disk; each readable and verified for row count and column completeness |
| 4.7 | **Log subsample metadata**: For each subsample, record: seed, n_train, n_test, persistence_rate (% Persistent), country_cluster distribution, age_group distribution, mean tenure_days. | -- | All metadata in `experiment_registry`; distributions are approximately consistent across subsamples |

---

## Phase 5: Supervised Classification (Discriminant Analysis)

**Goal**: Build and validate discriminant functions that classify users as Persistent vs Transient, comparing feature blocks to assess H1 vs H0.

**Inputs**: T=10 subsamples from Phase 4

**Outputs**: Model coefficients, feature loadings/importances, classification metrics per block per subsample, block comparison table

**Cross-reference**: Implements new analysis (not in original methods-pipeline); builds on methodology report Section 7 (segmentation concepts)

**Dependencies**: Phase 4

**Duration estimate**: 2-4 hours (iterative)

### 5.A Assumption Verification

Run before any model fitting. Repeat for each subsample.

| Step | Action | Reference | Acceptance Criteria |
|------|--------|-----------|---------------------|
| 5.A.1 | **Multicollinearity check**: Compute VIF for all continuous features in the full feature set. Flag features with VIF > 10. | LDA/logistic assumption | No feature with VIF > 10 in the final model; if found, drop the less theoretically important member of the correlated pair |
| 5.A.2 | **Class balance assessment**: Compute Persistent vs Transient ratio using the primary dichotomization method (from Phase 2, Step 2.14). | Classification assumption | If imbalance exceeds 60/40, apply class weights (inverse frequency) to all models; if exceeds 70/30, additionally test SMOTE on training set |
| 5.A.3 | **Normality of discriminators**: Shapiro-Wilk test on each continuous feature within each class. Log p-values. | LDA assumption | For LDA: note violations but proceed (LDA is robust to moderate non-normality with n > 200). For logistic/RF: not required |
| 5.A.4 | **Feature scaling**: Standardize all continuous features to mean=0, sd=1. Fit scaler on training set only; apply to test set. Categorical features: one-hot encode (country_cluster, age_group). ACCOUNT_TYPE excluded from modeling (see Hypothesis section). | LDA/logistic requirement | Scaled features have mean ≈ 0, sd ≈ 1 on training set; no data leakage from test set; ACCOUNT_TYPE not in feature matrix |

### 5.B Feature Block Definitions

| Block | Label | Features Included | Construct(s) |
|-------|-------|-------------------|---------------|
| 1 | Velocity Only | days_to_first_login, days_to_first_tree_edit, days_to_first_source, activation_speed | Velocity |
| 2 | Volume Only | log_tree_edits_pw, log_person_adds_pw, log_source_adds_pw, volume_90d_* features | Volume |
| 3 | Sequencing Only | activity_breadth, funnel_stage, milestone_sequence (encoded), has_* flags | Sequencing |
| 4 | H1 Combined | All features from Blocks 1 + 2 + 3 | Velocity + Volume + Sequencing |
| 5 | H0 Contextual | age_group, country_cluster, gdp_per_capita, hdi, lds_density, internet_pct (external enrichment columns). **Excludes ACCOUNT_TYPE** — reserved for downstream cross-validation. | Demographic + Contextual |
| 6 | Full Model | All features from Blocks 4 + 5 | All constructs |

### 5.C Model Fitting

For each block, fit the following models on each subsample's training set, evaluate on test set.

| Step | Action | Reference | Acceptance Criteria |
|------|--------|-----------|---------------------|
| 5.C.1 | **Linear Discriminant Analysis (LDA)**: Fit sklearn `LinearDiscriminantAnalysis` with default priors. Extract canonical coefficients (loadings). | Primary method | Model fits without singular covariance error; loadings extracted and ranked by absolute value |
| 5.C.2 | **Logistic Regression**: Fit `LogisticRegression` with L2 regularization (C=1.0 default; tune via 5-fold CV on training set if time permits). Extract coefficients. | Comparison method | Model converges; coefficients extracted; regularization strength logged |
| 5.C.3 | **Random Forest**: Fit `RandomForestClassifier` with n_estimators=500, max_depth=None. Extract feature importances (Gini). | Non-linear benchmark | OOB score logged; feature importances extracted and ranked |
| 5.C.4 | **(Optional) Gradient Boosted Trees**: Fit `GradientBoostingClassifier` or `XGBClassifier` if RF suggests strong interaction effects (i.e., RF importance ranking differs substantially from logistic coefficients). | Interaction detection | Only run if RF top-5 features differ substantially from logistic top-5; SHAP values computed for interaction analysis |

### 5.D Evaluation

| Step | Action | Reference | Acceptance Criteria |
|------|--------|-----------|---------------------|
| 5.D.1 | **Per-block, per-model metrics on test set**: Compute accuracy, precision, recall, F1, AUC-ROC. | -- | All metrics computed; no NaN/Inf values; results stored in structured table |
| 5.D.2 | **Cross-subsample aggregation**: For each block x model combination, compute mean and standard deviation of all metrics across T=10 subsamples. | -- | 10 values per metric; mean and std reported; std indicates stability |
| 5.D.3 | **Block comparison table**: Create a summary table: Block, Model, Mean AUC (std), Mean F1 (std), Mean Accuracy (std). Sort by Mean AUC descending. | -- | Table generated; Block 4 vs Block 5 comparison highlighted |
| 5.D.4 | **Feature loading/importance summary**: For LDA and RF, aggregate feature rankings across subsamples. Report: feature name, mean rank, mean absolute loading/importance, construct label (Velocity/Volume/Sequencing/Contextual). | -- | All features ranked; construct labels assigned; top-10 features identified with construct breakdown |
| 5.D.5 | **Incremental AUC analysis**: Compare Block 4 AUC, Block 5 AUC, Block 6 AUC. Compute: `delta_H1 = Block 6 AUC - Block 5 AUC` (incremental value of adding engagement features), `delta_H0 = Block 6 AUC - Block 4 AUC` (incremental value of adding contextual features). | -- | Deltas computed with confidence intervals (from the 10 subsamples); direction and magnitude interpreted |

---

## Phase 6: Unsupervised Clustering

**Goal**: Discover natural structure in the data and compare cluster membership against Persistence classification.

**Inputs**: Same subsamples from Phase 4; feature importance rankings from Phase 5

**Outputs**: Cluster assignments per subsample, stability metrics, Persistence overlay statistics

**Cross-reference**: Extends methodology report Section 7 (segmentation) with Persistence overlay

**Dependencies**: Phase 4 (subsamples); Phase 5 (feature importance for feature selection)

**Duration estimate**: 1-2 hours

| Step | Action | Reference | Acceptance Criteria |
|------|--------|-----------|---------------------|
| 6.1 | **Feature selection for clustering**: Use the top 15 features by RF importance (from Phase 5, Block 6 full model, aggregated across subsamples). Standardize selected features. | Phase 5 output | 15 features selected; standardized; no constant or near-constant features |
| 6.2 | **K-Means clustering**: For each subsample, fit K-Means with k=4,5,6,7,8. Use `tenure_weight` as sample weight. Record inertia, silhouette score, Calinski-Harabasz index, Davies-Bouldin index for each k. | Methodology 7.1 | All k values fitted; all metrics recorded; no empty clusters |
| 6.3 | **GMM clustering**: For each subsample, fit Gaussian Mixture Model with k=4,5,6,7,8. Full covariance. Record BIC, AIC, silhouette on hard assignments. | Methodology 7.1 | All k values fitted; BIC/AIC recorded; convergence achieved for all |
| 6.4 | **HDBSCAN**: For each subsample, fit HDBSCAN with min_cluster_size=50 (adjust if too few clusters). Record number of clusters found, noise percentage. | Methodology 7.1 | Clusters found; noise % < 30%; if noise > 30%, adjust min_cluster_size and re-run |
| 6.5 | **Select optimal k**: For K-Means and GMM, select k by majority vote across silhouette (max), CH (max), DB (min), BIC (min, GMM only). If methods disagree, prefer the k that produces the most interpretable clusters. | -- | Single k selected per method; rationale documented |
| 6.6 | **Cluster stability (Clusterboot)**: For the selected k, run bootstrap resampling: R=100 resample iterations, compute Jaccard similarity for each cluster across resamples. Report mean Jaccard per cluster. | Methodology 7.2 | Mean Jaccard >= 0.60 for all clusters (>= 0.75 preferred); clusters below 0.60 flagged as unstable |
| 6.7 | **Cross-subsample stability (ARI)**: Compare cluster assignments between all pairs of subsamples (on overlapping users, if any, or on the same feature space with held-out data). Report mean ARI. | Methodology 7.2 | Mean ARI >= 0.70 across subsample pairs |
| 6.8 | **Persistence overlay**: For each cluster in the selected solution, compute: % Persistent, % Transient, mean persistence_score_C, 95% CI for the mean. | -- | Overlay statistics computed for all clusters; variation across clusters assessed |
| 6.9 | **Chi-squared test and Cramer's V**: Test independence of cluster membership and Persistence classification. Compute Cramer's V as effect size. | -- | Chi-squared p-value and Cramer's V reported; V > 0.3 = strong association, V < 0.1 = weak |
| 6.10 | **Cluster profiling**: For each cluster, compute mean/median of all features (Velocity, Volume, Sequencing, contextual). Create radar chart data. Assign interpretive labels (e.g., \"Fast Starters,\" \"Slow Explorers,\" \"Power Users\"). | -- | All clusters profiled; labels assigned; radar chart data exported |

---

## Phase 7: Hypothesis Evaluation

**Goal**: Formally assess H1 vs H0 by synthesizing evidence from Phases 5 and 6.

**Inputs**: Block comparison table (Phase 5), feature loadings (Phase 5), cluster x Persistence contingency (Phase 6)

**Outputs**: Hypothesis verdict with supporting evidence, interaction analysis results

**Cross-reference**: Novel analysis; integrates all prior phases

**Dependencies**: Phases 5 and 6

**Duration estimate**: 1-2 hours

| Step | Action | Reference | Acceptance Criteria |
|------|--------|-----------|---------------------|
| 7.1 | **Discriminant loading composition**: From Phase 5.D.4, classify the top-20 features by construct (Velocity, Volume, Sequencing, Contextual). Compute proportion of total absolute loading weight belonging to each construct. | Phase 5.D.4 | Proportions sum to 1.0; each construct's share reported with subsample-level variability |
| 7.2 | **Incremental R-squared analysis**: Fit Nagelkerke pseudo-R-squared for logistic regression Blocks 4, 5, and 6. Compute incremental contributions: `R2_engagement_beyond_context = R2_block6 - R2_block5`, `R2_context_beyond_engagement = R2_block6 - R2_block4`. | Phase 5.C.2 | Pseudo-R-squared values computed for all blocks across subsamples; incremental values reported with CIs |
| 7.3 | **Cluster x Persistence verdict**: If behavioral-feature-driven clusters (Phase 6) predict Persistence well (Cramer's V > 0.3), this supports H1. If clusters are independent of Persistence (V < 0.1), contextual factors must be dominant. | Phase 6.9 | Cramer's V interpreted against threshold; verdict documented with confidence |
| 7.4 | **Country cluster interaction analysis**: Within each country cluster, re-fit the Block 4 (H1) logistic model. Compare AUC across country clusters. If AUC is consistent (within 0.05) across all clusters, engagement patterns are universal (H1). If AUC varies by > 0.10 across clusters, persistence is context-dependent (nuanced H0). | Phase 5 subsets | Per-country-cluster AUC reported; variation quantified; interpretation documented |
| 7.5 | **Age group interaction analysis**: Same as 7.4 but stratified by age group. Re-fit Block 4 model within each age group; compare AUC. | Phase 5 subsets | Per-age-group AUC reported; variation quantified; interpretation documented |
| 7.6 | **Synthesize verdict**: Compile evidence from Steps 7.1-7.5 into a verdict table. Assess overall weight of evidence for H1 vs H0 vs mixed. | -- | Verdict stated clearly with supporting evidence enumerated; ambiguity acknowledged if evidence is mixed |

### Verdict Decision Matrix

| Evidence | H1 Support | H0 Support | Mixed |
|----------|-----------|-----------|-------|
| Top-20 loading composition | >= 60% from Velocity/Volume/Sequencing | >= 60% from Contextual | Neither exceeds 60% |
| Incremental R-squared | `R2_engagement_beyond_context` > 2x `R2_context_beyond_engagement` | Reverse | Comparable magnitude |
| Cluster x Persistence (Cramer's V) | V > 0.3 | V < 0.1 | 0.1 <= V <= 0.3 |
| Country cluster AUC consistency | Range < 0.05 | Range > 0.10 | 0.05-0.10 |
| Age group AUC consistency | Range < 0.05 | Range > 0.10 | 0.05-0.10 |

---

## Phase 8: Reporting & Presentation

**Goal**: Translate findings into a committee-ready deliverable.

**Inputs**: All results from Phases 5, 6, 7

**Outputs**: Executive summary, updated methodology report, dashboard pages, statistical appendix

**Cross-reference**: Final synthesis

**Dependencies**: All prior phases

**Duration estimate**: 2-3 hours

| Step | Action | Reference | Acceptance Criteria |
|------|--------|-----------|---------------------|
| 8.1 | **Executive summary** (1 page): State the hypothesis, key finding (H1/H0/mixed verdict), top-3 most predictive features, business implication, and single recommended action. | -- | Fits on one page; accessible to non-technical committee members; no jargon without definition |
| 8.2 | **Update methodology-report.md**: Add sections documenting the discriminant analysis methodology, Persistence operationalization, and hypothesis testing framework. Reference this pipeline document. | Companion doc | Methodology report is self-consistent and complete |
| 8.3 | **Dashboard: Clustering Lab update**: Add Persistence overlay to existing cluster visualizations. For each cluster, show Persistence rate, mean score, and radar chart of construct scores. | Dashboard | Visualizations render correctly; Persistence overlay is visually clear |
| 8.4 | **Dashboard: Segment Profiles update**: Update segment profiles (E-H) with Persistence rates and discriminant score distributions. | Dashboard | Each segment has Persistence statistics and feature distributions |
| 8.5 | **Statistical appendix**: Full model coefficients for all blocks and methods; all validation metrics with confidence intervals; stability results (Clusterboot, cross-subsample ARI); assumption verification results (VIF, normality, class balance). | -- | All numbers reproducible from exported model objects; no cherry-picked results |
| 8.6 | **Limitations section**: Document all known limitations explicitly: (a) MNAR block exclusion and its potential bias, (b) cross-sectional data constraints (no longitudinal tracking), (c) Persistence proxy limitations (EARLIEST dates only, no LATEST), (d) Pew 36-country coverage gap, (e) Province/City Member-only confound, (f) fixed observation window approximation for Volume, (g) proof-of-concept sample size (5K per subsample). | -- | All limitations enumerated; each includes a brief assessment of likely impact direction |
| 8.7 | **Recommendations**: Three scenarios based on verdict. If H1: Optimize onboarding velocity (reduce days-to-first-edit) and early contribution breadth (encourage diverse activities in first 90 days). If H0: Target specific demographic/geographic segments with tailored strategies (e.g., different onboarding for high-LDS vs low-LDS countries). If mixed: Combine both — tailor the engagement velocity strategy by demographic context. | -- | Recommendations are specific, actionable, and directly tied to findings |

---

## Dependencies

```
Phase 1 ──► Phase 2 ──► Phase 4 ──► Phase 5 ──► Phase 7 ──► Phase 8
                │                       │            │
                │                       ▼            │
                │                    Phase 6 ────────┘
                │
                └──► Phase 3 (parallel with Phase 2; joins at Phase 4)
```

**Critical path**: Phases 1 → 2 → 4 → 5 → 7 → 8

**Parallel opportunity**: Phase 3 can begin as soon as Phase 1 is complete (ISO-3166 crosswalk available). Its outputs are consumed in Phase 4 (join) and Phase 5 (Block 5 features).

---

## Important Notes

1. **Proof-of-concept scope**: T=10 x 5K subsamples are sized for fast iteration and initial hypothesis testing. A production-grade analysis would use T=5 x 30K subsamples with full bootstrap validation.

2. **Fixed observation window for Volume**: 90 days is the default window. Phase 2 computes this as the primary feature. Sensitivity analysis with 60/120/180-day windows should be run in Phase 5 by swapping Volume features and comparing AUC impact. If results are robust across windows, report the 90-day version. If sensitive, report the window that maximizes cross-subsample stability.

3. **Persistence score limitations**: We have EARLIEST dates only, not LATEST or per-period activity counts. The persistence score is a best-available proxy, not a true survival curve. Definition C is recommended because it combines three facets (consistency, recency, breadth), but all three definitions should be reported as sensitivity checks. If results differ substantially between definitions, this is itself a finding about the construct's measurement sensitivity.

4. **External enrichment is optional but valuable**: Phase 3 can run in parallel and its outputs are only needed for Block 5 (H0 features). If some sources are unavailable (Google Trends, Pew for 150+ countries), proceed with available data and explicitly note coverage gaps. The GEPI composite requires >= 4 of 6 indicators; if fewer are available, use individual indicators instead.

5. **Assumption verification is mandatory**: Before each model in Phase 5, Steps 5.A.1 through 5.A.4 must be completed and documented. Common violations and their remedies: (a) VIF > 10: drop one member of the correlated pair, preferring to keep the more theoretically central feature; (b) class imbalance: apply inverse-frequency class weights; (c) non-normality: note for LDA but proceed (robust with n > 200); for severe skew, consider Box-Cox transform.

6. **Cross-reference to methodology report**: Each phase maps to methodology report sections as follows:

   | Phase | Methodology Report Sections |
   |-------|-----------------------------|
   | 1 | Sections 0, 6 |
   | 2 | Sections 1, 2, 3, 7 |
   | 3 | Section 4 |
   | 4 | Sections 5, 7.3 |
   | 5 | New (discriminant analysis) |
   | 6 | Section 7 (extended with Persistence overlay) |
   | 7 | New (hypothesis evaluation) |
   | 8 | New (reporting) |

7. **Reproducibility**: The analysis must be fully reproducible by a reviewer with access to the raw data.
   - **Seeds**: All random operations (subsampling, train/test splits, bootstrap) use recorded seeds stored in `experiment_registry`. No unseeded randomness.
   - **Folder structure**: Organize outputs by phase: `data/raw/`, `data/clean/`, `data/subsamples/`, `outputs/phase5/`, `outputs/phase6/`, `outputs/phase7/`, `reports/`. Each phase's outputs are self-contained.
   - **Code modularity**: Each phase should be executable independently via a single script or notebook (e.g., `src/phase1_qc.py`, `src/phase2_features.py`, etc.). Shared utilities live in `src/utils/`. No monolithic "run everything" script — phases can be re-run individually when upstream changes occur.
   - **Versioning**: All code committed to git with meaningful commit messages per phase. The `experiment_registry` table records which code version (commit hash) produced each subsample and model result. DuckDB database file is gitignored (too large), but the DDL and seed registry that reproduce it are tracked.
   - **Intermediate exports**: All intermediate results (feature tables, model coefficients, cluster assignments, metrics) exportable as Parquet or CSV for independent verification. A reviewer should be able to load any intermediate artifact and validate it against the documented acceptance criteria without re-running the full pipeline.

---

*Hypothesis Exploration Pipeline v1.0 -- FamilySearch User Persistence Analysis*
*2026-03-25*