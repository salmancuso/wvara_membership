# WVARA Membership: Handoff Notes

*Started November 5, 2026 after a two-day build session with Claude. **Rewritten end of day November 6, 2026** after the roster load, admin notes, Activity Log, access levels, Club Information card and temporary passwords all went live. Earlier versions are in `archive/HANDOFF-*.md`.*

*New session? Read this file, then ask Sal what's next. **Up next (section 8):** send members their login emails, push the latest commit, give the Secretary a Records Manager login, then the self check-in kiosk.*

---

## 1. Snapshot

| | |
|---|---|
| **What** | Membership tool for the West Valley Amateur Radio Association (WVARA) |
| **Owner / developer** | Sal Mancuso, W6SAL (System Administrator) |
| **Live URL** | https://salmancuso.com/tools/wvara (login: `/tools/wvara/login`) |
| **Server path** | `/var/www/html/salmancuso/tools/wvara` |
| **Local path (Mac)** | `/Users/smancuso/Documents/Personal/Sal/programming/wvara_membership` |
| **GitHub** | Private repo `github.com/salmancuso/wvara_membership`, branch `main` (section 6) |
| **Stack** | Flask 3.0, Flask-SQLAlchemy, SQLite, Bootstrap 5.3, Leaflet 1.9.4, ReportLab |
| **People** | Scott KK6IK (current President; moving to the East Coast). Eric Hendrickson W6HS (President starting January 2027; System Administrator). |
| **Live data (Nov 6, 2026)** | **140 members** loaded from the old club database: 102 Individual, 36 Family (15 family heads), 2 Lifetime; 120 can log in, 18 are inactive (incl. NT6F, Silent Key). 126 dues records on the server. Roles re-entered on the live site (Scott President now, Eric President from Jan 2027, Treasurer). **Every member except W6SAL and W6HS has a random temporary password**; emails with those passwords have not gone out yet. |
| **Backups of the live database** | `/root/wvara-backups/` (one per deploy), plus `instance/wvara_membership-before-load-20261106-105630.db` and `instance/wvara_membership-before-temp-passwords-*.db` on the server |

---

## 2. Sal's working rules (follow these)

