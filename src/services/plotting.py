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
from flask import session


def generate_group_plots(
    group: pd.DataFrame, output_row: Optional[pd.Series] = None, full_group: Optional[pd.DataFrame] = None
) -> Dict[str, str]:
    """Generate combined RA/Dec vs photAp plot with weighted linear fits."""
    group_orig = group.dropna(subset=["photAp", "ra", "dec", "rmsRA", "rmsDec"]).copy()
    group_fit = group.dropna(subset=["photAp", "ra", "dec", "rmsRA", "rmsDec"]).copy()
    urls: Dict[str, str] = {}
    if group_orig.empty or output_row is None:
        return urls

    coords = SkyCoord(ra=group_fit["ra"], dec=group_fit["dec"], unit=u.deg, frame="icrs")
    coords_rms = SkyCoord(ra=group_fit["rmsRA"], dec=group_fit["rmsDec"], unit=u.arcsec, frame="icrs")

    fullcoords = None
    fullcoords_rms = None
    excluded_subset = None
    if isinstance(full_group, pd.DataFrame) and not full_group.empty:
        full_orig = full_group.dropna(subset=["photAp", "ra", "dec", "rmsRA", "rmsDec"]).copy()
        if not full_orig.empty:
            fullcoords = SkyCoord(ra=full_orig["ra"], dec=full_orig["dec"], unit=u.deg, frame="icrs")
            fullcoords_rms = SkyCoord(ra=full_orig["rmsRA"], dec=full_orig["rmsDec"], unit=u.arcsec, frame="icrs")

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

        rms_ra = float(output_row["rmsRA"])
        raerr_sigfigs = abs(np.floor(np.log10(max(rms_ra * 2.0, 1e-12)))) + 1
        ra0_err = round(rms_ra * 2.0, int(raerr_sigfigs))
        ra0_ploterr = ra0_err
        ra_sig_figs = abs(np.floor(np.log10(max(ra0_ploterr / 3600.0, 1e-12)))) + 1
        ra0 = round(np.polyval(ra_fit, 0.0), int(ra_sig_figs))

        rms_dec = float(output_row["rmsDec"])
        decerr_sigfigs = abs(np.floor(np.log10(max(rms_dec * 2.0, 1e-12)))) + 1
        dec0_err = round(rms_dec * 2.0, int(decerr_sigfigs))
        dec0_ploterr = dec0_err
        dec_sig_figs = abs(np.floor(np.log10(max(dec0_ploterr / 3600.0, 1e-12)))) + 1
        dec0 = round(np.polyval(dec_fit, 0.0), int(dec_sig_figs))
        obs_time = str(output_row.get("obsTime", "Selected group"))

        ra_y = np.cos(np.radians(dec0)) * (coords.ra.deg - ra0) * 3600
        ra_y_err = coords_rms.ra.arcsec

        ex_ra_y = ex_ra_y_err = ex_dec_y = ex_dec_y_err = ex_x = None
        if fullcoords is not None and excluded_subset is not None and not excluded_subset.empty:
            ex_coords = SkyCoord(ra=excluded_subset["ra"], dec=excluded_subset["dec"], unit=u.deg, frame="icrs")
            ex_coords_rms = SkyCoord(ra=excluded_subset["rmsRA"], dec=excluded_subset["rmsDec"], unit=u.arcsec, frame="icrs")
            ex_x = excluded_subset["photAp"].astype(float)
            ex_ra_y = np.cos(np.radians(dec0)) * (ex_coords.ra.deg - ra0) * 3600
            ex_ra_y_err = ex_coords_rms.ra.arcsec
            ex_dec_y = (ex_coords.dec.deg - dec0) * 3600
            ex_dec_y_err = ex_coords_rms.dec.arcsec

        dec_y = (coords.dec.deg - dec0) * 3600
        dec_y_err = coords_rms.dec.arcsec

        plot_x_extrapolate = np.append([0.0], x)

        output_row["ra"] = ra0
        output_row["dec"] = dec0
        output_row["rmsRA"] = ra0_err
        output_row["rmsDec"] = dec0_err
        output_row["notes"] = "e" + output_row["notes"]

        try:
            base_cols = [c for c in group.columns if c != "_row_id"]
            aligned = output_row.copy()
            aligned["ra"] = ra0
            aligned["dec"] = dec0
            aligned["rmsRA"] = ra0_err
            aligned["rmsDec"] = dec0_err
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

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6))
        fig.suptitle(f"{obs_time} – Linear Fit")
        ax1.set_title(f"RA: ${ra0}^\\circ$")
        ax1.errorbar(0, 0, ra0_ploterr, label="0 Aperture Extrapolation", fmt="o")
        if ex_x is not None and ex_ra_y is not None and ex_ra_y_err is not None:
            ax1.errorbar(ex_x, ex_ra_y, ex_ra_y_err, label="Excluded RA data", fmt="s", c="r")
        ax1.errorbar(x, ra_y, ra_y_err, label="Included RA data", fmt="d", c="k", mew=3, zorder=10)
        ax1.plot(x, (np.polyval(ra_fit, x) - ra0) * 3600, label="RA fit", color="k")
        ax1.plot(plot_x_extrapolate, (np.polyval(ra_fit, plot_x_extrapolate) - ra0) * 3600, color="black", ls="--")
        ax1.set_ylabel(r"$\Delta$RA*cos(Dec) (arcseconds)")
        ax1.legend(loc=(1.1, 0.35))

        ax2.set_title(f"Dec: ${dec0}^\\circ$")
        ax2.errorbar(0, 0, dec0_ploterr, label="0 Aperture Extrapolation", fmt="o")
        if ex_x is not None and ex_dec_y is not None and ex_dec_y_err is not None:
            ax2.errorbar(ex_x, ex_dec_y, ex_dec_y_err, label="Excluded Dec data", fmt="s", c="r")
        ax2.errorbar(x, dec_y, dec_y_err, label="Included Dec data", fmt="s", c="k", mew=3, zorder=10)
        ax2.plot(x, (np.polyval(dec_fit, x) - dec0) * 3600, label="Dec fit", color="black")
        ax2.plot(plot_x_extrapolate, (np.polyval(dec_fit, plot_x_extrapolate) - dec0) * 3600, color="black", ls="--")
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
    except Exception:  # pragma: no cover - plotting best effort
        return urls

    return urls


