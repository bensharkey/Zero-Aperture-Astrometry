from __future__ import annotations

import base64
import io
from typing import Any, Dict, Optional

import astropy.units as u
import matplotlib

matplotlib.use("Agg")  # Non-interactive backend for server environments

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from astropy.coordinates import SkyCoord
from flask import session, current_app
import re


def _detect_decimal_places_from_series(s: pd.Series | None, sample_limit: int = 500) -> int:
    """Return the maximum number of decimal places found in string values of a series.

    If the series has string/object dtype the textual representation is inspected and
    the largest number of digits after the decimal point is returned. If no
    useful formatting is found or the series is numeric/empty, a sensible default
    (6) is returned.
    """
    default = 6
    if s is None or s.empty:
        return default
    # Prefer inspecting the original textual values when they are strings/object
    if pd.api.types.is_string_dtype(s) or s.dtype == object:
        max_dp = 0
        for v in s.dropna().astype(str).head(sample_limit):
            # Strip surrounding whitespace before inspecting the textual value.
            # Some uploaded files include trailing spaces which will prevent the
            # regex from matching the decimal portion (because of the end anchor),
            # causing the detector to fall back to the default precision.
            vs = v.strip()
            m = re.search(r"\.(\d+)(?:[eE].*|$)", vs)
            if m:
                dp = len(m.group(1))
                if dp > max_dp:
                    max_dp = dp
        return max_dp if max_dp > 0 else default
    # Numeric series: we don't have preserved formatting information
    return default


def _format_float_with_series_precision(value: float, s: pd.Series | None) -> str:
    """Format a float to the decimal places detected in series `s`.

    This returns a string preserving trailing zeros to match the detected
    precision.
    """
    dp = _detect_decimal_places_from_series(s)
    return f"{float(value):.{dp}f}"


