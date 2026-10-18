# api/index.py  – Vercel entry point for the Flask app
# This file exposes the Flask app as a WSGI handler for Vercel's Python runtime.
# All logic remains in app.py; this file only imports and re-exports it.

import sys
import os

# Ensure the project root is on the Python path so 'app' can be imported.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Vercel requires the WSGI callable to be named 'app'.
# Nothing else needs to change here.
