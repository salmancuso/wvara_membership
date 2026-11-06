"""
WVARA Membership - one-time roster load from the old club database export (ADDED 2026-11-06)

Reads instance/WVARA_DB.csv (the old database export Sal cleaned up), applies Sal's
Nov 6, 2026 fixes, and loads every member, family link and dues payment.

  - Dry run by default: reads the CSV and the database, prints the plan, changes NOTHING.
  - --yes: backs up the database, then loads everything in ONE transaction
    (if anything fails, nothing is written).
  - Stops if the database already has members other than W6SAL and W6HS (no double loads).
  - W6SAL and W6HS already exist: only their dues payments are added.
  - Every new member's temporary password is their call sign / username (forced change at first login).
  - No emails are sent.

Run from the project folder. Stop the local Flask app first on the Mac.

    Mac, dry run:      /Users/smancuso/salPython3/bin/python load_roster.py
    Mac, for real:     /Users/smancuso/salPython3/bin/python load_roster.py --yes
    Every member:      add --details to either command

    Server (as www-data so the database keeps the right owner):
        cd /var/www/html/salmancuso/tools/wvara
        sudo -u www-data venv/bin/python load_roster.py
        sudo -u www-data venv/bin/python load_roster.py --yes

Don't run it again after a successful load; it will refuse anyway.
"""
import argparse
import csv
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
DB_FILE = APP_DIR / 'instance' / 'wvara_membership.db'
DEFAULT_CSV = APP_DIR / 'instance' / 'WVARA_DB.csv'

EXISTING_CALL_SIGNS = ('W6SAL', 'W6HS')   # already in the database; only their dues are added
IMPORT_TAG = 'IMPORT'                      # recorded_by / created_by / admin log name for this load
PLACEHOLDER_DATE = date(2000, 1, 1)        # Sal, Nov 6, 2026: unknown join / payment dates
LOAD_DATE = date.today().isoformat()

# ---------------------------------------------------------------------------
# Sal's decisions, Nov 6, 2026 (see HANDOFF.md section 8, item 12)
# ---------------------------------------------------------------------------
SKIP_CALL_SIGNS = {
    'KC6QBF': 'License expired in 2002; removed from the roster (Sal, Nov 6, 2026).',
}

# The one row with no call sign: a non-ham who gets a username
USERNAMES_FOR_BLANK_CALL_SIGN = {
    ('richard', 'southern'): 'RSOUTHERN',
}

# Field fixes keyed by call sign (CSV column name -> corrected value)
FIXES = {
    'NT6S': {'State': 'CA', 'Zip': '95125'},
    'AI6NT': {'Zip': '95008'},
    'K6EBN': {'Zip': '95014'},
    'K6LOH': {'Email': 'K6LOH@SBCGlobal.net'},
    'KK6DZS': {'Email': 'jim@deloach.net'},           # same as her husband WU0I
    'KC6BIG': {'Email': 'KC6BIG@winlink.org'},
    'KM6AAY': {'Email': 'KM6AAY@winlink.org'},
    'KD6KRS': {'Email': 'KD6KRS@winlink.org'},
    'KK6HFV': {'Email': 'jonathanzdasiuk@gmail.com'},
    'KN6QZJ': {'Email': 'jonathanzdasiuk@gmail.com'},  # shared with KK6HFV
    'W6LKK': {'Email': 'W6LKK@winlink.org'},
    'N6MRO': {'MembDuesPayt': '15'},                   # old database showed $0
}

SILENT_KEYS = {
    'NT6F': 'Silent Key: passed away April 14, 2026.',
}

EXTRA_NOTES = {
    'N6MRO': 'Dues for 2026 recorded as $15 on 2026-01-15 per Sal (old database showed $0).',
    'KG6ENF': 'Kept as Lifetime per Sal (old database also shows a $15 payment on 1/1/17).',
    'KG6KRI': 'Family head with no family members linked (they may not have joined). Kept as Family per Sal.',
}

# Dues rows written exactly as given instead of from the CSV (year, amount, date, method, notes)
DUES_OVERRIDES = {
    'W6SAL': [
        (2026, 15.0, date(2026, 1, 1), 'PayPal', 'Payment date unknown (placeholder 2026-01-01). From old club database.'),
        (2027, 15.0, date(2026, 11, 5), 'PayPal', 'Paid Nov 5, 2026. Old database showed 11/5/27 (typo).'),
    ],
}

