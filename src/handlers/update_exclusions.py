from __future__ import annotations

import os

from flask import flash, redirect, request, session, url_for


def update_exclusions():
    filepath = session.get("last_file_path")
    filename = session.get("last_filename")
    if not filepath or not filename or not os.path.exists(filepath):
        flash("No file loaded. Please upload a file first.", "global")
        return redirect(url_for("main.index"))
    obstime = request.form.get("obstime")
    exclude_ids = request.form.getlist("exclude_id")
    selected_id = request.form.get("selected_id")
    excluded_by_obstime = session.get("excluded_by_obstime") or {}
    picked_by_obstime = session.get("picked_by_obstime") or {}
    if obstime:
        excluded_by_obstime[str(obstime)] = [str(x) for x in exclude_ids]
        session["excluded_by_obstime"] = excluded_by_obstime
        if selected_id:
            picked_by_obstime[str(obstime)] = str(selected_id)
            session["picked_by_obstime"] = picked_by_obstime
            flash(f"Updated: picked row set and {len(exclude_ids)} exclusion(s) applied.", "exclusions")
        else:
            flash(f"Updated exclusions for obstime {obstime}: {len(exclude_ids)} row(s) excluded.", "exclusions")
        session["fit_ready"] = True
    return redirect(url_for("main.index"))
