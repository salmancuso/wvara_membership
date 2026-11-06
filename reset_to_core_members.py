"""
WVARA Membership - one-time reset down to the core admin accounts (ADDED 2026-11-05)

Deletes every member except KEEP_CALL_SIGNS, plus ALL dues payments, roles,
attendance, PayPal notices and the Admin Log. The kept members keep their
login, password and admin rights; their family links are cleared and their
membership type goes back to Individual.

Standard library only (no venv needed). Dry run by default.

    Dry run (changes nothing):   python3 reset_to_core_members.py
    Do it for real:              python3 reset_to_core_members.py --yes

On the server, run it as www-data so the database keeps the right owner:
    cd /var/www/html/salmancuso/tools/wvara
    sudo -u www-data python3 reset_to_core_members.py
    sudo -u www-data python3 reset_to_core_members.py --yes

Stop the local Flask app first when running on the Mac.
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

KEEP_CALL_SIGNS = ('W6SAL', 'W6HS')
DB_FILE = Path(__file__).resolve().parent / 'instance' / 'wvara_membership.db'
CLEARED_TABLES = ('dues_payments', 'role_history', 'meeting_attendance', 'payment_notices', 'admin_log')


def table_columns(conn: sqlite3.Connection, table: str) -> set:
    """Column names of a table (empty set if the table doesn't exist)"""
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def count_rows(conn: sqlite3.Connection, table: str) -> int:
    """Row count, or 0 if the table doesn't exist"""
    if not table_columns(conn, table):
        return 0
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def check_keepers(conn: sqlite3.Connection) -> list:
    """Return the kept members as (id, call_sign, name, is_admin, is_active, type). Exits if anything is wrong."""
    placeholders = ','.join('?' for _ in KEEP_CALL_SIGNS)
    rows = conn.execute(
        f"SELECT id, call_sign, first_name || ' ' || last_name, is_admin, is_active, membership_type "
        f"FROM members WHERE call_sign IN ({placeholders})", KEEP_CALL_SIGNS).fetchall()
    found = {r[1] for r in rows}
    missing = [cs for cs in KEEP_CALL_SIGNS if cs not in found]
    if missing:
        sys.exit(f"STOPPED: {', '.join(missing)} not found in the database. Nothing was changed.")
    if not any(r[3] and r[4] for r in rows):
        sys.exit("STOPPED: none of the kept members is an active admin, so nobody could log in to manage the club. "
                 "Nothing was changed.")
    return rows


def show_plan(conn: sqlite3.Connection, keepers: list) -> None:
    """Print what the reset will do"""
    total = count_rows(conn, 'members')
    print(f"Database: {DB_FILE}")
    print("\nKEEPING these members (login, password and admin rights stay):")
    for _id, cs, name, is_admin, is_active, mtype in keepers:
        print(f"  {cs:<8} {name:<25} admin={'yes' if is_admin else 'no'}  "
              f"active={'yes' if is_active else 'no'}  type now: {mtype} -> Individual")
    print(f"\nDELETING {total - len(keepers)} other members, and ALL rows in:")
    for table in CLEARED_TABLES:
        print(f"  {table:<20} {count_rows(conn, table)} rows")


def backup_database(conn: sqlite3.Connection) -> Path:
    """Copy the database (safely, with SQLite's backup API) next to the original"""
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_path = DB_FILE.with_name(f'wvara_membership-before-reset-{stamp}.db')
    with sqlite3.connect(str(backup_path)) as backup_conn:
        conn.backup(backup_conn)
    return backup_path


def run_reset(conn: sqlite3.Connection, keepers: list) -> None:
    """Delete everything except the kept members, in one all-or-nothing transaction"""
    keep_ids = [r[0] for r in keepers]
    placeholders = ','.join('?' for _ in keep_ids)
    member_cols = table_columns(conn, 'members')
    with conn:  # commits on success, rolls back on any error
        for table in CLEARED_TABLES:
            if table_columns(conn, table):
                conn.execute(f"DELETE FROM {table}")
        conn.execute(f"DELETE FROM members WHERE id NOT IN ({placeholders})", keep_ids)
        conn.execute(f"UPDATE members SET membership_type = 'Individual' WHERE id IN ({placeholders})", keep_ids)
        for col in ('family_head_id', 'family_link_request'):
            if col in member_cols:
                conn.execute(f"UPDATE members SET {col} = NULL WHERE id IN ({placeholders})", keep_ids)
        if table_columns(conn, 'admin_log'):
            conn.execute(
                "INSERT INTO admin_log (admin_call_sign, action, target_member_call_sign, details, ip_address, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ('SYSTEM', 'Database reset to ' + ', '.join(KEEP_CALL_SIGNS), None,
                 'reset_to_core_members.py: removed all other members, dues, roles, attendance, '
                 'PayPal notices and the old admin log', 'local script',
                 datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')))
    conn.execute("VACUUM")  # shrink the file now that the test data is gone


def main() -> None:
    do_it = '--yes' in sys.argv[1:]
    if not DB_FILE.exists():
        sys.exit(f"STOPPED: database not found at {DB_FILE}")
    journal = DB_FILE.with_name(DB_FILE.name + '-journal')
    if journal.exists():
        sys.exit(f"STOPPED: {journal.name} exists, so something may be writing to the database. "
                 "Stop the app (or wait a moment) and try again.")

    conn = sqlite3.connect(str(DB_FILE))
    try:
        keepers = check_keepers(conn)
        show_plan(conn, keepers)
        if not do_it:
            print("\nDRY RUN: nothing was changed. Run again with --yes to do it for real.")
            return
        backup_path = backup_database(conn)
        print(f"\nBackup saved: {backup_path}")
        run_reset(conn, keepers)
        print(f"\nDONE. Members left: {count_rows(conn, 'members')}. "
              f"To undo, copy the backup over {DB_FILE.name}.")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
