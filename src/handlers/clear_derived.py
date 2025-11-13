from __future__ import annotations

import os

from flask import flash, redirect, url_for

from ..services.derived_store import _derived_store_path


def clear_derived():
    path = _derived_store_path()
    try:
        if os.path.exists(path):
            os.remove(path)
        flash("Cleared all derived rows.", "derived")
    except Exception as exc:
        flash(f"Error clearing derived rows: {str(exc)}", "derived")
    return redirect(url_for("main.index"))

