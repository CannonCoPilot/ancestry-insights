# Methods Pipeline: Implementation Roadmap

**Date**: 2026-03-25
**Companion to**: `docs/methodology-report.md` (analytical foundations)
**Purpose**: Execution-ordered pipeline for the FamilySearch user segmentation analysis. Each phase consumes the output of the previous phase.

---

## Pipeline Overview

```
  PHASE 1          PHASE 2          PHASE 3          PHASE 4         PHASE 5          PHASE 6
  INFRA            CLEANING         FEATURES         SUBSAMPLING     CLUSTERING       REPORTING
  ┌─────┐         ┌─────┐          ┌─────┐          ┌─────┐         ┌─────┐          ┌─────┐
  │ DB  │────────▶│Clean│─────────▶│Engi-│─────────▶│Strat│────────▶│Clus-│─────────▶│Prof-│
  │Setup│         │Data │          │neer │          │ified│         │ter  │          │ile  │
  └─────┘         └─────┘          └─────┘          │Draws│         │+Val │          │+Rec │
  run ONCE         run ONCE         run ONCE         └─────┘         └─────┘          └─────┘
                                                     T=5 draws       iterative        final
```

**Phases 1-3 are deterministic** — run exactly once, producing materialized database tables. Phase 4 runs T=5 times (reproducible via seeds stored in registry). Phases 5-6 are iterative (run many times during exploration). The database architecture ensures each phase reads from the previous phase's table, never from raw CSV.

---

## Phase 1: Infrastructure Setup

**Goal**: Stand up the database, load raw data, prepare enrichment tables.
**Runs**: Once.
**Inputs**: Raw CSV (1.5GB), external data sources.
**Outputs**: DuckDB file with Layer 1 (raw_users) + Layer 4 skeleton (country_enrichment schema).
**Methodology Report References**: Section 0 (schema design), Section 5 (external enrichment).

| Step | Action | SQL/Code Reference | Acceptance Criteria |
|------|--------|-------------------|-------------------|
| 1a | Install DuckDB, create `data/data.duckdb` | `pip install duckdb` | `import duckdb` succeeds |
| 1b | Load raw CSV into `raw_users` | `CREATE TABLE raw_users AS SELECT * FROM read_csv_auto(...)` | 7,625,105 rows, 33 columns |
| 1c | Build ISO-3166 crosswalk | `CREATE TABLE country_name_map` — manually map 215 FamilySearch country names to ISO-3166-alpha-3 codes | All 215 countries mapped |
| 1d | Create `country_enrichment` schema | DDL from methodology Section 0 | Table exists, empty (data loaded in Phase 3) |
| 1e | Create experiment tracking tables | `subsample_registry`, `clustering_experiments`, `cluster_assignments`, `cluster_profiles` | All Layer 5-6 tables exist |
| 1f | Create derived feature tables | `derived_feature_registry`, `derived_feature_values` | Layer 7 tables exist |
| 1g | Verify | `SELECT COUNT(*) FROM raw_users` = 7,625,105; all 12 tables exist | Full schema validated |

**Duration estimate**: 30-45 minutes (dominated by CSV load and country name mapping).

---

## Phase 2: Data Cleaning

**Goal**: Apply all quality decisions to produce a clean, analysis-ready table.
**Runs**: Once.
**Inputs**: Layer 1 (raw_users).
**Outputs**: Layer 2 (users_cleaned) — 7.6M rows, quality issues resolved.
**Methodology Report References**: Section 6 (missingness), Section 9 (column profiles).

