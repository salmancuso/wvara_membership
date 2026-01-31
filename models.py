"""
WVARA Membership Management System - Database Models
"""
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta

db = SQLAlchemy()


class Member(db.Model):
    """Core member information"""
    __tablename__ = 'members'
    
    id = db.Column(db.Integer, primary_key=True)
    call_sign = db.Column(db.String(10), unique=True, nullable=False, index=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    city = db.Column(db.String(100))
    state = db.Column(db.String(2))
    zip_code = db.Column(db.String(10))
    
    # FCC License information
    fcc_license_class = db.Column(db.String(20))  # Technician, General, Amateur Extra
    
    # Emergency contact
    emergency_contact_name = db.Column(db.String(100))
    emergency_contact_phone = db.Column(db.String(20))
    emergency_contact_relationship = db.Column(db.String(50))
    
    # Membership information
    membership_type = db.Column(db.String(20), nullable=False)  # Individual, Family, Lifetime
    join_date = db.Column(db.Date, nullable=False, default=date.today)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    
    # Profile photo from QRZ
    qrz_photo_url = db.Column(db.String(500))
    
    # Authentication
    password_hash = db.Column(db.String(200), nullable=False)
    password_is_temporary = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_contact = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    dues_payments = db.relationship('DuesPayment', backref='member', lazy=True, cascade='all, delete-orphan')
    role_history = db.relationship('RoleHistory', backref='member', lazy=True, cascade='all, delete-orphan')
    attendance = db.relationship('MeetingAttendance', backref='member', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password_hash, password)
    
    def get_full_name(self):
        """Return full name"""
        return f"{self.first_name} {self.last_name}"
    
    def get_current_dues_status(self):
        """Get current year dues payment status"""
        current_year = date.today().year
        payment = DuesPayment.query.filter_by(
            member_id=self.id,
            year=current_year
        ).first()
        return payment
    
    def is_dues_current(self):
        """Check if dues are paid for current year"""
        current_year = date.today().year
        current_date = date.today()
        
        # Grace period: through February of following year
        grace_end = date(current_year, 2, 28)
        if current_date.year > current_year and current_date <= grace_end:
            # Check previous year during grace period
            year_to_check = current_year - 1
        else:
            year_to_check = current_year
        
        payment = DuesPayment.query.filter_by(
            member_id=self.id,
            year=year_to_check
        ).first()
        
        return payment is not None
    
    def get_membership_duration(self):
        """Calculate how long member has been with club"""
        if not self.join_date:
            return "Unknown"
        
        delta = date.today() - self.join_date
        years = delta.days // 365
        months = (delta.days % 365) // 30
        
        if years > 0:
            return f"{years} year{'s' if years != 1 else ''}, {months} month{'s' if months != 1 else ''}"
        else:
            return f"{months} month{'s' if months != 1 else ''}"
    
    def has_recent_activity(self, months=6):
        """Check if member has attended any events in the last X months"""
        cutoff_date = date.today() - timedelta(days=months * 30)
        recent_attendance = MeetingAttendance.query.filter_by(
            member_id=self.id
        ).filter(MeetingAttendance.meeting_date >= cutoff_date).first()
        return recent_attendance is not None
    
    def is_truly_active(self):
        """Check if member is truly active (dues paid + recent activity)"""
        return self.is_dues_current() and self.has_recent_activity()
    
    def __repr__(self):
        return f'<Member {self.call_sign} - {self.get_full_name()}>'


class DuesPayment(db.Model):
    """Track dues payments"""
    __tablename__ = 'dues_payments'
    
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    payment_method = db.Column(db.String(50), default='PayPal')  # PayPal, Cash, Check
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(10))  # Call sign of admin who recorded it
    
    def __repr__(self):
        return f'<DuesPayment {self.member.call_sign} - {self.year}>'


class RoleHistory(db.Model):
    """Track leadership positions over time"""
    __tablename__ = 'role_history'
    
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    role_name = db.Column(db.String(100), nullable=False)  # President, Treasurer, Board Member, etc.
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    is_current = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<RoleHistory {self.member.call_sign} - {self.role_name}>'


class MeetingAttendance(db.Model):
    """Track meeting attendance"""
    __tablename__ = 'meeting_attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    meeting_date = db.Column(db.Date, nullable=False)
    attended = db.Column(db.Boolean, default=True)
    event_type = db.Column(db.String(20), default='Meeting')  # Meeting, Event, Other
    event_name = db.Column(db.String(200))  # Name of the event
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    recorded_by = db.Column(db.String(10))  # Call sign of admin who recorded it
    
    def __repr__(self):
        return f'<MeetingAttendance {self.member.call_sign} - {self.meeting_date}>'


class AdminLog(db.Model):
    """Audit trail for administrative actions"""
    __tablename__ = 'admin_log'
    
    id = db.Column(db.Integer, primary_key=True)
    admin_call_sign = db.Column(db.String(10), nullable=False)
    action = db.Column(db.String(200), nullable=False)
    target_member_call_sign = db.Column(db.String(10))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<AdminLog {self.admin_call_sign} - {self.action}>'
