# Tier Refinement Assessment: Rigorous Development-Tier Segmentation

**Date**: 2026-03-27
**Purpose**: Establish development tiers with geometrically correct segmentation boundaries and rigorously determined k.
**Scripts**: `src/final_analysis.py` (original tiers), ad-hoc exploration (this analysis)

---

## Background & Motivation

The original tier segmentation (Phases 5b/6b, segmentation analysis) defined 5 tiers via K-Means on PC2. Two issues emerged during review:

1. **Geometric correction**: The initial perpendicular-to-behavioral approach was wrong — the user identified that tier boundaries should be perpendicular to the *enrichment/contextual* eigenvectors (GDP, HDI, GEPI, religious diversity), not the behavioral ones. This ensures tiers partition along the development gradient with boundaries cutting across it.

2. **Optimal k**: The number of tiers (k=5) was assumed, not derived. A rigorous determination was needed.

---

## Methodology

### Step 1: Enrichment Axis Direction

Computed the magnitude-weighted mean direction of all enrichment feature vectors in PC1-PC2 space:

| Feature | PC1 Loading | PC2 Loading | Magnitude |
|---------|-----------|-----------|-----------|
| gdp_per_capita_ppp | +0.081 | +0.464 | 0.471 |
| gepi | +0.083 | +0.461 | 0.468 |
| religious_diversity_index | +0.072 | +0.420 | 0.426 |
| hdi | +0.066 | +0.412 | 0.417 |
| pct_christian | -0.037 | -0.293 | 0.295 |
| social_hostilities_index | -0.043 | -0.214 | 0.218 |
| lds_members_per_capita | +0.005 | -0.087 | 0.087 |
| govt_restrictions_index | -0.016 | +0.001 | 0.016 |

**Mean enrichment vector**: (0.176, 0.984), **angle = 79.9° from PC1**.

This is nearly vertical — the enrichment gradient runs almost straight up/down in the PCA projection. The previous PC2-only segmentation was only ~10° off from optimal, not the 12.4° suggested by the behavioral-axis approach.

### Step 2: Projection and Boundary Direction

- **Development score**: each user projected onto the enrichment axis direction → a single continuous "development score"
- **Tier boundaries**: lines perpendicular to the enrichment axis (at 79.9°), which cut across the development gradient
- **Behavioral residual**: the component perpendicular to enrichment, representing engagement variation *within* each tier

### Step 3: Optimal k Determination

Tested k=2 through k=8 on the 1D development score using three metrics:

| k | Silhouette | BIC | Davies-Bouldin |
|---|-----------|-----|---------------|
| **2** | **0.748** | 7,168 | **0.320** |
| 3 | 0.674 | **6,874** | 0.494 |
| 4 | 0.682 | 6,950 | 0.455 |
| 5 | 0.636 | 6,941 | 0.507 |
| 6 | 0.640 | 6,959 | 0.469 |
| 7 | 0.547 | 6,950 | 0.520 |
| 8 | 0.568 | 6,881 | 0.481 |

**Consensus: k=2** (silhouette + DB both favor k=2; BIC favors k=3).

### Step 4: Two-Tier Characterization

| Tier | n | Dev Score | GDP/cap | HDI | % Christian | Relig. Diversity | % LatAm | % NAm | Mean Age | % Member |
|------|---|---------|---------|-----|------------|-----------------|---------|-------|---------|---------|
| T1 (Developing) | 990 (48%) | -1.88 | $24K | 0.79 | 82% | 3.1 | 79% | 0.1% | 34.3 | 10.1% |
| T2 (Developed) | 1,055 (52%) | +1.76 | $77K | 0.93 | 62% | 5.7 | 4% | 65% | 40.1 | 8.1% |

T1 = predominantly Latin American, lower GDP, higher Christian %, lower religious diversity.
T2 = predominantly North American + European, high GDP, lower Christian %, higher religious diversity.

### Step 5: Nonlinearity with Refined Tiers

