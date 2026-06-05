"""Feature engineering for user segmentation."""

import pandas as pd
import numpy as np


def compute_tenure_days(df: pd.DataFrame, reference_date: str = "2026-03-24") -> pd.Series:
    """Days since account creation."""
    ref = pd.Timestamp(reference_date)
    return (ref - df["ACCOUNT_CREATE_DATE"]).dt.days.clip(lower=1)


def add_tenure_normalized_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add per-week and per-month rate features normalized by account tenure."""
    out = df.copy()
    tenure = compute_tenure_days(df).rename("TENURE_DAYS")
    out["TENURE_DAYS"] = tenure
    weeks = (tenure / 7).clip(lower=1)

    rate_cols = {
        "LOGINS_PER_WEEK": "DAYS_LOGGING_IN",
        "TREE_EDITS_PER_WEEK": "TREE_EDITS",
        "SOURCES_PER_WEEK": "SOURCES_ADDED",
        "MEMORIES_PER_WEEK": "MEMORIES_ADDED",
        "NAMES_PER_WEEK": "TOTAL_NAMES_ADDED",
        "GET_INVOLVED_PER_WEEK": "GET_INVOLVED_ITEMS_REVIEWED",
        "RECORD_EDITS_PER_WEEK": "RECORD_EDITS",
    }
    for new_col, src_col in rate_cols.items():
        if src_col in out.columns:
            out[new_col] = (out[src_col].fillna(0) / weeks).round(4)
    return out


def add_activity_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Binary flags for each activity type."""
    out = df.copy()
    flag_map = {
        "HAS_LOGGED_IN": "DAYS_LOGGING_IN",
        "HAS_TREE_EDITS": "TREE_EDITS",
        "HAS_SOURCES": "SOURCES_ADDED",
        "HAS_MEMORIES": "MEMORIES_ADDED",
        "HAS_GET_INVOLVED": "GET_INVOLVED_ITEMS_REVIEWED",
        "HAS_RECORD_EDITS": "RECORD_EDITS",
        "HAS_NAMES": "TOTAL_NAMES_ADDED",
    }
    for flag, src in flag_map.items():
        if src in out.columns:
            out[flag] = (out[src].fillna(0) > 0).astype(int)

    activity_flags = [f for f in flag_map if f != "HAS_LOGGED_IN" and f in out.columns]
    out["N_ACTIVITY_TYPES"] = out[activity_flags].sum(axis=1)
    return out


def add_engagement_depth(df: pd.DataFrame) -> pd.DataFrame:
    """Derived engagement depth metrics."""
    out = df.copy()

    # Days from account creation to first login
    if "EARLIEST_LOGIN_DATE" in out.columns and "ACCOUNT_CREATE_DATE" in out.columns:
        delta = (out["EARLIEST_LOGIN_DATE"] - out["ACCOUNT_CREATE_DATE"]).dt.days
        out["DAYS_TO_FIRST_LOGIN"] = delta.clip(lower=0)

    # Days from account creation to first tree edit
    if "EARLIEST_TREE_EDIT_DATE" in out.columns and "ACCOUNT_CREATE_DATE" in out.columns:
        delta = (out["EARLIEST_TREE_EDIT_DATE"] - out["ACCOUNT_CREATE_DATE"]).dt.days
        out["DAYS_TO_FIRST_TREE_EDIT"] = delta.clip(lower=0)

    # Ratio of deceased to total names (genealogy depth indicator)
    if "DECEASED_NAMES_ADDED" in out.columns and "TOTAL_NAMES_ADDED" in out.columns:
        total = out["TOTAL_NAMES_ADDED"].fillna(0)
        out["PCT_DECEASED_NAMES"] = np.where(
            total > 0,
            out["DECEASED_NAMES_ADDED"].fillna(0) / total,
            0,
        )

    # Novel names ratio
    if "NOVEL_NAMES_ADDED" in out.columns and "TOTAL_NAMES_ADDED" in out.columns:
        total = out["TOTAL_NAMES_ADDED"].fillna(0)
        out["PCT_NOVEL_NAMES"] = np.where(
            total > 0,
            out["NOVEL_NAMES_ADDED"].fillna(0) / total,
            0,
        )

    # Login consistency: days logging in / tenure days
    if "TENURE_DAYS" in out.columns:
        out["LOGIN_CONSISTENCY"] = (
            out["DAYS_LOGGING_IN"].fillna(0) / out["TENURE_DAYS"].clip(lower=1)
        ).clip(upper=1)

    return out


