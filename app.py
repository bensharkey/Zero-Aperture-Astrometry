from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
import pandas as pd
import os
import io
import base64
import json
import uuid
import re
import astropy.units as u
from astropy.coordinates import SkyCoord
from werkzeug.utils import secure_filename
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Required for non-interactive plotting
import matplotlib.pyplot as plt
import traceback
from xml.etree import ElementTree as ET
from xml.dom import minidom

app = Flask(__name__)
app.secret_key = 'dev-key-123'  # Change this in production
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'psv', 'xml'}

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def read_file_to_dataframe(filepath, filename):
    """Read different file types into a pandas DataFrame"""
    ext = filename.rsplit('.', 1)[1].lower()
    
    try:
        if ext == 'psv':
            df = pd.read_csv(filepath, sep='|')
        elif ext == 'xml':
            df = pd.read_xml(filepath, xpath='./obsBlock/obsData/*')
    except Exception as e:
        app.logger.error(f"Error reading file {filename}: {str(e)}")
        raise
    #print(df)
    df.rename(columns=lambda x: x.strip(), inplace=True)
    # Drop rows with missing obsTime
    df = df.dropna(subset=["obsTime"])

    # Convert required columns to numeric types
    df["ra"] = pd.to_numeric(df["ra"], errors="coerce")
    df["dec"] = pd.to_numeric(df["dec"], errors="coerce")
    # Ensure photAp exists per strict format and coerce numeric for plotting
    if "photAp" not in df.columns:
        raise ValueError("Required column 'photAp' not found in uploaded file.")
    df["photAp"] = pd.to_numeric(df["photAp"], errors="coerce")

    return df

def build_obstime_info(df: pd.DataFrame):
    """Return (available_obstimes:list[str], obstime_counts:dict[str,int]) with datetime-aware sorting."""
    vals = df['obsTime'].dropna().astype(str)
    obstime_counts = vals.value_counts().to_dict()
    unique_vals = pd.Index(vals.unique())
    sort_df = pd.DataFrame({'value': unique_vals})
    sort_df['dt'] = pd.to_datetime(sort_df['value'], errors='coerce')
    # Sort by parsed datetime (NaT last), then by string value
    sort_df = sort_df.sort_values(by=['dt', 'value'], na_position='last')
    available_obstimes = sort_df['value'].tolist()
    return available_obstimes, obstime_counts

