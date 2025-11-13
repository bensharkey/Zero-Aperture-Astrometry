from __future__ import annotations

import os
import traceback
from typing import Any, Optional

from flask import current_app, flash, redirect, render_template, request, session
from werkzeug.utils import secure_filename

from ..services.derived_store import load_derived_rows
from ..services.file_io import allowed_file, build_obstime_info, read_file_to_dataframe
from ..services.plotting import generate_group_plots
from ..services.selection import apply_selection_modifiers


def index():
    file_content = None
    plot_urls = None
    selected_df_html = None
    selected_rows: Optional[list[dict[str, Any]]] = None
    selected_columns = None
    modifiers_summary = None
    error = None
    available_obstimes = None
    obstime_counts = None
    selected_obstime = session.get("selected_obstime")
    current_filename = session.get("last_filename")
    picked_by_obstime = session.get("picked_by_obstime") or {}
    picked_id = picked_by_obstime.get(str(selected_obstime)) if selected_obstime else None
    selected_count_value = None
    fit_summary = None
    derived_rows = load_derived_rows()
    derived_columns = list(derived_rows[0].keys()) if derived_rows else None
    original_columns = session.get("original_columns")

    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part in the request", "global")
            return redirect(request.url)

        file = request.files["file"]
        if file.filename == "":
            flash("No file selected", "global")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            try:
                filename = secure_filename(file.filename)
                upload_folder = current_app.config["UPLOAD_FOLDER"]
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                session["last_file_path"] = filepath
                session["last_filename"] = filename
                current_filename = filename
                session.pop("selected_indices", None)
                session.pop("selected_obstime", None)

                df = read_file_to_dataframe(filepath, filename)
                available_obstimes, obstime_counts = build_obstime_info(df)
                session["available_obstimes"] = available_obstimes
                session["obstime_counts"] = obstime_counts
                session["original_columns"] = [c for c in df.columns if c != "_row_id"]
            except Exception as exc:
                error = f"Error processing file: {str(exc)}"
                current_app.logger.error(traceback.format_exc())
                flash(error, "global")
        else:
            allowed = ", ".join(current_app.config.get("ALLOWED_EXTENSIONS", []))
            flash(f"File type not allowed. Allowed types are: {allowed}", "global")

    last_path = session.get("last_file_path")
    last_name = session.get("last_filename")
    group_excluded: set[str] = set()
    if request.method == "GET" and last_path and last_name and os.path.exists(last_path):
        try:
            df = read_file_to_dataframe(last_path, last_name)
            available_obstimes, obstime_counts = build_obstime_info(df)
            session["available_obstimes"] = available_obstimes
            session["obstime_counts"] = obstime_counts
            original_columns = [c for c in df.columns if c != "_row_id"]
            session["original_columns"] = original_columns
            if selected_obstime is not None:
                selected_mask = df["obsTime"].astype(str) == str(selected_obstime)
                selected_df = df[selected_mask].copy()
                selected_df["_row_id"] = selected_df.index.astype(str)
                excluded_by_obstime = session.get("excluded_by_obstime") or {}
                group_excluded = set((excluded_by_obstime.get(str(selected_obstime)) or []))
                preview_df = selected_df.head(50)
                selected_columns = [c for c in preview_df.columns if c != "_row_id"]
                selected_rows = [
                    {"_row_id": str(row["_row_id"]), **{col: row[col] for col in selected_columns}}
                    for _, row in preview_df.iterrows()
                ]
                try:
                    selected_df_html = preview_df.drop(columns=["_row_id"]).to_html(
                        classes="table table-striped table-bordered table-hover", index=False
                    )
                except Exception:
                    selected_df_html = None
                selected_df_filtered = selected_df[~selected_df["_row_id"].isin(group_excluded)].copy()
                if not selected_df_filtered.empty:
                    selected_count_value = len(selected_df_filtered)
                    output_row_series = None
                    if picked_id:
                        sel_row = selected_df_filtered[selected_df_filtered["_row_id"] == str(picked_id)]
                        if sel_row.empty:
                            sel_row = selected_df[selected_df["_row_id"] == str(picked_id)]
                        if not sel_row.empty:
                            output_row_series = sel_row.iloc[0]
                    if output_row_series is not None:
                        plot_urls = generate_group_plots(
                            selected_df_filtered, output_row=output_row_series, full_group=selected_df
                        )
                else:
                    plot_urls = None
                    selected_df_html = None
                    flash("Selected obstime has no matching rows in the current file.", "plot")
            selected_indices = session.get("selected_indices")
            if selected_indices:
                try:
                    selected_df = df.iloc[selected_indices]
                    modifiers = session.get("selection_modifiers")
                    if modifiers:
                        selected_df = apply_selection_modifiers(selected_df, modifiers)
                        parts = []
                        for modifier in modifiers:
                            m_type = (modifier or {}).get("type")
                            if m_type == "drop_na":
                                parts.append("drop NA")
                            elif m_type == "head_n":
                                parts.append(f"head({modifier.get('n', 10)})")
                            else:
                                parts.append(m_type or "unknown")
                        modifiers_summary = ", ".join(parts) if parts else None
                    selected_df_html = selected_df.head(50).to_html(
                        classes="table table-striped table-bordered table-hover", index=False
                    )
                except Exception:
                    selected_df_html = None
        except Exception:
            pass

    return render_template(
        "index.html",
        file_content=file_content,
        plot_urls=plot_urls,
        selected_df_html=selected_df_html,
        selected_rows=selected_rows,
        selected_columns=selected_columns,
        excluded_ids=list(group_excluded),
        picked_id=picked_id,
        fit_summary=fit_summary,
        derived_rows=derived_rows,
        derived_columns=derived_columns,
        original_columns=original_columns,
        current_filename=current_filename,
        modifiers_summary=modifiers_summary,
        error=error,
        available_obstimes=available_obstimes,
        selected_obstime=selected_obstime,
        obstime_counts=obstime_counts,
        selected_count=selected_count_value,
    )
