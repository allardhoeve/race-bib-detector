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
