"""Clustering models and evaluation utilities."""

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans, MiniBatchKMeans
from sklearn.mixture import GaussianMixture
from sklearn.metrics import silhouette_score, calinski_harabasz_score, davies_bouldin_score
from sklearn.decomposition import PCA
from sklearn.preprocessing import RobustScaler, MinMaxScaler
import streamlit as st

try:
    from hdbscan import HDBSCAN
    HAS_HDBSCAN = True
except ImportError:
    HAS_HDBSCAN = False

try:
    from umap import UMAP
    HAS_UMAP = True
except ImportError:
    HAS_UMAP = False


def scale_features(features: pd.DataFrame, scaler=None) -> tuple[np.ndarray, StandardScaler]:
    """Standardize features. Returns (scaled_array, fitted_scaler)."""
    if scaler is None:
        scaler = StandardScaler()
        X = scaler.fit_transform(features)
    else:
        X = scaler.transform(features)
    return X, scaler


def run_kmeans(X: np.ndarray, k: int, seed: int = 42) -> dict:
    """Run K-Means clustering and return labels + model."""
    model = MiniBatchKMeans(n_clusters=k, random_state=seed, batch_size=2048, n_init=10)
    labels = model.fit_predict(X)
    return {"model": model, "labels": labels, "algorithm": "KMeans"}


def run_hdbscan(X: np.ndarray, min_cluster_size: int = 500, min_samples: int = 50) -> dict:
    """Run HDBSCAN clustering."""
    if not HAS_HDBSCAN:
        raise ImportError("hdbscan not installed")
    model = HDBSCAN(min_cluster_size=min_cluster_size, min_samples=min_samples,
                     core_dist_n_jobs=-1)
    labels = model.fit_predict(X)
    return {"model": model, "labels": labels, "algorithm": "HDBSCAN"}


def run_gmm(X: np.ndarray, k: int, seed: int = 42) -> dict:
    """Run Gaussian Mixture Model clustering and return labels + model + info criteria."""
    model = GaussianMixture(n_components=k, random_state=seed, n_init=5,
                            covariance_type="full", max_iter=200)
    labels = model.fit_predict(X)
    return {
        "model": model,
        "labels": labels,
        "algorithm": "GMM",
        "bic": round(model.bic(X), 2),
        "aic": round(model.aic(X), 2),
        "converged": model.converged_,
    }


def scale_features_multi(features: pd.DataFrame, method: str = "standard") -> tuple[np.ndarray, object]:
    """Scale features using specified method. Returns (scaled_array, fitted_scaler)."""
    if method == "robust":
        scaler = RobustScaler()
    elif method == "minmax":
        scaler = MinMaxScaler()
    else:
        scaler = StandardScaler()
    X = scaler.fit_transform(features)
    return X, scaler


def evaluate_clusters(X: np.ndarray, labels: np.ndarray, sample_size: int = 20_000) -> dict:
    """Compute cluster quality metrics. Samples for silhouette to keep it fast."""
    n_clusters = len(set(labels) - {-1})
    if n_clusters < 2:
        return {"n_clusters": n_clusters, "silhouette": None,
                "calinski_harabasz": None, "davies_bouldin": None}

    # Remove noise points for evaluation
    mask = labels >= 0
    X_clean = X[mask]
    labels_clean = labels[mask]

    # Subsample for silhouette (expensive)
    if len(X_clean) > sample_size:
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X_clean), sample_size, replace=False)
        sil = silhouette_score(X_clean[idx], labels_clean[idx])
    else:
        sil = silhouette_score(X_clean, labels_clean)

    ch = calinski_harabasz_score(X_clean, labels_clean)
    db = davies_bouldin_score(X_clean, labels_clean)

    return {
        "n_clusters": n_clusters,
        "n_noise": int((labels == -1).sum()),
        "silhouette": round(sil, 4),
        "calinski_harabasz": round(ch, 2),
        "davies_bouldin": round(db, 4),
    }


def elbow_analysis(X: np.ndarray, k_range: range = range(2, 11),
                   sample_size: int = 50_000, seed: int = 42) -> pd.DataFrame:
    """Run K-Means for a range of k values, returning inertia and silhouette scores."""
    if len(X) > sample_size:
        rng = np.random.RandomState(seed)
        idx = rng.choice(len(X), sample_size, replace=False)
        X_sub = X[idx]
    else:
        X_sub = X

    records = []
    for k in k_range:
        model = MiniBatchKMeans(n_clusters=k, random_state=seed, batch_size=2048, n_init=10)
        labels = model.fit_predict(X_sub)
        sil = silhouette_score(X_sub[:20_000], labels[:20_000]) if len(X_sub) > 20_000 else silhouette_score(X_sub, labels)
        records.append({
            "k": k,
            "inertia": round(model.inertia_, 2),
            "silhouette": round(sil, 4),
        })
    return pd.DataFrame(records)


def compute_pca(X: np.ndarray, n_components: int = 2) -> tuple[np.ndarray, PCA]:
    """PCA reduction for visualization."""
    pca = PCA(n_components=n_components, random_state=42)
    X_pca = pca.fit_transform(X)
    return X_pca, pca


def compute_umap(X: np.ndarray, n_components: int = 2,
                 n_neighbors: int = 30, min_dist: float = 0.3,
                 sample_size: int = 50_000) -> np.ndarray:
    """UMAP reduction for visualization. Samples if too large."""
    if not HAS_UMAP:
        raise ImportError("umap-learn not installed")

    if len(X) > sample_size:
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X), sample_size, replace=False)
        X_sub = X[idx]
    else:
        X_sub = X
        idx = np.arange(len(X))

    reducer = UMAP(n_components=n_components, n_neighbors=n_neighbors,
                   min_dist=min_dist, random_state=42)
    X_reduced = reducer.fit_transform(X_sub)
    return X_reduced, idx


def profile_clusters(df: pd.DataFrame, labels: np.ndarray,
                     feature_cols: list[str]) -> pd.DataFrame:
    """Generate a profile table: mean of each feature per cluster."""
    df_work = df.copy()
    df_work["cluster"] = labels

    # Remove noise
    df_work = df_work[df_work["cluster"] >= 0]

    profile = df_work.groupby("cluster")[feature_cols].agg(["mean", "median", "count"])

    # Flatten multi-level columns
    profile.columns = [f"{col}_{stat}" for col, stat in profile.columns]

    # Add cluster size
    sizes = df_work["cluster"].value_counts().sort_index()
    result = pd.DataFrame({"cluster": sizes.index, "size": sizes.values,
                            "pct": (sizes.values / sizes.values.sum() * 100).round(1)})
    return result, df_work.groupby("cluster")[feature_cols].mean().round(4)
