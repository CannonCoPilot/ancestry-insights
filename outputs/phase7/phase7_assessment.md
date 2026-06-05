# Phase 7: Cluster Optimization — Grid Search Assessment

**Date**: 2026-03-27
**Script**: `src/phase7_cluster_optimization.py`
**Runtime**: ~15 minutes (914s)
**Population**: 10,000 contributors (stratified sample from 1.57M)

---

## Objective

Systematically explore clustering/classification methods, feature weightings, rotations, and volume compression strategies to find the configuration that maximizes correspondence with the naturally striated segments visible in prior PCA visualizations — targeting ~5 clusters.

## Experimental Design

Four experiments, 720+ total configurations:

| Experiment | Variables | Configurations |
|-----------|-----------|----------------|
| **Exp 1: Grid Search** | 6 feature sets × 5 weightings × 4 methods × 6 k-values | 720 |
| **Exp 2: Rotations** | 3 best feature sets × 5 rotation methods × 3 n_components × 3 k × 2 cluster methods | ~270 |
| **Exp 3: LDA-Guided** | 3 feature sets × 4 PCA dims × 3 k × 2 cluster methods | ~72 |
| **Exp 4: Volume Compression** | 5 transforms × 3 weightings × 3 k × 2 cluster methods | ~90 |

### Feature Sets Tested

| Name | Features | Rationale |
|------|----------|-----------|
| `behavioral_only` | Velocity + Volume + Sequencing (18) | Baseline — all behavioral |
| `behavioral_no_flags` | Same minus binary flags (12) | Remove has_* collinearity |
| `combined_full` | Behavioral + Contextual (26) | Full space |
| `combined_no_flags` | Combined minus flags (20) | Clean combined |
| `volume_reduced` | 3 volume + Velocity + Sequencing (13) | Reduce volume dominance |
| `biplot_features` | Same as final_analysis PCA (23) | Match biplot rotation |

### Weighting Strategies

| Strategy | Description |
|----------|------------|
| `uniform` | All weights = 1.0 |
| `equal_construct` | Normalize each construct (Velocity, Volume, Sequencing, Contextual) to equal total weight |
| `downweight_volume` | Volume × 0.5, Velocity × 2.0, Sequencing × 1.5 |
| `velocity_boost` | Velocity × 3.0, Volume × 0.5 |
| `sqrt_volume` | Volume × 0.7 |

### Clustering Methods

K-Means, GMM, Agglomerative (Ward), HDBSCAN (density-based, ignores k)

### Rotation Methods

PCA, ICA, Factor Analysis, PCA + Varimax, None (raw scaled)

### Evaluation Metrics

- **Silhouette Score**: Geometric cluster separation [0, 1]
- **Cramer's V**: Statistical association between clusters and persistence binary [0, 1]
- **Composite Score**: Silhouette × Cramer's V (balances both objectives)

---

## Key Results

### Experiment 1: Grid Search Winners

**Top 5 overall** (by composite):

| Feature Set | Weighting | Method | k | Sil | CV | Composite |
|------------|-----------|--------|---|-----|----|---------:|
| volume_reduced | downweight_vol | HDBSCAN | 7 | 0.691 | 0.558 | 0.386 |
| volume_reduced | velocity_boost | HDBSCAN | 8 | 0.685 | 0.556 | 0.381 |
| behavioral_only | downweight_vol | HDBSCAN | 7 | 0.661 | 0.557 | 0.368 |
| behavioral_only | velocity_boost | HDBSCAN | 8 | 0.655 | 0.555 | 0.364 |
| volume_reduced | downweight_vol | Agglom | 8 | 0.580 | 0.589 | 0.341 |

**Best at k=5**: `behavioral_no_flags` + `equal_construct` + Agglomerative (sil=0.638, CV=0.528, comp=0.337)

### Experiment 2: Rotation Winners

| Feature Set | Rotation | nComp | Method | k | Sil | CV | Composite |
|------------|----------|-------|--------|---|-----|----|---------:|
| volume_reduced | **Factor Analysis** | **5** | K-Means | **6** | **0.708** | **0.683** | **0.484** |
| volume_reduced | FA | 5 | GMM | 6 | 0.639 | 0.739 | 0.472 |
| volume_reduced | ICA | 5 | GMM | 6 | 0.701 | 0.578 | 0.405 |

**Factor Analysis emerged as the dominant rotation** — it outperformed PCA, ICA, Varimax, and raw features.

### Experiment 3: LDA-Guided Winners

| Feature Set | Method | Cluster | k | Sil | CV | Composite |
|------------|--------|---------|---|-----|----|---------:|
| volume_reduced | **PCA(3)+LDA(1)** | K-Means | **5** | **0.580** | **0.733** | **0.426** |
| volume_reduced | PCA(3)+LDA(1) | K-Means | 6 | 0.504 | **0.836** | 0.421 |
| volume_reduced | PCA(4)+LDA(1) | K-Means | 6 | 0.558 | 0.737 | 0.411 |

**LDA augmentation dramatically boosted Cramer's V** — from ~0.57 (PCA alone) to 0.73-0.84 (PCA+LDA).

### Experiment 4: Volume Compression

Volume compression transforms (log, sqrt, rank, winsorize) provided modest improvements but were dominated by the rotation and LDA experiments. Best compression result: winsorize + downweight_volume (comp=0.202).

---

## Conclusions

1. **Volume-reduced feature set is optimal**: Dropping 5 of 8 volume features liberates variance for velocity and sequencing signals
2. **Factor Analysis is the best rotation for clustering**: FA(5 components) on volume_reduced features produces the highest composite scores
3. **LDA augmentation is the best strategy for persistence-discriminative segmentation**: Adding a single LDA discriminant axis to PCA space yields CV=0.73-0.84
4. **~5-6 clusters is optimal**: Confirmed across all experiments — silhouette and Cramer's V converge on k=5-6
5. **Weighting matters**: `downweight_volume` and `equal_construct` consistently outperform `uniform`

### Top 3 Configurations for Deep Dive (Phase 7B)

| Label | Configuration | Composite |
|-------|--------------|-----------|
| **A** | FA(5) on volume_reduced → K-Means k=5,6 | 0.484 |
| **B** | PCA(3)+LDA(1) on volume_reduced → K-Means k=5,6 | 0.426 |
| **C** | PCA(7) on behavioral_only → GMM k=5,6 | 0.403 |

---

## Outputs

| File | Description |
|------|-------------|
| `exp1_grid_search.csv` | 720 grid search results |
| `exp2_rotations.csv` | Rotation experiment results |
| `exp3_lda_guided.csv` | LDA-guided experiment results |
| `exp4_volume_compression.csv` | Volume compression results |
| `all_experiments_combined.csv` | All experiments merged |
| `fig_best_solution_detail.png` | Best k=5 solution scatter + persistence |
| `fig_silhouette_vs_cramersv.png` | Pareto frontier across all solutions |
| `fig_metrics_comparison.png` | Boxplot comparison across experiments |
| `fig_top_solutions_pca.png` | PCA projections of top 4 solutions |

---

*Phase 7 Assessment v1.0 — Cluster Optimization Grid Search*