def generate_group_plots(
    group: pd.DataFrame, output_row: Optional[pd.Series] = None, full_group: Optional[pd.DataFrame] = None
) -> Dict[str, str]:
    """Generate combined RA/Dec vs photAp plot with weighted linear fits.

    Behaviour:
    - The uploaded `ra`, `dec`, `rmsRA`, `rmsDec` columns are preserved as strings
      at ingest. This function casts them to float only for numeric work.
    - After computing derived values for aperture=0, the function overwrites
      `output_row["ra"]`, `output_row["dec"]`, `output_row["rmsRA"]`,
      `output_row["rmsDec"]` with formatted strings matching the input precision.
    - The function returns a dict of data-URLs for embedded PNG plots.
    """
    urls: Dict[str, str] = {}
    if group is None or group.empty or output_row is None:
        return urls

    # Work on rows that have the required columns
    group_orig = group.dropna(subset=["photAp", "ra", "dec", "rmsRA", "rmsDec"]).copy()
    group_fit = group_orig.copy()
    if group_orig.empty:
        return urls

    # detect precision from uploaded values (strings)
    ra_dp = _detect_decimal_places_from_series(group_orig.get("ra"))
    dec_dp = _detect_decimal_places_from_series(group_orig.get("dec"))
    rmsRA_dp = _detect_decimal_places_from_series(group_orig.get("rmsRA"))
    rmsDec_dp = _detect_decimal_places_from_series(group_orig.get("rmsDec"))

    # Cast to float only for numeric computations
    coords = SkyCoord(ra=group_fit["ra"].astype(float), dec=group_fit["dec"].astype(float), unit=u.deg, frame="icrs")
    coords_rms = SkyCoord(ra=group_fit["rmsRA"].astype(float), dec=group_fit["rmsDec"].astype(float), unit=u.arcsec, frame="icrs")

    # If a full_group (all rows including excluded) is provided, prepare numeric coords
    fullcoords = None
    fullcoords_rms = None
    excluded_subset = None
    if isinstance(full_group, pd.DataFrame) and not full_group.empty:
        full_orig = full_group.dropna(subset=["photAp", "ra", "dec", "rmsRA", "rmsDec"]).copy()
        if not full_orig.empty:
            fullcoords = SkyCoord(ra=full_orig["ra"].astype(float), dec=full_orig["dec"].astype(float), unit=u.deg, frame="icrs")
            fullcoords_rms = SkyCoord(ra=full_orig["rmsRA"].astype(float), dec=full_orig["rmsDec"].astype(float), unit=u.arcsec, frame="icrs")

            def _ids(df: pd.DataFrame) -> set[str]:
                if "_row_id" in df.columns:
                    return set(df["_row_id"].astype(str))
                return set(df.index.astype(str))

            try:
                inc_ids = _ids(group_orig)
                all_ids = _ids(full_orig)
                excl_ids = list(all_ids - inc_ids)
                if excl_ids:
                    key = "_row_id" if "_row_id" in full_orig.columns else None
                    if key:
                        excluded_subset = full_orig[full_orig["_row_id"].astype(str).isin(excl_ids)].copy()
                    else:
                        excluded_subset = full_orig.loc[full_orig.index.astype(str).isin(excl_ids)].copy()
            except Exception:  # pragma: no cover - best effort
                excluded_subset = None

    if len(group_fit) < 2:
        return urls

    try:
        x = group_fit["photAp"].astype(float)

        try:
            ra_fit, _ = np.polyfit(x, coords.ra.deg, 1, w=1 / coords_rms.ra.deg, cov="unscaled")
            dec_fit, _ = np.polyfit(x, coords.dec.deg, 1, w=1 / coords_rms.dec.deg, cov="unscaled")
        except Exception:
            ra_fit, _ = np.polyfit(x, coords.ra.deg, 1, cov="unscaled")
            dec_fit, _ = np.polyfit(x, coords.dec.deg, 1, cov="unscaled")

        # Numeric values used for plotting and internal storage
        rms_ra = float(output_row["rmsRA"])
        ra0_err = rms_ra * 2.0
        ra0_ploterr = ra0_err
        # use unrounded numeric values for computations/plots
        ra0_num = float(np.polyval(ra_fit, 0.0))

        rms_dec = float(output_row["rmsDec"])
        dec0_err = rms_dec * 2.0
        dec0_ploterr = dec0_err
        dec0_num = float(np.polyval(dec_fit, 0.0))

        obs_time = str(output_row.get("obsTime", "Selected group"))

        ra_y = np.cos(np.radians(dec0_num)) * (coords.ra.deg - np.median(coords.ra.deg)) * 3600
        ra_y_err = coords_rms.ra.arcsec

        ex_ra_y = ex_ra_y_err = ex_dec_y = ex_dec_y_err = ex_x = None
        if fullcoords is not None and excluded_subset is not None and not excluded_subset.empty:
            ex_coords = SkyCoord(ra=excluded_subset["ra"].astype(float), dec=excluded_subset["dec"].astype(float), unit=u.deg, frame="icrs")
            ex_coords_rms = SkyCoord(ra=excluded_subset["rmsRA"].astype(float), dec=excluded_subset["rmsDec"].astype(float), unit=u.arcsec, frame="icrs")
            ex_x = excluded_subset["photAp"].astype(float)
            ex_ra_y = np.cos(np.radians(dec0_num)) * (ex_coords.ra.deg - np.median(coords.ra.deg)) * 3600
            ex_ra_y_err = ex_coords_rms.ra.arcsec
            ex_dec_y = (ex_coords.dec.deg - np.median(coords.dec.deg)) * 3600
            ex_dec_y_err = ex_coords_rms.dec.arcsec

        dec_y = (coords.dec.deg - np.median(coords.dec.deg)) * 3600
        dec_y_err = coords_rms.dec.arcsec

        plot_x_extrapolate = np.append([0.0], x)

        # Save formatted strings in output_row (overwrite numeric columns) so user-displayed
        # data preserves original formatting / trailing zeros.
        try:
            output_row["ra"] = _format_float_with_series_precision(ra0_num, group_orig.get("ra"))
            output_row["dec"] = _format_float_with_series_precision(dec0_num, group_orig.get("dec"))
            output_row["rmsRA"] = _format_float_with_series_precision(ra0_err, group_orig.get("rmsRA"))
            output_row["rmsDec"] = _format_float_with_series_precision(dec0_err, group_orig.get("rmsDec"))
        except Exception:  # pragma: no cover - best effort fallback to plain strings
            output_row["ra"] = str(ra0_num)
            output_row["dec"] = str(dec0_num)
            output_row["rmsRA"] = str(ra0_err)
            output_row["rmsDec"] = str(dec0_err)

        # Ensure notes has no whitespace (remove spaces, tabs, newlines)
        raw_notes = str(output_row.get("notes", ""))
        cleaned_notes = "".join(raw_notes.split())
        output_row["notes"] = "e" + cleaned_notes

        try:
            base_cols = [c for c in group.columns if c != "_row_id"]
            aligned = output_row.copy()
            # aligned now contains user-facing formatted strings for the spatial columns
            row_dict: dict[str, Any] = {}
            for col in base_cols:
                value = aligned[col] if col in aligned else None
                if isinstance(value, float) and np.isnan(value):
                    value = None
                elif hasattr(value, "item"):
                    value = value.item()
                row_dict[col] = value
            prelim = session.get("prelim_derived_by_obstime") or {}
            prelim[str(obs_time)] = row_dict
            session["prelim_derived_by_obstime"] = prelim
            picked = session.get("picked_by_obstime") or {}
            if "_row_id" in output_row:
                picked[str(obs_time)] = str(output_row["_row_id"])
                session["picked_by_obstime"] = picked
        except Exception:  # pragma: no cover - fail silently for session persistence
            pass

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharey=True)
        fig.suptitle(f"{obs_time} – Linear Fit")
        ax1.set_title(f"RA: ${output_row['ra']}^\\circ$")
        ax1.errorbar(0, (np.polyval(ra_fit, 0) - np.median(coords.ra.deg)) * 3600, ra0_ploterr, label="0 Aperture Extrapolation", fmt="o")
        if ex_x is not None and ex_ra_y is not None and ex_ra_y_err is not None:
            ax1.errorbar(ex_x, ex_ra_y, ex_ra_y_err, label="Excluded RA data", fmt="s", c="r")
        ax1.errorbar(x, ra_y, ra_y_err, label="Included RA data", fmt="d", c="k", mew=3, zorder=10)
        ax1.plot(x, (np.polyval(ra_fit, x) - np.median(coords.ra.deg)) * 3600, label="RA fit", color="k")
        ax1.plot(plot_x_extrapolate, (np.polyval(ra_fit, plot_x_extrapolate) - np.median(coords.ra.deg)) * 3600, color="black", ls="--")
        ax1.set_ylabel(r"$\Delta$RA*cos(Dec) (arcseconds)")
        ax1.legend(loc=(1.1, 0.35))

        ax2.set_title(f"Dec: ${output_row['dec']}^\\circ$")
        ax2.errorbar(0, (np.polyval(dec_fit, 0) - np.median(coords.dec.deg)) * 3600, dec0_ploterr, label="0 Aperture Extrapolation", fmt="o")
        if ex_x is not None and ex_dec_y is not None and ex_dec_y_err is not None:
            ax2.errorbar(ex_x, ex_dec_y, ex_dec_y_err, label="Excluded Dec data", fmt="s", c="r")
        ax2.errorbar(x, dec_y, dec_y_err, label="Included Dec data", fmt="s", c="k", mew=3, zorder=10)
        ax2.plot(x, (np.polyval(dec_fit, x) - np.median(coords.dec.deg)) * 3600, label="Dec fit", color="black")
        ax2.plot(plot_x_extrapolate, (np.polyval(dec_fit, plot_x_extrapolate) - np.median(coords.dec.deg)) * 3600, color="black", ls="--")
        ax2.set_xlabel("Photometric Aperture (photAp)")
        ax2.set_ylabel(r"$\Delta$Dec (arcseconds)")
        ax2.legend(loc=(1.1, 0.35))
        buf = io.BytesIO()
        plt.tight_layout()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii").strip()
        urls["coords_photAp"] = f"data:image/png;base64,{b64}"
    except Exception as exc:  # pragma: no cover - plotting best effort
        # Log exception details to aid debugging in the server logs
        try:
            current_app.logger.exception("generate_group_plots failed: %s", exc)
        except Exception:
            import logging

            logging.exception("generate_group_plots failed")
        return urls

    return urls

