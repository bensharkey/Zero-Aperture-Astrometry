from __future__ import annotations

import os

from flask import flash, redirect, session, url_for

from ..services.derived_store import load_derived_rows, save_derived_rows


def select_single_entry():
    filepath = session.get("last_file_path")
    filename = session.get("last_filename")
    obstime = session.get("selected_obstime")
    if not filepath or not filename or not os.path.exists(filepath) or obstime is None:
        flash("No file loaded. Please upload a file first.", "global")
        return redirect(url_for("main.index"))
    try:
        prelim = (session.get("prelim_derived_by_obstime") or {}).get(str(obstime))
        if not prelim:
            flash(
                "No staged derived entry available. Adjust selection/exclusions to generate a plot first.",
                "derived",
            )
            return redirect(url_for("main.index"))
        derived_rows = load_derived_rows()
        derived_rows.append(prelim)
        save_derived_rows(derived_rows)
        prelim_all = session.get("prelim_derived_by_obstime") or {}
        prelim_all.pop(str(obstime), None)
        session["prelim_derived_by_obstime"] = prelim_all
        flash("Derived entry added. You can download or manage derived entries below.", "derived")
    except Exception as exc:
        flash(f"Error creating derived entry: {str(exc)}", "derived")
    return redirect(url_for("main.index"))

