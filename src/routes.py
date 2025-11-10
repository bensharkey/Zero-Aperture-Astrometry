from __future__ import annotations

import os
import traceback
from datetime import datetime
from typing import Any, Optional

import pandas as pd
from flask import (
    Blueprint,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

from .services.derived_store import (
    _derived_store_path,
    format_psv_aligned,
    load_derived_rows,
    save_derived_rows,
)
from .services.file_io import allowed_file, build_obstime_info, read_file_to_dataframe
from .services.plotting import generate_group_plots
from .services.selection import apply_selection_modifiers, parse_row_indices

main_bp = Blueprint("main", __name__)


@main_bp.app_context_processor
def inject_global_context() -> dict[str, Any]:
    return {"current_year": datetime.utcnow().year}


@main_bp.route("/", methods=["GET", "POST"])
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


@main_bp.route("/about", methods=["GET"])
def about():
    return render_template("about.html")


@main_bp.route("/download", methods=["GET"])
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


@main_bp.route("/update_exclusions", methods=["POST"])
def update_exclusions():
    filepath = session.get("last_file_path")
    filename = session.get("last_filename")
    if not filepath or not filename or not os.path.exists(filepath):
        flash("No file loaded. Please upload a file first.", "global")
        return redirect(url_for("main.index"))
    obstime = request.form.get("obstime")
    exclude_ids = request.form.getlist("exclude_id")
    selected_id = request.form.get("selected_id")
    excluded_by_obstime = session.get("excluded_by_obstime") or {}
    picked_by_obstime = session.get("picked_by_obstime") or {}
    if obstime:
        excluded_by_obstime[str(obstime)] = [str(x) for x in exclude_ids]
        session["excluded_by_obstime"] = excluded_by_obstime
        if selected_id:
            picked_by_obstime[str(obstime)] = str(selected_id)
            session["picked_by_obstime"] = picked_by_obstime
            flash(f"Updated: picked row set and {len(exclude_ids)} exclusion(s) applied.", "exclusions")
        else:
            flash(f"Updated exclusions for obstime {obstime}: {len(exclude_ids)} row(s) excluded.", "exclusions")
    return redirect(url_for("main.index"))


@main_bp.route("/clear_exclusions", methods=["POST"])
def clear_exclusions():
    obstime = request.form.get("obstime")
    excluded_by_obstime = session.get("excluded_by_obstime") or {}
    if obstime and str(obstime) in excluded_by_obstime:
        excluded_by_obstime.pop(str(obstime), None)
        session["excluded_by_obstime"] = excluded_by_obstime
        flash(f"Cleared exclusions for obstime {obstime}.", "exclusions")
    return redirect(url_for("main.index"))


@main_bp.route("/select_rows", methods=["POST"])
def select_rows():
    filepath = session.get("last_file_path")
    filename = session.get("last_filename")
    if not filepath or not filename or not os.path.exists(filepath):
        flash("No file loaded. Please upload a file first.")
        return redirect(url_for("main.index"))

    try:
        df = read_file_to_dataframe(filepath, filename)
        raw = request.form.get("row_indices", "")
        indices = parse_row_indices(raw, len(df))
        if not indices:
            session.pop("selected_indices", None)
            flash(
                "No valid row indices provided. Expect comma-separated indices or ranges like 0,2,5-8.",
                "global",
            )
        else:
            session["selected_indices"] = indices
            flash(f"Selected {len(indices)} row(s). Preview updated below.", "global")
    except Exception as exc:
        flash(f"Error selecting rows: {str(exc)}", "global")

    return redirect(url_for("main.index"))


@main_bp.route("/clear_selection", methods=["POST"])
def clear_selection():
    session.pop("selected_indices", None)
    flash("Selection cleared.", "global")
    return redirect(url_for("main.index"))


@main_bp.route("/select_group", methods=["POST"])
def select_group():
    filepath = session.get("last_file_path")
    filename = session.get("last_filename")
    if not filepath or not filename or not os.path.exists(filepath):
        flash("No file loaded. Please upload a file first.", "group")
        return redirect(url_for("main.index"))
    value = request.form.get("selected_obstime")
    if value is None or value == "":
        session.pop("selected_obstime", None)
        flash("Cleared group selection.", "group")
    else:
        session["selected_obstime"] = value
        flash(f"Selected group obstime = {value}", "group")
    return redirect(url_for("main.index"))


@main_bp.route("/download_selected", methods=["GET"])
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


@main_bp.route("/set_modifiers", methods=["POST"])
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


@main_bp.route("/clear_modifiers", methods=["POST"])
def clear_modifiers():
    session.pop("selection_modifiers", None)
    flash("Modifiers cleared.", "global")
    return redirect(url_for("main.index"))


@main_bp.route("/select_single_entry", methods=["POST"])
def select_single_entry():
    filepath = session.get("last_file_path")
    filename = session.get("last_filename")
    obstime = session.get("selected_obstime")
    if not filepath or not filename or not os.path.exists(filepath) or obstime is None:
        flash("No file loaded. Please upload a file first.", "global")
        return redirect(url_for("main.index"))
    try:
        prelim = (session.get("prelim_derived_by_obstime") or {}).get(str(obstime))
        if not prelim:
            flash(
                "No staged derived entry available. Adjust selection/exclusions to generate a plot first.",
                "derived",
            )
            return redirect(url_for("main.index"))
        derived_rows = load_derived_rows()
        derived_rows.append(prelim)
        save_derived_rows(derived_rows)
        prelim_all = session.get("prelim_derived_by_obstime") or {}
        prelim_all.pop(str(obstime), None)
        session["prelim_derived_by_obstime"] = prelim_all
        flash("Derived entry added. You can download or manage derived entries below.", "derived")
    except Exception as exc:
        flash(f"Error creating derived entry: {str(exc)}", "derived")
    return redirect(url_for("main.index"))


@main_bp.route("/delete_derived", methods=["POST"])
def delete_derived():
    rows = load_derived_rows()
    to_delete = request.form.getlist("delete_idx")
    if not to_delete:
        flash("No derived rows selected for deletion.", "derived")
        return redirect(url_for("main.index"))
    try:
        idxs = sorted({int(i) for i in to_delete}, reverse=True)
        for idx in idxs:
            if 0 <= idx < len(rows):
                rows.pop(idx)
        save_derived_rows(rows)
        flash(f"Deleted {len(idxs)} derived row(s).", "derived")
    except Exception as exc:
        flash(f"Error deleting derived rows: {str(exc)}", "derived")
    return redirect(url_for("main.index"))


@main_bp.route("/clear_derived", methods=["POST"])
def clear_derived():
    path = _derived_store_path()
    try:
        if os.path.exists(path):
            os.remove(path)
        flash("Cleared all derived rows.", "derived")
    except Exception as exc:
        flash(f"Error clearing derived rows: {str(exc)}", "derived")
    return redirect(url_for("main.index"))


@main_bp.route("/download_derived", methods=["GET"])
def download_derived():
    rows = load_derived_rows()
    if not rows:
        flash("No derived rows to download.", "derived")
        return redirect(url_for("main.index"))
    try:
        cols = session.get("original_columns")
        df = pd.DataFrame(rows, columns=cols) if cols else pd.DataFrame(rows)
        psv = format_psv_aligned(df)
        response = make_response(psv)
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response.headers["Content-Disposition"] = 'attachment; filename="derived.psv"'
        return response
    except Exception as exc:
        flash(f"Error downloading derived data: {str(exc)}", "derived")
        return redirect(url_for("main.index"))


@main_bp.route("/download_derived_xml", methods=["GET"])
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
        from xml.dom import minidom

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
