"""
WVARA Membership Management System - Main Application
"""
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash
from models import db, Member, DuesPayment, RoleHistory, MeetingAttendance, AdminLog
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

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(16))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///WVARA_membership.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)


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
    
    for member in all_members:
        if not member.is_dues_current():
            expired_dues.append(member)
        else:
            # Check if it's December (dues expiring in next month)
            if current_date.month == 12:
                expiring_soon.append(member)
    
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
            
            db.session.commit()
            log_admin_action(f'Updated member information', member.call_sign)
            flash('Member information updated successfully!', 'success')
        
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
        
        # Determine status based on current year
        if most_recent_payment and most_recent_payment.year == current_year:
            status = 'paid'
        else:
            status = 'expired'
        
        member_payment_data.append({
            'member': member,
            'payment': most_recent_payment,
            'status': status
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
                         current_year=current_year)


@app.template_filter('get_attendance_for_date')
def get_attendance_for_date(meeting_date):
    """Get all attendance records for a specific date"""
    return MeetingAttendance.query.filter_by(meeting_date=meeting_date).all()


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
            
            # Delete existing attendance for this date (in case of correction)
            MeetingAttendance.query.filter_by(meeting_date=meeting_date).delete()
            
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
            MeetingAttendance.query.filter_by(meeting_date=meeting_date).delete()
            db.session.commit()
            log_admin_action('Deleted attendance record', details=f'Date: {meeting_date}')
            flash(f'Attendance record for {meeting_date} deleted', 'success')
        
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
    
    return render_template('admin/roles.html', current_roles=current_roles, members=members)


@app.route('/admin/reports')
@admin_required
def admin_reports():
    """Reports page"""
    return render_template('admin/reports.html')


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
                        f'{current_year} Payment Date', f'{current_year} Amount'])
        
        for member in members:
            payment = member.get_current_dues_status()
            writer.writerow([
                member.call_sign,
                member.get_full_name(),
                member.email,
                member.membership_type,
                'Yes' if member.is_dues_current() else 'No',
                payment.payment_date.strftime('%Y-%m-%d') if payment else '',
                f'${payment.amount:.2f}' if payment else ''
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
            attendance = MeetingAttendance.query.filter_by(
                member_id=member.id,
                meeting_date=meeting.meeting_date
            ).first()
            
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
    app.run(debug=True, host='0.0.0.0', port=1977)
