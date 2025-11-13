from __future__ import annotations

from xml.dom import minidom

import pandas as pd
from flask import flash, make_response, redirect, session, url_for

from ..services.derived_store import load_derived_rows


def download_derived_xml():
    rows = load_derived_rows()
    if not rows:
        flash("No derived rows to download.", "derived")
        return redirect(url_for("main.index"))
    try:
        cols = session.get("original_columns")
        df = pd.DataFrame(rows, columns=cols) if cols else pd.DataFrame(rows)
        df = df.applymap(lambda v: "" if pd.isna(v) else (v.strip() if isinstance(v, str) else v))
        xml_data = df.to_xml(index=False, root_name="obsData", row_name="optical")

        parsed = minidom.parseString(xml_data)
        pretty_xml = parsed.toprettyxml(indent="  ")
        pretty_no_blank = "\n".join([line for line in pretty_xml.splitlines() if line.strip()]) + "\n"
        response = make_response(pretty_no_blank)
        response.headers["Content-Type"] = "application/xml; charset=utf-8"
        response.headers["Content-Disposition"] = 'attachment; filename="derived.xml"'
        return response
    except Exception as exc:
        flash(f"Error downloading derived data as XML: {str(exc)}", "derived")
        return redirect(url_for("main.index"))