@app.route('/', methods=['GET', 'POST'])
def index():
    file_content = None
    plot_urls = None
    selected_df_html = None
    selected_rows = None
    selected_columns = None
    modifiers_summary = None
    error = None
    available_obstimes = None
    obstime_counts = None
    selected_obstime = session.get('selected_obstime')
    current_filename = session.get('last_filename')
    picked_by_obstime = session.get('picked_by_obstime') or {}
    picked_id = picked_by_obstime.get(str(selected_obstime)) if selected_obstime else None
    selected_count_value = None
    fit_summary = None
    derived_rows = load_derived_rows()
    derived_columns = list(derived_rows[0].keys()) if derived_rows else None
    # Preserve original column order across requests (used for rendering and downloads)
    original_columns = session.get('original_columns')
    
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part in the request', 'global')
            return redirect(request.url)
            
        file = request.files['file']
        
        # If user does not select file, browser also
        # submit an empty part without filename
        if file.filename == '':
            flash('No file selected', 'global')
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            try:
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                # Remember last uploaded file in session for download route
                session['last_file_path'] = filepath
                session['last_filename'] = filename
                # Clear any prior row selection when a new file is uploaded
                session.pop('selected_indices', None)
                # Clear any prior group selection when a new file is uploaded
                session.pop('selected_obstime', None)
                
                # Read file into DataFrame
                df = read_file_to_dataframe(filepath, filename)
                
                # Compute available obstime groups for UI with counts and smart sorting
                available_obstimes, obstime_counts = build_obstime_info(df)
                session['available_obstimes'] = available_obstimes
                session['obstime_counts'] = obstime_counts
                # Save original column order for later rendering and downloads
                session['original_columns'] = [c for c in df.columns if c != '_row_id']
                
            except Exception as e:
                error = f"Error processing file: {str(e)}"
                app.logger.error(traceback.format_exc())
                flash(error, 'global')
        else:
            flash('File type not allowed. Allowed types are: ' + ', '.join(app.config['ALLOWED_EXTENSIONS']), 'global')

    # On GET (or after POST handling), if a file is already uploaded, build previews
    last_path = session.get('last_file_path')
    last_name = session.get('last_filename')
    if (request.method == 'GET') and last_path and last_name and os.path.exists(last_path):
        try:
            df = read_file_to_dataframe(last_path, last_name)
            # Available obstime groups for selection UI with counts and smart sorting
            available_obstimes, obstime_counts = build_obstime_info(df)
            session['available_obstimes'] = available_obstimes
            session['obstime_counts'] = obstime_counts
            # Preserve original column order for rendering derived table and downloads
            original_columns = [c for c in df.columns if c != '_row_id']
            session['original_columns'] = original_columns
            # If a group is selected, filter and prepare table and plots
            if selected_obstime is not None:
                # Compare as string for robust matching via session storage
                selected_mask = df['obsTime'].astype(str) == str(selected_obstime)
                selected_df = df[selected_mask].copy()
                # Add a stable row identifier for exclusion handling
                selected_df = selected_df.copy()
                selected_df['_row_id'] = selected_df.index.astype(str)
                # Load current exclusions for this group
                excluded_by_obstime = session.get('excluded_by_obstime') or {}
                group_excluded = set((excluded_by_obstime.get(str(selected_obstime)) or []))
                # Build preview rows (first 50) for UI checkboxes
                preview_df = selected_df.head(50)
                selected_columns = [c for c in preview_df.columns if c != '_row_id']
                selected_rows = [
                    {
                        '_row_id': str(row['_row_id']),
                        **{col: row[col] for col in selected_columns}
                    }
                    for _, row in preview_df.iterrows()
                ]
                # Also render a basic HTML preview table (first 50 rows)
                try:
                    selected_df_html = preview_df.drop(columns=['_row_id']).to_html(
                        classes='table table-striped table-bordered table-hover', index=False
                    )
                except Exception:
                    selected_df_html = None
                # Apply exclusions for plotting
                selected_df_filtered = selected_df[~selected_df['_row_id'].isin(group_excluded)].copy()
                if not selected_df_filtered.empty:
                    selected_count_value = len(selected_df_filtered)
                    # Use the picked row to initialize output reference for plotting when available
                    output_row_series = None
                    if picked_id:
                        sel_row = selected_df_filtered[selected_df_filtered['_row_id'] == str(picked_id)]
                        if sel_row.empty:
                            # fall back to any row with that id from the unfiltered set (may be excluded)
                            sel_row = selected_df[selected_df['_row_id'] == str(picked_id)]
                        if not sel_row.empty:
                            output_row_series = sel_row.iloc[0]
                    # Pass unfiltered group as full_group so excluded points can be drawn distinctly
                    plot_urls = generate_group_plots(selected_df_filtered, output_row=output_row_series, full_group=selected_df)
                    # Compute linear fits for photAp->RA and photAp->Dec on filtered data
                    #fit = compute_linear_fits(selected_df_filtered)
                    #if fit:
                    #    fit_summary = fit
                else:
                    plot_urls = None
                    selected_df_html = None
                    flash('Selected obstime has no matching rows in the current file.', 'plot')
            selected_indices = session.get('selected_indices')
            if selected_indices:
                try:
                    selected_df = df.iloc[selected_indices]
                    modifiers = session.get('selection_modifiers')
                    if modifiers:
                        # Apply modifiers and prepare a summary
                        selected_df = apply_selection_modifiers(selected_df, modifiers)
                        parts = []
                        for m in modifiers:
                            t = (m or {}).get('type')
                            if t == 'drop_na':
                                parts.append('drop NA')
                            elif t == 'head_n':
                                parts.append(f"head({m.get('n', 10)})")
                            else:
                                parts.append(t or 'unknown')
                        modifiers_summary = ', '.join(parts) if parts else None
                    selected_df_html = selected_df.head(50).to_html(classes='table table-striped table-bordered table-hover', index=False)
                except Exception:
                    selected_df_html = None
        except Exception:
            pass

    return render_template('index.html', 
                         file_content=file_content, 
                         plot_urls=plot_urls,
                         selected_df_html=selected_df_html,
                         selected_rows=selected_rows,
                         selected_columns=selected_columns,
                         excluded_ids=list(group_excluded) if ('group_excluded' in locals()) else [],
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
                         selected_count=selected_count_value)


@app.route('/download', methods=['GET'])
def download_dataframe():
    """Download the most recently uploaded DataFrame as a tab-delimited text file."""
    filepath = session.get('last_file_path')
    filename = session.get('last_filename')

    if not filepath or not filename or not os.path.exists(filepath):
        flash('No file available to download. Please upload a file first.', 'global')
        return redirect(url_for('index'))
    try:
        df = read_file_to_dataframe(filepath, filename)
        txt_data = df.to_csv(sep='\t', index=False)
        response = make_response(txt_data)
        download_name = os.path.splitext(filename)[0] + '.txt'
        response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename="{download_name}"'
        return response
    except Exception as e:
        flash(f'Error generating download: {str(e)}', 'global')
        return redirect(url_for('index'))