| Step | Action | Methodology Reference | Acceptance Criteria |
|------|--------|----------------------|-------------------|
| 2a | Create `users_cleaned` table | Section 0 DDL | All 7.6M rows present |
| 2b | Age clipping (0-110) and age=0 → NULL | Section 3, Section 9 | `MAX(user_age) = 110`; `MIN(user_age) = 8` (after NULL); 757 age=0 rows set to NULL (min account age is 8; no ages 1-7 exist) |
| 2c | Null activity block flagging | Section 6: MNAR detection | `is_null_activity_block = TRUE` for exactly 10.2% of rows |
| 2d | Activity null → 0 imputation | Section 6: impute as zero | Zero nulls in activity count columns |
| 2e | Name null → 0 imputation | Section 6: semantic zeros | Zero nulls in name count columns |
| 2f | Date milestone derivation | Section 9: date columns | `days_to_first_login` etc. computed, negatives clipped to 0 |
| 2g | Province/City NULL conversion | Section 9: Province, City | "Unknown"/"Redacted"/"-" → NULL; columns retained (97%+ NULL); excluded from clustering features (Member-only data leaks account type) |
| 2h | Tenure computation | Section 1 | `tenure_days >= 1` for all rows |
| 2i | Verify exclusion eligibility | Section 8, Step 1 | Can identify: MNAR block (10.2%), 0-30d tenure (0%) |

**Duration estimate**: 30-60 seconds (single SQL CREATE TABLE AS SELECT).

**Design decision**: Rows are NOT excluded in this phase — the `is_null_activity_block` flag and `tenure_days` column allow Phase 4 (subsampling) to apply exclusions at draw time. This preserves the full dataset for exploratory analysis while ensuring clustering subsamples are clean.

---

## Phase 3: Feature Engineering & Enrichment

**Goal**: Compute all derived features and join external country-level covariates.
**Runs**: Once (plus incremental updates when new derived features are created in Feature Lab).
**Inputs**: Layer 2 (users_cleaned), external data sources.
**Outputs**: Layer 3 (users_features), Layer 4 (users_enriched).
**Methodology Report References**: Section 1 (tenure normalization), Section 2 (pseudo-longitudinal features), Section 3 (age interaction), Section 4 (country clusters, US split), Section 5 (enrichment), Section 7 (skew, multicollinearity), Section 9 (column profiles).

| Step | Action | Methodology Reference | Acceptance Criteria |
|------|--------|----------------------|-------------------|
| 3a | Create `users_features` | Section 0 DDL | +25 engineered columns (58 total) |
| 3b | Tenure-normalized rates | Section 1 | 7 `_per_week` columns, all non-negative |
| 3c | Log-transformed counts | Section 7.1 | 4 `_log` columns |
| 3d | Binary activity flags | Section 9: activity counts | 7 `has_*` flags, all 0 or 1 |
| 3e | Activity breadth | Section 9: cross-column | `n_activity_types` in [0, 6] |
| 3f | Engagement ratios | Section 9: name columns | `pct_deceased_names`, `pct_novel_names` in [0, 1] |
| 3g | Login consistency | Section 9 | `login_consistency` in [0, 1] |
| 3g2 | Tenure weight | Section 1 | `tenure_weight = LN(tenure_days / 7)`, non-negative; used as sample weight in Phase 5 clustering |
| 3h | Age groups | Section 3 (binning rationale) | 8 bins: 8-19, 20-29, ..., 70-79, 80+ (age=0 already NULL from step 2b) |
| 3h2 | Onboarding latency features | Section 2 | `days_to_first_login`, `days_to_first_tree_edit`, etc. (7 columns); negatives clipped to 0 |
| 3h3 | Activation velocity | Section 2 | `activation_speed = mean(days_to_first_X)` across milestones reached; `early_contributor` flag (first contribution within 7d) |
| 3h4 | Funnel stage classification | Section 2 | `funnel_stage` (0-4): registered-only → logged-in → browsed → contributor → deep contributor |
| 3i | Country cluster assignment | Section 4 | `country_cluster` (5 values): US split via USER_AREA_NAME (Utah Area → High-LDS); 122 micro-countries binned; Kruskal-Wallis confirms separation |
| 3j | ETL external data | Section 5 | `country_enrichment` populated for 180+ countries |
| 3k | Country name crosswalk | Section 5, Finding 5.3 | 215 FamilySearch names mapped to ISO-3166 |
| 3l | Create `users_enriched` | Section 0 DDL | users_features LEFT JOIN country_enrichment |
| 3m | Multicollinearity check | Section 7.2 | Correlation matrix computed; tree-building block identified |
| 3n | Index creation | Section 0 | Indexes on COUNTRY, USER_WORLD_REGION, ACCOUNT_TYPE |

