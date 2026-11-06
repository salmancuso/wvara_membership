"""
WVARA Membership Management System - Main Application
"""
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash
from models import db, Member, DuesPayment, RoleHistory, MeetingAttendance, AdminLog
from models import DUES_AMOUNT, DUES_RENEWAL_WARNING_MONTHS  # ADDED 2026-11-04
from models import PaymentNotice, DUES_BY_TYPE, dues_amount_for  # ADDED 2026-11-05

# ADDED 2026-11-05: the club's PayPal dues buttons (public button IDs, not secrets)
PAYPAL_BUTTONS = {
    'Individual': 'F54PDUUYZN668',   # $15.00 / year
    'Family': 'AVGLTZVHUWR8W',       # $25.00 / year
}


def paypal_url(choice: str) -> str:
    return f"https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id={PAYPAL_BUTTONS[choice]}"
from datetime import datetime, date, timedelta
from functools import wraps
import secrets
import string
import os
import csv
import io
import re
import base64
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
import random

from pathlib import Path  # ADDED 2026-11-04

# ADDED 2026-11-04: read secrets from a dedicated keys file (no environment variables)
KEYS_FILE = Path(__file__).resolve().parent / 'wvara.keys'


def load_keys(keys_file: Path = KEYS_FILE) -> dict:
    """Read KEY=VALUE lines from the keys file. Creates the file with a new SECRET_KEY if missing."""
    if not keys_file.exists():
        keys_file.write_text(
            "# WVARA Membership secrets. Do NOT commit this file.\n"
            f"SECRET_KEY={secrets.token_hex(32)}\n"
        )
        try:
            keys_file.chmod(0o600)
        except OSError:
            pass
    keys = {}
    for line in keys_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        keys[name.strip()] = value.strip()
    return keys


APP_KEYS = load_keys()