@app.route('/update_exclusions', methods=['POST'])
def update_exclusions():
    """Update the set of excluded row IDs for the current selected obstime group."""
    filepath = session.get('last_file_path')
    filename = session.get('last_filename')
    if not filepath or not filename or not os.path.exists(filepath):
        flash('No file loaded. Please upload a file first.', 'global')
        return redirect(url_for('index'))
    obstime = request.form.get('obstime')
    # Collect all checkbox values for excluded rows
    exclude_ids = request.form.getlist('exclude_id')
    # Collect the currently picked row for initializing plotting/derived
    selected_id = request.form.get('selected_id')
    excluded_by_obstime = session.get('excluded_by_obstime') or {}
    picked_by_obstime = session.get('picked_by_obstime') or {}
    if obstime:
        excluded_by_obstime[str(obstime)] = [str(x) for x in exclude_ids]
        session['excluded_by_obstime'] = excluded_by_obstime
        if selected_id:
            picked_by_obstime[str(obstime)] = str(selected_id)
            session['picked_by_obstime'] = picked_by_obstime
            flash(f"Updated: picked row set and {len(exclude_ids)} exclusion(s) applied.", 'exclusions')
        else:
            flash(f"Updated exclusions for obstime {obstime}: {len(exclude_ids)} row(s) excluded.", 'exclusions')
    return redirect(url_for('index'))

@app.route('/clear_exclusions', methods=['POST'])
def clear_exclusions():
    """Clear exclusions for the current selected obstime group."""
    obstime = request.form.get('obstime')
    excluded_by_obstime = session.get('excluded_by_obstime') or {}
    if obstime and str(obstime) in excluded_by_obstime:
        excluded_by_obstime.pop(str(obstime), None)
        session['excluded_by_obstime'] = excluded_by_obstime
        flash(f"Cleared exclusions for obstime {obstime}.", 'exclusions')
    return redirect(url_for('index'))

@app.route('/select_rows', methods=['POST'])
def select_rows():
    """Accept a string of row indices/ranges and store selection in session, then redirect back to index to preview."""
    filepath = session.get('last_file_path')
    filename = session.get('last_filename')
    if not filepath or not filename or not os.path.exists(filepath):
        flash('No file loaded. Please upload a file first.')
        return redirect(url_for('index'))

    try:
        df = read_file_to_dataframe(filepath, filename)
        raw = request.form.get('row_indices', '')
        indices = parse_row_indices(raw, len(df))
        if not indices:
            session.pop('selected_indices', None)
            flash('No valid row indices provided. Expect comma-separated indices or ranges like 0,2,5-8.', 'global')
        else:
            session['selected_indices'] = indices
            flash(f'Selected {len(indices)} row(s). Preview updated below.', 'global')
    except Exception as e:
        flash(f'Error selecting rows: {str(e)}', 'global')

    return redirect(url_for('index'))

@app.route('/clear_selection', methods=['POST'])
def clear_selection():
    session.pop('selected_indices', None)
    flash('Selection cleared.', 'global')
    return redirect(url_for('index'))

@app.route('/select_group', methods=['POST'])
def select_group():
    """Store the selected obsTime group in session and redirect to index."""
    filepath = session.get('last_file_path')
    filename = session.get('last_filename')
    if not filepath or not filename or not os.path.exists(filepath):
        flash('No file loaded. Please upload a file first.', 'group')
        return redirect(url_for('index'))
    value = request.form.get('selected_obstime')
    if value is None or value == '':
        session.pop('selected_obstime', None)
        flash('Cleared group selection.', 'group')
    else:
        session['selected_obstime'] = value
        flash(f"Selected group obstime = {value}", 'group')
    return redirect(url_for('index'))

@app.route('/download_selected', methods=['GET'])
def download_selected():
    filepath = session.get('last_file_path')
    filename = session.get('last_filename')
    indices = session.get('selected_indices')
    if not filepath or not filename or not os.path.exists(filepath):
        flash('No file loaded. Please upload a file first.')
        return redirect(url_for('index'))
    if not indices:
        flash('No rows selected to download.')
        return redirect(url_for('index'))

    try:
        df = read_file_to_dataframe(filepath, filename)
        selected_df = df.iloc[indices]
        modifiers = session.get('selection_modifiers')
        if modifiers:
            selected_df = apply_selection_modifiers(selected_df, modifiers)
        txt_data = selected_df.to_csv(sep='\t', index=False)
        response = make_response(txt_data)
        base = os.path.splitext(filename)[0]
        response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename="{base}_selected.txt"'
        return response
    except Exception as e:
        flash(f'Error generating selected download: {str(e)}')
        return redirect(url_for('index'))

    # (nothing else here)

