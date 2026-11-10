# WVARA Site: Server Setup Checklist

*Started November 9, 2026 (ADDED 2026-11-09). These are the exact steps used to stand up the **test site** at `https://salmancuso.com/tools/wvara-site` on salmancuso.com (Ubuntu 20.04, Apache 2.4.41, mod_wsgi on Python 3.8). Reuse them for the future WVARA server, changing paths and URLs as needed. Add each new setup step here as it happens (sync script cron, deploy key for `wvara-content`, ticker cron, and so on).*

---

## Before you start

- Run everything below **on the server as root**, except where it says "on the Mac."
- Apache's mod_wsgi is linked to **Python 3.8** (`ldd /usr/lib/apache2/modules/mod_wsgi.so | grep -i python` → `libpython3.8`). The venv **must** be built with `python3.8`, even though `python3` is 3.12.
- **Order matters.** Until Apache has the `WSGIScriptAlias` for the path, it serves files in the folder as plain downloads. So: folder → venv → Apache lines → database and keys → code. Never put the database or `wvara.keys` in the folder before the Apache lines are live.

## 1. Create the folder (server)

```
mkdir -p /var/www/html/salmancuso/tools/wvara-site/instance
chown www-data:www-data /var/www/html/salmancuso/tools/wvara-site/instance
chmod 770 /var/www/html/salmancuso/tools/wvara-site/instance
```

## 2. Build the venv with the live tool's exact package versions (server)

```
cd /var/www/html/salmancuso/tools/wvara-site
/var/www/html/salmancuso/tools/wvara/venv/bin/pip freeze > /root/wvara-live-freeze-20261109.txt
python3.8 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install -r /root/wvara-live-freeze-20261109.txt
venv/bin/python --version        # Python 3.8.10 on Nov 9
```

The freeze file (`/root/wvara-live-freeze-20261109.txt`, 27 lines) is the record of the working versions: Flask 3.0.0, Flask-SQLAlchemy 3.1.1, Flask-Migrate 4.0.5, Werkzeug 3.0.1, SQLAlchemy 2.0.57, reportlab 4.0.7, Pillow 10.1.0, requests 2.31.0, beautifulsoup4 4.12.2, and their dependencies. On a new server without the live venv, copy that file over and install from it.

## 3. Apache lines (server)

Back up first:

```
cp -p /etc/apache2/sites-enabled/salmancuso.com-le-ssl.conf /root/salmancuso.com-le-ssl.conf-20261109
```

Then, in `/etc/apache2/sites-enabled/salmancuso.com-le-ssl.conf`, **above** the live tool's `# WVARA Membership` block (longer path first):

```
        # WVARA Site Rebuild TEST site (added 2026-11-09)
        WSGIDaemonProcess wvara-site user=www-data group=www-data threads=5 python-home=/var/www/html/salmancuso/tools/wvara-site/venv python-path=/var/www/html/salmancuso/tools/wvara-site
        WSGIScriptAlias /tools/wvara-site /var/www/html/salmancuso/tools/wvara-site/wvara-site.wsgi process-group=wvara-site application-group=%{GLOBAL}
        <Directory /var/www/html/salmancuso/tools/wvara-site>
            <Files wvara-site.wsgi>
                Require all granted
            </Files>
        </Directory>
```

```
apache2ctl configtest && systemctl reload apache2
```

- `AH00558 ... fully qualified domain name` is an old harmless warning; look for `Syntax OK`.
- Check: the live tool still loads, and the new URL shows Apache's **"Not Found"** (not a folder listing). That proves the folder is guarded.
- The vhost also has `WSGIProcessGroup nhoStatus` as a default; the WVARA lines set their own `process-group`, so they are unaffected.

## 4. Database snapshot and keys file (server)

```
cd /var/www/html/salmancuso/tools/wvara-site
cp -p ../wvara/instance/wvara_membership.db ../wvara/instance/zip_cache.json instance/
chown www-data:www-data instance/*
printf "# WVARA TEST site secrets. Do NOT commit this file.\nSECRET_KEY=%s\nSESSION_COOKIE_NAME=wvara_site_session\n" "$(python3 -c 'import secrets; print(secrets.token_hex(32))')" > wvara.keys
chown www-data:www-data wvara.keys
chmod 600 wvara.keys
```

- The database is a **snapshot** of live data (real member information). Test changes never flow back to the live tool.
- Its own `SECRET_KEY`, so a login on one site is never valid on the other.
- `SESSION_COOKIE_NAME` keeps the two sites from sharing the `session` cookie and logging each other out (read by `app.py`, ADDED 2026-11-09).

## 5. Code (on the Mac)

```
cd /Users/smancuso/Documents/Personal/Sal/programming/wvara_membership
git switch site-rebuild
./deploy-site.sh
```

`deploy-site.sh` refuses unless on `site-rebuild`, backs up the test database to `/root/wvara-site-backups/`, rsyncs the code (never `instance/`, `wvara.keys`, `venv`, `archive/`), resets permissions and reloads Apache.

**Check:** `https://salmancuso.com/tools/wvara-site` shows the login page and a normal login works (done Nov 9).

## Refreshing the test database later (optional)

To give testers fresher data, repeat the `cp -p ../wvara/instance/wvara_membership.db instance/` and `chown` lines from step 4. `deploy-site.sh` backs up the old test copy on its next run, but take a manual copy first if the test data matters.

## Still to add

- Clone of `wvara-content` with a **read-only deploy key**, and the cron job for the sync script.
- Cron job for the Groups.io ticker cache.
- For the new server: Apache or other web server install, mod_wsgi (or a newer Python), SSL certificate, firewall, timezone note (server clock on UTC), backups.