app = Flask(__name__)
# CHANGED 2026-11-04: SECRET_KEY now comes from wvara.keys so sessions survive restarts
app.config['SECRET_KEY'] = APP_KEYS['SECRET_KEY']
# CHANGED 2026-11-04: explicit path to the existing instance/wvara_membership.db (works on Mac and Linux)
Path(app.instance_path).mkdir(parents=True, exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + str(Path(app.instance_path) / 'wvara_membership.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)


# ADDED 2026-11-04: add new columns to an existing database on startup (no migration step needed)
def ensure_schema():
    """Create missing tables and add the directory_opt_out column if this database predates it"""
    with app.app_context():
        db.create_all()
        with db.engine.begin() as conn:
            columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(members)")}
            if 'directory_opt_out' not in columns:
                conn.exec_driver_sql(
                    "ALTER TABLE members ADD COLUMN directory_opt_out BOOLEAN NOT NULL DEFAULT 0")
                print("Database updated: added members.directory_opt_out")


ensure_schema()


# Utility Functions

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'call_sign' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'call_sign' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        
        member = Member.query.filter_by(call_sign=session['call_sign']).first()
        if not member or not member.is_admin:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def log_admin_action(action, target_member_call_sign=None, details=None):
    """Log administrative action"""
    log_entry = AdminLog(
        admin_call_sign=session.get('call_sign', 'SYSTEM'),
        action=action,
        target_member_call_sign=target_member_call_sign,
        details=details,
        ip_address=request.remote_addr
    )
    db.session.add(log_entry)
    db.session.commit()


def validate_password(password):
    """Validate password meets requirements"""
    if len(password) < 10:
        return False, "Password must be at least 10 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    return True, "Password is valid"


def generate_temp_password(length=12):
    """Generate a temporary password"""
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(characters) for _ in range(length))
    # Ensure it meets requirements
    if not re.search(r'[A-Z]', password):
        password = password[:-1] + 'A'
    if not re.search(r'[0-9]', password):
        password = password[:-1] + '1'
    if not re.search(r'[!@#$%^&*]', password):
        password = password[:-1] + '!'
    return password


def scrape_qrz_photo(call_sign):
    """Scrape photo URL from QRZ.com"""
    try:
        url = f"https://www.qrz.com/db/{call_sign.upper()}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Look for the profile image
            img_tag = soup.find('img', {'class': 'main-photo'})
            if not img_tag:
                # Try alternative selector
                img_tag = soup.find('img', alt=re.compile(call_sign, re.IGNORECASE))
            
            if img_tag and img_tag.get('src'):
                photo_url = img_tag['src']
                if not photo_url.startswith('http'):
                    photo_url = 'https://www.qrz.com' + photo_url
                return photo_url
    except Exception as e:
        print(f"Error scraping QRZ for {call_sign}: {e}")
    
    return None


# ADDED 2026-11-04: FCC call sign lookup (free public data via callook.info, HamDB as backup)
LOOKUP_HEADERS = {'User-Agent': 'WVARA-Membership/1.0'}
LOOKUP_TIMEOUT = 6  # seconds

FCC_CLASS_NAMES = {
    'TECHNICIAN': 'Technician', 'T': 'Technician',
    'GENERAL': 'General', 'G': 'General',
    'EXTRA': 'Amateur Extra', 'AMATEUR EXTRA': 'Amateur Extra', 'E': 'Amateur Extra',
    'ADVANCED': 'Advanced', 'A': 'Advanced',
    'NOVICE': 'Novice', 'N': 'Novice',
}
NAME_SUFFIXES = {'JR', 'JR.', 'SR', 'SR.', 'II', 'III', 'IV', 'V'}


def nice_case(text: str) -> str:
    """'SAN JOSE' -> 'San Jose', "O'BRIEN" -> "O'Brien" """
    return (text or '').strip().title()


def split_full_name(full_name: str) -> tuple:
    """'SALVATORE P MANCUSO JR' -> ('Salvatore', 'Mancuso Jr')"""
    parts = (full_name or '').replace(',', ' ').split()
    if not parts:
        return '', ''
    suffix = ''
    if len(parts) > 2 and parts[-1].upper() in NAME_SUFFIXES:
        suffix = ' ' + parts.pop().title()
    first = nice_case(parts[0])
    last = nice_case(parts[-1]) + suffix if len(parts) > 1 else ''
    return first, last


def parse_city_state_zip(line: str) -> tuple:
    """'SAN JOSE, CA 95125' -> ('San Jose', 'CA', '95125')"""
    match = re.match(r'^\s*(.*?),?\s+([A-Za-z]{2})\s+(\d{5})(?:-\d{4})?\s*$', line or '')
    if not match:
        return nice_case(line), '', ''
    return nice_case(match.group(1)), match.group(2).upper(), match.group(3)


def lookup_callook(call_sign: str):
    """Look up a US call sign on callook.info. Returns a dict of form fields or None."""
    response = requests.get(f'https://callook.info/{call_sign}/json',
                            headers=LOOKUP_HEADERS, timeout=LOOKUP_TIMEOUT)
    if response.status_code != 200:
        return None
    data = response.json()
    if data.get('status') != 'VALID':
        return None
    first, last = split_full_name(data.get('name', ''))
    address = data.get('address') or {}
    city, state, zip_code = parse_city_state_zip(address.get('line2', ''))
    oper_class = ((data.get('current') or {}).get('operClass') or '').upper()
    return {
        'first_name': first,
        'last_name': last,
        'address': nice_case(address.get('line1', '')),
        'city': city,
        'state': state,
        'zip_code': zip_code,
        'fcc_license_class': FCC_CLASS_NAMES.get(oper_class, ''),
        'license_type': (data.get('type') or '').title(),
        'expires': (data.get('otherInfo') or {}).get('expiryDate', ''),
        'source': 'callook.info',
    }


def lookup_hamdb(call_sign: str):
    """Backup lookup on HamDB.org. Returns a dict of form fields or None."""
    response = requests.get(f'https://api.hamdb.org/{call_sign}/json/wvara_membership',
                            headers=LOOKUP_HEADERS, timeout=LOOKUP_TIMEOUT)
    if response.status_code != 200:
        return None
    data = (response.json() or {}).get('hamdb') or {}
    if (data.get('messages') or {}).get('status') != 'OK':
        return None
    cs = data.get('callsign') or {}
    if not cs.get('call') or cs.get('call') == 'NOT_FOUND':
        return None
    return {
        'first_name': nice_case(cs.get('fname', '')),
        'last_name': nice_case(cs.get('name', '')),
        'address': nice_case(cs.get('addr1', '')),
        'city': nice_case(cs.get('addr2', '')),
        'state': (cs.get('state') or '').upper(),
        'zip_code': (cs.get('zip') or '')[:5],
        'fcc_license_class': FCC_CLASS_NAMES.get((cs.get('class') or '').upper(), ''),
        'license_type': '',
        'expires': cs.get('expires', ''),
        'source': 'HamDB.org',
    }


def lookup_call_sign(call_sign: str):
    """Try callook.info first, then HamDB. Returns (result_dict_or_None, error_message)."""
    for lookup in (lookup_callook, lookup_hamdb):
        try:
            result = lookup(call_sign)
            if result:
                return result, ''
        except Exception as e:  # network trouble or unexpected data; try the next service
            print(f"Call sign lookup error ({lookup.__name__}) for {call_sign}: {e}")
    return None, f'No FCC record found for {call_sign}. You can still enter the details by hand.'


# ADDED 2026-11-04: Member Map (ZIP code bubbles within 75 miles of Campbell, CA)
import json
import math

# CHANGED 2026-11-04: distances now measured from the WVARA repeater site
# Good Samaritan Hospital, 2425 Samaritan Dr, San Jose, CA 95124 (US Census geocoder)
MAP_CENTER = (37.251167, -121.945463)
MAP_CENTER_NAME = 'the repeaters (Good Samaritan Hospital)'
MAP_RADIUS_MILES = 75
ZIP_SEED_FILE = Path(__file__).resolve().parent / 'static' / 'data' / 'zip_centroids.json'
ZIP_LOOKUPS_PER_PAGE = 25           # new ZIPs looked up per page load (keeps the page quick)
_zip_seed_cache = None


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line distance in miles between two lat/lon points"""
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def zip_cache_file() -> Path:
    return Path(app.instance_path) / 'zip_cache.json'


def load_zip_seed() -> dict:
    """ZIP centroids shipped with the app (static/data/zip_centroids.json)"""
    global _zip_seed_cache
    if _zip_seed_cache is None:
        try:
            _zip_seed_cache = json.loads(ZIP_SEED_FILE.read_text()).get('zips', {})
        except (OSError, ValueError):
            _zip_seed_cache = {}
    return _zip_seed_cache


def load_zip_cache() -> dict:
    """ZIPs looked up later and saved in instance/zip_cache.json"""
    try:
        return json.loads(zip_cache_file().read_text())
    except (OSError, ValueError):
        return {}


def lookup_zip_online(zip5: str):
    """Ask api.zippopotam.us for a ZIP's center point. Only the ZIP code is sent."""
    response = requests.get(f'https://api.zippopotam.us/us/{zip5}', headers=LOOKUP_HEADERS, timeout=4)
    if response.status_code == 404:
        return {'not_found': True}
    response.raise_for_status()
    place = response.json()['places'][0]
    return {'lat': float(place['latitude']), 'lon': float(place['longitude']),
            'place': place['place name'], 'state': place['state abbreviation']}


def resolve_zip_locations(zip_codes) -> dict:
    """Return {zip: location} using the seed file, then the cache, then a small number of online lookups"""
    seed, cache = load_zip_seed(), load_zip_cache()
    found, lookups, cache_changed = {}, 0, False
    for z in zip_codes:
        loc = seed.get(z) or cache.get(z)
        if loc is None and lookups < ZIP_LOOKUPS_PER_PAGE:
            lookups += 1
            try:
                loc = lookup_zip_online(z)
                cache[z] = loc
                cache_changed = True
            except Exception as e:
                print(f"ZIP lookup error for {z}: {e}")
        if loc and not loc.get('not_found'):
            found[z] = loc
    if cache_changed:
        try:
            zip_cache_file().write_text(json.dumps(cache, indent=1))
        except OSError as e:
            print(f"Could not save ZIP cache: {e}")
    return found


def generate_captcha():
    """Generate an image-based CAPTCHA"""
    # Generate random word (5 characters)
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # Excluding confusing characters
    captcha_text = ''.join(random.choice(chars) for _ in range(5))
    
    # Create image
    width, height = 200, 80
    image = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(image)
    
    # Add background noise lines
    for _ in range(5):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        draw.line([(x1, y1), (x2, y2)], fill=(200, 200, 200), width=2)
    
    # Try to use a system font, fall back to default if not available
    try:
        from PIL import ImageFont
        # Try common system fonts
        font_paths = [
            '/System/Library/Fonts/Supplemental/Arial Bold.ttf',  # macOS
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',  # Linux
            'C:\\Windows\\Fonts\\arialbd.ttf',  # Windows
        ]
        font = None
        for font_path in font_paths:
            try:
                font = ImageFont.truetype(font_path, 48)
                break
            except:
                continue
        if font is None:
            font = ImageFont.load_default()
    except:
        font = None
    
    # Draw text with slight variations
    x_start = 20
    for i, char in enumerate(captcha_text):
        # Random position variation
        x = x_start + (i * 32) + random.randint(-3, 3)
        y = 15 + random.randint(-5, 5)
        
        # Random color (dark colors)
        color = (
            random.randint(0, 100),
            random.randint(0, 100),
            random.randint(0, 100)
        )
        
        # Draw character
        if font:
            draw.text((x, y), char, fill=color, font=font)
        else:
            draw.text((x, y), char, fill=color)
    
    # Add some noise dots
    for _ in range(100):
        x, y = random.randint(0, width), random.randint(0, height)
        draw.point((x, y), fill=(random.randint(150, 200), random.randint(150, 200), random.randint(150, 200)))
    
    # Save to bytes
    import io
    img_io = io.BytesIO()
    image.save(img_io, 'PNG')
    img_io.seek(0)
    
    # Store text in session
    session['captcha'] = captcha_text
    
    # Return base64 encoded image
    import base64
    img_base64 = base64.b64encode(img_io.getvalue()).decode()
    
    return img_base64


def verify_captcha(user_input):
    """Verify CAPTCHA input"""
    if 'captcha' not in session:
        return False
    
    captcha = session.get('captcha', '')
    # Case-insensitive comparison, remove spaces
    return user_input.upper().replace(' ', '') == captcha.upper().replace(' ', '')


# ADDED 2026-11-04: CSRF protection (no extra packages needed)
def get_csrf_token() -> str:
    """Return this session's CSRF token, creating one if needed"""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


app.jinja_env.globals['csrf_token'] = get_csrf_token


@app.before_request
def csrf_protect():
    """Reject any POST that does not carry this session's CSRF token"""
    if request.method == 'POST':
        sent = request.form.get('csrf_token', '')
        expected = session.get('_csrf_token', '')
        if not expected or not secrets.compare_digest(sent, expected):
            flash('Your session expired or the form was out of date. Please try again.', 'warning')
            return redirect(request.url)


# ADDED 2026-11-04: members on a temporary password cannot go anywhere until they set their own
PASSWORD_CHANGE_ALLOWED = {'change_password', 'logout', 'login', 'refresh_captcha', 'static', 'index'}


@app.before_request
def force_password_change():
    """Send members with a temporary password to the change password page"""
    if 'call_sign' not in session or request.endpoint in PASSWORD_CHANGE_ALLOWED:
        return None
    member = Member.query.filter_by(call_sign=session['call_sign']).first()
    if member is None:
        session.clear()
        return redirect(url_for('login'))
    if member.password_is_temporary:
        flash('Please create your own password before continuing.', 'warning')
        return redirect(url_for('change_password'))
    return None


# ADDED 2026-11-04: one rule for "Expiring Soon", shared by the dashboard and the members filter
def is_expiring_soon(member, today=None) -> bool:
    """Grace period members, or paid members within 2 months of the Dec 31 end date"""
    today = today or date.today()
    status = member.get_dues_status()
    if status == 'grace':
        return True
    return status == 'paid' and today.month > 12 - DUES_RENEWAL_WARNING_MONTHS


# ADDED 2026-11-04: guard so an admin action can never leave the club with zero admins
def would_remove_last_admin(member) -> bool:
    """True if this member is the only active admin left"""
    if not (member.is_admin and member.is_active):
        return False
    return Member.query.filter_by(is_admin=True, is_active=True).count() <= 1


# Routes

@app.route('/')
def index():
    """Home page - redirect to login or dashboard"""
    if 'call_sign' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page"""
    if request.method == 'POST':
        call_sign = request.form.get('call_sign', '').upper().strip()
        password = request.form.get('password', '')
        captcha_input = request.form.get('captcha', '')
        
        # Verify CAPTCHA first
        if not verify_captcha(captcha_input):
            flash('Invalid CAPTCHA. Please try again.', 'danger')
            generate_captcha()  # Generate new one
            return redirect(url_for('login'))
        
        member = Member.query.filter_by(call_sign=call_sign).first()
        
        if member and member.check_password(password):
            session['call_sign'] = member.call_sign
            session['is_admin'] = member.is_admin
            
            # Update last contact
            member.last_contact = datetime.utcnow()
            db.session.commit()
            
            flash(f'Welcome back, {member.first_name}!', 'success')
            
            # Redirect to change password if temporary
            if member.password_is_temporary:
                flash('You are using a temporary password. Please change it now.', 'warning')
                return redirect(url_for('change_password'))
            
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid call sign or password', 'danger')
            generate_captcha()  # Generate new one for retry
            return redirect(url_for('login'))
    
    # Generate CAPTCHA for GET request
    captcha_text = generate_captcha()
    
    return render_template('login.html', captcha=captcha_text)


@app.route('/logout')
def logout():
    """Logout"""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/refresh_captcha')
def refresh_captcha():
    """Generate new CAPTCHA"""
    captcha_text = generate_captcha()
    return {'captcha': captcha_text}


@app.route('/dashboard')
@login_required
def dashboard():
    """Member dashboard"""
    member = Member.query.filter_by(call_sign=session['call_sign']).first()
    
    # Get current dues status
    current_year = date.today().year
    dues_status = member.get_current_dues_status()
    
    # Get recent meetings attended
    recent_meetings = MeetingAttendance.query.filter_by(
        member_id=member.id
    ).order_by(MeetingAttendance.meeting_date.desc()).limit(5).all()
    
    # Get current roles
    current_roles = RoleHistory.query.filter_by(
        member_id=member.id,
        is_current=True
    ).all()
    
    return render_template('dashboard.html',
                         member=member,
                         dues_status=dues_status,
                         dues_state=member.get_dues_status(),  # ADDED 2026-11-04
                         current_year=current_year,
                         recent_meetings=recent_meetings,
                         current_roles=current_roles)


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """View/edit member profile"""
    member = Member.query.filter_by(call_sign=session['call_sign']).first()
    
    if request.method == 'POST':
        action = request.form.get('action', 'update_info')
        
        if action == 'update_qrz_photo':
            photo_url = scrape_qrz_photo(member.call_sign)
            if photo_url:
                member.qrz_photo_url = photo_url
                db.session.commit()
                flash('QRZ photo updated successfully!', 'success')
            else:
                flash('Could not retrieve photo from QRZ.com. Make sure your call sign has a photo on QRZ.', 'warning')
            return redirect(url_for('profile'))
        
        # Update contact information
        member.first_name = request.form.get('first_name')
        member.last_name = request.form.get('last_name')
        member.email = request.form.get('email')
        member.phone = request.form.get('phone')
        member.address = request.form.get('address')
        member.city = request.form.get('city')
        member.state = request.form.get('state')
        member.zip_code = request.form.get('zip_code')
        
        # Emergency contact
        member.emergency_contact_name = request.form.get('emergency_contact_name')
        member.emergency_contact_phone = request.form.get('emergency_contact_phone')
        member.emergency_contact_relationship = request.form.get('emergency_contact_relationship')
        
        # FCC License class
        member.fcc_license_class = request.form.get('fcc_license_class')

        # ADDED 2026-11-04: hide my email, phone and street address from the member directory
        member.directory_opt_out = request.form.get('directory_opt_out') == 'on'

        member.updated_at = datetime.utcnow()
        member.last_contact = datetime.utcnow()
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        
        return redirect(url_for('profile'))
    
    return render_template('profile.html', member=member)


@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password"""
    member = Member.query.filter_by(call_sign=session['call_sign']).first()
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Verify current password
        if not member.check_password(current_password):
            flash('Current password is incorrect', 'danger')
            return redirect(url_for('change_password'))
        
        # Validate new password
        if new_password != confirm_password:
            flash('New passwords do not match', 'danger')
            return redirect(url_for('change_password'))
        
        is_valid, message = validate_password(new_password)
        if not is_valid:
            flash(message, 'danger')
            return redirect(url_for('change_password'))

        # ADDED 2026-11-04: the new password has to be different from the temporary one
        if member.check_password(new_password):
            flash('Your new password must be different from your current password', 'danger')
            return redirect(url_for('change_password'))
        
        # Update password
        member.set_password(new_password)
        member.password_is_temporary = False
        db.session.commit()
        
        flash('Password changed successfully!', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('change_password.html', member=member)


# Admin Routes

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Admin dashboard"""
    total_members = Member.query.count()
    all_members = Member.query.filter_by(is_active=True).all()
    
    # Calculate members with paid dues
    members_with_paid_dues = sum(1 for m in all_members if m.is_dues_current())
    
    # Calculate truly active members (dues paid + recent activity in last 6 months)
    truly_active = sum(1 for m in all_members if m.is_truly_active())
    
    # Members with expiring/expired dues
    current_year = date.today().year
    current_date = date.today()
    
    # Check dues status for each
    expired_dues = []
    expiring_soon = []
    
    # CHANGED 2026-11-04: use the single dues status; Lifetime members never expire
    for member in all_members:
        status = member.get_dues_status()
        if status == 'expired':
            expired_dues.append(member)
        # CHANGED 2026-11-04: grace period, or within 2 months of Dec 31 (shared rule)
        elif is_expiring_soon(member, current_date):
            expiring_soon.append(member)

    # ADDED 2026-11-04: Lifetime members tile
    lifetime_members = [m for m in all_members if m.is_lifetime()]
    
    # Recent activity
    recent_attendance = MeetingAttendance.query.order_by(
        MeetingAttendance.meeting_date.desc()
    ).limit(10).all()
    
    recent_payments = DuesPayment.query.order_by(
        DuesPayment.payment_date.desc()
    ).limit(10).all()
    
    return render_template('admin/dashboard.html',
                         total_members=total_members,
                         members_with_paid_dues=members_with_paid_dues,
                         truly_active_members=truly_active,
                         expired_dues=expired_dues,
                         expiring_soon=expiring_soon,
                         lifetime_members=lifetime_members,  # ADDED 2026-11-04
                         recent_attendance=recent_attendance,
                         recent_payments=recent_payments)


@app.route('/admin/members')
@admin_required
def admin_members():
    """View all members"""
    search = request.args.get('search', '')
    status_filter = request.args.get('status', 'all')  # all, active, inactive, expired
    
    query = Member.query
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Member.call_sign.ilike(search_term),
                Member.first_name.ilike(search_term),
                Member.last_name.ilike(search_term),
                Member.email.ilike(search_term)
            )
        )
    
    # Apply status filter
    all_members = query.order_by(Member.call_sign).all()
    
    if status_filter == 'active':
        # Truly active: dues paid + activity in last 6 months
        members = [m for m in all_members if m.is_active and m.is_truly_active()]
    elif status_filter == 'inactive':
        # Inactive: dues paid but no recent activity
        members = [m for m in all_members if m.is_active and m.is_dues_current() and not m.has_recent_activity()]
    elif status_filter == 'expired':
        # Expired: dues not current
        members = [m for m in all_members if m.is_active and not m.is_dues_current()]
    elif status_filter == 'disabled':
        # Disabled accounts
        members = [m for m in all_members if not m.is_active]
    # ADDED 2026-11-04: filters the dashboard tiles link to
    elif status_filter == 'current':
        members = [m for m in all_members if m.is_active and m.is_dues_current()]
    elif status_filter == 'expiring':
        members = [m for m in all_members if m.is_active and is_expiring_soon(m)]
    elif status_filter == 'lifetime':
        members = [m for m in all_members if m.is_active and m.is_lifetime()]
    elif status_filter == 'everyone':
        members = list(all_members)
    else:
        # All active accounts
        members = [m for m in all_members if m.is_active]
    
    return render_template('admin/members.html',
                         members=members,
                         search=search,
                         status_filter=status_filter)


@app.route('/admin/member/add', methods=['GET', 'POST'])
@admin_required
def admin_add_member():
    """Add new member"""
    if request.method == 'POST':
        call_sign = request.form.get('call_sign', '').upper().strip()
        
        # Check if call sign already exists
        existing = Member.query.filter_by(call_sign=call_sign).first()
        if existing:
            flash(f'Call sign {call_sign} already exists', 'danger')
            return redirect(url_for('admin_add_member'))
        
        # Parse join date
        try:
            join_date = datetime.strptime(request.form.get('join_date'), '%Y-%m-%d').date()
        except:
            join_date = date.today()
        
        # Create new member
        new_member = Member(
            call_sign=call_sign,
            first_name=request.form.get('first_name'),
            last_name=request.form.get('last_name'),
            email=request.form.get('email'),
            phone=request.form.get('phone', ''),
            address=request.form.get('address', ''),
            city=request.form.get('city', ''),
            state=request.form.get('state', ''),
            zip_code=request.form.get('zip_code', ''),
            fcc_license_class=request.form.get('fcc_license_class', ''),
            membership_type=request.form.get('membership_type', 'Individual'),
            join_date=join_date,
            is_active=True,
            is_admin=False,
            emergency_contact_name=request.form.get('emergency_contact_name'),
            emergency_contact_phone=request.form.get('emergency_contact_phone'),
            emergency_contact_relationship=request.form.get('emergency_contact_relationship', '')
        )
        
        # Set initial password to call sign
        new_member.set_password(call_sign)
        new_member.password_is_temporary = True
        
        db.session.add(new_member)
        db.session.commit()
        
        log_admin_action('Added new member', call_sign, f'Initial password: {call_sign}')
        flash(f'Member {call_sign} added successfully! Initial password: {call_sign}', 'success')
        
        return redirect(url_for('admin_member_detail', member_id=new_member.id))
    
    return render_template('admin/add_member.html', today=date.today().strftime('%Y-%m-%d'))


# ADDED 2026-11-04: Look Up button on Add Member calls this and fills in the form
@app.route('/admin/lookup_callsign')
@admin_required
def admin_lookup_callsign():
    """Return public FCC data for a call sign as JSON"""
    call_sign = request.args.get('call_sign', '').upper().strip()
    if not re.fullmatch(r'[A-Z0-9]{3,8}', call_sign):
        return {'found': False, 'message': 'Please enter a valid call sign (letters and numbers only).'}

    existing = Member.query.filter_by(call_sign=call_sign).first()
    result, message = lookup_call_sign(call_sign)

    response = {'found': result is not None, 'message': message, 'data': result or {}}
    if existing:
        response['existing_member'] = {
            'name': existing.get_full_name(),
            'url': url_for('admin_member_detail', member_id=existing.id),
        }
    return response


@app.route('/admin/member/<int:member_id>', methods=['GET', 'POST'])
@admin_required
def admin_member_detail(member_id):
    """View/edit member details (admin)"""
    member = Member.query.get_or_404(member_id)
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_info':
            # Update member information including call sign and join date
            new_call_sign = request.form.get('call_sign', '').upper().strip()
            
            # Check if call sign changed and if new one is available
            if new_call_sign != member.call_sign:
                existing = Member.query.filter_by(call_sign=new_call_sign).first()
                if existing:
                    flash(f'Call sign {new_call_sign} is already in use', 'danger')
                    return redirect(url_for('admin_member_detail', member_id=member_id))
                # ADDED 2026-11-04: keep the admin logged in if they change their own call sign
                if member.call_sign == session.get('call_sign'):
                    session['call_sign'] = new_call_sign
                member.call_sign = new_call_sign
            
            member.first_name = request.form.get('first_name')
            member.last_name = request.form.get('last_name')
            member.email = request.form.get('email')
            member.phone = request.form.get('phone')
            member.address = request.form.get('address')
            member.city = request.form.get('city')
            member.state = request.form.get('state')
            member.zip_code = request.form.get('zip_code')
            member.fcc_license_class = request.form.get('fcc_license_class')
            member.membership_type = request.form.get('membership_type')
            
            # Update join date
            try:
                join_date_str = request.form.get('join_date')
                if join_date_str:
                    member.join_date = datetime.strptime(join_date_str, '%Y-%m-%d').date()
            except:
                flash('Invalid join date format', 'warning')
            
            # Emergency contact
            member.emergency_contact_name = request.form.get('emergency_contact_name')
            member.emergency_contact_phone = request.form.get('emergency_contact_phone')
            member.emergency_contact_relationship = request.form.get('emergency_contact_relationship')

            # ADDED 2026-11-04: admins can set the directory opt-out for a member who asks by phone
            member.directory_opt_out = request.form.get('directory_opt_out') == 'on'

            db.session.commit()
            log_admin_action(f'Updated member information', member.call_sign)
            flash('Member information updated successfully!', 'success')
        
        # ADDED 2026-11-04: lockout guards (no removing your own access, never zero admins)
        elif action in ('toggle_admin', 'toggle_active', 'delete_member') and member.call_sign == session.get('call_sign'):
            flash('You cannot remove your own admin access, deactivate, or delete your own account. Ask another admin.', 'danger')
        elif action in ('toggle_admin', 'toggle_active', 'delete_member') and would_remove_last_admin(member):
            flash(f'{member.call_sign} is the last active admin. Grant admin to someone else first.', 'danger')

        elif action == 'toggle_admin':
            member.is_admin = not member.is_admin
            db.session.commit()
            log_admin_action(f'{"Granted" if member.is_admin else "Revoked"} admin access', member.call_sign)
            flash(f'Admin access {"granted" if member.is_admin else "revoked"} for {member.call_sign}', 'success')
        
        elif action == 'toggle_active':
            member.is_active = not member.is_active
            db.session.commit()
            log_admin_action(f'{"Activated" if member.is_active else "Deactivated"} member', member.call_sign)
            flash(f'Member {member.call_sign} {"activated" if member.is_active else "deactivated"}', 'success')
        
        elif action == 'reset_password':
            temp_password = generate_temp_password()
            member.set_password(temp_password)
            member.password_is_temporary = True
            db.session.commit()
            log_admin_action('Reset password', member.call_sign)
            flash(f'Temporary password for {member.call_sign}: {temp_password}', 'warning')
        
        elif action == 'update_qrz_photo':
            photo_url = scrape_qrz_photo(member.call_sign)
            if photo_url:
                member.qrz_photo_url = photo_url
                db.session.commit()
                flash('QRZ photo updated successfully!', 'success')
            else:
                flash('Could not retrieve photo from QRZ.com', 'warning')
        
        elif action == 'delete_member':
            # Confirm deletion
            call_sign = member.call_sign
            db.session.delete(member)
            db.session.commit()
            log_admin_action('Deleted member', call_sign)
            flash(f'Member {call_sign} has been permanently deleted', 'success')
            return redirect(url_for('admin_members'))
        
        return redirect(url_for('admin_member_detail', member_id=member_id))
    
    # Get member history
    dues_history = DuesPayment.query.filter_by(member_id=member_id).order_by(DuesPayment.year.desc()).all()
    role_history = RoleHistory.query.filter_by(member_id=member_id).order_by(RoleHistory.start_date.desc()).all()
    attendance_history = MeetingAttendance.query.filter_by(member_id=member_id).order_by(MeetingAttendance.meeting_date.desc()).limit(20).all()
    
    return render_template('admin/member_detail.html',
                         member=member,
                         dues_history=dues_history,
                         role_history=role_history,
                         attendance_history=attendance_history)


@app.route('/admin/dues', methods=['GET', 'POST'])
@admin_required
def admin_dues():
    """Manage dues payments"""
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        
        if action == 'add':
            member_id = request.form.get('member_id')
            year = int(request.form.get('year'))
            amount = float(request.form.get('amount'))
            payment_date = datetime.strptime(request.form.get('payment_date'), '%Y-%m-%d').date()
            payment_method = request.form.get('payment_method', 'PayPal')
            notes = request.form.get('notes', '')
            
            # Check if payment already exists
            existing = DuesPayment.query.filter_by(member_id=member_id, year=year).first()
            if existing:
                flash('Dues payment for this year already recorded. Use Edit to modify.', 'warning')
            else:
                payment = DuesPayment(
                    member_id=member_id,
                    year=year,
                    amount=amount,
                    payment_date=payment_date,
                    payment_method=payment_method,
                    notes=notes,
                    created_by=session['call_sign']
                )
                db.session.add(payment)
                db.session.commit()
                
                member = Member.query.get(member_id)
                log_admin_action(f'Recorded dues payment for {year}', member.call_sign, f'Amount: ${amount}')
                flash('Dues payment recorded successfully!', 'success')
        
        elif action == 'edit':
            payment_id = request.form.get('payment_id')
            payment = DuesPayment.query.get(payment_id)
            
            # ADDED 2026-11-04: block edits that would create a second payment for the same year
            new_year = int(request.form.get('year'))
            duplicate = None
            if payment:
                duplicate = DuesPayment.query.filter(
                    DuesPayment.member_id == payment.member_id,
                    DuesPayment.year == new_year,
                    DuesPayment.id != payment.id
                ).first()
            if duplicate:
                flash(f'{payment.member.call_sign} already has a {new_year} payment. Edit that one instead.', 'warning')
                payment = None

            if payment:
                payment.year = int(request.form.get('year'))
                payment.amount = float(request.form.get('amount'))
                payment.payment_date = datetime.strptime(request.form.get('payment_date'), '%Y-%m-%d').date()
                payment.payment_method = request.form.get('payment_method', 'PayPal')
                payment.notes = request.form.get('notes', '')
                
                db.session.commit()
                log_admin_action(f'Updated dues payment for {payment.year}', payment.member.call_sign)
                flash('Dues payment updated successfully!', 'success')
        
        elif action == 'delete':
            payment_id = request.form.get('payment_id')
            payment = DuesPayment.query.get(payment_id)
            
            if payment:
                member_call = payment.member.call_sign
                year = payment.year
                db.session.delete(payment)
                db.session.commit()
                log_admin_action(f'Deleted dues payment for {year}', member_call)
                flash('Dues payment deleted successfully!', 'success')

        # ADDED 2026-11-05: confirm or dismiss a PayPal payment a member started
        elif action == 'confirm_notice':
            notice = db.session.get(PaymentNotice, int(request.form.get('notice_id', 0) or 0))
            if notice and notice.status == 'pending':
                existing = DuesPayment.query.filter_by(member_id=notice.member_id, year=notice.dues_year).first()
                if existing:
                    notice.dues_payment_id = existing.id
                    flash(f'{notice.member.call_sign} already had a {notice.dues_year} payment recorded, so nothing new was added.', 'warning')
                else:
                    note_parts = [f'PayPal {notice.membership_choice}',
                                  f'started {notice.created_at.strftime("%Y-%m-%d")}']
                    if notice.family_members:
                        note_parts.append(f'Family: {notice.family_members}')
                    payment = DuesPayment(
                        member_id=notice.member_id,
                        year=notice.dues_year,
                        amount=notice.amount,
                        payment_date=date.today(),
                        payment_method='PayPal',
                        notes='; '.join(note_parts),
                        created_by=session['call_sign'],
                    )
                    db.session.add(payment)
                    db.session.flush()
                    notice.dues_payment_id = payment.id
                    flash(f'Marked {notice.member.call_sign} paid for {notice.dues_year} (${notice.amount:.2f}).', 'success')
                notice.status = 'confirmed'
                notice.handled_by = session['call_sign']
                notice.handled_at = datetime.utcnow()
                db.session.commit()
                log_admin_action(f'Confirmed PayPal dues for {notice.dues_year}', notice.member.call_sign,
                                 f'{notice.membership_choice} ${notice.amount:.2f}')

        elif action == 'dismiss_notice':
            notice = db.session.get(PaymentNotice, int(request.form.get('notice_id', 0) or 0))
            if notice and notice.status == 'pending':
                notice.status = 'dismissed'
                notice.handled_by = session['call_sign']
                notice.handled_at = datetime.utcnow()
                db.session.commit()
                log_admin_action('Dismissed PayPal payment notice', notice.member.call_sign, f'{notice.dues_year}')
                flash(f'Dismissed the PayPal notice from {notice.member.call_sign}.', 'info')

        return redirect(url_for('admin_dues'))
    
    # Get all active members
    members = Member.query.filter_by(is_active=True).order_by(Member.call_sign).all()
    
    # Get most recent payment for each member
    member_payment_data = []
    current_year = date.today().year
    
    for member in members:
        # Get most recent payment for this member
        most_recent_payment = DuesPayment.query.filter_by(
            member_id=member.id
        ).order_by(DuesPayment.year.desc(), DuesPayment.payment_date.desc()).first()
        
        # CHANGED 2026-11-04: same dues status used everywhere (lifetime / paid / grace / expired)
        status = member.get_dues_status()

        # ADDED 2026-11-04: full payment history so older payments can be edited or deleted
        all_payments = DuesPayment.query.filter_by(
            member_id=member.id
        ).order_by(DuesPayment.year.desc(), DuesPayment.payment_date.desc()).all()

        member_payment_data.append({
            'member': member,
            'payment': most_recent_payment,
            'status': status,
            'history': all_payments,
            'has_current_year': any(p.year == current_year for p in all_payments)
        })
    
    # Sort by most recent payment year (descending), then by payment date
    member_payment_data.sort(
        key=lambda x: (
            x['payment'].year if x['payment'] else 0,
            x['payment'].payment_date if x['payment'] else date.min
        ),
        reverse=True
    )
    
    return render_template('admin/dues.html',
                         members=members,
                         member_payment_data=member_payment_data,
                         current_year=current_year,
                         dues_amount=DUES_AMOUNT,  # ADDED 2026-11-04
                         dues_by_type=DUES_BY_TYPE,  # ADDED 2026-11-05
                         pending_notices=PaymentNotice.query.filter_by(status='pending')
                             .order_by(PaymentNotice.created_at.desc()).all())  # ADDED 2026-11-05


@app.template_filter('get_attendance_for_date')
def get_attendance_for_date(meeting_date):
    """Get all attendance records for a specific date"""
    return MeetingAttendance.query.filter_by(meeting_date=meeting_date).all()


# ADDED 2026-11-04: attendance for one specific event (date + type + name)
def event_attendance_query(meeting_date, event_type, event_name):
    """Query for attendance records belonging to one event"""
    query = MeetingAttendance.query.filter_by(meeting_date=meeting_date, event_type=event_type)
    if event_name:
        return query.filter_by(event_name=event_name)
    return query.filter(db.or_(MeetingAttendance.event_name.is_(None), MeetingAttendance.event_name == ''))


@app.template_filter('get_attendance_for_event')
def get_attendance_for_event(meeting):
    """Template filter: all attendance records for one event row"""
    return event_attendance_query(meeting.meeting_date, meeting.event_type, meeting.event_name).all()


@app.route('/admin/attendance', methods=['GET', 'POST'])
@admin_required
def admin_attendance():
    """Record meeting attendance"""
    if request.method == 'POST':
        action = request.form.get('action', 'add')
        
        if action == 'add':
            meeting_date = datetime.strptime(request.form.get('meeting_date'), '%Y-%m-%d').date()
            event_type = request.form.get('event_type', 'Meeting')
            event_name = request.form.get('event_name', '')
            attended_members = request.form.getlist('attended')
            
            # CHANGED 2026-11-04: only replace attendance for this SAME event (date + type + name),
            # so a second event on the same day no longer wipes out the first one
            MeetingAttendance.query.filter_by(
                meeting_date=meeting_date,
                event_type=event_type,
                event_name=event_name
            ).delete()
            
            # Record new attendance
            for member_id in attended_members:
                attendance = MeetingAttendance(
                    member_id=int(member_id),
                    meeting_date=meeting_date,
                    attended=True,
                    event_type=event_type,
                    event_name=event_name,
                    recorded_by=session['call_sign']
                )
                db.session.add(attendance)
            
            db.session.commit()
            log_admin_action('Recorded meeting attendance', details=f'Date: {meeting_date}, Type: {event_type}, Attendees: {len(attended_members)}')
            flash(f'Attendance recorded for {len(attended_members)} members', 'success')
        
        elif action == 'remove_attendee':
            # Remove individual attendee from a meeting
            attendance_id = request.form.get('attendance_id')
            attendance = MeetingAttendance.query.get(attendance_id)
            if attendance:
                member_call = attendance.member.call_sign
                event_date = attendance.meeting_date
                db.session.delete(attendance)
                db.session.commit()
                log_admin_action('Removed attendee from event', member_call, f'Date: {event_date}')
                flash(f'Removed {member_call} from attendance', 'success')
        
        elif action == 'delete':
            meeting_date = datetime.strptime(request.form.get('meeting_date'), '%Y-%m-%d').date()
            # CHANGED 2026-11-04: delete only this event, not every event on that date
            event_type = request.form.get('event_type')
            event_name = request.form.get('event_name') or None
            event_query = MeetingAttendance.query.filter_by(meeting_date=meeting_date, event_type=event_type)
            if event_name:
                event_query = event_query.filter_by(event_name=event_name)
            else:
                event_query = event_query.filter(db.or_(MeetingAttendance.event_name.is_(None),
                                                        MeetingAttendance.event_name == ''))
            event_query.delete(synchronize_session=False)
            db.session.commit()
            log_admin_action('Deleted attendance record', details=f'Date: {meeting_date}, Event: {event_name or event_type}')
            flash(f'Attendance for {event_name or event_type} on {meeting_date} deleted', 'success')
        
        return redirect(url_for('admin_attendance'))
    
    # Get active members
    members = Member.query.filter_by(is_active=True).order_by(Member.call_sign).all()
    
    # Get recent meetings with details
    recent_meetings_query = db.session.query(
        MeetingAttendance.meeting_date,
        MeetingAttendance.event_type,
        MeetingAttendance.event_name,
        db.func.count(MeetingAttendance.id).label('count')
    ).group_by(
        MeetingAttendance.meeting_date,
        MeetingAttendance.event_type,
        MeetingAttendance.event_name
    ).order_by(MeetingAttendance.meeting_date.desc()).limit(10).all()
    
    return render_template('admin/attendance.html', 
                         members=members, 
                         recent_meetings=recent_meetings_query)


@app.route('/admin/roles', methods=['GET', 'POST'])
@admin_required
def admin_roles():
    """Manage member roles"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            member_id = request.form.get('member_id')
            role_name = request.form.get('role_name')
            start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
            notes = request.form.get('notes', '')
            
            role = RoleHistory(
                member_id=member_id,
                role_name=role_name,
                start_date=start_date,
                is_current=True,
                notes=notes
            )
            db.session.add(role)
            db.session.commit()
            
            member = Member.query.get(member_id)
            log_admin_action(f'Added role: {role_name}', member.call_sign)
            flash(f'Role "{role_name}" added for {member.call_sign}', 'success')
        
        elif action == 'end':
            role_id = request.form.get('role_id')
            end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
            
            role = RoleHistory.query.get(role_id)
            role.end_date = end_date
            role.is_current = False
            db.session.commit()
            
            log_admin_action(f'Ended role: {role.role_name}', role.member.call_sign)
            flash('Role ended successfully', 'success')
        
        return redirect(url_for('admin_roles'))
    
    # Get all current roles
    current_roles = RoleHistory.query.filter_by(is_current=True).order_by(RoleHistory.start_date.desc()).all()
    
    # Get all members for dropdown
    members = Member.query.filter_by(is_active=True).order_by(Member.call_sign).all()
    
    # CHANGED 2026-11-04: pass today's date so the Duration column can be calculated
    return render_template('admin/roles.html', current_roles=current_roles, members=members, now=date.today())


@app.route('/admin/reports')
@admin_required
def admin_reports():
    """Reports page"""
    return render_template('admin/reports.html')


# ADDED 2026-11-04: member-facing Reports page (any logged-in member)
@app.route('/reports')
@login_required
def member_reports():
    """Reports any member can pull"""
    hidden_count = Member.query.filter_by(is_active=True, directory_opt_out=True).count()
    return render_template('member_reports.html', hidden_count=hidden_count)


@app.route('/reports/directory')
@login_required
def member_directory():
    """Member directory for all members. Respects each member's opt-out choice."""
    fmt = request.args.get('format', 'pdf')
    members = Member.query.filter_by(is_active=True).order_by(Member.last_name, Member.first_name).all()

    def contact(m, value):
        """Contact details are left out for members who opted out"""
        return '' if m.directory_opt_out else (value or '')

    if fmt == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Call Sign', 'Name', 'Email', 'Phone', 'Street Address', 'City', 'State', 'ZIP'])
        for m in members:
            writer.writerow([
                m.call_sign, m.get_full_name(),
                contact(m, m.email), contact(m, m.phone), contact(m, m.address),
                m.city or '', m.state or '', contact(m, m.zip_code),
            ])
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv', as_attachment=True,
            download_name=f'WVARA_member_directory_{date.today().strftime("%Y%m%d")}.csv')

    # PDF (landscape so the address fits)
    from reportlab.lib.pagesizes import landscape
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter),
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    cell = ParagraphStyle('cell', parent=styles['Normal'], fontSize=8, leading=10)
    private = ParagraphStyle('private', parent=cell, textColor=colors.HexColor('#526174'))
    title = ParagraphStyle('wvTitle', parent=styles['Heading1'], fontSize=18,
                           textColor=colors.HexColor('#0b1220'), spaceAfter=6)
    elements = [
        Paragraph('WVARA Member Directory', title),
        Paragraph(f'Generated {date.today().strftime("%B %d, %Y")}. For WVARA members only, please do not share.',
                  styles['Normal']),
        Spacer(1, 0.2 * inch),
    ]
    data = [['Call Sign', 'Name', 'Email', 'Phone', 'Address']]
    for m in members:
        city_line = ', '.join(p for p in [m.city or '', m.state or ''] if p)
        if m.directory_opt_out:
            data.append([m.call_sign, Paragraph(m.get_full_name(), cell),
                         Paragraph('Private', private), Paragraph('Private', private),
                         Paragraph(city_line, cell)])
        else:
            address = ', '.join(p for p in [m.address or '', city_line] if p)
            if m.zip_code:
                address = f'{address} {m.zip_code}'.strip()
            data.append([m.call_sign, Paragraph(m.get_full_name(), cell),
                         Paragraph(m.email or '', cell), Paragraph(m.phone or '', cell),
                         Paragraph(address, cell)])
    table = Table(data, colWidths=[0.9 * inch, 1.6 * inch, 2.4 * inch, 1.2 * inch, 3.9 * inch], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#111b2f')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f3f5f9')]),
        ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f'WVARA_member_directory_{date.today().strftime("%Y%m%d")}.pdf')


