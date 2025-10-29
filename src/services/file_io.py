from __future__ import annotations

import os

import pandas as pd
from flask import current_app


def allowed_file(filename: str) -> bool:
    allowed = current_app.config.get("ALLOWED_EXTENSIONS", set())
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def read_file_to_dataframe(filepath: str, filename: str) -> pd.DataFrame:
    """Read supported file types into a pandas DataFrame."""
    ext = filename.rsplit(".", 1)[1].lower()

    try:
        if ext == "psv":
            df = pd.read_csv(filepath, sep="|")
        elif ext == "xml":
            df = pd.read_xml(filepath, xpath="./obsBlock/obsData/*")
        else:
            raise ValueError(f"Unsupported file extension: {ext}")
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.error("Error reading file %s: %s", filename, exc)
        raise

    df.rename(columns=lambda x: x.strip(), inplace=True)
    df = df.dropna(subset=["obsTime"])

    df["ra"] = pd.to_numeric(df["ra"], errors="coerce")
    df["dec"] = pd.to_numeric(df["dec"], errors="coerce")
    if "photAp" not in df.columns:
        raise ValueError("Required column 'photAp' not found in uploaded file.")
    df["photAp"] = pd.to_numeric(df["photAp"], errors="coerce")
    return df


def build_obstime_info(df: pd.DataFrame) -> tuple[list[str], dict[str, int]]:
    """Return sorted obstime values and counts for UI rendering."""
    vals = df["obsTime"].dropna().astype(str)
    obstime_counts = vals.value_counts().to_dict()
    unique_vals = pd.Index(vals.unique())
    sort_df = pd.DataFrame({"value": unique_vals})
    sort_df["dt"] = pd.to_datetime(sort_df["value"], errors="coerce")
    sort_df = sort_df.sort_values(by=["dt", "value"], na_position="last")
    available_obstimes = sort_df["value"].tolist()
    return available_obstimes, obstime_counts
