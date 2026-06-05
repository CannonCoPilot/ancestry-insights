"""Data loading, sampling, and caching utilities."""

import os
import hashlib
import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "users.csv"
SAMPLE_PATH = PROJECT_ROOT / "data" / "samples"

# Column groups for quick reference
DATE_COLS = [
    "ACCOUNT_CREATE_DATE", "EARLIEST_LOGIN_DATE",
    "EARLIEST_NAME_CONTRIBUTOR_DATE", "EARLIEST_SOURCE_CONTRIBUTOR_DATE",
    "EARLIEST_MEMORY_CONTRIBUTOR_DATE", "EARLIEST_GET_INVOLVED_USAGE_DATE",
    "EARLIEST_RECORD_EDIT_DATE", "EARLIEST_TREE_EDIT_DATE",
]

ACTIVITY_COUNT_COLS = [
    "DAYS_LOGGING_IN", "SOURCES_ADDED", "DAYS_ADDING_SOURCES",
    "MEMORIES_ADDED", "DAYS_ADDING_MEMORIES",
    "GET_INVOLVED_ITEMS_REVIEWED", "DAYS_REVIEWING_GET_INVOLVED_ITEMS",
    "RECORD_EDITS", "DAYS_EDITING_RECORDS",
    "TREE_EDITS", "DAYS_EDITING_TREES",
]

NAME_COLS = [
    "DAYS_ADDING_NAMES", "TOTAL_NAMES_ADDED", "DECEASED_NAMES_ADDED",
    "LIVING_NAMES_ADDED", "NOVEL_NAMES_ADDED", "QUALIFIED_NAMES_ADDED",
]

DEMOGRAPHIC_COLS = [
    "ACCOUNT_TYPE", "USER_CURRENT_AGE", "COUNTRY",
    "USER_WORLD_REGION", "USER_AREA_NAME",
]

ALL_NUMERIC_ACTIVITY = ACTIVITY_COUNT_COLS + NAME_COLS


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Convert date columns, coercing bad values to NaT."""
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _clean_ages(df: pd.DataFrame) -> pd.DataFrame:
    """Cap ages to sensible range."""
    df["USER_CURRENT_AGE"] = df["USER_CURRENT_AGE"].clip(lower=0, upper=110)
    return df


def load_raw(nrows: int | None = None) -> pd.DataFrame:
    """Load raw CSV (or first nrows)."""
    df = pd.read_csv(RAW_DATA_PATH, nrows=nrows)
    df = _parse_dates(df)
    df = _clean_ages(df)
    return df


def create_sample(n: int = 500_000, seed: int = 42) -> pd.DataFrame:
    """Create a stratified sample and cache to parquet."""
    sample_file = SAMPLE_PATH / f"sample_{n}.parquet"
    if sample_file.exists():
        return pd.read_parquet(sample_file)

    SAMPLE_PATH.mkdir(parents=True, exist_ok=True)

    # Read full file, sample, save
    df = load_raw()
    if len(df) > n:
        df = df.sample(n=n, random_state=seed)
    df = df.reset_index(drop=True)
    df.to_parquet(sample_file, index=False)
    return df


@st.cache_data(ttl=3600, show_spinner="Loading dataset...")
def load_for_dashboard(n: int = 500_000) -> pd.DataFrame:
    """Load data for dashboard use — cached by Streamlit."""
    sample_file = SAMPLE_PATH / f"sample_{n}.parquet"
    if sample_file.exists():
        df = pd.read_parquet(sample_file)
        df = _parse_dates(df)
        df = _clean_ages(df)
        return df
    return create_sample(n)


def get_data_health_report(df: pd.DataFrame) -> pd.DataFrame:
    """Generate a data health report: missing, zeros, outliers per column."""
    records = []
    for col in df.columns:
        rec = {
            "column": col,
            "dtype": str(df[col].dtype),
            "n_total": len(df),
            "n_missing": int(df[col].isna().sum()),
            "pct_missing": round(df[col].isna().mean() * 100, 2),
        }
        if col == "USER_ID":
            # Identity column — only n_unique is meaningful
            rec["n_unique"] = int(df[col].nunique())
            records.append(rec)
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            valid = df[col].dropna()
            rec["n_zeros"] = int((valid == 0).sum()) if len(valid) > 0 else None
            rec["pct_zeros"] = round((valid == 0).mean() * 100, 2) if len(valid) > 0 else None
            rec["mean"] = round(valid.mean(), 2) if len(valid) > 0 else None
            rec["median"] = int(valid.median()) if len(valid) > 0 else None
            rec["std"] = round(valid.std(), 2) if len(valid) > 0 else None
            rec["min"] = int(valid.min()) if len(valid) > 0 else None
            rec["max"] = int(valid.max()) if len(valid) > 0 else None
            rec["p99"] = int(valid.quantile(0.99)) if len(valid) > 0 else None
            rec["skewness"] = round(valid.skew(), 2) if len(valid) > 100 else None
        else:
            rec["n_unique"] = int(df[col].nunique())

        records.append(rec)
    result = pd.DataFrame(records)
    # Cast integer-display columns to nullable Int64 so they render without .0
    for col in ["n_zeros", "median", "min", "max", "p99", "n_unique"]:
        if col in result.columns:
            result[col] = result[col].astype("Int64")
    return result
