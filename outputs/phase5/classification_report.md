# Phase 5: Classification Results Summary

**Generated**: 2026-03-26T03:49:22.701509
**Subsamples**: T=10

---

## Block Comparison (sorted by Mean AUC)

|                                |   mean_auc |   std_auc |   mean_f1 |   std_f1 |   mean_acc |   std_acc |
|:-------------------------------|-----------:|----------:|----------:|---------:|-----------:|----------:|
| ('B6_Full', 'RF')              |     0.9994 |    0.0008 |    0.9971 |   0.0011 |     0.997  |    0.0012 |
| ('B4_H1_Combined', 'RF')       |     0.999  |    0.001  |    0.9971 |   0.0009 |     0.9971 |    0.0009 |
| ('B4_H1_Combined', 'LogReg')   |     0.9983 |    0.0009 |    0.9721 |   0.0058 |     0.9728 |    0.0055 |
| ('B6_Full', 'LogReg')          |     0.9977 |    0.001  |    0.968  |   0.0077 |     0.9688 |    0.0073 |
| ('B2_Volume', 'RF')            |     0.9858 |    0.0032 |    0.9769 |   0.0036 |     0.9772 |    0.0033 |
| ('B2_Volume', 'LogReg')        |     0.9757 |    0.004  |    0.9488 |   0.0082 |     0.9509 |    0.0075 |
| ('B4_H1_Combined', 'LDA')      |     0.9607 |    0.0041 |    0.813  |   0.0097 |     0.8411 |    0.0075 |
| ('B6_Full', 'LDA')             |     0.9541 |    0.006  |    0.8166 |   0.0082 |     0.8428 |    0.0075 |
| ('B2_Volume', 'LDA')           |     0.9095 |    0.008  |    0.7612 |   0.0091 |     0.8009 |    0.0072 |
| ('B3_Sequencing', 'LogReg')    |     0.6906 |    0.0054 |    0.5519 |   0.0113 |     0.6901 |    0.0051 |
| ('B3_Sequencing', 'RF')        |     0.6906 |    0.0054 |    0.5519 |   0.0113 |     0.6901 |    0.0051 |
| ('B3_Sequencing', 'LDA')       |     0.6901 |    0.0055 |    0.5513 |   0.0113 |     0.6897 |    0.0054 |
| ('B5_H0_Contextual', 'LogReg') |     0.6349 |    0.0132 |    0.5973 |   0.0172 |     0.6014 |    0.0147 |
| ('B5_H0_Contextual', 'LDA')    |     0.6347 |    0.0134 |    0.5972 |   0.0166 |     0.601  |    0.014  |
| ('B5_H0_Contextual', 'RF')     |     0.5908 |    0.0155 |    0.5656 |   0.0189 |     0.5721 |    0.0144 |
| ('B1_Velocity', 'LogReg')      |     0.5718 |    0.0153 |    0.4647 |   0.0202 |     0.5547 |    0.016  |
| ('B1_Velocity', 'RF')          |     0.5708 |    0.0149 |    0.2993 |   0.1082 |     0.5549 |    0.0076 |
| ('B1_Velocity', 'LDA')         |     0.5705 |    0.0162 |    0.4636 |   0.0204 |     0.5541 |    0.016  |

## QC Log

| Step | Metric | Value | Note |
|------|--------|-------|------|
| 5.A.2 | tier_d_median_persistence_c | 0.1633 |  |
| 5.A.2 | class_balance_train | 0:1770, 1:1785 |  |
| 5.A.2 | class_balance_test | 0:763, 1:761 |  |
| 5.D.5 | LDA_B4_mean_auc | 0.9607 |  |
| 5.D.5 | LDA_B5_mean_auc | 0.6347 |  |
| 5.D.5 | LDA_B6_mean_auc | 0.9541 |  |
| 5.D.5 | LDA_delta_H1 | 0.3194 | Incremental value of engagement features |
| 5.D.5 | LDA_delta_H0 | -0.0066 | Incremental value of contextual features |
| 5.D.5 | LogReg_B4_mean_auc | 0.9983 |  |
| 5.D.5 | LogReg_B5_mean_auc | 0.6349 |  |
| 5.D.5 | LogReg_B6_mean_auc | 0.9977 |  |
| 5.D.5 | LogReg_delta_H1 | 0.3628 | Incremental value of engagement features |
| 5.D.5 | LogReg_delta_H0 | -0.0007 | Incremental value of contextual features |
| 5.D.5 | RF_B4_mean_auc | 0.999 |  |
| 5.D.5 | RF_B5_mean_auc | 0.5908 |  |
| 5.D.5 | RF_B6_mean_auc | 0.9994 |  |
| 5.D.5 | RF_delta_H1 | 0.4085 | Incremental value of engagement features |
| 5.D.5 | RF_delta_H0 | 0.0004 | Incremental value of contextual features |
| 5.D.4 | rf_importance:logins_90d | 0.347 | Volume |
| 5.D.4 | rf_importance:log_logins_pw | 0.3122 | Volume |
| 5.D.4 | rf_importance:activity_breadth | 0.0557 | Sequencing |
| 5.D.4 | rf_importance:funnel_stage | 0.0356 | Sequencing |
| 5.D.4 | rf_importance:log_sources_pw | 0.0313 | Volume |
| 5.D.4 | rf_importance:has_sources | 0.0307 | Sequencing |
| 5.D.4 | rf_importance:sources_90d | 0.0303 | Volume |
| 5.D.4 | rf_importance:log_tree_edits_pw | 0.0205 | Volume |
| 5.D.4 | rf_importance:tree_edits_90d | 0.0204 | Volume |
| 5.D.4 | rf_importance:names_90d | 0.0201 | Volume |
| 5.D.4 | rf_importance:log_names_pw | 0.0186 | Volume |