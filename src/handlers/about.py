from __future__ import annotations

from flask import render_template


def about():
    return render_template("about.html")

