from __future__ import annotations

import os

from flask import flash, redirect, request, session, url_for

from ..services.file_io import read_file_to_dataframe
from ..services.selection import parse_row_indices


def select_rows():
    filepath = session.get("last_file_path")
    filename = session.get("last_filename")
    if not filepath or not filename or not os.path.exists(filepath):
        flash("No file loaded. Please upload a file first.")
        return redirect(url_for("main.index"))

    try:
        df = read_file_to_dataframe(filepath, filename)
        raw = request.form.get("row_indices", "")
        indices = parse_row_indices(raw, len(df))
        if not indices:
            session.pop("selected_indices", None)
            flash(
                "No valid row indices provided. Expect comma-separated indices or ranges like 0,2,5-8.",
                "global",
            )
        else:
            session["selected_indices"] = indices
            flash(f"Selected {len(indices)} row(s). Preview updated below.", "global")
    except Exception as exc:
        flash(f"Error selecting rows: {str(exc)}", "global")

    return redirect(url_for("main.index"))