@app.route('/set_modifiers', methods=['POST'])
def set_modifiers():
    """Set simple selection modifiers; acts as a scaffold for more complex future logic."""
    mods = []
    # Checkbox: drop_na
    if request.form.get('mod_drop_na') == 'on':
        how = request.form.get('mod_drop_na_how', 'any')
        mods.append({'type': 'drop_na', 'how': how})
    # Numeric: head_n
    head_n_val = request.form.get('mod_head_n')
    if head_n_val:
        try:
            n = int(head_n_val)
            if n >= 0:
                mods.append({'type': 'head_n', 'n': n})
        except ValueError:
            pass

    session['selection_modifiers'] = mods if mods else None
    if mods:
        flash('Modifiers applied to selection.')
    else:
        flash('No modifiers set; selection will be unmodified.')
    return redirect(url_for('index'))

@app.route('/clear_modifiers', methods=['POST'])
def clear_modifiers():
    session.pop('selection_modifiers', None)
    flash('Modifiers cleared.')
    return redirect(url_for('index'))

def generate_group_plots(group, output_row=None, full_group=None):
    """Generate combined RA/Dec vs photAp plot with weighted linear fits.
    Returns dict with key 'coords_photAp' containing a base64 data URL.
    """

    # Preferred subset with uncertainties for weighted fit
    group_orig = group.dropna(subset=["photAp", "ra", "dec", "rmsRA", "rmsDec"]).copy()
    group_fit = group.dropna(subset=["photAp", "ra", "dec", "rmsRA", "rmsDec"]).copy()
    urls = {}
    if group_orig.empty:
        return urls
    
    # first for the downselected (to be fit) data
    coords = SkyCoord(ra=group_fit['ra'], dec=group_fit['dec'], unit=u.deg, frame = 'icrs')
    coords_rms = SkyCoord(ra=group_fit['rmsRA'], dec=group_fit['rmsDec'], unit=u.arcsec, frame = 'icrs')

    # Build full (unfiltered) subset if provided, for visualizing excluded points
    fullcoords = None
    fullcoords_rms = None
    fullx = None
    excluded_subset = None
    if isinstance(full_group, pd.DataFrame) and not full_group.empty:
        full_orig = full_group.dropna(subset=["photAp", "ra", "dec", "rmsRA", "rmsDec"]).copy()
        if not full_orig.empty:
            fullcoords = SkyCoord(ra=full_orig['ra'], dec=full_orig['dec'], unit=u.deg, frame = 'icrs')
            fullcoords_rms = SkyCoord(ra=full_orig['rmsRA'], dec=full_orig['rmsDec'], unit=u.arcsec, frame = 'icrs')
            fullx = full_orig["photAp"].astype(float)
            # Determine excluded points by _row_id if present; otherwise by index string
            def _ids(df):
                return set(df['_row_id'].astype(str)) if ('_row_id' in df.columns) else set(df.index.astype(str))
            try:
                inc_ids = _ids(group_orig)
                all_ids = _ids(full_orig)
                excl_ids = list(all_ids - inc_ids)
                if excl_ids:
                    key = '_row_id' if ('_row_id' in full_orig.columns) else None
                    if key:
                        excluded_subset = full_orig[full_orig['_row_id'].astype(str).isin(excl_ids)].copy()
                    else:
                        excluded_subset = full_orig.loc[full_orig.index.astype(str).isin(excl_ids)].copy()
            except Exception:
                excluded_subset = None
    
    if len(group_fit) >= 2:
        try:
            # Define convenience variables for plotting the list of aperture sizes
            x = group_fit["photAp"].astype(float)
            # fullx already set above

            # Linear fits with weights (1/sigma). Fallback to unweighted if needed.
            try:
                ra_fit, C_ra = np.polyfit(x, coords.ra.deg, 1, w=1/coords_rms.ra.deg, cov='unscaled')
                dec_fit, C_dec = np.polyfit(x, coords.dec.deg, 1, w=1/coords_rms.dec.deg, cov='unscaled')
            except Exception:
                ra_fit, C_ra = np.polyfit(x, coords.ra.deg, 1, cov='unscaled')
                dec_fit, C_dec = np.polyfit(x, coords.dec.deg, 1, cov='unscaled')

            # Format outputs to give the uncertainties to two digits, and the RA/Dec values
            # to be at that same precision (accounting for unit differences)
            rms_ra = float(output_row['rmsRA'])
            raerr_sigfigs = abs(np.floor(np.log10(max(rms_ra * 2.0, 1e-12)))) + 1
            ra0_err = round(rms_ra * 2.0, int(raerr_sigfigs))
            ra0_ploterr = ra0_err
            ra_sig_figs = abs(np.floor(np.log10(max(ra0_ploterr / 3600.0, 1e-12)))) + 1
            ra0 = round(np.polyval(ra_fit, 0.0), int(ra_sig_figs))
            rms_dec = float(output_row['rmsDec'])
            decerr_sigfigs = abs(np.floor(np.log10(max(rms_dec * 2.0, 1e-12)))) + 1
            dec0_err = round(rms_dec * 2.0, int(decerr_sigfigs))
            dec0_ploterr = dec0_err
            dec_sig_figs = abs(np.floor(np.log10(max(dec0_ploterr / 3600.0, 1e-12)))) + 1
            dec0 = round(np.polyval(dec_fit, 0.0), int(dec_sig_figs))
            obs_time = str(output_row.get('obsTime', 'Selected group'))

            ### Plot variables: RA as (RA_i - RA_0)*cos(Dec_0), where RA_0, Dec_0 is at zero aperture solution
            ### RA_i is individual measurements
            ra_y = np.cos(np.radians(dec0))*(coords.ra.deg - ra0)*3600 # convert from deg to arcseconds
            ra_y_err = coords_rms.ra.arcsec # errors already properly defined

            # Excluded RA data (from full set minus included)
            if fullcoords is not None and excluded_subset is not None and not excluded_subset.empty:
                ex_coords = SkyCoord(ra=excluded_subset['ra'], dec=excluded_subset['dec'], unit=u.deg, frame='icrs')
                ex_coords_rms = SkyCoord(ra=excluded_subset['rmsRA'], dec=excluded_subset['rmsDec'], unit=u.arcsec, frame='icrs')
                ex_x = excluded_subset['photAp'].astype(float)
                ex_ra_y = np.cos(np.radians(dec0)) * (ex_coords.ra.deg - ra0) * 3600
                ex_ra_y_err = ex_coords_rms.ra.arcsec

            # Format Dec plot variables as Dec_i - Dec_0, in arcseconds
            dec_y = (coords.dec.deg - dec0)*3600
            dec_y_err = coords_rms.dec.arcsec

            # Excluded Dec data
            if fullcoords is not None and excluded_subset is not None and not excluded_subset.empty:
                ex_dec_y = (ex_coords.dec.deg - dec0) * 3600
                ex_dec_y_err = ex_coords_rms.dec.arcsec

            ### add 0 to  array of aperture sizes (x) for plotting the fit 
            plot_x_extrapolate = np.append([0.0], x)

            # Replace original RA/Dec and rms values with the new zero aperture fit values
            output_row['ra'] = ra0
            output_row['dec'] = dec0
            output_row['rmsRA'] = ra0_err
            output_row['rmsDec'] = dec0_err
            output_row['notes'] = 'e' + output_row['notes']
            # Stage preliminary derived entry in session for this obstime
            try:
                # Align output row to the original dataframe structure:
                # - keep only original columns from the current group
                # - ensure helper columns like _row_id are removed
                # - keep original photAp (do NOT force to 0)
                base_cols = [c for c in group.columns if c != '_row_id']
                # Start with a copy and align to base columns
                aligned = output_row.copy()
                # Apply derived values while maintaining original photAp
                aligned['ra'] = ra0
                aligned['dec'] = dec0
                aligned['rmsRA'] = ra0_err
                aligned['rmsDec'] = dec0_err
                # Build dict in base_cols order, filling missing with None and stripping helpers
                row_dict = {}
                for col in base_cols:
                    v = aligned[col] if col in aligned else None
                    # Normalize NaN and numpy types
                    if isinstance(v, float) and np.isnan(v):
                        v = None
                    elif hasattr(v, 'item'):
                        v = v.item()
                    row_dict[col] = v
                # Persist staged entry keyed by obstime
                prelim = session.get('prelim_derived_by_obstime') or {}
                prelim[str(obs_time)] = row_dict
                session['prelim_derived_by_obstime'] = prelim
                # Also remember which source row was picked (if available)
                picked = session.get('picked_by_obstime') or {}
                if '_row_id' in output_row:
                    picked[str(obs_time)] = str(output_row['_row_id'])
                    session['picked_by_obstime'] = picked
            except Exception:
                pass
            # Plotting for user inspection of data, fit quality
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6))
            fig.suptitle(f"{obs_time} – Linear Fit")
            ax1.set_title(f"RA: ${ra0}^\circ$")
            ax1.errorbar(0,0,ra0_ploterr,label='0 Aperture Extrapolation',fmt='o')
            if fullcoords is not None and excluded_subset is not None and not excluded_subset.empty:
                ax1.errorbar(ex_x, ex_ra_y, ex_ra_y_err, label="Excluded RA data", fmt='s', c='r')
            ax1.errorbar(x, ra_y, ra_y_err, label="Included RA data",fmt='d',c='k',mew=3,zorder=10)
            ax1.plot(x, (np.polyval(ra_fit, x)-ra0)*3600, label="RA fit", color="k")
            ax1.plot(plot_x_extrapolate, (np.polyval(ra_fit, plot_x_extrapolate)-ra0)*3600, color="black",ls='--')
            ax1.set_ylabel("$\Delta$RA*cos(Dec) (arcseconds)")
            ax1.legend(loc=(1.1,0.35))
            ax2.set_title(f"Dec: ${dec0}^\circ$")
            ax2.errorbar(0,0,dec0_ploterr,label='0 Aperture Extrapolation',fmt='o')
            if fullcoords is not None and excluded_subset is not None and not excluded_subset.empty:
                ax2.errorbar(ex_x, ex_dec_y, ex_dec_y_err, label="Excluded Dec data", fmt='s', c='r')
            ax2.errorbar(x, dec_y, dec_y_err, label="Included Dec data",fmt='s',c='k',mew=3,zorder=10)
            ax2.plot(x, (np.polyval(dec_fit, x)-dec0)*3600, label="Dec fit", color="black")
            ax2.plot(plot_x_extrapolate, (np.polyval(dec_fit, plot_x_extrapolate)-dec0)*3600, color="black",ls='--')
            ax2.set_xlabel("Photometric Aperture (photAp)")
            ax2.set_ylabel("$\Delta$Dec (arcseconds)")
            ax2.legend(loc=(1.1,0.35))
            buf = io.BytesIO()
            plt.tight_layout()
            #plt.ion()
            #plt.show()
            fig.savefig(buf, format='png')
            plt.close(fig)
            buf.seek(0)
            # Use ASCII decode and strip to avoid any stray whitespace/newlines in data URL
            b64 = base64.b64encode(buf.getvalue()).decode('ascii').strip()
            urls['coords_photAp'] = f"data:image/png;base64,{b64}"

        except Exception as e:
            # If numpy or fitting fails, continue without regression
            print(e)
            pass

        return urls


    # Not enough valid points to compute fits; return empty dict
    return urls

