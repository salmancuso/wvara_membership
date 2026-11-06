"""
WVARA Membership - issue random temporary passwords (ADDED 2026-11-06)

Replaces the "call sign = password" starting password with a random, easy-to-read
temporary password (e.g. Maple-Radio-4827) for every member who is STILL on a temporary
password, except W6SAL and W6HS. Anyone who has already set their own password is left alone,
so running it again later never clobbers a real password.

At first login the existing forced-change screen makes each member pick their own password.

  - Dry run by default: lists who would get a new password, changes nothing, shows no passwords.
  - --yes: backs up the database, writes the private list, then saves the new passwords
    in ONE transaction (if anything fails, nothing is saved and the list is deleted).
  - --only K6ABC,N6XYZ: reissue just these members (e.g. someone lost their email).
  - A second full run is refused (it would cancel the passwords already emailed) unless --again is added.
  - The list goes to instance/temp_passwords-YYYYMMDD-HHMMSS.csv (owner-only file).
    instance/ is never deployed and is gitignored. Copy it to the Mac, then DELETE it from the server.
  - The Activity Log records that passwords were issued, never the passwords.

Run on the SERVER (the live database is the real one), as www-data:
    cd /var/www/html/salmancuso/tools/wvara
    sudo -u www-data venv/bin/python issue_temp_passwords.py
    sudo -u www-data venv/bin/python issue_temp_passwords.py --yes
"""
import argparse
import csv
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DB_FILE = APP_DIR / 'instance' / 'wvara_membership.db'
SKIP_CALL_SIGNS = ('W6SAL', 'W6HS')
LOGIN_URL = 'https://salmancuso.com/tools/wvara/login'
SCRIPT_TAG = 'SCRIPT'


def backup_database() -> Path:
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    target = DB_FILE.with_name(f'wvara_membership-before-temp-passwords-{stamp}.db')
    src, dst = sqlite3.connect(DB_FILE), sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


def pick_members(Member, only: list) -> list:
    """Members who get a new temporary password"""
    query = Member.query.filter(~Member.call_sign.in_(SKIP_CALL_SIGNS))
    if only:
        query = query.filter(Member.call_sign.in_(only))
    else:
        query = query.filter(Member.password_is_temporary == True)  # noqa: E712  (never touch real passwords)
    return query.order_by(Member.call_sign).all()


def write_list(path: Path, rows: list) -> None:
    """Owner-only CSV: call sign, name, email, temporary password, login link"""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Call Sign / Username', 'First Name', 'Last Name', 'Email', 'Temporary Password',
                         'Active', 'Login Page'])
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description='Issue random temporary passwords (dry run unless --yes).')
    parser.add_argument('--yes', action='store_true', help='actually issue the passwords')
    parser.add_argument('--only', default='', help='comma-separated call signs to reissue (even if already changed)')
    parser.add_argument('--again', action='store_true', help='allow a second full run (cancels earlier emailed passwords)')
    args = parser.parse_args()
    only = [c.strip().upper() for c in args.only.split(',') if c.strip()]
    if any(c in SKIP_CALL_SIGNS for c in only):
        sys.exit(f"STOPPED: {', '.join(SKIP_CALL_SIGNS)} are never reissued by this script. Nothing was changed.")

    sys.path.insert(0, str(APP_DIR))
    from app import app, generate_readable_temp_password
    from models import db, Member, AdminLog

    with app.app_context():
        members = pick_members(Member, only)
        if only:
            missing = sorted(set(only) - {m.call_sign for m in members})
            if missing:
                sys.exit(f"STOPPED: not found: {', '.join(missing)}. Nothing was changed.")
        active = [m for m in members if m.is_active]
        no_email = [m.call_sign for m in members if not (m.email or '').strip()]
        kept = Member.query.filter(~Member.call_sign.in_(SKIP_CALL_SIGNS),
                                   Member.password_is_temporary == False).count()  # noqa: E712

        print('=' * 66)
        print(' WVARA temporary passwords')
        print('=' * 66)
        print(f'Database: {DB_FILE}')
        print(f'Members getting a new temporary password: {len(members)} '
              f'({len(active)} active, {len(members) - len(active)} inactive)')
        print(f'Never touched: {", ".join(SKIP_CALL_SIGNS)}' +
              ('' if only else f', plus {kept} member(s) who already set their own password'))
        if no_email:
            print(f'Heads up, no email on file: {", ".join(no_email)}')
        print('  ' + ', '.join(m.call_sign for m in members[:15]) + (' ...' if len(members) > 15 else ''))

        if not members:
            print('\nNothing to do.')
            return

        # Safety: a second full run would cancel the passwords already emailed to everyone
        earlier = AdminLog.query.filter_by(action='Issued temporary passwords').order_by(AdminLog.id.desc()).first()
        if earlier and not only and not args.again:
            sys.exit(f'\nSTOPPED: temporary passwords were already issued on {earlier.created_at:%Y-%m-%d %H:%M} UTC. '
                     'Running again would cancel the passwords you emailed. Use --only CALL1,CALL2 for '
                     'individual members, or add --again if you really mean everyone. Nothing was changed.')
        if not args.yes:
            print('\nDRY RUN: nothing was changed and no passwords were made. Run again with --yes.')
            return

        backup = backup_database()
        print(f'\nDatabase backed up to {backup}')

        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        out = APP_DIR / 'instance' / f'temp_passwords-{stamp}.csv'
        rows = []
        try:
            for m in members:
                password = generate_readable_temp_password()
                m.set_password(password)
                m.password_is_temporary = True
                rows.append([m.call_sign, m.first_name, m.last_name, m.email or '', password,
                             'Yes' if m.is_active else 'No', LOGIN_URL])
            write_list(out, rows)
            db.session.add(AdminLog(
                admin_call_sign=SCRIPT_TAG, action='Issued temporary passwords',
                details=f'issue_temp_passwords.py: {len(rows)} members ({len(active)} active)'
                        + (f'; only {", ".join(only)}' if only else '') + f'; list saved as {out.name}'))
            db.session.commit()
        except Exception:
            db.session.rollback()
            if out.exists():
                out.unlink()
            print('\nSTOPPED: something went wrong, so nothing was saved (the list was deleted too).')
            raise

        print(f'Done. {len(rows)} temporary passwords issued.')
        print(f'Private list: {out}')
        print('Next: copy it to your Mac, then delete it from the server.')


if __name__ == '__main__':
    main()
