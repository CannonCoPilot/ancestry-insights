# Phase 4: Subsampling Report

**Generated**: 2026-03-26T03:40:15.097860
**Tier D Population**: 3,176,788 users (41.7%)
**Subsamples**: T=10, n≈5000 each
**Stratification**: country_cluster × region, floor=15

---

## QC Log

| Step | Metric | Value | Note |
|------|--------|-------|------|
| 4.1 | mnar_excluded | 771519 | 10.1% |
| 4.1 | short_tenure_excluded | 0 | 0.0% |
| 4.1 | after_exclusions | 6853586 |  |
| 4.2 | segment:A_MNAR | 771519 | 10.1% |
| 4.2 | segment:B_NO_ACTIVITY | 2084 | 0.0% |
| 4.2 | segment:C_NONLOGIN_CONTRIB | 434268 | 5.7% |
| 4.2 | segment:D_SINGLE_BROWSE | 2088647 | 27.4% |
| 4.2 | segment:E_LIGHT | 2844382 | 37.3% |
| 4.2 | segment:F_MODERATE | 1035774 | 13.6% |
| 4.2 | segment:G_REGULAR | 349642 | 4.6% |
| 4.2 | segment:H_POWER | 98789 | 1.3% |
| 4.3 | tier_d_count | 3176788 | 41.7% |
| 4.3 | nonlogin_contributors | 434268 |  |
| 4.3 | single_browse | 2088647 |  |
| 4.4 | tier_d_loaded | 3253850 |  |
| 4.4 | distinct_strata | 24 |  |
| 4.4 | strata_pooled | 3 |  |
| 4.4 | final_strata | 22 |  |
| 4.4 | subsample_01 | n=5079, train=3555, test=1524, seed=43 |  |
| 4.4 | subsample_02 | n=5079, train=3554, test=1525, seed=44 |  |
| 4.4 | subsample_03 | n=5079, train=3554, test=1525, seed=45 |  |
| 4.4 | subsample_04 | n=5079, train=3554, test=1525, seed=46 |  |
| 4.4 | subsample_05 | n=5079, train=3554, test=1525, seed=47 |  |
| 4.4 | subsample_06 | n=5079, train=3555, test=1524, seed=48 |  |
| 4.4 | subsample_07 | n=5079, train=3554, test=1525, seed=49 |  |
| 4.4 | subsample_08 | n=5079, train=3555, test=1524, seed=50 |  |
| 4.4 | subsample_09 | n=5079, train=3555, test=1524, seed=51 |  |
| 4.4 | subsample_10 | n=5079, train=3555, test=1524, seed=52 |  |
| 4.6 | verify_01 | 5079 rows, 91 cols |  |
| 4.6 | verify_02 | 5079 rows, 91 cols |  |
| 4.6 | verify_03 | 5079 rows, 91 cols |  |
| 4.6 | verify_04 | 5079 rows, 91 cols |  |
| 4.6 | verify_05 | 5079 rows, 91 cols |  |
| 4.6 | verify_06 | 5079 rows, 91 cols |  |
| 4.6 | verify_07 | 5079 rows, 91 cols |  |
| 4.6 | verify_08 | 5079 rows, 91 cols |  |
| 4.6 | verify_09 | 5079 rows, 91 cols |  |
| 4.6 | verify_10 | 5079 rows, 91 cols |  |