# ADDED 2026-11-04: member-facing map (no admin links, no "couldn't be mapped" list)
@app.route('/map')
@login_required
def member_map():
    return render_template('admin/map.html', **build_member_map_data(admin_view=False))


# ADDED 2026-11-04: Member Map, ZIP code bubbles within 75 miles of the repeater site
@app.route('/admin/map')
@admin_required
def admin_member_map():
    """Map of where active members live, grouped by ZIP code"""
    return render_template('admin/map.html', **build_member_map_data(admin_view=True))


# ADDED 2026-11-05: license class ribbon + one-click "fill from FCC" for blank classes
LICENSE_CLASSES = [   # (stored value, ribbon label, color)
    ('Amateur Extra', 'Extra', '#d71920'),
    ('Advanced', 'Advanced', '#f36f21'),
    ('General', 'General', '#2b73ff'),
    ('Technician', 'Technician', '#198754'),
    ('Novice', 'Novice', '#6f42c1'),
]
LICENSE_FILL_PER_CLICK = 20         # FCC lookups per click (keeps it polite and quick)
LICENSE_FILL_TIME_BUDGET = 20       # seconds; stop early if the lookup service is slow
LICENSE_RETRY_DAYS = 30             # don't re-check a "not found" call sign for 30 days


def build_license_mix(members) -> tuple:
    """Ordered ribbon chips [{label, count, pct, color}] and how many have no class on file"""
    counts = {stored: 0 for stored, _, _ in LICENSE_CLASSES}
    blank = 0
    for m in members:
        value = (m.fcc_license_class or '').strip()
        if value.lower() in ('extra', 'amateur extra'):
            value = 'Amateur Extra'
        if value in counts:
            counts[value] += 1
        else:
            blank += 1
    total = len(members) or 1
    chips = [{'label': label, 'count': counts[stored], 'pct': round(100 * counts[stored] / total), 'color': color}
             for stored, label, color in LICENSE_CLASSES if counts[stored]]
    if blank:
        chips.append({'label': 'Not on file', 'count': blank, 'pct': round(100 * blank / total), 'color': '#94a3b8'})
    return chips, blank