LICENSE_CLASSES = {'E': 'Amateur Extra', 'A': 'Advanced', 'G': 'General', 'T': 'Technician', 'N': 'Novice'}

REQUIRED_COLUMNS = ('Callsign', 'FirstName', 'LastName', 'MasterFamilyCallsign', 'StreetAddress', 'City',
                    'State', 'Zip', 'Phone', 'licenseClass', 'DateJoined', 'PaymentDate', 'CheckNumber',
                    'TotalPayt', 'MembDuesPayt', 'RptrDuesPayt', 'OtherPayt', 'DuesPaidThru',
                    'memberStatusType', 'Email', 'HideStreetAddr', 'HidePhone', 'HideEmail', 'HideAll')


# ---------------------------------------------------------------------------
# Small cleaners
# ---------------------------------------------------------------------------
def clean(value) -> str:
    """Trim spaces (and treat None as blank)"""
    return (value or '').strip()


def is_true(value) -> bool:
    return clean(value).upper() == 'TRUE'


def money(value) -> float:
    try:
        return round(float(clean(value) or 0), 2)
    except ValueError:
        return 0.0


def parse_date(value):
    """'1/30/26' -> date; blank or '0000-00-00' -> None"""
    value = clean(value)
    if not value or value.startswith('0000'):
        return None
    for fmt in ('%m/%d/%y', '%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def clean_phone(value: str):
    """Return (phone, leftover note). 10 digits become 408-555-1234."""
    value = clean(value)
    if not value:
        return None, None
    digits = re.sub(r'\D', '', value)
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) != 10:
        return value[:20], None
    words = re.sub(r'[\d\s\-\.\(\)\+]', '', value)
    note = f'Phone as entered: {value}' if words else None
    return f'{digits[:3]}-{digits[3:6]}-{digits[6:]}', note


def clean_zip(value: str):
    """95125 stays; 951254463 or 95125-4463 become 95125-4463"""
    value = clean(value)
    digits = re.sub(r'\D', '', value)
    if len(digits) == 5:
        return digits
    if len(digits) == 9:
        return f'{digits[:5]}-{digits[5:]}'
    return value or None


def payment_method(value: str):
    """Return (method, note) using the Dues page's choices: PayPal, Cash, Check"""
    value = clean(value)
    low = value.lower()
    if 'paypal' in low:
        return 'PayPal', None
    if 'cash' in low:
        return 'Cash', None
    number = re.sub(r'\D', '', value)
    if 'check' in low or number:
        return 'Check', (f'Check #{number}' if number else None)
    return 'PayPal', 'Payment method not recorded in the old database.'


def dues_year_of(paid_on, paid_thru: int) -> int:
    """The year a payment counts toward: Oct-Dec payments count for next year (if covered)"""
    if paid_on is None:
        return paid_thru
    year = paid_on.year + 1 if paid_on.month >= 10 else paid_on.year
    return min(year, paid_thru)


# ---------------------------------------------------------------------------
# Reading and planning (no database writes)
# ---------------------------------------------------------------------------
def read_csv_rows(csv_file: Path) -> list:
    if not csv_file.exists():
        sys.exit(f"STOPPED: {csv_file} not found. Copy WVARA_DB.csv into the instance/ folder first.")
    with csv_file.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            sys.exit(f"STOPPED: the CSV is missing columns: {', '.join(missing)}. Nothing was changed.")
        rows = [{k: clean(v) for k, v in row.items() if k} for row in reader]
    return rows


def apply_fixes(row: dict) -> dict:
    """Return a copy of the row with Sal's fixes applied and the call sign settled"""
    row = dict(row)
    row['_original'] = dict(row)   # untouched CSV values, for the legacy notes
    call_sign = row['Callsign'].upper()
    is_licensed = True
    if not call_sign:
        key = (row['FirstName'].lower(), row['LastName'].lower())
        call_sign = USERNAMES_FOR_BLANK_CALL_SIGN.get(key, '')
        is_licensed = False
    row['Callsign'] = call_sign
    row['_is_licensed'] = is_licensed
    for column, value in FIXES.get(call_sign, {}).items():
        row[column] = value
    return row


