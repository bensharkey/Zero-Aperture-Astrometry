from __future__ import annotations

from flask import flash, redirect, session, url_for


def clear_modifiers():
    session.pop("selection_modifiers", None)
    flash("Modifiers cleared.", "global")
    return redirect(url_for("main.index"))

