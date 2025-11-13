from __future__ import annotations

from flask import flash, redirect, session, url_for


def reset_session():
    session.clear()
    flash("Session reset. Start by uploading a new file.", "global")
    return redirect(url_for("main.index"))

