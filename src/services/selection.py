from __future__ import annotations

import itertools
import re
from typing import Iterable

import pandas as pd


def parse_row_indices(raw: str, max_length: int) -> list[int]:
    """Parse comma separated indices/ranges like '0,2,5-8'."""
    tokens = [tok.strip() for tok in raw.split(",") if tok.strip()]
    indices: set[int] = set()
    range_pattern = re.compile(r"^(?P<start>\d+)\s*-\s*(?P<end>\d+)$")

    for token in tokens:
        match = range_pattern.match(token)
        if match:
            start = int(match.group("start"))
            end = int(match.group("end"))
            if start > end:
                start, end = end, start
            indices.update(i for i in range(start, end + 1) if i < max_length)
            continue
        if token.isdigit():
            value = int(token)
            if value < max_length:
                indices.add(value)

    return sorted(indices)


def apply_selection_modifiers(df: pd.DataFrame, modifiers: Iterable[dict]) -> pd.DataFrame:
    """Apply a small set of modifiers (dropna, head) to a DataFrame."""
    result = df.copy()
    for modifier in modifiers or []:
        m_type = (modifier or {}).get("type")
        if m_type == "drop_na":
            how = modifier.get("how", "any")
            result = result.dropna(how=how)
        elif m_type == "head_n":
            n = modifier.get("n", 10)
            if isinstance(n, int) and n >= 0:
                result = result.head(n)
    return result
