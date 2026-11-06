"""
WVARA Membership - one-time fix: blank "Last Contact" for imported members (ADDED 2026-11-06)

The Nov 6, 2026 roster load (load_roster.py) accidentally stamped the load time as
"Last Contact" on every imported member. This clears it for members who:
  - were imported (admin notes start with "Imported ... from the old club database"), and
  - have never logged in (still on their temporary password).
Anyone who has logged in since keeps their real Last Contact.

Standard library only. Dry run by default. Stop the local Flask app first on the Mac.

    Dry run (changes nothing):   /Users/smancuso/salPython3/bin/python fix_last_contact.py
    Do it for real:              /Users/smancuso/salPython3/bin/python fix_last_contact.py --yes

Only needed on the Mac: the fixed load_roster.py leaves Last Contact blank on the server.
"""
import sqlite3
import sys
from pathlib import Path

DB_FILE = Path(__file__).resolve().parent / 'instance' / 'wvara_membership.db'
WHERE = ("admin_notes LIKE 'Imported % from the old club database%' "
         "AND password_is_temporary = 1 AND last_contact IS NOT NULL")


def main() -> None:
    if not DB_FILE.exists():
        sys.exit(f'STOPPED: database not found at {DB_FILE}. Nothing was changed.')
    do_it = '--yes' in sys.argv[1:]
    conn = sqlite3.connect(DB_FILE)
    try:
        rows = conn.execute(f'SELECT call_sign, last_contact FROM members WHERE {WHERE} ORDER BY call_sign').fetchall()
        print(f'Imported members who never logged in, with a Last Contact set: {len(rows)}')
        if rows:
            print('  ' + ', '.join(r[0] for r in rows[:12]) + (' ...' if len(rows) > 12 else ''))
        if not do_it:
            print('DRY RUN: nothing was changed. Run again with --yes to clear them.')
            return
        with conn:
            changed = conn.execute(f'UPDATE members SET last_contact = NULL WHERE {WHERE}').rowcount
        print(f'Done. Cleared Last Contact for {changed} members.')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
