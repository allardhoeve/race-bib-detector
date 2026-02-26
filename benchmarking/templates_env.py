"""Shared Jinja2Templates instance — imported by app.py and route files."""

from pathlib import Path

from starlette.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).parent / "templates"

TEMPLATES = Jinja2Templates(directory=str(_TEMPLATES_DIR))
