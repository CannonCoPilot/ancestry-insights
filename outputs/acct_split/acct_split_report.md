# Account Type Split Analysis: Member vs Public

**Date**: 2026-03-27T13:11:58.581377
**Design**: Member T=5 × 2,500 | Public T=5 × 5,000
**Purpose**: Confirm H1 findings hold independently within each account type; test whether LDS membership confounds the tier gradient pattern.

---

## Classification Results (RF, T=5)

|                       |   mean_auc |   std_auc |   mean_f1 |
|:----------------------|-----------:|----------:|----------:|
| ('Member', 'B4_H1')   |     0.9944 |    0.0028 |    0.9803 |
| ('Member', 'B5_H0')   |     0.5461 |    0.0247 |    0.5188 |
| ('Member', 'B6_Full') |     0.9949 |    0.0037 |    0.9797 |
| ('Public', 'B4_H1')   |     0.9969 |    0.0011 |    0.9891 |
| ('Public', 'B5_H0')   |     0.5262 |    0.0119 |    0.5142 |
| ('Public', 'B6_Full') |     0.9969 |    0.0011 |    0.9882 |

## Nonlinearity by Tier

| group   | tier   |    n |   r2_lin |   r2_quad |   r2_log |   delta_r2 | best_model   |   quad_coeff |   lin_slope |
|:--------|:-------|-----:|---------:|----------:|---------:|-----------:|:-------------|-------------:|------------:|
| Member  | T1     |   83 |   0.2219 |    0.3751 |   0.4196 |     0.1978 | Log          |    -0.000795 |      0.0088 |
| Member  | T2     |  449 |   0.3589 |    0.3983 |   0.3901 |     0.0394 | Quad         |    -0.003986 |      0.0557 |
| Member  | T3     |  732 |   0.1663 |    0.2678 |   0.2769 |     0.1106 | Log          |    -0.00191  |      0.0288 |
| Member  | T4     |  210 |   0.2157 |    0.2635 |   0.2726 |     0.0568 | Log          |    -0.002942 |      0.028  |
| Member  | T5     | 1026 |   0.2694 |    0.3422 |   0.3344 |     0.0728 | Quad         |    -0.0054   |      0.0421 |
| Public  | T1     | 2429 |   0.2533 |    0.2846 |   0.2804 |     0.0313 | Quad         |    -0.003339 |      0.0403 |
| Public  | T2     | 2318 |   0.3777 |    0.4118 |   0.3939 |     0.0341 | Quad         |    -0.001106 |      0.0281 |
| Public  | T3     |  145 |   0.1739 |    0.332  |   0.2975 |     0.1581 | Quad         |    -0.000973 |      0.0096 |
| Public  | T4     |   81 |   0.3101 |    0.3302 |   0.2158 |     0.0201 | Quad         |     0.001702 |      0.03   |

## QC Log

| Step | Metric | Value | Note |
|------|--------|-------|------|
| Member | median_persist_c | 0.2231 |  |
| Member | n_per_subsample | 2500 |  |
| Member | class_balance | 0:879, 1:871 |  |
| Public | median_persist_c | 0.2079 |  |
| Public | n_per_subsample | 5000 |  |
| Public | class_balance | 0:1744, 1:1756 |  |
| Member | B4_auc | 0.9944 |  |
| Member | B5_auc | 0.5461 |  |
| Member | B6_auc | 0.9949 |  |
| Member | delta_H1 | 0.4488 |  |
| Member | delta_H0 | 0.0005 |  |
| Public | B4_auc | 0.9969 |  |
| Public | B5_auc | 0.5262 |  |
| Public | B6_auc | 0.9969 |  |
| Public | delta_H1 | 0.4707 |  |
| Public | delta_H0 | 0.0 |  |