**Duration estimate**: 1-2 minutes for SQL; external data ETL is variable (hours if manual, minutes if API-based).

**Note**: External data ETL (Step 3j) can run in parallel with Phases 1-2. The LEFT JOIN in Step 3l handles NULLs gracefully if enrichment data isn't ready yet.

---

## Phase 4: Subsampling

**Goal**: Produce T=5 reproducible, stratified subsamples with composite allocation.
**Runs**: T=5 times (each with a different seed).
**Inputs**: Layer 3/4 (users_features or users_enriched).
**Outputs**: Layer 5 (subsample_registry + subsample_members), Parquet exports for dashboard.
**Methodology Report References**: Section 10 (subsampling strategy).

| Step | Action | Methodology Reference | Acceptance Criteria |
|------|--------|----------------------|-------------------|
| 4a | Classify country strata | Section 10: strata classification | ~75 census strata, ~140 sampled strata |
| 4b | Compute allocations | Section 10: composite algorithm | n_h >= min(30, N_h) for all countries |
| 4c | Apply exclusions | Section 8, Step 1 | Exclude `is_null_activity_block = TRUE`; exclude `tenure_days < 31` |
| 4d | Draw subsample #1 (seed=42) | Section 10: Step 3 | ~30,000 rows; all countries represented |
| 4e | Record in `subsample_registry` | Section 0: Layer 5 | subsample_id=1, n_actual, seed, exclusion flags |
| 4f | Record member weights | Section 10: Step 3 | `sampling_weight = N_h / n_h` for each user |
| 4g | Repeat for seeds 43, 44, 45, 46 | Section 10: multi-trial | 5 entries in registry; 5 × ~30K in members |
| 4h | Export Parquet | — | `data/samples/subsample_T{1-5}.parquet` for dashboard |
| 4i | Validate coverage | Section 10: protocol | All 215 countries present in each subsample (via census strata) |

**Duration estimate**: 5-10 seconds per subsample draw (SQL + Parquet export).

---

## Phase 5: Clustering & Validation

**Goal**: Discover and validate user segments through iterative experimentation.
**Runs**: Many times (iterative exploration).
**Inputs**: Layer 5 subsamples.
**Outputs**: Layer 6 (clustering_experiments, cluster_assignments, cluster_profiles).
**Methodology Report References**: Section 2 (pseudo-longitudinal modeling), Section 7 (skew, multicollinearity, inactive segment, stability), Section 8 (pre-clustering pipeline), Section 10 (stability protocol).