def license_tried_file() -> Path:
    return Path(app.instance_path) / 'license_lookup_tried.json'


@app.route('/admin/map/fill-license', methods=['POST'])
@admin_required
def admin_fill_license_classes():
    """Look up blank license classes with the FCC (via callook.info / HamDB). Fills blanks only."""
    import time
    try:
        tried = json.loads(license_tried_file().read_text())
    except (OSError, ValueError):
        tried = {}
    cutoff = (date.today() - timedelta(days=LICENSE_RETRY_DAYS)).isoformat()

    blanks = [m for m in Member.query.filter_by(is_active=True).order_by(Member.call_sign).all()
              if not (m.fcc_license_class or '').strip() and tried.get(m.call_sign, '') < cutoff]

    filled, not_found, started = [], [], time.time()
    for m in blanks[:LICENSE_FILL_PER_CLICK]:
        if time.time() - started > LICENSE_FILL_TIME_BUDGET:
            break
        result, _ = lookup_call_sign(m.call_sign)
        license_class = (result or {}).get('fcc_license_class', '')
        if license_class:
            m.fcc_license_class = license_class
            filled.append(m.call_sign)
            tried.pop(m.call_sign, None)
        else:
            not_found.append(m.call_sign)
            tried[m.call_sign] = date.today().isoformat()
    db.session.commit()
    try:
        license_tried_file().write_text(json.dumps(tried, indent=1))
    except OSError as e:
        print(f"Could not save license lookup list: {e}")

    remaining = max(0, len(blanks) - len(filled) - len(not_found))
    log_admin_action('Filled license classes from FCC', details=f'Filled {len(filled)}, not found {len(not_found)}')
    message = f'Filled {len(filled)} license class{"es" if len(filled) != 1 else ""} from the FCC.'
    if not_found:
        message += f' Not found: {len(not_found)} ({", ".join(not_found[:8])}{"..." if len(not_found) > 8 else ""}).'
    if remaining:
        message += f' {remaining} more to check, click the button again.'
    flash(message, 'success' if filled else 'info')
    return redirect(url_for('admin_member_map'))


