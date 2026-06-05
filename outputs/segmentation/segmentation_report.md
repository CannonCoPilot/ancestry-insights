# Segmentation Analysis: Contextual-Development Tiers × Persistence Gradient

**Date**: 2026-03-26 (revised: axis interpretation corrected)
**Data**: Contributors Only (2+ logins), n=4,948
**Method**: K-Means on PC2 (Contextual/Development axis in contributors-only PCA), k=5 tiers

---

## Key Finding

The PCA projection reveals 5 distinct contextual-development tiers arranged vertically.
Within each tier, Persistence increases from left to right along the Volume axis (PC1).
**Critically, the persistence gradient (slope) varies by tier** — users in different
development contexts show different Volume→Persistence relationships.

## Tier Definitions

Tiers are defined by K-Means clustering on PC2. **Note**: In the contributors-only PCA,
PC2 loads on contextual/development features (GEPI: 0.46, GDP: 0.46, HDI: 0.36),
NOT on velocity features (which shifted to PC3 after 1-login users were removed).
See `outputs/exploratory_b/exploratory_b_assessment.md` for the axis swap analysis.

## Tier Profiles

| Tier   |    n |   PC2_mean |   Persist_mean |   Persist_min |   Persist_max |   Persist_range |   Gradient_slope |   Gradient_R2 |   Gradient_p |   Mean_logins_90d |   Mean_activity_breadth |   Mean_activation_speed |   Mean_days_to_first_tree |   Mean_age |   Pct_persistent |
|:-------|-----:|-----------:|---------------:|--------------:|--------------:|----------------:|-----------------:|--------------:|-------------:|------------------:|------------------------:|------------------------:|--------------------------:|-----------:|-----------------:|
| T1     |  201 |      -4.05 |         0.4026 |        0.155  |        0.6667 |          0.5117 |           0.0117 |        0.2866 |    2.65e-16  |             19.66 |                    3.48 |                  0.8323 |                       0.2 |       33   |             81.1 |
| T2     |  810 |      -2.22 |         0.2809 |        0.1536 |        0.8297 |          0.676  |           0.0318 |        0.3609 |    1.29e-80  |              5.53 |                    3.26 |                  0.8048 |                       0.7 |       33.3 |             54.8 |
| T3     | 1303 |      -1.21 |         0.2249 |        0.1534 |        0.7056 |          0.5521 |           0.038  |        0.4793 |    1.39e-186 |              2.81 |                    3.31 |                  0.7747 |                       1.9 |       35.3 |             37.5 |
| T4     |  728 |       0.43 |         0.2789 |        0.1535 |        0.8077 |          0.6542 |           0.0382 |        0.4098 |    3.51e-85  |              5.38 |                    3.37 |                  0.7814 |                       8.4 |       37.1 |             53   |
| T5     | 1906 |       2.03 |         0.2411 |        0.1535 |        0.8871 |          0.7336 |           0.031  |        0.3119 |    9.48e-157 |              2.41 |                    3.47 |                  0.7179 |                       7.1 |       39.1 |             52   |

## Interaction Analysis

- Model without interaction (persistence ~ PC1 + tier): R² = 0.3710
- Model with interaction (persistence ~ PC1 + tier + PC1×tier): R² = 0.3943
- **Interaction R² gain: 0.0233**
- F-statistic: 190.10, p = 0.00e+00
- Interaction coefficient: 0.004890

The interaction is statistically significant (p < 0.001), meaning the effect of Volume on Persistence
does vary significantly across contextual-development tiers.

## Figures

| Figure | Description |
|--------|-------------|
| fig_pca_tiers.png | PCA scatter colored by 5 contextual-development tiers |
| fig_pca_persistence_with_tiers.png | PCA scatter colored by persistence with tier boundaries |
| fig_gradient_by_tier.png | Persistence vs PC1 with regression lines per tier |
| fig_gradient_slopes.png | Bar chart comparing gradient slopes across tiers |
| fig_persistence_range.png | Persistence range and mean per tier |
| fig_tier_heatmap.png | Tier profile heatmap (all features) |
| fig_persistence_boxplots.png | Box plots of persistence distribution per tier |
| fig_3d_tiers_persistence.html/png | Interactive 3D: Volume × Context × Persistence by tier |