def legacy_notes(row: dict, extra: list) -> str:
    """Admin-only notes block built from the old database columns that have no home in the app"""
    lines = [f'Imported {LOAD_DATE} from the old club database (WVARA_DB.csv).']
    lines += extra

    def add(label, column, skip=('',)):
        value = clean(row.get(column))
        if value not in skip:
            lines.append(f'{label}: {value}')

    def yes_no(label, column):
        value = clean(row.get(column)).upper()
        if value in ('TRUE', 'FALSE'):
            lines.append(f'{label}: {"Yes" if value == "TRUE" else "No"}')

    add('Old status', 'memberStatusType')
    add('Handle', 'Handle')
    add('Spouse', 'Spouse')
    yes_no('ARRL member', 'ARRLMemb')
    yes_no('Repeater member', 'RptrMemb')
    add('Badge', 'Badge')
    add('HET notice', 'HetNotice')
    add('Email lists', 'EmailListsInit')
    add('E-list year', 'MembEListYear', skip=('', '0000'))
    add('AutoCode', 'AutoCode')
    add('Family master (old database)', 'MasterFamilyCallsign')

    hidden = [name for name, column in (('street address', 'HideStreetAddr'), ('phone', 'HidePhone'),
                                        ('email', 'HideEmail'), ('everything', 'HideAll')) if is_true(row.get(column))]
    if hidden:
        lines.append('Asked to hide: ' + ', '.join(hidden) + ' (loaded as a full directory opt-out)')

    old = row.get('_original', row)   # show what the old database said, before Sal's fixes
    paid = (f"Last payment in old database: {old.get('PaymentDate') or 'none'}, "
            f"{old.get('CheckNumber') or 'method not recorded'}, total ${money(old.get('TotalPayt')):.2f} "
            f"(dues ${money(old.get('MembDuesPayt')):.2f}, repeater ${money(old.get('RptrDuesPayt')):.2f}, "
            f"other ${money(old.get('OtherPayt')):.2f}), paid through {old.get('DuesPaidThru') or 'unknown'}")
    lines.append(paid)

    comments = clean(row.get('Comments')).replace('\r\n', '\n').replace('\r', '\n')
    if comments:
        lines.append('Comments:')
        lines += ['  ' + c.strip() for c in comments.split('\n') if c.strip()]
    return '\n'.join(lines)


def plan_dues(row: dict, membership_type: str, has_head: bool) -> list:
    """Dues rows for one member: one per covered year. The real payment goes on its own year;
    other covered years get a $0 'prepaid' row so the dues status works."""
    call_sign = row['Callsign']
    if call_sign in DUES_OVERRIDES:
        return [dict(year=y, amount=a, payment_date=d, method=m, notes=n) for y, a, d, m, n in DUES_OVERRIDES[call_sign]]
    if membership_type == 'Lifetime' or has_head:
        return []
    amount = money(row.get('MembDuesPayt'))
    try:
        paid_thru = int(row.get('DuesPaidThru') or 0)
    except ValueError:
        paid_thru = 0
    if amount <= 0 or paid_thru < 2000 or paid_thru > 2090:
        return []

    paid_on = parse_date(row.get('PaymentDate')) or PLACEHOLDER_DATE
    first_year = dues_year_of(parse_date(row.get('PaymentDate')), paid_thru)
    method, method_note = payment_method(row.get('CheckNumber'))

    extras = []
    if method_note:
        extras.append(method_note)
    if money(row.get('RptrDuesPayt')):
        extras.append(f"Also paid ${money(row.get('RptrDuesPayt')):.2f} repeater dues.")
    if money(row.get('OtherPayt')):
        extras.append(f"Also paid ${money(row.get('OtherPayt')):.2f} other (donation/merchandise).")
    base_note = 'From old club database.'

    rows = [dict(year=first_year, amount=amount, payment_date=paid_on, method=method,
                 notes=' '.join([base_note] + extras))]
    for year in range(first_year + 1, paid_thru + 1):
        rows.append(dict(year=year, amount=0.0, payment_date=paid_on, method=method,
                         notes=f'Prepaid per old club database (paid through {paid_thru}).'))
    return rows


def dues_status_preview(paid_years: set, is_lifetime: bool) -> str:
    """Same rules as Member.get_dues_status() (grace through February)"""
    if is_lifetime:
        return 'lifetime'
    today = date.today()
    if today.year in paid_years:
        return 'paid'
    if today.month <= 2 and (today.year - 1) in paid_years:
        return 'grace'
    return 'expired'


