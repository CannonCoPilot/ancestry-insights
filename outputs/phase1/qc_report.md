# Phase 1: QC Report

**Generated**: 2026-03-26T02:42:45.731387
**Database**: `/Users/nathanielcannon/Claude/Projects/familysearch_hw/data/familysearch.duckdb`
**Source**: `/Users/nathanielcannon/Claude/Projects/familysearch_hw/data/raw/users.csv`

---

## QC Log

| Step | Metric | Value | Note |
|------|--------|-------|------|
| 1.1 | raw_row_count | 7625105 |  |
| 1.1 | raw_col_count | 33 |  |
| 1.1 | col_type:USER_ID | BIGINT |  |
| 1.1 | col_type:ACCOUNT_CREATE_DATE | TIMESTAMP |  |
| 1.1 | col_type:ACCOUNT_TYPE | VARCHAR |  |
| 1.1 | col_type:USER_CURRENT_AGE | BIGINT |  |
| 1.1 | col_type:COUNTRY | VARCHAR |  |
| 1.1 | col_type:PROVINCE | VARCHAR |  |
| 1.1 | col_type:CITY | VARCHAR |  |
| 1.1 | col_type:USER_WORLD_REGION | VARCHAR |  |
| 1.1 | col_type:USER_AREA_NAME | VARCHAR |  |
| 1.1 | col_type:EARLIEST_LOGIN_DATE | TIMESTAMP |  |
| 1.1 | col_type:EARLIEST_NAME_CONTRIBUTOR_DATE | TIMESTAMP |  |
| 1.1 | col_type:EARLIEST_SOURCE_CONTRIBUTOR_DATE | TIMESTAMP |  |
| 1.1 | col_type:EARLIEST_MEMORY_CONTRIBUTOR_DATE | TIMESTAMP |  |
| 1.1 | col_type:EARLIEST_GET_INVOLVED_USAGE_DATE | TIMESTAMP |  |
| 1.1 | col_type:EARLIEST_RECORD_EDIT_DATE | TIMESTAMP |  |
| 1.1 | col_type:EARLIEST_TREE_EDIT_DATE | TIMESTAMP |  |
| 1.1 | col_type:DAYS_LOGGING_IN | DOUBLE |  |
| 1.1 | col_type:SOURCES_ADDED | DOUBLE |  |
| 1.1 | col_type:DAYS_ADDING_SOURCES | DOUBLE |  |
| 1.1 | col_type:MEMORIES_ADDED | DOUBLE |  |
| 1.1 | col_type:DAYS_ADDING_MEMORIES | DOUBLE |  |
| 1.1 | col_type:GET_INVOLVED_ITEMS_REVIEWED | DOUBLE |  |
| 1.1 | col_type:DAYS_REVIEWING_GET_INVOLVED_ITEMS | DOUBLE |  |
| 1.1 | col_type:RECORD_EDITS | DOUBLE |  |
| 1.1 | col_type:DAYS_EDITING_RECORDS | DOUBLE |  |
| 1.1 | col_type:TREE_EDITS | DOUBLE |  |
| 1.1 | col_type:DAYS_EDITING_TREES | DOUBLE |  |
| 1.1 | col_type:DAYS_ADDING_NAMES | DOUBLE |  |
| 1.1 | col_type:TOTAL_NAMES_ADDED | DOUBLE |  |
| 1.1 | col_type:DECEASED_NAMES_ADDED | DOUBLE |  |
| 1.1 | col_type:LIVING_NAMES_ADDED | DOUBLE |  |
| 1.1 | col_type:NOVEL_NAMES_ADDED | DOUBLE |  |
| 1.1 | col_type:QUALIFIED_NAMES_ADDED | DOUBLE |  |
| 1.2 | age_eq_0 | 0 | Will be set to NULL (system default) |
| 1.2 | age_1_to_7 | 0 | Will be set to NULL (below min account age 8) |
| 1.2 | age_gt_110 | 16720 | Will be clipped to 110 |
| 1.2 | age_negative | 23134 | Will be set to NULL |
| 1.2 | total_age_nullified | 23134 |  |
| 1.3 | PROVINCE_sentinel:Unknown | 7417060 |  |
| 1.3 | PROVINCE_sentinel:- | 1037 |  |
| 1.3 | CITY_sentinel:Unknown | 7379755 |  |
| 1.3 | CITY_sentinel:Redacted | 20439 |  |
| 1.3 | CITY_sentinel:- | 970 |  |
| 1.3 | CITY_empty_or_null | 10 |  |
| 1.4 | mnar_block_count | 771519 |  |
| 1.4 | mnar_block_pct | 10.12 |  |
| 1.4 | any_activity_null_count | 771519 | Should equal mnar_block_count if block-or-nothing |
| 1.5 | reference_date | 2026-03-18 |  |
| 1.5 | max_dates_by_col | {'ACCOUNT_CREATE_DATE': '2025-12-30', 'EARLIEST_LOGIN_DATE': '2026-03-17', 'E... |  |
| 1.6 | distinct_countries | 244 |  |
| 1.6 | matched_countries | 242 |  |
| 1.6 | null_mapped | 2 |  |
| 1.6 | unmatched_countries | 0 |  |
| 1.6 | crosswalk_total_rows | 244 |  |
| 1.6 | crosswalk_null_iso3 | 2 | Includes 'Unknown' and unmatched |
| 1.7 | users_clean_rows | 7625105 |  |
| 1.7 | row_count_match | True |  |
| 1.7 | age_nulls | 23134 |  |
| 1.7 | age_min | 9 | Should be >= 8 |
| 1.7 | age_max | 110 | Should be <= 110 |
| 1.7 | mnar_flagged | 771519 |  |
| 1.7 | province_null | 7418097 |  |
| 1.7 | city_null | 7401174 |  |
| 1.7 | iso3_null | 3324 | Includes 'Unknown' country |
| 1.7 | tenure_negative | 0 | Should be 0 |
| 1.8 | experiment_registry | created |  |
| 1.8 | qc_log | created |  |
| 1.9 | total_rows | 7625105 |  |
| 1.9 | null_pct:user_age | 0.3 |  |
| 1.9 | null_pct:province | 97.29 |  |
| 1.9 | null_pct:city | 97.06 |  |
| 1.9 | null_pct:iso3_code | 0.04 |  |
| 1.9 | null_pct:earliest_login_date | 15.6 |  |
| 1.9 | null_pct:earliest_name_date | 48.12 |  |
| 1.9 | null_pct:earliest_source_date | 91.58 |  |
| 1.9 | null_pct:earliest_memory_date | 97.49 |  |
| 1.9 | null_pct:earliest_get_involved_date | 99.38 |  |
| 1.9 | null_pct:earliest_record_edit_date | 99.42 |  |
| 1.9 | null_pct:earliest_tree_edit_date | 47.04 |  |
| 1.9 | null_pct:DAYS_LOGGING_IN | 10.12 |  |
| 1.9 | null_pct:SOURCES_ADDED | 10.12 |  |
| 1.9 | null_pct:DAYS_ADDING_SOURCES | 10.12 |  |
| 1.9 | null_pct:MEMORIES_ADDED | 10.12 |  |
| 1.9 | null_pct:DAYS_ADDING_MEMORIES | 10.12 |  |
| 1.9 | null_pct:GET_INVOLVED_ITEMS_REVIEWED | 10.12 |  |
| 1.9 | null_pct:DAYS_REVIEWING_GET_INVOLVED_ITEMS | 10.12 |  |
| 1.9 | null_pct:RECORD_EDITS | 10.12 |  |
| 1.9 | null_pct:DAYS_EDITING_RECORDS | 10.12 |  |
| 1.9 | null_pct:TREE_EDITS | 10.12 |  |
| 1.9 | null_pct:DAYS_EDITING_TREES | 10.12 |  |
| 1.9 | null_pct:DAYS_ADDING_NAMES | 48.52 |  |
| 1.9 | null_pct:TOTAL_NAMES_ADDED | 48.52 |  |
| 1.9 | null_pct:DECEASED_NAMES_ADDED | 48.52 |  |
| 1.9 | null_pct:LIVING_NAMES_ADDED | 48.52 |  |
| 1.9 | null_pct:NOVEL_NAMES_ADDED | 48.52 |  |
| 1.9 | null_pct:QUALIFIED_NAMES_ADDED | 48.52 |  |
| 1.9 | mnar_pct | 10.12 |  |
| 1.9 | tenure_min | 78 |  |
| 1.9 | tenure_median | 262.0 |  |
| 1.9 | tenure_max | 441 |  |
| 1.9 | tenure_mean | 260.8 |  |
| 1.9 | tenure_negative_count | 0 |  |
| 1.9 | age_min | 9 |  |
| 1.9 | age_median | 30.0 |  |
| 1.9 | age_max | 110 |  |
| 1.9 | age_mean | 35.1 |  |
| 1.9 | age_null_count | 23134 |  |
| 1.9 | distinct_countries | 244 |  |
| 1.9 | account_type:Public | 7396756 |  |
| 1.9 | account_type:Member | 228349 |  |
| 1.9 | region:Latin America | 2952031 |  |
| 1.9 | region:North America | 2124285 |  |
| 1.9 | region:Europe | 1696691 |  |
| 1.9 | region:Asia Pacific | 542301 |  |
| 1.9 | region:Middle East | 177159 |  |
| 1.9 | region:Africa | 130146 |  |
| 1.9 | region:Unknown | 2492 |  |
| 1.9 | iso3_coverage_pct | 99.96 |  |