def compute_linear_fits(group: pd.DataFrame) -> Optional[dict[str, dict[str, float]]]:
    """Compute linear fits for RA vs photAp and Dec vs photAp on given DataFrame."""
    group_orig = group.dropna(subset=["photAp", "ra", "dec", "rmsRA", "rmsDec"]).copy()
    coords = SkyCoord(ra=group["ra"], dec=group["dec"], unit=u.deg, frame="icrs")
    coords_rms = SkyCoord(ra=group["rmsRA"], dec=group["rmsDec"], unit=u.arcsec, frame="icrs")
    output_row = group.iloc[0]

    if group.empty or len(group) < 2:
        return None

    try:
        x = group["photAp"].astype(float)
        np.polyfit(x, coords.ra.deg, 1, w=1 / coords_rms.ra.deg, cov="unscaled")
        np.polyfit(x, coords.dec.deg, 1, w=1 / coords_rms.dec.deg, cov="unscaled")
        raerr_sigfigs = np.abs(np.floor(np.log10(output_row["rmsRA"].astype(float) * 2))) + 1
        ra0_err = round(output_row["rmsRA"].astype(float) * 2, int(raerr_sigfigs.iloc[0]))
        ra_sig_figs = np.abs(np.floor(np.log10(ra0_err / 3600))) + 1
        ra0 = round(np.polyval(np.polyfit(x, coords.ra.deg, 1), 0), int(ra_sig_figs.iloc[0]))
        decerr_sigfigs = np.abs(np.floor(np.log10(output_row["rmsDec"].astype(float) * 2))) + 1
        dec0_err = round(output_row["rmsDec"].astype(float) * 2, int(decerr_sigfigs.iloc[0]))
        dec_sig_figs = np.abs(np.floor(np.log10(dec0_err / 3600))) + 1
        dec0 = round(np.polyval(np.polyfit(x, coords.dec.deg, 1), 0), int(dec_sig_figs.iloc[0]))
    except Exception:
        return None

    return {
        "ra": {"b": float(ra0), "err": float(ra0_err)},
        "dec": {"b": float(dec0), "err": float(dec0_err)},
    }