def compute_linear_fits(group):
    """Compute linear fits for RA vs photAp and Dec vs photAp on given DataFrame.
    Returns dict: {'ra': {'m': m, 'b': b, 'r2': r2}, 'dec': {...}} or None if insufficient data.
    """
    # Drop rows with missing values required for plotting
    group_orig = group.dropna(subset=["photAp", "ra", "dec", "rmsRA", "rmsDec"]).copy()

    # first for the downselected (to be fit) data
    coords = SkyCoord(ra=group['ra'], dec=group['dec'], unit=u.deg, frame = 'icrs')
    coords_rms = SkyCoord(ra=group['rmsRA'], dec=group['rmsDec'], unit=u.arcsec, frame = 'icrs')

    # while retaining a full copy for plotting the entire dataset in the background
    fullcoords = SkyCoord(ra=group_orig['ra'], dec=group_orig['dec'], unit=u.deg, frame = 'icrs')
    fullcoords_rms = SkyCoord(ra=group_orig['rmsRA'], dec=group_orig['rmsDec'], unit=u.arcsec, frame = 'icrs')
    output_row = group.iloc[0]
    if group.empty or len(group) >= 2:
        try:
            # Define convenience variables for plotting the list of aperture sizes
            x = group["photAp"].astype(float)
            fullx = group_orig["photAp"].astype(float)

            # Linear fits, in quirk of np.polyfit logic, the propoer Gaussian weights 
            # are 1/sigma instead of normal 1/sigma^2
            ra_fit, C_ra = np.polyfit(x, coords.ra.deg, 1,w=1/coords_rms.ra.deg,cov='unscaled')
            dec_fit, C_dec = np.polyfit(x, coords.dec.deg, 1,w=1/coords_rms.dec.deg,cov='unscaled')

            # Format outputs to give the uncertainties to two digits, and the RA/Dec values
            # to be at that same precision (accounting for unit differences)
            raerr_sigfigs = np.abs(np.floor(np.log10(output_row['rmsRA'].astype(float)*2)))+1
            ra0_err = round(output_row['rmsRA'].astype(float)*2,int(raerr_sigfigs.iloc[0]))
            ra0_ploterr = ra0_err
            ra_sig_figs = np.abs(np.floor(np.log10(ra0_ploterr/3600)))+1
            ra0 = round(np.polyval(ra_fit, 0),int(ra_sig_figs.iloc[0]))
            decerr_sigfigs = np.abs(np.floor(np.log10(output_row['rmsDec'].astype(float)*2)))+1
            dec0_err = round(output_row['rmsDec'].astype(float)*2,int(decerr_sigfigs.iloc[0]))
            dec0_ploterr = dec0_err
            dec_sig_figs = np.abs(np.floor(np.log10(dec0_ploterr/3600)))+1
            dec0 = round(np.polyval(dec_fit, 0),int(dec_sig_figs.iloc[0]))

            ### Plot variables: RA as (RA_i - RA_0)*cos(Dec_0), where RA_0, Dec_0 is at zero aperture solution
            ### RA_i is individual measurements
            ra_y = np.cos(np.radians(dec0))*(coords.ra.deg - ra0)*3600 # convert from deg to arcseconds
            ra_y_err = coords_rms.ra.arcsec # errors already properly defined

            # Apply same logic to the full (untrimmed) RA data
            fullra_y = np.cos(dec0)*(fullcoords.ra.deg - ra0)*3600
            fullra_y_err = fullcoords_rms.ra.arcsec

            # Format Dec plot variables as Dec_i - Dec_0, in arcseconds
            dec_y = (coords.dec.deg - dec0)*3600
            dec_y_err = coords_rms.dec.arcsec

            # Same for untrimmed data
            fulldec_y = (fullcoords.dec.deg - dec0)*3600
            fulldec_y_err = fullcoords_rms.dec.arcsec

            ### add 0 to  array of aperture sizes (x) for plotting the fit 
            plot_x_extrapolate = np.append([0],x)

            # Replace original RA/Dec and rms values with the new zero aperture fit values
            output_row['ra'] = ra0
            output_row['dec'] = dec0
            output_row['rmsRA'] = ra0_err
            output_row['rmsDec'] = dec0_err
        except Exception:
            return None        
    
    #if len(sub) < 2:
    #    return None
        
    # Fit RA = m_ra * photAp + b_ra
    #x = sub['photAp'].astype(float).values
    #y_ra = sub['ra'].astype(float).values
    #y_dec = sub['dec'].astype(float).values

    #try:
    #    m_ra, b_ra = np.polyfit(x, y_ra, 1,w=1/sub['rmsRA'].astype(float))
    #    y_pred_ra = m_ra * x + b_ra
    #    ss_res_ra = ((y_ra - y_pred_ra) ** 2).sum()
    #    ss_tot_ra = ((y_ra - y_ra.mean()) ** 2).sum()
    #    r2_ra = 1 - ss_res_ra / ss_tot_ra if ss_tot_ra != 0 else float('nan')

    #    m_dec, b_dec = np.polyfit(x, y_dec, 1,w=1/sub['rmsDec'].astype(float))
    #    y_pred_dec = m_dec * x + b_dec
    #    ss_res_dec = ((y_dec - y_pred_dec) ** 2).sum()
    #    ss_tot_dec = ((y_dec - y_dec.mean()) ** 2).sum()
    #    r2_dec = 1 - ss_res_dec / ss_tot_dec if ss_tot_dec != 0 else float('nan')
    #except Exception:
    #    return None
    return {
        'ra': {'b': float(ra0), 'err': float(ra0_err)},
        'dec': {'b': float(dec0), 'err': float(dec0_err)},
    }