def build_member_map_data(admin_view: bool) -> dict:
    """Everything the map page needs. Members get call signs and names, but no admin links."""
    members = Member.query.filter_by(is_active=True).order_by(Member.call_sign).all()

    by_zip, no_zip = {}, []
    for m in members:
        zip5 = (m.zip_code or '').strip()[:5]
        if re.fullmatch(r'\d{5}', zip5):
            by_zip.setdefault(zip5, []).append(m)
        else:
            no_zip.append(m)

    locations = resolve_zip_locations(sorted(by_zip))

    nearby, far_away, unmapped = [], [], []
    for zip5, zip_members in sorted(by_zip.items()):
        people = [{'call_sign': m.call_sign, 'name': m.get_full_name(),
                   'url': url_for('admin_member_detail', member_id=m.id) if admin_view else None}
                  for m in zip_members]
        loc = locations.get(zip5)
        if not loc:
            unmapped.append({'zip': zip5, 'members': people})
            continue
        miles = haversine_miles(MAP_CENTER[0], MAP_CENTER[1], loc['lat'], loc['lon'])
        row = {'zip': zip5, 'place': loc.get('place', ''), 'state': loc.get('state', ''),
               'lat': loc['lat'], 'lon': loc['lon'], 'miles': round(miles, 1),
               'count': len(people), 'members': people}
        (nearby if miles <= MAP_RADIUS_MILES else far_away).append(row)

    for m in no_zip:
        unmapped.append({'zip': m.zip_code or '(blank)', 'members': [{
            'call_sign': m.call_sign, 'name': m.get_full_name(),
            'url': url_for('admin_member_detail', member_id=m.id) if admin_view else None}]})

    far_away.sort(key=lambda r: r['miles'])
    nearby.sort(key=lambda r: -r['count'])

    # ADDED 2026-11-05: license class mix for the ribbon under the stats (counts only, no names)
    license_mix, license_blank_count = build_license_mix(members)

    return dict(admin_view=admin_view,
                license_mix=license_mix,                  # ADDED 2026-11-05
                license_blank_count=license_blank_count,  # ADDED 2026-11-05
                license_total=len(members),               # ADDED 2026-11-05
                nearby=nearby,
                far_away=far_away,
                unmapped=unmapped if admin_view else [],   # data clean-up list is admin only
                nearby_count=sum(r['count'] for r in nearby),
                far_count=sum(r['count'] for r in far_away),
                unmapped_count=sum(len(r['members']) for r in unmapped),
                center={'lat': MAP_CENTER[0], 'lon': MAP_CENTER[1], 'name': MAP_CENTER_NAME},
                radius_miles=MAP_RADIUS_MILES)




