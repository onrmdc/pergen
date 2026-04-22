"""Pergen operator CLI commands.

Each command is a small Python module that can be invoked via
``python -m backend.cli.<name>``. CLIs in this package are operator
tools (not user-facing API surfaces) and are intentionally kept
self-contained — they do not import the Flask app, only the
repositories and config they need.
"""