- **Ask before writing code.** Explain the plan, get a yes, then build.
- **Add-only edits.** Preserve working code; don't restructure or "clean up" unrelated code.
- **Dated backups before changing a file, saved in `archive/`** (not next to the live file), mirroring the live path: `archive/app-20261106.py`, `archive/templates/admin/members-20261106.html`. Add `-v2`, `-v3` for more the same day. Mark changes with `# ADDED 2026-11-06` / `# CHANGED ...` comments. Database copies are the exception and stay in `instance/`.
- **Credentials live in `.keys` files, never environment variables.** The secret key is in `wvara.keys`.
- **Functions over classes.** Ask before introducing a class (including a new SQLAlchemy model; a plain table created with SQL is the class-free option).
- **One step at a time** for multi-step instructions; wait for confirmation.
- **Writing style:** no em dashes; end replies with one follow-up question.
- **Local Python:** `/Users/smancuso/salPython3/bin/python app.py` (runs at http://localhost:1977, reachable from a phone on the same Wi-Fi at `http://<Mac's IP>:1977`). Debug is OFF, so restart after template changes.
- **Test on a copy first.** Claude tests changes on a sandbox copy of the database, then Sal checks locally, then `./deploy.sh`, then commit and push.
- **Run git on the Mac, never from Claude's sandbox** (a sandbox `git status` once left a stale `.git/index.lock`).

---

## 3. Key files

| File | Purpose |
|---|---|
| `app.py` | All routes and helpers (function-based) |
| `models.py` | `Member`, `DuesPayment`, `RoleHistory`, `MeetingAttendance`, `AdminLog`, `PaymentNotice`; dues constants |
| `wvara.wsgi` | mod_wsgi entry point (finds the venv's `python3.x` folder automatically) |
| `wvara.keys` | `SECRET_KEY=...` (auto-created if missing; never commit, never deploy over) |
| `deploy.sh` | One-command deploy from the Mac (section 6) |
| `load_roster.py` | One-time roster load from `instance/WVARA_DB.csv` (**done**; refuses to run twice). Sal's fixes are in the `FIXES` / `SKIP_CALL_SIGNS` / `DUES_OVERRIDES` tables at the top. |
| `fix_last_contact.py` | One-time Mac fix for Last Contact after the first load (**done**; not needed on the server) |
| `issue_temp_passwords.py` | Random temporary passwords (**run on the server Nov 6**). Use `--only CALL1,CALL2` to reissue individuals. A second full run is refused unless `--again`. |
| `reset_to_core_members.py` | Nov 5 reset to W6SAL + W6HS. **Never run it again**: it deletes everyone else. |
| `static/css/wvara-theme.css` | WVARA site theme, layered over the original styles |
| `static/img/wvara-logo.png` | Club logo (copied from wvara.org) |
| `static/data/zip_centroids.json` | ZIP code coordinates for the map |
| `templates/_pay_dues_modal.html` | Pay Dues lightbox, included from `base.html` |
| `templates/signup.html` | Self sign-up page (`/signup`) |
| `templates/member_reports.html` | Member-facing Reports & Directory page |
| `templates/admin/map.html` | Member Map (admin and member views) |
| `templates/admin/activity_log.html` | Activity Log report |
| `templates/admin/_access_levels_modal.html` | "What's this?" lightbox explaining the admin access levels |
| `instance/wvara_membership.db` | SQLite database (**the server's copy is the real one**) |
| `instance/WVARA_DB.csv` | Old club database export (personal data). **Mac only**; deleted from the server after the load. |
| `instance/temp_passwords-*.csv` | The private temporary-password list. **Mac only**; deleted from the server. Every member's password is in it, so never email, commit or upload it. |
| `instance/zip_cache.json`, `instance/license_lookup_tried.json` | Runtime caches for the map and the FCC fill |
| `archive/` | Every dated code/template/doc backup, in the live folder layout (section 12). Committed to git; never deployed. |

---

## 4. What's built

### Security and access
- **CSRF protection** on every POST (hand-rolled: `get_csrf_token`, `csrf_protect`). Fetch calls send `FormData` that includes `csrf_token`.
- **Passwords** are hashed with Werkzeug scrypt. Admins can't see them, only reset them.
- **Temporary passwords:** readable, random, e.g. `Carbon-Cobalt-3101` (`generate_readable_temp_password()`: two of 189 words plus four digits). Used by `issue_temp_passwords.py` and by **Add Member**, which shows the password once in the success message. Passwords are never written to the Activity Log. Admin **Reset Password** still uses the older 12-character `generate_temp_password()`.
- **Forced password change:** anyone on a temporary password (`password_is_temporary`) is blocked from every page until they set their own (10+ characters, uppercase, number, special character).
- **Three admin access levels** (`members.admin_level`; `is_admin` stays True for any level so older checks keep working):

  | | Records Manager | Club Administrator | System Administrator |
  |---|---|---|---|
  | Meant for | Board members, Secretary | President, VP, Treasurer | People who run the tool (W6SAL, W6HS) |
  | Members, admin notes, Add Member, family links | Yes | Yes | Yes |
  | Attendance, Roles, Reports, Member Map | Yes | Yes | Yes |
  | Reset a password | Regular members only | Yes | Yes |
  | Dues and PayPal notices | No | Yes | Yes |
  | Activity Log, FCC fill | No | Yes | Yes |
  | Deactivate / delete members | No | Yes | Yes |
  | Set access levels | No | Up to Club Administrator | All levels |

  - **Safety rules:** nobody can change, reset the password of, deactivate or delete someone at a higher level; nobody changes their own level; there is always at least one active System Administrator. Every access change is logged ("Access level: X → Y").
  - **Roles and access are separate.** Holding an office (Roles page) never grants access; levels are set by hand on the member page.
  - **Code:** `ADMIN_LEVELS`, `ADMIN_LEVEL_LABELS`, `admin_level_of()`, `admin_rank()`, `admin_level_label()`, `current_viewer()`, decorator `admin_level_required('club')` (on `/admin/dues`, the Activity Log, FCC fill), `member_action_block_reason()` (checked on every POST to the admin member page), action `set_access_level`, context processor `inject_admin_levels`. The old `toggle_admin` action is refused.
  - **Screens:** an **Access level** pull-down with a "What's this?" lightbox in the member page's Quick Actions; level badges on the member page and the Members list; Dues links and the Activity Log card are hidden from Records Managers.
- **Member roles (non-admin):** own Dashboard, Profile, Change Password, Reports & Directory, Member Map, Pay Dues.
- **Directory opt-out** (`Member.directory_opt_out`): the *member* directory shows only name and call sign; admin reports always show everything.

### Activity Log (Admin → Reports, Club Administrator and up)
- `/admin/reports/activity` (`report_activity()`, `filtered_activity()`): date, time (Pacific), admin (with a **Self** badge for members editing their own record), member affected, what happened, what changed. Filters by admin, member and date range; 100 per page; CSV adds the IP address. Read-only, no delete. Downloading the CSV is itself logged.
- **"Old → new" detail** (`log_snapshot()`, `log_value()`, `describe_changes()`, `MEMBER_LOG_FIELDS`, `DUES_LOG_FIELDS`) for admin member edits, admin notes (trimmed to 200 characters), dues edits, deletes and new payments, role start and end dates, access level changes, and member self-edits on `/profile` ("Updated own profile"). Entries before Nov 6 have no detail.

### Dues logic (`models.py`)
- `DUES_BY_TYPE = {'Individual': 15.00, 'Family': 25.00}`; Lifetime pays nothing.
- `is_lifetime()` treats "Lifetime", "Life Member" and "Life" as lifetime.
- `get_dues_status()` returns `lifetime` / `paid` / `grace` / `expired`. **This is the single source of truth** used everywhere. Family members follow their head.
- **Grace period:** last year's dues count through the end of February (`GRACE_PERIOD_LAST_MONTH = 2`).
- `is_expiring_soon()` in `app.py`: grace members, or paid members from November 1 on, **unless next year is already paid**.

### Pay Dues (PayPal, manual confirmation)
- **Member side:** the lightbox (`_pay_dues_modal.html`) is pre-filled; Individual $15 or Family $25; a "Dues are for" year pull-down (unpaid years among this year and next); a family members box. **Continue to PayPal** saves a `PaymentNotice`, then opens a PayPal pop-up (PayPal can't be framed).
- **PayPal buttons** (public IDs in `PAYPAL_BUTTONS`): Individual `F54PDUUYZN668`, Family `AVGLTZVHUWR8W`.
- **Treasurer side (Dues page):** "PayPal Payments to Confirm" with **Mark Paid** and **Dismiss**. `/dues/pay/start` refuses a year that's already paid.
- **Manage Dues Payments:** starts in call sign A to Z order; every column header sorts (History rows move with their member). The Record Payment form defaults to **Check** and Family members to $25.

### Members and admin pages
- **Members list:** sortable columns, paging (25/50/100/All), Member Since, `mailto:` / `tel:` links, dues badges, Account (Enabled/Disabled), access level badge, filters (all, active, current, inactive, expiring, expired, lifetime, disabled, everyone).
- **Admin dashboard:** five clickable tiles (Total, Active, Expired, Expiring Soon, Lifetime), Expiring Soon and Expired lists (Last Contact shows **Never** when blank), Family Links to Confirm.
- **Admin member page:** edit form (emergency contact is optional here, since imported members have none), **Admin Notes** card (admins only; holds the old-database details for imported members), Family Membership card, Dues History, Quick Actions (access level, deactivate, reset password, delete, as the viewer's level allows).
- **Add Member:** **Look Up** pulls FCC data (callook.info, HamDB.org as backup); creates a random temporary password.
- **Attendance:** keyed on date + event type + event name. Works fine on an iPhone (Sal, Nov 6). **Saving the form replaces the whole list for that event** (see section 8, kiosk).
- **Roles:** duration column, "Starts Mon YYYY" for future start dates.
- **License class dropdowns** show "Extra" but store "Amateur Extra"; Advanced and Novice included.

### Club Information card (member Dashboard) and login page
- Meetings: **Second Wednesday of each month, 7:00 PM** (`CLUB_MEETING_TEXT`, `CLUB_MEETING_TIME`, also used on the login page).
- President and Treasurer come from the Roles page (`current_officer()`: exact title, current, already started; "Vice President" never matches). Shown as name + call sign, with the email link always going to the role address in `OFFICER_EMAILS`: **president@wvara.org**, **treasurer@wvara.org**. Eric's January 2027 start shows up on its own.

### Member Map
- **Admin:** `/admin/map`. **Members:** `/map`. ZIP-level bubbles within **75 miles of the repeater site at Good Samaritan Hospital** (`MAP_CENTER = (37.251167, -121.945463)`); others are "Remote / Virtual." New ZIPs are looked up once via api.zippopotam.us and cached. License class ribbon. "Fill blanks from FCC" (Club Administrator and up): 20 lookups per click, blanks only.

### Reports
- **Member directory** (`/reports/directory`, PDF or CSV); respects opt-out.
- **Admin reports:** directory, dues status, attendance, mailing labels, email list, Activity Log.

### Self sign-up and family memberships (Nov 5, 2026; rules in section 11)
- **Sign-up (`/signup`):** licensed hams use their call sign (FCC Look Up); non-hams pick a username (3 to 15 letters and numbers, nothing shaped like a call sign). CAPTCHA, password rules, instant access, `AdminLog` entry tagged `SIGNUP`.
- **Non-hams:** `is_licensed = False`; "Call Sign / Username" labels; "Not licensed" tag; skipped by FCC Fill; Admin edit page has a **Licensed ham** checkbox.
- **Families:** `family_head_id` (one level); `get_family_head()`, `get_family_members()`, `is_family_head()`, `link_family_member()`, `family_head_choices()`. Family members share the head's dues status and never see Pay Dues.
- **Pacific time:** the `pacific` Jinja filter (`to_pacific`) shows stored UTC times in PST/PDT (hand-written DST fallback because the server's Python 3.8 has no `zoneinfo`). The database stores UTC.

### Look and feel
- Matches wvara.org: navy header and footer (`#0b1220`), Inter font, red primary buttons (`#d71920`), orange accent (`#f36f21`), peach eyebrow labels (`#ffbf8e`), rounded cards.

---

## 5. Database changes (all automatic)

`ensure_schema()` runs on startup and adds anything missing:
- `db.create_all()` for new tables (`payment_notices`).
- `members.directory_opt_out`.
- Nov 5: `members.is_licensed` (default 1), `members.family_head_id` (+ index), `members.family_link_request`.
- Nov 6: `members.admin_notes` (TEXT) and `members.admin_level` (VARCHAR(10)). The first time `admin_level` is added, every existing admin becomes `system` (that's how W6SAL and W6HS became System Administrators on both the Mac and the server).
- Login-name columns are `String(15)`; SQLite doesn't enforce lengths, so no migration was needed.

**No migration step is needed.** Flask-Migrate is wired up, but there's no `migrations/` folder.

*Mac only:* the removed Check-In experiment created an `event_guests` table and a test event in the Mac database. Harmless; delete the test event on the Attendance page.

---

## 6. Server, deployment and GitHub

- **Server:** Ubuntu 20.04, Apache 2.4.41, mod_wsgi on **Python 3.8**. The venv **must** be built with `python3.8` (the default `python3` is 3.12 and breaks mod_wsgi). **The server clock runs on UTC.**
- **Apache:** block in `/etc/apache2/sites-enabled/salmancuso.com-le-ssl.conf` with its own `WSGIDaemonProcess wvara` and `WSGIScriptAlias /tools/wvara .../wvara.wsgi`. Original conf backed up at `/root/salmancuso.com-le-ssl.conf-20261104`.
- **Permissions:** app files `root:www-data`, `u=rwX,g=rX,o=`; `instance/` owned by `www-data`, mode 770; `wvara.keys` `www-data`, mode 600.
- **Deploy:** `./deploy.sh` from the project folder on the Mac:
  1. backs up the live database to `/root/wvara-backups/`
  2. rsyncs the code, **excluding** `venv`, `instance/`, `wvara.keys`, `__pycache__`, `*-2026*`, `archive/`, `.git`, `.DS_Store`, `deploy.sh`
  3. resets permissions
  4. checks the Apache config and reloads Apache
- **Running a script on the server:** `cd /var/www/html/salmancuso/tools/wvara` then `sudo -u www-data venv/bin/python <script>.py` (dry run), then add `--yes`. Running as www-data keeps the database owner right.
- **Copying a file down:** from a Mac Terminal (not inside ssh): `scp 'root@salmancuso.com:/var/www/html/salmancuso/tools/wvara/instance/<file>' /Users/smancuso/Documents/Personal/Sal/programming/wvara_membership/instance/`
- **Logs:** `/var/log/apache2/error.log` (app lines tagged `WVARA:`).
- **GitHub:** commit and push after each deployed change: `git add -A`, `git status` (check: **no `.db`, `.csv` or `.keys` files**), `git commit -m "..."`, `git push`. `.gitignore` blocks `*.db`, `*.csv`, `*.keys`, `instance/`, `venv/`, `__pycache__/`. HANDOFF.md and `archive/` are committed (private repo). Last confirmed push: Nov 6, end of day (everything live is on GitHub).
- **SSH key setup: on hold** (Sal, Nov 6). The tool will eventually move to the club's server, deployed from GitHub. If picked up again: `ssh-keygen -t ed25519`, `ssh-copy-id root@salmancuso.com`, test with `ssh root@salmancuso.com`. The "post-quantum" SSH warning is harmless.

---

## 7. Gotchas learned the hard way

- `grep -r` skips symlinks in `/etc/apache2/sites-enabled`; use `grep -R`.
- rsync run as root copies the Mac's file owners, so `deploy.sh` resets permissions afterward.
- Writing to SQLite from Claude's sandbox through the shared folder caused a `disk I/O error`. **Do database edits through the app or a script Sal runs, or on a copy.** Never leave a hot journal file next to the database.
- Claude's sandbox can't fetch web pages directly; use the built-in browser pane for research.
- PayPal checkout pages can't be framed, so use a pop-up window.
- The server's database is the source of truth. Never deploy `instance/` from the Mac.
- **The server runs on UTC.** Use Pacific time for anything date-of-meeting related (a 7 PM meeting is "tomorrow" in UTC).
- **SQLAlchemy column defaults fire even when you pass `None`** (the first load stamped "now" as everyone's Last Contact). Blank it with an UPDATE after the insert.
- **Jinja prints `None` as the word "None"** in form fields. Always write `value="{{ x or '' }}"`, or saving the form stores "None".
- **Saving the Attendance page replaces the whole list** for that event.
- **Run git on the Mac.** A sandbox `git status` left a stale `.git/index.lock`.

---

## 8. Open items and next steps

1. **Send the login emails (next).** The private list is in the Mac's `instance/temp_passwords-*.csv` (138 rows: call sign, name, email, temporary password, active, login link). A draft email is in the Nov 6 chat: login page, call sign, temporary password, "the site will ask you to pick your own password." Watch for: **KK6HFV and KN6QZJ share one inbox** (separate emails, or both passwords clearly labeled); **RSOUTHERN** gets "username" instead of "call sign." Inactive members can't log in, so skip their emails unless they're being reactivated. Lost email later → `issue_temp_passwords.py --only CALLSIGN` on the server.
2. ~~**Commit and push** the last round~~: done Nov 6, 2026 (Check-In removal, Check default, temporary passwords, Add Member fix, HANDOFF rewrite). GitHub matches the live site.
3. **Give the Secretary a Records Manager login** on the live site (their member page → Access level).
4. **Self check-in kiosk (idea; no code yet).** A laptop or iPad by the door. A Records Manager or higher sets up the event and taps "Start check-in"; members type their call sign or username and tap "I'm here."
   - **Fix first:** make the Attendance page *add* to an event's list instead of replacing it, or it will wipe kiosk check-ins.
   - Lock the device to the kiosk screen (ideally drop the admin login on that device; exit with a PIN or password).
   - Show nothing private: no member list, just "Welcome, Sal. You're checked in." A discreet renewal note for expired dues, plus an expired-dues list for the Treasurer afterward.
   - Handle "already checked in," "not found / guest?" (guest count), former members (admins get a heads-up to reactivate), and auto-reset after a few seconds.
   - Reusable from the removed Check-In experiment (`archive/app-20261106-v7-with-checkin.py`): `pacific_today()`, the expired-dues note wording, the plain `event_guests` guest-count table.
5. **PayPal IPN (automatic "paid" updates).** Waiting on Eric (W6HS) for access to the club PayPal account. Check **Account Settings → Website payments → Instant payment notifications** (is IPN on, and what URL? It's account-wide, so don't overwrite one). Plan: a `/paypal/ipn` listener that verifies with PayPal (`cmd=_notify-validate`), matches pending `PaymentNotice` records by email and amount, and auto-confirms confident matches; unclear ones stay in the Treasurer's list.
6. **Equipment inventory (idea; no code yet).** The club owns radios, antennas, surplus and a trailer with a mast and beam; there's no complete inventory and no clear rule on what's club-use only, loanable or for sale.
   - **Phase 1:** admin-only inventory: asset tag (e.g. `WVARA-0001`), category, make/model/serial, condition, location and custodian (a member), photo, how acquired, and a **disposition** (Club use only / Loanable / For sale / Retired / **Undecided**, the default). Kits link to a parent item (the trailer owns its mast and beam).
   - **Phase 2:** members see Loanable and For sale items and request a loan or purchase; requests land in a "to confirm" list on the Admin Dashboard. Loans track out date, due date and return condition.
   - **Board questions:** who approves loans and sales; dues current to borrow; non-hams and transmitting gear; loan length and late rules; pricing and a members-first window; whether selling club assets needs a board vote; trailer towing, liability and insurance; an Equipment Manager role.
7. **Mobile polish:** Attendance is fine on an iPhone (Sal, Nov 6). The Members list could still use a phone layout.
8. **Future features Sal mentioned:** FCC license *expiration* alerts; member activity interests (Field Day, POTA, CW, ARES/CERT and so on).
9. **Small to-dos:**
   - Sal fixes his own and Eric's records by hand (Sal's record still has test details: phone `(408) 555-1234`, address `123 Radio Signal Lane`; real values are in the CSV: W6SAL joined 3/17/24; W6HS joined 1/24/25, license class E).
   - Check KK6IK on the live site for literal "None" emergency contact values (fixed on the Mac).
   - One live test sign-up, deleted afterward.
   - Tell Eric about the Lifetime-family decision (section 11).
   - Optional: `.git`, screenshots and `.DS_Store` were copied to the server in the first deploy (harmless, not web-accessible).

---

## 9. Open questions

- **Late-year joiners:** if someone joins in November and pays $15, do they owe again in January? (Not decided. The Pay Dues year pull-down lets the member choose; the Treasurer can adjust.)
- **Does PayPal pass a member identifier back?** Not confirmed for these hosted buttons; IPN matching may need email and amount.
- **Unknown old-database codes** (kept in each member's Admin Notes): what AutoCode, HetNotice (Requested/Published), EmailListsInit (A, M, C, WL) and MembEListYear mean. Eric or Scott might know.

---

## 10. Roster load record (Nov 6, 2026)

*Source: `WVARA_DB.csv`, the old club database export (141 rows, 35 columns). Loaded with `load_roster.py` on the Mac at 10:39 and on the server at 10:56.*

- **Mapping:** Regular → Individual; Regular-FamilyMaster → Family head; Family → linked to its head (`MasterFamilyCallsign`); Life → Lifetime; Inactive and SK → login disabled. License letters E/A/G/T/N → full names. Any CSV hide flag → full directory opt-out (AJ6LG, W6PGC). Family members whose address said "See <head>" got the head's address.
- **Dues records:** one per covered year. The real payment goes on its own year (Oct to Dec payments count for the next year); other prepaid years get a $0 "Prepaid per old club database" row. Family members and Lifetime members get none (they follow the head / are always current).
- **Legacy details** (Handle, Spouse, ARRL and repeater membership, Badge, old codes, Comments, last payment line, placeholder-date flags) went into each member's **Admin Notes**.
- **Sal's fixes:** Richard Southern → non-ham username `RSOUTHERN`; NT6S → CA 95125; AI6NT → 95008; K6EBN → 95014; missing emails filled (K6LOH, KK6DZS uses husband WU0I's, KC6BIG / KM6AAY / KD6KRS / W6LKK use `<call>@winlink.org`, KK6HFV and KN6QZJ share `jonathanzdasiuk@gmail.com`); **KC6QBF not loaded** (license expired 2002); missing join dates and `0000-00-00` payment dates → 2000-01-01 (flagged in Admin Notes); **NT6F, Silent Key**, passed April 14, 2026 (inactive); KG6KRI stays a family head with no family; KG6ENF stays Lifetime; N6MRO 2026 dues = $15 on 2026-01-15; W6SAL paid 2026 and 2027 (the CSV's 11/5/27 was a typo for 11/5/26). The 10 "Regular" members paid only through 2025 show as Expired.
- **Results:** server 140 members and 126 dues rows (the Mac got 129; the server skipped 3 years W6SAL and W6HS already had). W6SAL and W6HS kept their records; only their dues were added, and Sal will fix the rest by hand.

---

## 11. Decisions: self sign-up and family memberships (Nov 5, 2026)

- **Self sign-up at `/signup` gives instant access.** No admin approval; the CAPTCHA stays.
- **Licensed hams must use their call sign as their username.**
- **Non-hams pick a username:** 3 to 15 letters and numbers, nothing shaped like a call sign. Stored in `members.call_sign` with `is_licensed = False`. If they get licensed, an admin changes it to their call sign.
- **Family memberships:** everyone gets their own account; `family_head_id` points to the member who pays the $25; family members share the head's dues status; one level only.
  - A sign-up can request a family link; an admin confirms or declines it on the Admin Dashboard.
  - Confirming under an Individual head switches the head to Family ($25); the Treasurer settles any difference by hand.
  - If the head leaves or stops paying, the family expires with them; an admin can **Make Family Head** or **Move to Individual**.
  - Deleting a head moves their family members to Individual. No limit on family size.
- **Lifetime families:** if the head is Lifetime, the whole family is treated as Lifetime (Sal's call; Eric not yet told). The Lifetime tile counts only the head.

---

## 12. Backup archive (Nov 6, 2026)

- **`archive/`** holds every dated code, template and doc backup in the live folder layout (`archive/`, `archive/templates/`, `archive/templates/admin/`). Live folders hold live files only.
- **Database copies stay in `instance/`**, so member data lives in one place.
- **Deploy** skips `archive/` (`--exclude 'archive/'`, added Nov 6); the old `*-2026*` exclude stays as a safety net.
- **Git:** `archive/` is committed (Sal's call; private repo).
- **Removed Check-In experiment** (built and removed Nov 6, never deployed): `archive/app-20261106-v7-with-checkin.py`, `archive/templates/admin/checkin-20261106-removed.html`, `archive/templates/admin/checkin_summary-20261106-removed.html`, and the `-with-checkin` copies of `base.html` and `attendance.html`. Sal decided the regular Attendance page already works on an iPhone.
- **Restoring an old version:** back up the live file first, then copy the old one from `archive/` over it.

---

## 13. Moving the tool to wvara.org/members/ (planning, Nov 7, 2026; ADDED 2026-11-07)

*No code written yet. Backup of this file before the edit: `archive/HANDOFF-20261107.md`.*

- **Goal (board liked it):** host the tool at `https://wvara.org/members/`, separate from the PHP site, with the wvara.org header and footer around it.
- **WVARA PHP repo:** `github.com/WestValleyARA/website`, cloned to `/Users/smancuso/Documents/Personal/Sal/programming/WVARA-PHP/website`. Maintainer: Eric W6HS.
- **Hosting:** interserver.net. Sal says cPanel with "Setup Python App"; the repo's `docs/SUPPORTED-RUNTIME.md` shows a DirectAdmin-style panel (`:2222/evo`), **LiteSpeed 6.3.7** (not Apache), PHP 8.2, account `wvaraorg`. Python app selector runs a WSGI app from `passenger_wsgi.py`.
- **Findings from the PHP repo:**
  1. `header.php` is dynamic (nav from `config.php`, active-page class, Groups.io events ticker with cache), so a shared static header file won't work. Plan: Python fetches the rendered header/footer from a small PHP page and caches it.
  2. Every asset and nav link in `header.php`/`config.php` is **relative** (`assets/css/main.css`, `events`, `./`), so they break under `/members/`. Needs root-relative paths (`/assets/...`, `/events`) in the PHP; small change for Eric.
  3. `members.php` already exists (Groups.io buttons) and the nav's **Members** link points to it. A `/members/` app would take over that URL; its content should move into the tool's landing page (board/Eric decision).
  4. **Their deploy uses `rsync --delete`** on the whole public root (only `private/`, `.wvara-environment`, `cache/*` are preserved, `tools/release/interim-wvara-org-common.sh`). A `members/` folder in `public_html` would be wiped on the next PHP deploy unless `--exclude='/members/'` is added (3 rsync calls) and the CI checks allow it.
  5. `join.php` / `process-membership.php` handle Join/Renew and are "temporarily unavailable" in the interim production overlay; overlap with our `/signup` and Pay Dues needs a decision.
- **Our side:** Flask uses `url_for` everywhere, so a new mount path should mostly just work. SQLite is fine on shared hosting (keep `instance/` and `wvara.keys` outside `public_html`). Watch for Bootstrap 5.3 vs `main.css` style clashes once the PHP header is wrapped around our pages. Scheduled jobs would need cron (no long-running process).
- **Next step:** Sal checks the Python versions offered in the hosting panel's Python app setup.

---

## 14. Decision: rebuild wvara.org in Python/Flask (Nov 7, 2026; ADDED 2026-11-07)

*Backup of this file before the edit: `archive/HANDOFF-20261107-v2.md`. Section 13 is superseded by this section.*

- **Email trail:** Sal emailed Eric options (Nov 7, 5:47 PM). Eric replied (7:14 PM) favoring **converting the whole site to Python**: "the entire site is like six pages, a bunch of photos, and a stylesheet"; the design is his creative part and it's done; "I'm not married to PHP"; Groups.io security still needs work. Sal agrees.
- **Sal's proposed shape (being evaluated, no code yet):**
  1. The membership Flask app becomes the main wvara.org site (public pages + member area, one base template, so the header/footer sync problem goes away).
  2. A separate sync script (cron, not part of Flask) checks a GitHub repo every ~5 minutes for Markdown files with front matter that drive the public pages: home, Repeaters, New Hams, Membership Information, Mission, Donation Information (plus Events/About).
  3. Other club members get repo access to submit content changes.
  4. The Groups.io ticker (events, announcements) is rebuilt in Python.
- **Claude's recommended tweaks (Nov 7):** separate content repo from code repo; sync script pulls into a staging folder, validates front matter, then swaps (last good copy stays live on errors); sanitize Markdown (no raw HTML/scripts); nav built from front matter; Groups.io fetched by a background job into a JSON cache, never during a page load; Groups.io API key and ICS URL in a `.keys` file (the ICS URL with its tokens is currently committed in `config.php`; the API key lives in server-only `private/groupsio-config.php`); reuse Eric's `main.css`, images and `main.js` as is to keep his design; Join/Donate fold into `/signup` and Pay Dues; host on a club-owned DigitalOcean droplet ($6 to $12/mo).
- **Dependencies:** DNS/domain likely controlled by Scott Nacey (KK6IK, moving east); get registrar/DNS logins into a club account before cutover.
- **Next step:** Sal drafts a reply to Eric with the plan.

---

## 15. Site rebuild design decisions (Nov 9, 2026; ADDED 2026-11-09)

*Planning only, no code written. Backup of this file before the edit: `archive/HANDOFF-20261109.md`. Builds on section 14.*

### PHP review (Nov 9)
- The PHP site is 8 content pages (`index`, `events`, `members`, `repeaters`, `new-hams`, `join`, `mission`, `about`, plus `donate`), mostly hand-written HTML. Page bodies for About/Events/Mission are in `content/*.html`.
- Only five dynamic pieces: the **Upcoming Events ticker** (`includes/groupsio-events.php`, Groups.io ICS feed, 30-min cache, max 5 items; markup in `header.php`, rotation + detail overlay in `assets/js/main.js`), the **Latest from WVARA Chat** box (`includes/groupsio-latest-post.php`, Groups.io API key in server-only `private/groupsio-config.php`), **Join/Renew** (`join.php`, `process-membership.php` → replaced by `/signup` + Pay Dues), **Donate** (`donate.php`: PayPal JS SDK + a relay to Scott's Google Sheet; needs a talk with Scott/Eric), and reCAPTCHA.
- Plan: eliminate PHP entirely; the whole site lives in Flask. Port the ticker to Python (cron job → JSON cache), reuse Eric's ticker HTML/JS/CSS as is.

### Two repos
- **`wvara_membership`** (Sal only): Flask, templates, CSS/JS/images, sync script, ticker.
- **`wvara-content`** (private, WestValleyARA org): `pages/*.md`, `documents/*.md` (one per document), `files/` (the documents), `images/`. Editors for now: **Sal and Eric only**, pushing straight to `main`. Purpose is an easy handoff to a future Webmaster/Secretary/President, not editing by every board member. **Repo access = board-level access** (board documents live there, and git history keeps old versions).
- Sync script (cron, ~5 min): fetch, pull into staging, validate front matter / layouts / referenced files / file types / sizes, then swap; last good copy stays live on errors and Sal gets an email. Raw HTML and scripts stripped from Markdown (login shares the domain). Read-only deploy key.

### Officers page
- **Comes from the content repo, not the Roles page** (Sal): front matter with role, name, call, email, **photo and bio**. Photo/bio are not worth adding to the tool.
- The member Dashboard's Club Information card still reads President/Treasurer from Roles, so an officer change means updating both places.

### Members area and Documents
- Nav "Members" becomes **"Members Login"**. After login: Membership Tool, Groups.io how-to (members-only Markdown page), Documents.
- **One Documents page** lists everything (grouped by `category`), each document backed by its own `.md` file. Files live outside `static/` and are served by a login-checked route that **re-checks the tier on download**.
- Example front matter: `title`, `description`, `file`, `category`, `view`.
- **Today the board shares these documents only by email**; this is the first shared home for them.

| `view:` | Who sees it | Examples (Sal) |
|---|---|---|
| `members` | Any **active** member (account enabled, can log in), dues paid or not | Bylaws (encouraged, so people can see what membership requires) |
| `current` | Active **and** dues current | Repeater DTMF / autopatch codes, net control scripts |
| `board` | Active, dues current, **and** holds any **current** role on the Roles page (any title; started and not ended) | Repeater room access, the Good Samaritan Hospital entry procedure |
| *(System Administrator)* | **Sees everything**, regardless of dues or roles ("God mode") | Sal currently holds no board role |

- **Dues before the board seat:** a board member whose dues lapse drops to `members` only.
- **Active ≠ current.** Active = account enabled (can log in). Current = paid for this calendar year, Lifetime, in the grace period, or a family member whose head is current. Keep the two terms separate in code and on screen.
- Missing or misspelled `view:` → treated as `board` (fail closed) and flagged to Sal by the sync check.
- Members who see fewer documents get a short note ("Some club documents are available once your dues are current") with Pay Dues; no document names shown.
- Access levels and roles stay separate. Records Manager and Club Administrator levels grant **no** extra document access; only System Administrator does (the override above).

### Grace period change (decided Nov 9, not yet coded)
- **New rule:** dues for the year must be paid **no later than February 1**. Grace is January only. Unpaid after that → not current.
- Code today: `GRACE_PERIOD_LAST_MONTH = 2` in `models.py` (through the end of February). Change to `1`; update the `get_dues_status()` docstring ("January/February") and the HANDOFF line in section 4. This one setting drives dues badges, Expiring Soon, dashboard tiles, the members filters and document access.
- `get_dues_status()` uses `date.today()`, which is **UTC on the server**, so grace would end at 4 PM Pacific on Jan 31. Use a Pacific date (`pacific_today()` from the archived check-in code) when making this change.