# ADDED 2026-11-04: footer copyright year on every page
@app.context_processor
def inject_current_year():
    return {'current_year': date.today().year}


# ADDED 2026-11-05: everything the Pay Dues lightbox needs (on every page, for logged-in non-Lifetime members)
@app.context_processor
def inject_pay_dues():
    if 'call_sign' not in session:
        return {'pay_dues': None}
    m = Member.query.filter_by(call_sign=session['call_sign']).first()
    if not m or m.is_lifetime():
        return {'pay_dues': None}
    today = date.today()
    status = m.get_dues_status()
    paid_years = {p.year for p in m.dues_payments}
    # default to this year, unless this year is already paid
    default_year = today.year + 1 if today.year in paid_years else today.year
    choice = 'Family' if (m.membership_type or '').strip().lower() == 'family' else 'Individual'
    return {'pay_dues': {
        'call_sign': m.call_sign,
        'name': m.get_full_name(),
        'email': m.email or '',
        'choice': choice,
        'years': [today.year, today.year + 1],
        'default_year': default_year,
        'amounts': DUES_BY_TYPE,
        'needs_payment': status in ('expired', 'grace') or (status == 'paid' and is_expiring_soon(m, today)),
    }}


# ADDED 2026-11-05: member clicked "Continue to PayPal" in the Pay Dues lightbox
@app.route('/dues/pay/start', methods=['POST'])
@login_required
def pay_dues_start():
    """Save who is paying, for which year and type, then hand back the PayPal link"""
    member = Member.query.filter_by(call_sign=session['call_sign']).first()
    if not member or member.is_lifetime():
        return {'ok': False, 'message': 'Lifetime members do not owe annual dues.'}, 400

    choice = request.form.get('membership_choice', '')
    if choice not in PAYPAL_BUTTONS:
        return {'ok': False, 'message': 'Please choose Individual or Family.'}, 400

    this_year = date.today().year
    try:
        dues_year = int(request.form.get('dues_year', ''))
    except ValueError:
        dues_year = 0
    if dues_year not in (this_year, this_year + 1):
        return {'ok': False, 'message': f'Please choose {this_year} or {this_year + 1}.'}, 400

    family = (request.form.get('family_members', '') or '').strip()[:1000] if choice == 'Family' else ''
    notice = PaymentNotice(
        member_id=member.id,
        dues_year=dues_year,
        membership_choice=choice,
        amount=DUES_BY_TYPE[choice],
        call_sign=(request.form.get('call_sign', '') or member.call_sign).strip().upper()[:10],
        name=(request.form.get('name', '') or member.get_full_name()).strip()[:120],
        email=(request.form.get('email', '') or member.email or '').strip()[:120],
        family_members=family or None,
    )
    db.session.add(notice)
    db.session.commit()
    return {'ok': True, 'paypal_url': paypal_url(choice)}


