from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any, List

import pandas as pd
from flask import current_app, session


def _derived_store_path() -> str:
    token = session.get("derived_token")
    if not token:
        token = uuid.uuid4().hex
        session["derived_token"] = token
    upload_folder = Path(current_app.config["UPLOAD_FOLDER"])
    return str(upload_folder / f"derived_{token}.json")


def load_derived_rows() -> List[dict[str, Any]]:
    path = _derived_store_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:  # pragma: no cover - defensive read
        return []


def save_derived_rows(rows: list[dict[str, Any]]) -> None:
    path = _derived_store_path()
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(rows, handle)
    except Exception as exc:  # pragma: no cover
        current_app.logger.error("Failed to save derived rows: %s", exc)


def format_psv_aligned(df: pd.DataFrame) -> str:
    """Return PSV text with padded columns for readability."""
    if df is None or df.empty:
        return ""
    str_df = df.applymap(lambda v: "" if pd.isna(v) else str(v))
    widths = []
    for col in str_df.columns:
        col_width = max(len(str(col)), int(str_df[col].str.len().max() or 0))
        widths.append(col_width)
    header = "|".join(str(col).ljust(widths[i]) for i, col in enumerate(str_df.columns))
    lines = [header]
    for _, row in str_df.iterrows():
        line = "|".join(str(row[i]).ljust(widths[i]) for i in range(len(widths)))
        lines.append(line)
    return "\n".join(lines) + "\n"