def add_age_group(df: pd.DataFrame) -> pd.DataFrame:
    """Bin ages into decade groups (8-19 first bin; age=0 treated as missing; 80+ collapsed)."""
    out = df.copy()
    out.loc[out["USER_CURRENT_AGE"] == 0, "USER_CURRENT_AGE"] = np.nan
    bins = [7, 19, 29, 39, 49, 59, 69, 79, 110]
    labels = ["8-19", "20-29", "30-39", "40-49", "50-59", "60-69", "70-79", "80+"]
    out["AGE_GROUP"] = pd.cut(
        out["USER_CURRENT_AGE"], bins=bins, labels=labels, include_lowest=True
    )
    return out


def build_clustering_features(df: pd.DataFrame) -> pd.DataFrame:
    """Full feature engineering pipeline for clustering. Returns a clean numeric DataFrame."""
    out = df.copy()
    out = add_tenure_normalized_features(out)
    out = add_activity_flags(out)
    out = add_engagement_depth(out)
    out = add_age_group(out)

    # Select features for clustering
    feature_cols = [
        # Tenure-normalized rates
        "LOGINS_PER_WEEK", "TREE_EDITS_PER_WEEK", "SOURCES_PER_WEEK",
        "MEMORIES_PER_WEEK", "NAMES_PER_WEEK", "GET_INVOLVED_PER_WEEK",
        "RECORD_EDITS_PER_WEEK",
        # Activity breadth
        "N_ACTIVITY_TYPES",
        # Engagement depth
        "LOGIN_CONSISTENCY",
        "PCT_DECEASED_NAMES", "PCT_NOVEL_NAMES",
        # Demographics
        "USER_CURRENT_AGE",
        # Raw counts (log-transformed below)
        "DAYS_LOGGING_IN", "TREE_EDITS", "SOURCES_ADDED",
        "TOTAL_NAMES_ADDED",
    ]
    feature_cols = [c for c in feature_cols if c in out.columns]
    features = out[feature_cols].copy()

    # Fill NaN with 0 (null activity = no activity)
    features = features.fillna(0)

    # Log-transform highly skewed raw counts
    log_cols = ["DAYS_LOGGING_IN", "TREE_EDITS", "SOURCES_ADDED", "TOTAL_NAMES_ADDED"]
    for col in log_cols:
        if col in features.columns:
            features[f"{col}_LOG"] = np.log1p(features[col])

    return features


def get_feature_descriptions() -> dict[str, str]:
    """Human-readable descriptions of engineered features."""
    return {
        "LOGINS_PER_WEEK": "Average login days per week since account creation",
        "TREE_EDITS_PER_WEEK": "Average tree edits per week",
        "SOURCES_PER_WEEK": "Average sources added per week",
        "MEMORIES_PER_WEEK": "Average memories added per week",
        "NAMES_PER_WEEK": "Average names added per week",
        "GET_INVOLVED_PER_WEEK": "Average Get Involved items reviewed per week",
        "RECORD_EDITS_PER_WEEK": "Average record edits per week",
        "N_ACTIVITY_TYPES": "Number of distinct activity types (0-6)",
        "LOGIN_CONSISTENCY": "Fraction of tenure days with a login (0-1)",
        "PCT_DECEASED_NAMES": "Fraction of added names that are deceased",
        "PCT_NOVEL_NAMES": "Fraction of added names that are novel/new",
        "USER_CURRENT_AGE": "User's current age in years",
        "DAYS_LOGGING_IN": "Total distinct days with a login",
        "TREE_EDITS": "Total family tree edits",
        "SOURCES_ADDED": "Total sources attached",
        "TOTAL_NAMES_ADDED": "Total names added to family tree",
        "DAYS_LOGGING_IN_LOG": "Log-transformed login days",
        "TREE_EDITS_LOG": "Log-transformed tree edits",
        "SOURCES_ADDED_LOG": "Log-transformed sources added",
        "TOTAL_NAMES_ADDED_LOG": "Log-transformed names added",
        "TENURE_DAYS": "Days since account creation",
        "HAS_LOGGED_IN": "Ever logged in (0/1)",
        "HAS_TREE_EDITS": "Ever edited family tree (0/1)",
        "HAS_SOURCES": "Ever added a source (0/1)",
        "HAS_MEMORIES": "Ever added a memory (0/1)",
        "HAS_GET_INVOLVED": "Ever used Get Involved (0/1)",
        "HAS_RECORD_EDITS": "Ever edited a record (0/1)",
        "HAS_NAMES": "Ever added a name (0/1)",
        "AGE_GROUP": "Age bracket",
        "DAYS_TO_FIRST_LOGIN": "Days from account creation to first login",
        "DAYS_TO_FIRST_TREE_EDIT": "Days from account creation to first tree edit",
    }