| Tier | Lin R² | ΔR² (nonlinear gain) | Best Model | Slope |
|------|--------|---------------------|-----------|-------|
| T1 (Developing) | 0.457 | +0.098 | Quadratic | -0.052 |
| T2 (Developed) | 0.226 | **+0.210** | Quadratic | -0.019 |

The developed tier (T2) shows 2x the nonlinearity of the developing tier — consistent with the saturation/plateau finding from the 5-tier analysis. The developed-context curve saturates more strongly.

---

## Key Findings

### 1. The Enrichment Axis Is Nearly Vertical

At 79.9° from PC1, the enrichment gradient aligns closely with PC2. This means the original PC2-only segmentation was approximately correct geometrically — it was segmenting ~10° off from the true enrichment direction.

### 2. The Data Is Fundamentally Bimodal Along the Development Axis

Silhouette score of 0.748 at k=2 is very high — the development scores form two well-separated groups centered at -1.88 (developing) and +1.76 (developed). The gap between them is where GDP jumps from ~$25K to ~$75K.

### 3. Finer Tiers (k=4-6) Subdivide a Bimodal Distribution

The previous k=5 analysis was subdividing within the two natural modes. This is not statistically "wrong" — it captures real sub-structure (e.g., upper-middle vs high-development within T2) — but the boundaries between sub-tiers are fuzzy compared to the clean T1/T2 boundary.

### 4. The Nonlinearity Gradient Is Preserved at k=2

T2 (developed) has ΔR²=+0.21 (strong plateau); T1 (developing) has ΔR²=+0.10 (moderate). The core finding — that the engagement→persistence curve saturates more in higher-development contexts — holds at the cleanest possible segmentation.

---

## Open Question: k=2 vs k=5?

**The tension**: Statistics favor k=2 (clean bimodal split), but the 5-tier analysis revealed a richer gradient from logarithmic→quadratic→linear that k=2 collapses into two groups.

**Arguments for k=2**:
- Highest silhouette (0.748 vs ~0.64 for k=5)
- Clearest demographic interpretation (developing vs developed)
- Most statistically defensible

**Arguments for k=4-5**:
- Captures the nonlinearity gradient (log→quad→linear transition)
- More actionable for segmented marketing strategies
- Visually discernible in the biplot (multiple bands, not just two)
- BIC at k=3 is close to k=5, and silhouette only drops moderately (0.75→0.64)

**Possible resolution**: Report k=2 as the primary statistically-derived segmentation, with k=4-5 as a secondary exploratory analysis that reveals sub-structure within each tier. The nonlinearity gradient finding can be reported as a continuous relationship (dev_score × engagement interaction) rather than requiring discrete tiers.

---

## Figures

| Figure | Description |
|--------|-------------|
| `fig_k_selection.png` | Silhouette / BIC / DB metrics for k=2-8 |
| `fig_dev_axis_distribution.png` | Histogram of development scores with tier boundaries |
| `fig_enrichment_axis_tiers.png` | Biplot with enrichment axis arrow, perpendicular boundaries, tier-colored points |
| `fig_refined_persistence_gradient.png` | Persistence vs behavioral residual, per tier |
| `k_selection_metrics.csv` | All k-selection metrics |
| `refined_nonlinearity.csv` | Per-tier nonlinearity test results |

---

## Comparison: Three Segmentation Approaches

| Approach | k | Axis | Angle from PC1 | Interaction R² | Silhouette | Status |
|----------|---|------|---------------|---------------|-----------|--------|
| Original (K-Means PC2) | 5 | PC2 (horizontal) | 90° | 0.366 | 0.64 | Superseded |
| Perpendicular to behavioral | 5 | ⊥ behavioral | ~102° | 0.403 | 0.64 | Wrong direction |
| **Perpendicular to enrichment** | **2** | **⊥ enrichment** | **~170°** | — | **0.75** | **Current best** |

The enrichment-perpendicular approach with k=2 is the most statistically rigorous. Whether to report k=2 or a higher k for richer narrative is a presentation choice, not a statistical one.

---

*Tier Refinement Assessment v1.0 — FamilySearch User Persistence Analysis*
*Nathaniel Cannon, March 2026*
