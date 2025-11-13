from __future__ import annotations

import os

from flask import flash, redirect, request, session, url_for


def select_group():
    filepath = session.get("last_file_path")
    filename = session.get("last_filename")
    if not filepath or not filename or not os.path.exists(filepath):
        flash("No file loaded. Please upload a file first.", "group")
        return redirect(url_for("main.index"))
    value = request.form.get("selected_obstime")
    if value is None or value == "":
        session.pop("selected_obstime", None)
        session["fit_ready"] = False
        flash("Cleared group selection.", "group")
    else:
        session["selected_obstime"] = value
        session["fit_ready"] = False
        flash(f"Selected group obstime = {value}", "group")
    return redirect(url_for("main.index"))
