from __future__ import annotations

from flask import flash, redirect, request, url_for

from ..services.derived_store import load_derived_rows, save_derived_rows


def delete_derived():
    rows = load_derived_rows()
    to_delete = request.form.getlist("delete_idx")
    if not to_delete:
        flash("No derived rows selected for deletion.", "derived")
        return redirect(url_for("main.index"))
    try:
        idxs = sorted({int(i) for i in to_delete}, reverse=True)
        for idx in idxs:
            if 0 <= idx < len(rows):
                rows.pop(idx)
        save_derived_rows(rows)
        flash(f"Deleted {len(idxs)} derived row(s).", "derived")
    except Exception as exc:
        flash(f"Error deleting derived rows: {str(exc)}", "derived")
    return redirect(url_for("main.index"))

