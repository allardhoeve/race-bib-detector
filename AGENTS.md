# Claude Code Guidelines

## Python Environment

This project uses a virtual environment. Always use the venv when running Python commands:

```bash
# Use these paths for Python and pip:
venv/bin/python
venv/bin/pip

# Examples:
venv/bin/pip install -r requirements.txt
venv/bin/python scan_album.py <album_url>
venv/bin/python web_viewer.py
```

Do NOT use `python`, `python3`, `pip`, or `pip3` directly - they won't use the correct environment.

## Entrypoints

If you create entrypoints (scripts you can run), always:
- Start with a /usr/bin/env python hashbang
- Chmod them 755

## Photo Identification

Photos are identified by an 8-character **photo hash** (e.g., `298706ee`), not by database ID. This hash is derived from the photo URL and remains stable regardless of:
- When the photo was scanned
- Database ID changes
- Re-scanning the album

**Always use photo hashes when:**
- Referring to photos in code, UI, and conversations
- Building URLs (e.g., `/photo/298706ee`)
- Logging and debugging
- Discussing specific photos with users

The hash is computed from the photo URL using SHA-256 (first 8 chars): `hashlib.sha256(photo_url.encode()).hexdigest()[:8]`

## Rescanning Single Photos

To rescan a single photo after making code changes, use:

```bash
# By photo hash (8 hex characters):
venv/bin/python scan_album.py 6dde41fd

# By 1-based index (photo number in database order):
venv/bin/python scan_album.py 47
```

This is useful for testing detection changes on specific photos without rescanning the entire album.

## Configuration

All tunable detection parameters are centralized in `config.py`. Key values include:

- `TARGET_WIDTH`: Image preprocessing width (default: 1280)
- `WHITE_REGION_CONFIDENCE_THRESHOLD`: OCR confidence for white regions (default: 0.4)
- `MEDIAN_BRIGHTNESS_THRESHOLD`: Brightness filter (default: 120)
- `MIN_DETECTION_AREA_RATIO`: Minimum bib size relative to region (default: 0.10)

See `config.py` for the full list of configurable values.