@app.route('/select_single_entry', methods=['POST'])
def select_single_entry():
    """Confirm and persist the staged preliminary derived entry for the current obstime.

    The staging is produced by generate_group_plots() using the picked row.
    """
    filepath = session.get('last_file_path')
    filename = session.get('last_filename')
    obstime = session.get('selected_obstime')
    if not filepath or not filename or not os.path.exists(filepath) or obstime is None:
        flash('No file loaded. Please upload a file first.', 'global')
        return redirect(url_for('index'))
    try:
        prelim = (session.get('prelim_derived_by_obstime') or {}).get(str(obstime))
        if not prelim:
            flash('No staged derived entry available. Adjust selection/exclusions to generate a plot first.', 'derived')
            return redirect(url_for('index'))
        # Append staged entry to derived rows
        derived_rows = load_derived_rows()
        derived_rows.append(prelim)
        save_derived_rows(derived_rows)
        # Clear staged entry for this obstime now that it is persisted
        prelim_all = session.get('prelim_derived_by_obstime') or {}
        prelim_all.pop(str(obstime), None)
        session['prelim_derived_by_obstime'] = prelim_all
        flash('Derived entry added. You can download or manage derived entries below.', 'derived')
    except Exception as e:
        flash(f'Error creating derived entry: {str(e)}', 'derived')
    return redirect(url_for('index'))

