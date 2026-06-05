# Phase 6: Clustering Results Summary

**Generated**: 2026-03-26T04:02:09.848919
**Selected k**: 3
**Cross-subsample ARI**: 0.0273

---

## K-Means Metrics (averaged across T=10)

|   k |   mean_sil |   mean_ch |   mean_db |   mean_inertia |
|----:|-----------:|----------:|----------:|---------------:|
|   3 |     0.5157 |   1490.52 |    1.0477 |         264591 |
|   4 |     0.5119 |   1341.2  |    1.1191 |         233836 |
|   5 |     0.5142 |   1278.7  |    1.0235 |         207768 |
|   6 |     0.4709 |   1261.74 |    1.0223 |         185519 |
|   7 |     0.3747 |   1282.2  |    1.0762 |         165015 |
|   8 |     0.3348 |   1338.49 |    1.0663 |         145712 |

## GMM Metrics (averaged across T=10)

|   k |   mean_sil |   mean_bic |   mean_aic |
|----:|-----------:|-----------:|-----------:|
|   3 |     0.4754 |    -251935 |    -254594 |
|   4 |     0.4406 |    -286736 |    -290283 |
|   5 |     0.3327 |    -348511 |    -352947 |
|   6 |     0.3202 |    -378252 |    -383577 |
|   7 |     0.2895 |    -398279 |    -404492 |
|   8 |     0.2812 |    -407866 |    -414967 |

## Cluster Profiles

|   cluster |   subsample |      n |   mean_logins_90d |   mean_log_logins_pw |   mean_activity_breadth |   mean_funnel_stage |   mean_log_sources_pw |   mean_sources_90d |   mean_log_tree_edits_pw |   mean_tree_edits_90d |   mean_names_90d |   mean_log_names_pw |   mean_has_sources |   mean_has_memories |   mean_days_to_first_login |   mean_activation_speed |   mean_user_age |   pct_persistent |   mean_age |   mean_persistence_c |
|----------:|------------:|-------:|------------------:|---------------------:|------------------------:|--------------------:|----------------------:|-------------------:|-------------------------:|----------------------:|-----------------:|--------------------:|-------------------:|--------------------:|---------------------------:|------------------------:|----------------:|-----------------:|-----------:|---------------------:|
|         0 |         5.5 | 2790.4 |            3.4185 |               0.1844 |                  3.5019 |              2.4194 |                0.2564 |            12.7674 |                   0.796  |               36.4846 |            7.943 |              0.3363 |             0.3573 |              0.0927 |                     1.2077 |                  0.7998 |         35.0308 |            63.51 |      35.03 |               0.242  |
|         1 |         5.5 | 1440.9 |           15.6837 |               0.6062 |                  4.2666 |              2.9001 |                1.8319 |          1048.64   |                   2.5526 |             1107.23   |          272.967 |              1.6007 |             0.633  |              0.3534 |                     0.7592 |                  0.7827 |         40.9702 |            81.86 |      40.97 |               0.3836 |
|         2 |         5.5 |  847.7 |           15.7135 |               0.6134 |                  4.4275 |              3.112  |                2.0133 |           863.266  |                   2.4621 |              978.03   |          128.427 |              1.405  |             0.8449 |              0.2925 |                     3.0614 |                  0.773  |         36.4598 |            93.88 |      36.47 |               0.3936 |

## QC Log

| Step | Metric | Value | Note |
|------|--------|-------|------|
| 6.5 | best_k_kmeans | 3 | silhouette=0.5157 |
| 6.5 | best_k_gmm | 3 | silhouette=0.4754 |
| 6.5 | selected_k | 3 |  |
| 6.9 | chi2 | 1052.72 |  |
| 6.9 | chi2_p_value | 2.55e-229 |  |
| 6.9 | cramers_v | 0.4553 |  |
| 6.7 | mean_cross_subsample_ari | 0.0273 |  |
| 6.7 | ari_std | 0.0095 |  |
| 6.7 | ari_min | 0.0073 |  |
| 6.7 | ari_max | 0.0482 |  |
| 6.6 | cluster_0_mean_jaccard | 0.1577 | unstable |
| 6.6 | cluster_1_mean_jaccard | 0.7145 | borderline |
| 6.6 | cluster_2_mean_jaccard | 0.0017 | unstable |
| 6.10 | persona_cluster_0 | Minimal Engagers |  |
| 6.10 | persona_cluster_1 | Mid-Range (Cluster 1) |  |
| 6.10 | persona_cluster_2 | Power Contributors |  |