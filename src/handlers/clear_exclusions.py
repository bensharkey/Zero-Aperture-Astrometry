from __future__ import annotations

from flask import flash, redirect, request, session, url_for


def clear_exclusions():
    obstime = request.form.get("obstime")
    excluded_by_obstime = session.get("excluded_by_obstime") or {}
    if obstime and str(obstime) in excluded_by_obstime:
        excluded_by_obstime.pop(str(obstime), None)
        session["excluded_by_obstime"] = excluded_by_obstime
        flash(f"Cleared exclusions for obstime {obstime}.", "exclusions")
    return redirect(url_for("main.index"))