| Step | Action | Methodology Reference | Acceptance Criteria |
|------|--------|----------------------|-------------------|
| **Stage A: Activity-Based Pre-Segmentation** | | | |
| 5a.1 | Classify users into activity segments (A-H) | Section 7.3 | 8 segments assigned based on login count + contribution presence |
| 5a.2 | Exclude MNAR block (Segment A) | Section 6, 7.3 | Already excluded in Phase 4 subsampling; verify 0% MNAR in subsample |
| 5a.3 | Separate non-login contributors (Segment C, ~5.8%) | Section 7.3 | Flag for independent analysis; 0 logins but 87% have tree edits |
| 5a.4 | Separate single-browse visitors (Segment D, ~27.4%) | Section 7.3 | Record as Segment 0 (no contribution features to cluster on) |
| 5a.5 | Clustering population = Segments E-H (~58% of tracked) | Section 7.3 | Single-session contributors through power users; all have login + contribution data |
| **Stage B: Exploratory Clustering** | | | |
| 5b.1 | Feature selection (from Feature Lab or default set) | Section 9: column profiles | 10-15 features selected, multicollinearity resolved |
| 5b.2 | Scale features (RobustScaler) | Section 7.1 | All features zero-mean, unit-IQR; `tenure_weight` excluded from scaling (used as sample weight, not feature) |
| 5b.3 | K-Means: K=4,5,6,7,8 on subsample #1 | Section 1, Section 8 | Weighted K-Means using `tenure_weight`; silhouette + inertia recorded per K |
| 5b.4 | GMM: K=4,5,6,7,8 on subsample #1 | Section 1, Section 8 | `tenure_weight` as prior weight; BIC + AIC + silhouette recorded per K |
| 5b.5 | HDBSCAN: min_cluster_size=300,600,1000 | Section 8, Step 6 | Cluster count + noise % recorded |
| 5b.6 | Select candidate K by elbow + silhouette + BIC consensus | Section 10: Phase 1 | Candidate K identified |
| 5b.7 | Repeat 5b.3-5b.6 on subsamples #2-5 | Section 10: multi-trial | Candidate K consistent across T=5 |
| **Stage C: Stability Assessment** | | | |
| 5c.1 | Clusterboot on best subsample (R=200) | Section 10: Phase 2 | Per-cluster Jaccard scores recorded |
| 5c.2 | Classify clusters: stable (>=0.75), borderline (0.60-0.75), unstable (<0.60) | Section 10: Hennig threshold | n_stable_clusters >= K-1 |
| 5c.3 | Cross-subsample ARI | Section 10: Phase 3 | Mean ARI >= 0.70 across T=5 pairs |
| 5c.4 | If unstable: merge borderline clusters or adjust K, return to 5b | — | Iterate until stable |
| **Stage D: Algorithm Comparison** | | | |
| 5d.1 | Compare K-Means vs GMM vs HDBSCAN at selected K | Section 8, Step 6 | Metrics table: silhouette, CH, DB per algorithm |
| 5d.2 | Select final algorithm by stability + interpretability | — | One algorithm chosen with documented rationale |
| 5d.3 | Record final experiment in `clustering_experiments` | Section 0: Layer 6 | experiment_id, all metrics, feature list |
| **Stage E: Pseudo-Longitudinal Enrichment (optional)** | | | |
| 5e.1 | Within-stage clustering | Section 2 | Cluster separately within each `funnel_stage` (0-4); compare segment stability vs pooled clustering |
| 5e.2 | Survival modeling for engagement propensity | Section 2 | Cox PH or AFT model: time-to-first-tree-edit ~ demographics + tenure; hazard scores as additional clustering features |
| 5e.3 | Latent class analysis (mixed-type) | Section 2 | LCA on milestone reached (binary) + days-to-milestone (continuous); compare class count and membership vs Stage B results |
| 5e.4 | Sequence analysis (Optimal Matching) | Section 2 | Encode milestone order as sequences; OM distance matrix; hierarchical clustering; compare path typologies to behavioral segments |
| 5e.5 | Evaluate enrichment value | — | Compare silhouette/ARI of Stage B baseline vs Stage E variants; adopt only if measurable improvement in stability or interpretability |

**Stage E guidance**: These approaches should be attempted only after the baseline clustering (Stages A-D) is validated and stable. They serve as enrichment — if baseline segments are already well-separated and interpretable, Stage E may not add value. Run on subsample #1 first; extend to multi-trial only if promising.

**Duration estimate**: 2-4 hours for Stages A-D (dominated by clusterboot R=200 iterations). Stage E adds 1-3 hours if pursued.

---

## Phase 6: Interpretation & Reporting

**Goal**: Translate cluster assignments into actionable business insights.
**Runs**: Once (with iterative refinement of presentation).
**Inputs**: Layer 6 (final clustering experiment), Layer 3/4 (full feature set for profiling).
**Outputs**: Segment profiles, business recommendations, scaled-up assignments.
**Methodology Report References**: Section 3 (age interaction), Section 4 (country), Section 7.5 (Member confound).

