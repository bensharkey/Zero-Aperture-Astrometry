from __future__ import annotations

from flask import flash, redirect, request, session, url_for


def set_modifiers():
    mods = []
    if request.form.get("mod_drop_na") == "on":
        how = request.form.get("mod_drop_na_how", "any")
        mods.append({"type": "drop_na", "how": how})
    head_n_val = request.form.get("mod_head_n")
    if head_n_val:
        try:
            n = int(head_n_val)
            if n >= 0:
                mods.append({"type": "head_n", "n": n})
        except ValueError:
            pass

    session["selection_modifiers"] = mods if mods else None
    if mods:
        flash("Modifiers applied to selection.")
    else:
        flash("No modifiers set; selection will be unmodified.")
    return redirect(url_for("main.index"))

