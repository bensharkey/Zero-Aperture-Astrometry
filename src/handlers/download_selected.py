from __future__ import annotations

import os

from flask import flash, make_response, redirect, session, url_for

from ..services.file_io import read_file_to_dataframe
from ..services.selection import apply_selection_modifiers


def download_selected():
    filepath = session.get("last_file_path")
    filename = session.get("last_filename")
    indices = session.get("selected_indices")
    if not filepath or not filename or not os.path.exists(filepath):
        flash("No file loaded. Please upload a file first.")
        return redirect(url_for("main.index"))
    if not indices:
        flash("No rows selected to download.")
        return redirect(url_for("main.index"))

    try:
        df = read_file_to_dataframe(filepath, filename)
        selected_df = df.iloc[indices]
        modifiers = session.get("selection_modifiers")
        if modifiers:
            selected_df = apply_selection_modifiers(selected_df, modifiers)
        txt_data = selected_df.to_csv(sep="\t", index=False)
        response = make_response(txt_data)
        base = os.path.splitext(filename)[0]
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Content-Disposition"] = f'attachment; filename="{base}_selected.txt"'
        return response
    except Exception as exc:
        flash(f"Error generating selected download: {str(exc)}")
        return redirect(url_for("main.index"))

