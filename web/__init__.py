"""
Web interface module for the bib scanner.

Provides a Flask-based web UI for browsing scanned photos and their
detected bib numbers.
"""

from .app import create_app, main

__all__ = ["create_app", "main"]
