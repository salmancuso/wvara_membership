#!/usr/bin/python3
"""
WVARA Membership - mod_wsgi entry point (ADDED 2026-11-04)
Served at https://salmancuso.com/tools/wvara
App lives at /var/www/html/salmancuso/tools/wvara
"""
import sys
import glob
import logging
import site

APP_DIR = '/var/www/html/salmancuso/tools/wvara'

# Log to Apache's error log
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# Add the virtual environment's site-packages to the path
# (finds python3.x automatically, so it keeps working if the server's Python version changes)
venv_site_packages = glob.glob(f'{APP_DIR}/venv/lib/python3*/site-packages')
if venv_site_packages:
    site.addsitedir(venv_site_packages[0])
    logging.info(f"WVARA: using venv at {venv_site_packages[0]}")
else:
    logging.error(f"WVARA: no venv found under {APP_DIR}/venv")

# Add application directory to path
sys.path.insert(0, APP_DIR)

# Import the Flask app
try:
    from app import app as application
    logging.info("WVARA: Flask app imported successfully")
except Exception as e:
    logging.error(f"WVARA: failed to import Flask app: {e}")
    raise