| Step | Action | Methodology Reference | Acceptance Criteria |
|------|--------|----------------------|-------------------|
| **Stage A: Profiling** | | | |
| 6a.1 | Compute per-cluster feature means/medians | Section 8, Step 7 | `cluster_profiles` table populated |
| 6a.2 | Radar charts (normalized 0-1) | Dashboard: Segment Profiles page | Visual separation across all features |
| 6a.3 | Demographic breakdown (age, region, account type) | Section 3 | Per-cluster demographic tables |
| 6a.4 | Auto-generate segment personas | Dashboard: Segment Profiles page | Human-readable names for each cluster |
| **Stage B: Statistical Validation** | | | |
| 6b.1 | Kruskal-Wallis test per feature | Section 8, Step 7 | All features p < 0.001 |
| 6b.2 | Effect size (eta-squared or Cliff's delta) | — | Report practical significance, not just statistical |
| 6b.3 | Country-level cluster composition | Section 4 | No single country dominates any cluster artificially |
| **Stage C: Business Translation** | | | |
| 6c.1 | Audience-adaptive insights (Technical / Business / Non-Technical) | Dashboard: Insights page | Three versions of each finding |
| 6c.2 | Segment-specific recommendations | Dashboard: Insights page | Actionable onboarding/product recommendations per segment |
| 6c.3 | Opportunity sizing (extrapolate to 7.6M) | Section 10: Phase 4 | Per-segment estimated population with confidence |
| **Stage D: Scale-Up** | | | |
| 6d.1 | Assign all 7.6M users to nearest centroid | Section 10: Step 8 | `cluster_assignments` for full dataset |
| 6d.2 | Validate against subsample assignments | — | ARI >= 0.85 between subsample and full-dataset labels |
| 6d.3 | Export final segment assignments | — | `outputs/final_segments.parquet` |
| 6d.4 | Downloadable report (Markdown) | Dashboard: Insights page | Complete methodology + findings document |

**Duration estimate**: 2-3 hours (profiling and interpretation are human-in-the-loop).

---

## Pipeline Summary

| Phase | Name | Runs | Duration | Output |
|-------|------|------|----------|--------|
| 1 | Infrastructure | Once | 30-45 min | DuckDB with 12 tables |
| 2 | Cleaning | Once | <1 min | Layer 2: users_cleaned |
| 3 | Feature Engineering | Once (+incremental) | 2-5 min | Layers 3-4: 68 columns |
| 4 | Subsampling | T=5 | <1 min | 5 × 30K subsamples + Parquet |
| 5 | Clustering | Iterative | 2-4 hours | Stable K, validated segments |
| 6 | Reporting | Once (+refinement) | 2-3 hours | Profiles, insights, full assignment |
| **Total** | | | **~5-8 hours** | **End-to-end segmentation** |

## Dependencies Graph

```
Phase 1 ──▶ Phase 2 ──▶ Phase 3 ──▶ Phase 4 ──▶ Phase 5 ──▶ Phase 6
  │                        │                        │
  │                        ├─ External data ETL     ├─ Feature Lab (UI)
  │                        │  (can run in parallel) │  (incremental adds)
  │                        │                        │
  └── Country crosswalk    └── Derived features     └── Dashboard updates
      (manual, ~1hr)           (Phase 3 + Lab)          (live during Phase 5-6)
```

**Critical path**: Phases 1 → 2 → 3 → 4 → 5 are sequential (each depends on previous). Phase 6 can begin as soon as Phase 5 produces a candidate clustering. External data ETL (Phase 3i) can run in parallel with Phases 1-2. The Feature Lab (Phase 3 + Layer 7) can add derived features incrementally at any time after Phase 3a.

---

*Methods Pipeline v1.0 — FamilySearch User Segmentation*
*6 phases, 45 steps, ~5-8 hours end-to-end*
*Companion to methodology-report.md*
