from __future__ import annotations

from flask import Blueprint

from .handlers import (
    about,
    clear_derived,
    clear_exclusions,
    clear_modifiers,
    clear_selection,
    delete_derived,
    download_dataframe,
    download_derived,
    download_derived_xml,
    download_selected,
    index,
    inject_global_context,
    select_group,
    select_rows,
    select_single_entry,
    set_modifiers,
    update_exclusions,
)

main_bp = Blueprint("main", __name__)
main_bp.app_context_processor(inject_global_context)

main_bp.add_url_rule("/", view_func=index, methods=["GET", "POST"])
main_bp.add_url_rule("/about", view_func=about, methods=["GET"])
main_bp.add_url_rule("/download", view_func=download_dataframe, methods=["GET"])
main_bp.add_url_rule("/update_exclusions", view_func=update_exclusions, methods=["POST"])
main_bp.add_url_rule("/clear_exclusions", view_func=clear_exclusions, methods=["POST"])
main_bp.add_url_rule("/select_rows", view_func=select_rows, methods=["POST"])
main_bp.add_url_rule("/clear_selection", view_func=clear_selection, methods=["POST"])
main_bp.add_url_rule("/select_group", view_func=select_group, methods=["POST"])
main_bp.add_url_rule("/download_selected", view_func=download_selected, methods=["GET"])
main_bp.add_url_rule("/set_modifiers", view_func=set_modifiers, methods=["POST"])
main_bp.add_url_rule("/clear_modifiers", view_func=clear_modifiers, methods=["POST"])
main_bp.add_url_rule("/select_single_entry", view_func=select_single_entry, methods=["POST"])
main_bp.add_url_rule("/delete_derived", view_func=delete_derived, methods=["POST"])
main_bp.add_url_rule("/clear_derived", view_func=clear_derived, methods=["POST"])
main_bp.add_url_rule("/download_derived", view_func=download_derived, methods=["GET"])
main_bp.add_url_rule("/download_derived_xml", view_func=download_derived_xml, methods=["GET"])