def build_plan(rows: list) -> dict:
    """Turn CSV rows into members, family links and dues rows. Exits on anything that would break the load."""
    rows = [apply_fixes(r) for r in rows]
    problems, warnings, skipped = [], [], []

    by_call = {}
    for r in rows:
        cs = r['Callsign']
        if not cs:
            problems.append(f"Row for {r['FirstName']} {r['LastName']} has no call sign or username.")
            continue
        if cs in SKIP_CALL_SIGNS:
            skipped.append(f'{cs}: {SKIP_CALL_SIGNS[cs]}')
            continue
        if cs in by_call:
            problems.append(f'{cs} appears twice in the CSV.')
            continue
        if len(cs) > 15:
            problems.append(f'{cs} is longer than 15 characters.')
        by_call[cs] = r

    heads = {r['MasterFamilyCallsign'].upper() for r in by_call.values() if r['MasterFamilyCallsign']}
    members = []
    for cs, r in by_call.items():
        status = r['memberStatusType']
        head = r['MasterFamilyCallsign'].upper() or None
        if head == cs:
            head = None
        if head and head not in by_call:
            warnings.append(f'{cs}: family head {head} is not being loaded, so no family link.')
            head = None

        if status == 'Life':
            membership_type = 'Lifetime'
        elif head or cs in heads or status == 'Regular-FamilyMaster':
            membership_type = 'Family'
        else:
            membership_type = 'Individual'

        is_active = status not in ('Inactive', 'SK')
        extra = []
        if cs in SILENT_KEYS:
            extra.append(SILENT_KEYS[cs])
        if cs in EXTRA_NOTES:
            extra.append(EXTRA_NOTES[cs])
        if not r['_is_licensed']:
            extra.append(f'No call sign in the old database; loaded as non-ham with username {cs}.')

        join_date = parse_date(r['DateJoined'])
        if join_date is None:
            join_date = PLACEHOLDER_DATE
            extra.append('Join date unknown in the old database; set to 2000-01-01 as a placeholder.')
        if clean(r['PaymentDate']).startswith('0000'):
            extra.append('Payment date was 0000-00-00 in the old database.')

        phone, phone_note = clean_phone(r['Phone'])
        if phone_note:
            extra.append(phone_note)

        email = r['Email']
        if not email:
            problems.append(f'{cs} has no email (the app requires one).')

        members.append(dict(
            call_sign=cs, first_name=r['FirstName'], last_name=r['LastName'], email=email,
            phone=phone, address=r['StreetAddress'] or None, city=r['City'] or None,
            state=(r['State'].upper() or None), zip_code=clean_zip(r['Zip']),
            fcc_license_class=LICENSE_CLASSES.get(r['licenseClass'].upper()) if r['_is_licensed'] else None,
            membership_type=membership_type, join_date=join_date, is_active=is_active,
            is_licensed=r['_is_licensed'],
            directory_opt_out=any(is_true(r[c]) for c in ('HideStreetAddr', 'HidePhone', 'HideEmail', 'HideAll')),
            head=head, row=r, extra=extra,
        ))

    # Family members whose address says "See <head>" (or is blank) get the head's address
    member_by_call = {m['call_sign']: m for m in members}
    for m in members:
        address = (m['address'] or '').lower()
        if m['head'] and not m['city'] and (not address or address.startswith('see ')):
            h = member_by_call[m['head']]
            if m['address']:
                m['extra'].append(f"Address in old database: {m['address']}")
            m['address'], m['city'], m['state'], m['zip_code'] = h['address'], h['city'], h['state'], h['zip_code']

    for m in members:
        m['dues'] = plan_dues(m['row'], m['membership_type'], bool(m['head']))
        m['admin_notes'] = legacy_notes(m['row'], m['extra'])
        if m['state'] and not re.fullmatch(r'[A-Z]{2}', m['state']):
            warnings.append(f"{m['call_sign']}: state '{m['state']}' doesn't look like a 2-letter state.")
        if m['zip_code'] and not re.fullmatch(r'\d{5}(-\d{4})?', m['zip_code']):
            warnings.append(f"{m['call_sign']}: ZIP '{m['zip_code']}' doesn't look right.")

    if problems:
        print('\nSTOPPED: fix these first. Nothing was changed.')
        for p in problems:
            print('  - ' + p)
        sys.exit(1)

    # Dues status preview (family members follow their head)
    paid_years = {m['call_sign']: {d['year'] for d in m['dues']} for m in members}
    for m in members:
        source = member_by_call.get(m['head']) if m['head'] else m
        m['dues_status'] = dues_status_preview(paid_years[source['call_sign']], source['membership_type'] == 'Lifetime')

    return dict(members=members, warnings=warnings, skipped=skipped)