# ADDED 2026-11-04: show the Admin menu from the live database value, not the value saved at login,
# so revoking admin hides the menu right away
@app.context_processor
def inject_viewer_is_admin():
    if 'call_sign' not in session:
        return {'viewer_is_admin': False}
    viewer = Member.query.filter_by(call_sign=session['call_sign']).first()
    return {'viewer_is_admin': bool(viewer and viewer.is_admin)}


@app.route('/admin/reports/directory')
@admin_required
def report_directory():
    """Generate member directory"""
    format = request.args.get('format', 'pdf')
    
    members = Member.query.filter_by(is_active=True).order_by(Member.last_name, Member.first_name).all()
    
    if format == 'csv':
        # Generate CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Call Sign', 'Name', 'Email', 'Phone', 'Address', 'City', 'State', 'ZIP', 
                        'FCC Class', 'Membership Type', 'Join Date', 'Dues Current'])
        
        for member in members:
            writer.writerow([
                member.call_sign,
                member.get_full_name(),
                member.email,
                member.phone or '',
                member.address or '',
                member.city or '',
                member.state or '',
                member.zip_code or '',
                member.fcc_license_class or '',
                member.membership_type,
                member.join_date.strftime('%Y-%m-%d'),
                'Yes' if member.is_dues_current() else 'No'
            ])
        
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'WVARA_directory_{date.today().strftime("%Y%m%d")}.csv'
        )
    
    else:  # PDF
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1a5490'),
            spaceAfter=30,
        )
        elements.append(Paragraph('WVARA Member Directory', title_style))
        elements.append(Paragraph(f'Generated: {date.today().strftime("%B %d, %Y")}', styles['Normal']))
        elements.append(Spacer(1, 0.3*inch))
        
        # Table
        data = [['Call Sign', 'Name', 'Email', 'Phone', 'City, State']]
        
        for member in members:
            location = f"{member.city or ''}, {member.state or ''}".strip(', ')
            data.append([
                member.call_sign,
                member.get_full_name(),
                member.email,
                member.phone or '',
                location
            ])
        
        table = Table(data, colWidths=[1*inch, 1.8*inch, 2*inch, 1.2*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a5490')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
        ]))
        
        elements.append(table)
        doc.build(elements)
        
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'WVARA_directory_{date.today().strftime("%Y%m%d")}.pdf'
        )