@app.route('/delete_derived', methods=['POST'])
def delete_derived():
    """Delete selected rows from the accumulated derived DataFrame in session."""
    rows = load_derived_rows()
    to_delete = request.form.getlist('delete_idx')
    if not to_delete:
        flash('No derived rows selected for deletion.', 'derived')
        return redirect(url_for('index'))
    # Convert to set of ints and remove in reverse order to preserve indices
    try:
        idxs = sorted({int(i) for i in to_delete}, reverse=True)
        for i in idxs:
            if 0 <= i < len(rows):
                rows.pop(i)
        save_derived_rows(rows)
        flash(f'Deleted {len(idxs)} derived row(s).', 'derived')
    except Exception as e:
        flash(f'Error deleting derived rows: {str(e)}', 'derived')
    return redirect(url_for('index'))

@app.route('/clear_derived', methods=['POST'])
def clear_derived():
    # Remove persisted file if exists
    path = _derived_store_path()
    try:
        if os.path.exists(path):
            os.remove(path)
        flash('Cleared all derived rows.', 'derived')
    except Exception as e:
        flash(f'Error clearing derived rows: {str(e)}', 'derived')
    return redirect(url_for('index'))

@app.route('/download_derived', methods=['GET'])
def download_derived():
    rows = load_derived_rows()
    if not rows:
        flash('No derived rows to download.', 'derived')
        return redirect(url_for('index'))
    try:
        # Preserve original column order if available
        cols = session.get('original_columns')
        df = pd.DataFrame(rows, columns=cols) if cols else pd.DataFrame(rows)
        psv = format_psv_aligned(df)
        response = make_response(psv)
        response.headers['Content-Type'] = 'text/plain; charset=utf-8'
        response.headers['Content-Disposition'] = 'attachment; filename="derived.psv"'
        return response
    except Exception as e:
        flash(f'Error downloading derived data: {str(e)}', 'derived')
        return redirect(url_for('index'))