def existing_members() -> list:
    """Call signs already in the database (read-only)"""
    if not DB_FILE.exists():
        sys.exit(f'STOPPED: database not found at {DB_FILE}. Nothing was changed.')
    conn = sqlite3.connect(f'file:{DB_FILE}?mode=ro', uri=True)
    try:
        return [r[0] for r in conn.execute('SELECT call_sign FROM members ORDER BY call_sign')]
    finally:
        conn.close()


def check_database(found: list) -> None:
    extra = [cs for cs in found if cs not in EXISTING_CALL_SIGNS]
    if extra:
        shown = ', '.join(extra[:10]) + (' ...' if len(extra) > 10 else '')
        sys.exit(f'STOPPED: the database already has {len(extra)} other member(s) ({shown}). '
                 'The roster looks loaded already. Nothing was changed.')
    missing = [cs for cs in EXISTING_CALL_SIGNS if cs not in found]
    if missing:
        print(f"Note: {', '.join(missing)} not in the database; they'll be loaded from the CSV like everyone else.")


def show_plan(plan: dict, found: list, details: bool) -> None:
    members = plan['members']
    new = [m for m in members if m['call_sign'] not in found]
    kept = [m for m in members if m['call_sign'] in found]

    def count(items, key):
        out = {}
        for i in items:
            out[i[key]] = out.get(i[key], 0) + 1
        return ', '.join(f'{k} {v}' for k, v in sorted(out.items(), key=lambda kv: str(kv[0])))

    print('=' * 70)
    print(' WVARA roster load plan')
    print('=' * 70)
    print(f'Database: {DB_FILE}')
    print(f'New members to add: {len(new)}  (already in the database, dues only: '
          f"{', '.join(m['call_sign'] for m in kept) or 'none'})")
    print(f"  Membership type: {count(new, 'membership_type')}")
    print(f"  Login enabled:   {sum(m['is_active'] for m in new)}   disabled (inactive / SK): "
          f"{sum(not m['is_active'] for m in new)}")
    print(f"  Non-hams:        {', '.join(m['call_sign'] for m in new if not m['is_licensed']) or 'none'}")
    print(f"  Directory opt-out: {', '.join(m['call_sign'] for m in new if m['directory_opt_out']) or 'none'}")
    active = [m for m in members if m['is_active']]
    print(f"  Dues status today (active members): {count(active, 'dues_status')}")

    heads = sorted({m['head'] for m in members if m['head']})
    print(f'\nFamilies ({len(heads)} heads):')
    for h in heads:
        print(f"  {h}: " + ', '.join(m['call_sign'] for m in members if m['head'] == h))
    lonely = [m['call_sign'] for m in members if m['membership_type'] == 'Family' and not m['head'] and m['call_sign'] not in heads]
    if lonely:
        print(f"  Family heads with nobody linked: {', '.join(lonely)}")

    dues = [(m['call_sign'], d) for m in members for d in m['dues']]
    print(f"\nDues payments to add: {len(dues)} "
          f"({sum(1 for _, d in dues if d['amount'] > 0)} real payments, "
          f"{sum(1 for _, d in dues if d['amount'] == 0)} $0 prepaid-year rows)")
    multi = sorted({cs for cs, d in dues if d['amount'] == 0 or cs in DUES_OVERRIDES})
    for cs in multi:
        print(f'  {cs}: ' + ', '.join(f"{d['year']} ${d['amount']:.0f}" for c, d in dues if c == cs))

    if plan['skipped']:
        print('\nSkipped (not loaded):')
        for s in plan['skipped']:
            print('  - ' + s)
    if plan['warnings']:
        print('\nWarnings (load still works):')
        for w in plan['warnings']:
            print('  - ' + w)

    if details:
        print('\nEvery member:')
        for m in sorted(members, key=lambda x: x['call_sign']):
            years = ','.join(str(d['year']) for d in m['dues']) or '-'
            print(f"  {m['call_sign']:<10} {m['first_name'] + ' ' + m['last_name']:<26} {m['membership_type']:<10} "
                  f"{'active' if m['is_active'] else 'OFF':<6} {m['dues_status']:<8} dues {years:<15} "
                  f"{(m['head'] or ''):<7} {m['zip_code'] or ''}")
    print()


