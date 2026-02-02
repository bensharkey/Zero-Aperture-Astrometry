# Zero-Aperture Astrometry Correction Tool

A Flask web app to derive zero-aperture astrometric corrections from ADES-format observations. Upload an ADES PSV or XML file, select an `obsTime` group, pick the calibration aperture, exclude outliers, review the linear fits, and download a corrected ADES entry (PSV or XML) preserving the original column order.

## Features

- **ADES upload (PSV/XML)**: Accepts `.psv` and `.xml` ADES files only.
- **Group selection by `obsTime`**: Smart, datetime-aware sorting and per-group counts.
- **Pick and exclude**: Choose the calibration aperture entry; exclude points from fits.
- **Plot with context**: Shows included points (black) and excluded points (red), with linear fits and zero-aperture extrapolation marker.
- **Derived entry staging**: Creates a staged zero-aperture–corrected entry using the picked row’s schema, maintaining the original `photAp`.
- **Preserve column order**: Derived table and downloads retain the original file’s column order.
- **Downloads**:
  - PSV: pipe-delimited, width-aligned, original column order.
  - XML: pretty-printed, one tag per line, no blank lines, original column order.

## Requirements

- Python 3.9+
- See `requirements.txt` for Python packages.

## Installation

1. Create a virtual environment (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running

```bash
python app.py
```

Open http://127.0.0.1:5000 in your browser.

### Production via Docker Compose

1. Build and start the stack in detached mode:
   ```bash
   docker-compose up -d
   ```
   This uses the provided `Dockerfile`, `_app_entry`, and `docker-compose.yml` to run Gunicorn/Uvicorn inside a container.
2. Tail the service logs to verify startup:
   ```bash
   docker-compose logs -f web
   ```
   The `-f` flag stands for “follow”, causing the command to stream log output continuously (similar to `tail -f`). Omit `-f` if you only want a snapshot of existing logs.

## Usage

1. Upload an ADES `.psv` or `.xml` file. See examples directory for nonscientific psv and xml files that read correctly.
2. Choose an `obsTime` group to analyze.
3. In the table, use:
   - **Select Aperture** to pick the entry matching the stellar catalog extraction aperture/PSF used for the reference frame.
   - **Exclude?** to remove outliers from the linear fits.
4. Review the plot. Excluded points are shown in red; included points in black.
5. Click “Store Above Fit for Download?” to stage a derived entry for the group.
6. Review and download the derived data as PSV or XML.

Notes:

- Derived rows are stored per-session under `uploads/derived_<token>.json`.
- Column order is taken from the original uploaded file.
- XML is formatted with indentation, one tag per line, with whitespace stripped from values.

## Project Structure

```
.
├── app.py                 # Flask app and routes
├── templates/
│   ├── base.html          # Base layout
│   └── index.html         # UI for upload, selection, plotting, downloads
├── uploads/               # Uploads and per-session derived store
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

## Configuration

- Max upload size: set in `app.config['MAX_CONTENT_LENGTH']` (default 16MB).
- Allowed extensions: `app.config['ALLOWED_EXTENSIONS'] = {'psv','xml'}`.
- Secret key: `app.secret_key` (development default in code, change for production).

## License

This project is open source and available under the [MIT License](LICENSE).

This project is open source and available under the MIT License.
