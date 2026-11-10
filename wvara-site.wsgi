#!/usr/bin/python3
"""
WVARA Site Rebuild (TEST site) - mod_wsgi entry point (ADDED 2026-11-09)
Served at https://salmancuso.com/tools/wvara-site
App lives at /var/www/html/salmancuso/tools/wvara-site

Same as wvara.wsgi except APP_DIR and the log tag. Never point this at /tools/wvara:
that would run the LIVE tool's database from the test site.
"""
import sys
import glob
import logging
import site

APP_DIR = '/var/www/html/salmancuso/tools/wvara-site'

# Log to Apache's error log
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# Add the virtual environment's site-packages to the path
# (finds python3.x automatically, so it keeps working if the server's Python version changes)
venv_site_packages = glob.glob(f'{APP_DIR}/venv/lib/python3*/site-packages')
if venv_site_packages:
    site.addsitedir(venv_site_packages[0])
    logging.info(f"WVARA-SITE: using venv at {venv_site_packages[0]}")
else:
    logging.error(f"WVARA-SITE: no venv found under {APP_DIR}/venv")

# Add application directory to path
sys.path.insert(0, APP_DIR)

# Import the Flask app
try:
    from app import app as application
    logging.info("WVARA-SITE: Flask app imported successfully")
except Exception as e:
    logging.error(f"WVARA-SITE: failed to import Flask app: {e}")
    raise
