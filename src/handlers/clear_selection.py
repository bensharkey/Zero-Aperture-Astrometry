from __future__ import annotations

from flask import flash, redirect, session, url_for


def clear_selection():
    session.pop("selected_indices", None)
    flash("Selection cleared.", "global")
    return redirect(url_for("main.index"))

