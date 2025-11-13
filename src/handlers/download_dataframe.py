from __future__ import annotations

import os

from flask import flash, make_response, redirect, session, url_for

from ..services.file_io import read_file_to_dataframe


def download_dataframe():
    filepath = session.get("last_file_path")
    filename = session.get("last_filename")

    if not filepath or not filename or not os.path.exists(filepath):
        flash("No file available to download. Please upload a file first.", "global")
        return redirect(url_for("main.index"))
    try:
        df = read_file_to_dataframe(filepath, filename)
        txt_data = df.to_csv(sep="\t", index=False)
        response = make_response(txt_data)
        download_name = os.path.splitext(filename)[0] + ".txt"
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Content-Disposition"] = f'attachment; filename="{download_name}"'
        return response
    except Exception as exc:
        flash(f"Error generating download: {str(exc)}", "global")
        return redirect(url_for("main.index"))