@app.route('/download_derived_xml', methods=['GET'])
def download_derived_xml():
    rows = load_derived_rows()
    if not rows:
        flash('No derived rows to download.', 'derived')
        return redirect(url_for('index'))
    try:
        # Preserve original column order if available
        cols = session.get('original_columns')
        df = pd.DataFrame(rows, columns=cols) if cols else pd.DataFrame(rows)
        # Strip whitespace inside text entries and replace NaN/None with empty string
        df = df.applymap(lambda v: '' if pd.isna(v) else (v.strip() if isinstance(v, str) else v))
        xml_data = df.to_xml(index=False, root_name='obsData', row_name='optical')
        # Pretty-print XML: one tag per line with indentation
        parsed = minidom.parseString(xml_data)
        pretty_xml = parsed.toprettyxml(indent="  ")
        # Remove blank lines introduced by toprettyxml while keeping indentation
        pretty_no_blank = "\n".join([line for line in pretty_xml.splitlines() if line.strip()]) + "\n"
        response = make_response(pretty_no_blank)
        response.headers['Content-Type'] = 'application/xml; charset=utf-8'
        response.headers['Content-Disposition'] = 'attachment; filename="derived.xml"'
        return response
    except Exception as e:
        flash(f'Error downloading derived data as XML: {str(e)}', 'derived')
        return redirect(url_for('index'))

def format_psv_aligned(df: pd.DataFrame) -> str:
    """Return a pipe-delimited string with whitespace padding so columns are aligned.
    Header is included and padded to the max width across values and header per column.
    """
    if df is None or df.empty:
        return ''
    # Convert values to strings, replacing NaN/None with empty string
    str_df = df.applymap(lambda v: '' if pd.isna(v) else str(v))
    # Compute max width per column including header
    widths = []
    for col in str_df.columns:
        col_width = max(len(str(col)), int(str_df[col].str.len().max() or 0))
        widths.append(col_width)
    # Build header
    header = '|'.join(str(col).ljust(widths[i]) for i, col in enumerate(str_df.columns))
    # Build rows
    lines = [header]
    for _, row in str_df.iterrows():
        line = '|'.join(str(row[i]).ljust(widths[i]) for i in range(len(widths)))
        lines.append(line)
    return '\n'.join(lines) + '\n'

def _derived_store_path():
    token = session.get('derived_token')
    if not token:
        token = uuid.uuid4().hex
        session['derived_token'] = token
    return os.path.join(app.config['UPLOAD_FOLDER'], f"derived_{token}.json")

def load_derived_rows():
    path = _derived_store_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def save_derived_rows(rows):
    path = _derived_store_path()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(rows, f)
    except Exception as e:
        app.logger.error(f"Failed to save derived rows: {e}")

if __name__ == '__main__':
    app.run(debug=True)
