from __future__ import annotations

import pandas as pd
from flask import flash, make_response, redirect, session, url_for

from ..services.derived_store import format_psv_aligned, load_derived_rows


def download_derived():
    rows = load_derived_rows()
    if not rows:
        flash("No derived rows to download.", "derived")
        return redirect(url_for("main.index"))
    try:
        cols = session.get("original_columns")
        df = pd.DataFrame(rows, columns=cols) if cols else pd.DataFrame(rows)
        psv = format_psv_aligned(df)
        response = make_response(psv)
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Content-Disposition"] = 'attachment; filename="derived.psv"'
        return response
    except Exception as exc:
        flash(f"Error downloading derived data: {str(exc)}", "derived")
        return redirect(url_for("main.index"))