@app.route('/admin/reports/dues_status')
@admin_required
def report_dues_status():
    """Generate dues status report"""
    format = request.args.get('format', 'csv')
    current_year = date.today().year
    
    members = Member.query.filter_by(is_active=True).order_by(Member.last_name, Member.first_name).all()
    
    if format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Call Sign', 'Name', 'Email', 'Membership Type', 'Dues Current',
                        f'{current_year} Payment Date', f'{current_year} Amount',
                        'Dues Status'])  # ADDED 2026-11-04: Dues Status column

        for member in members:
            payment = member.get_current_dues_status()
            writer.writerow([
                member.call_sign,
                member.get_full_name(),
                member.email,
                member.membership_type,
                'Yes' if member.is_dues_current() else 'No',
                payment.payment_date.strftime('%Y-%m-%d') if payment else '',
                f'${payment.amount:.2f}' if payment else '',
                member.get_dues_status().title()  # ADDED 2026-11-04
            ])
        
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'WVARA_dues_status_{date.today().strftime("%Y%m%d")}.csv'
        )


@app.route('/admin/reports/attendance')
@admin_required
def report_attendance():
    """Generate attendance report"""
    format = request.args.get('format', 'csv')
    
    # Get last 12 meetings with event info
    meetings = db.session.query(
        MeetingAttendance.meeting_date,
        MeetingAttendance.event_name,
        MeetingAttendance.event_type
    ).distinct().order_by(
        MeetingAttendance.meeting_date.desc()
    ).limit(12).all()
    
    meetings_list = list(meetings)
    meetings_list.reverse()  # Chronological order
    
    members = Member.query.filter_by(is_active=True).order_by(Member.last_name, Member.first_name).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header with event names
    header = ['Call Sign', 'Name']
    for meeting in meetings_list:
        event_label = f"{meeting.meeting_date.strftime('%Y-%m-%d')}: {meeting.event_name or meeting.event_type}"
        header.append(event_label)
    header.append('Total')
    writer.writerow(header)
    
    # Data
    for member in members:
        row = [member.call_sign, member.get_full_name()]
        total = 0
        
        for meeting in meetings_list:
            # CHANGED 2026-11-04: match the specific event, not just the date
            attendance = event_attendance_query(
                meeting.meeting_date, meeting.event_type, meeting.event_name
            ).filter_by(member_id=member.id).first()
            
            if attendance:
                row.append('X')
                total += 1
            else:
                row.append('')
        
        row.append(total)
        writer.writerow(row)
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'WVARA_attendance_{date.today().strftime("%Y%m%d")}.csv'
    )


@app.route('/admin/reports/mailing_labels')
@admin_required
def report_mailing_labels():
    """Generate mailing labels"""
    members = Member.query.filter_by(is_active=True).order_by(Member.zip_code, Member.last_name).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Address', 'City', 'State', 'ZIP'])
    
    for member in members:
        if member.address and member.city and member.state and member.zip_code:
            writer.writerow([
                member.get_full_name(),
                member.address,
                member.city,
                member.state,
                member.zip_code
            ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'WVARA_mailing_labels_{date.today().strftime("%Y%m%d")}.csv'
    )


@app.route('/admin/reports/email_list')
@admin_required
def report_email_list():
    """Generate email distribution list"""
    members = Member.query.filter_by(is_active=True).order_by(Member.last_name, Member.first_name).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Call Sign', 'Name', 'Email'])
    
    for member in members:
        writer.writerow([
            member.call_sign,
            member.get_full_name(),
            member.email
        ])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'WVARA_email_list_{date.today().strftime("%Y%m%d")}.csv'
    )


# Initialize database
@app.cli.command()
def init_db():
    """Initialize the database"""
    db.create_all()
    print("Database initialized!")


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    # CHANGED 2026-11-04: debug off so the interactive debugger is never exposed on the network
    app.run(debug=False, host='0.0.0.0', port=1977)