# ---------------------------------------------------------------------------
# Writing (only with --yes)
# ---------------------------------------------------------------------------
def backup_database() -> Path:
    """Safe copy of the live database (SQLite backup API) before any change"""
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    target = DB_FILE.with_name(f'wvara_membership-before-load-{stamp}.db')
    src = sqlite3.connect(DB_FILE)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


def write_plan(plan: dict) -> None:
    """Load everything through the app's own models in a single transaction"""
    sys.path.insert(0, str(APP_DIR))
    from app import app                      # also runs ensure_schema (adds members.admin_notes)
    from models import db, Member, DuesPayment, AdminLog

    with app.app_context():
        found = [m.call_sign for m in Member.query.all()]
        check_database(found)                # re-check right before writing
        try:
            by_call = {m.call_sign: m for m in Member.query.all()}
            added = 0
            for p in plan['members']:
                if p['call_sign'] in by_call:
                    continue
                m = Member(
                    call_sign=p['call_sign'], first_name=p['first_name'], last_name=p['last_name'],
                    email=p['email'], phone=p['phone'], address=p['address'], city=p['city'],
                    state=p['state'], zip_code=p['zip_code'], fcc_license_class=p['fcc_license_class'],
                    membership_type=p['membership_type'], join_date=p['join_date'],
                    is_active=p['is_active'], is_admin=False, is_licensed=p['is_licensed'],
                    directory_opt_out=p['directory_opt_out'], admin_notes=p['admin_notes'],
                    password_is_temporary=True, last_contact=None,
                )
                m.set_password(p['call_sign'])   # same as Add Member: temporary password = call sign / username
                db.session.add(m)
                by_call[p['call_sign']] = m
                added += 1
            db.session.flush()                   # gives every new member an id

            # ADDED 2026-11-06: the model's default stamps "now" on insert even when we pass None,
            # so blank Last Contact for the new members after the insert (nobody has logged in yet)
            new_ids = [by_call[p['call_sign']].id for p in plan['members'] if p['call_sign'] not in found]
            if new_ids:
                Member.query.filter(Member.id.in_(new_ids)).update({Member.last_contact: None},
                                                                    synchronize_session=False)

            for p in plan['members']:
                if p['head']:
                    by_call[p['call_sign']].family_head_id = by_call[p['head']].id

            dues_added = 0
            for p in plan['members']:
                member = by_call[p['call_sign']]
                have = {d.year for d in DuesPayment.query.filter_by(member_id=member.id).all()} if member.id else set()
                for d in p['dues']:
                    if d['year'] in have:
                        continue
                    db.session.add(DuesPayment(
                        member_id=member.id, year=d['year'], amount=d['amount'],
                        payment_date=d['payment_date'], payment_method=d['method'],
                        notes=d['notes'], created_by=IMPORT_TAG,
                    ))
                    dues_added += 1

            db.session.add(AdminLog(
                admin_call_sign=IMPORT_TAG, action='Loaded roster from old club database',
                details=f'load_roster.py: {added} members, {dues_added} dues payments from WVARA_DB.csv; '
                        f"skipped: {', '.join(SKIP_CALL_SIGNS) or 'none'}",
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            print('\nSTOPPED: something went wrong, so nothing was written (the transaction was rolled back).')
            raise

        print(f'Done. Added {added} members and {dues_added} dues payments.')
        print(f'Members in the database now: {Member.query.count()}')


def main() -> None:
    parser = argparse.ArgumentParser(description='One-time WVARA roster load (dry run unless --yes).')
    parser.add_argument('--yes', action='store_true', help='actually load (after a database backup)')
    parser.add_argument('--details', action='store_true', help='list every member in the plan')
    parser.add_argument('--csv', type=Path, default=DEFAULT_CSV, help=f'CSV file (default {DEFAULT_CSV})')
    args = parser.parse_args()

    found = existing_members()
    check_database(found)
    plan = build_plan(read_csv_rows(args.csv))
    show_plan(plan, found, args.details)

    if not args.yes:
        print('DRY RUN: nothing was changed. Run again with --yes to load.')
        return

    backup = backup_database()
    print(f'Database backed up to {backup}')
    write_plan(plan)


if __name__ == '__main__':
    main()
