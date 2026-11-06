"""
WVARA Membership Management System - Database Models
"""
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta

db = SQLAlchemy()

# ADDED 2026-11-04: club dues rules
DUES_AMOUNT = 15.00            # $15 per calendar year
GRACE_PERIOD_LAST_MONTH = 2    # last year's dues still count through the end of February
DUES_RENEWAL_WARNING_MONTHS = 2  # "Expiring Soon" starts 2 months before Dec 31 (Nov 1)

# ADDED 2026-11-05: annual dues by membership type (Lifetime pays nothing)
DUES_BY_TYPE = {'Individual': 15.00, 'Family': 25.00}


def dues_amount_for(membership_type) -> float:
    """Annual dues for a membership type (Family $25, everything else $15)"""
    return DUES_BY_TYPE.get((membership_type or '').strip().title(), DUES_AMOUNT)


class Member(db.Model):
    """Core member information"""
    __tablename__ = 'members'
    
    id = db.Column(db.Integer, primary_key=True)
    call_sign = db.Column(db.String(15), unique=True, nullable=False, index=True)  # CHANGED 2026-11-05: 10 -> 15 for usernames
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

    # ADDED 2026-11-04: member chose to hide email, phone and street address from the member directory
    directory_opt_out = db.Column(db.Boolean, default=False, nullable=False, server_default='0')

    # ADDED 2026-11-05: False for members without an amateur radio license (call_sign then holds their username)
    is_licensed = db.Column(db.Boolean, default=True, nullable=False, server_default='1')

    # ADDED 2026-11-05: family membership; points to the member who pays the $25 Family dues
    family_head_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=True, index=True)

    # ADDED 2026-11-05: call sign / username typed at sign-up, waiting for an admin to confirm the family link
    family_link_request = db.Column(db.String(15))  # CHANGED 2026-11-05: 10 -> 15 for usernames

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
    
    # ADDED 2026-11-04: "Lifetime" and "Life Member" both count as lifetime
    def is_lifetime(self):
        """True for Lifetime / Life Member membership types"""
        return (self.membership_type or '').strip().lower() in ('lifetime', 'life member', 'life')

    # ADDED 2026-11-04: single source of truth for dues status, used by every page and report
    def get_dues_status(self):
        """
        Return one of: 'lifetime', 'paid', 'grace', 'expired'
        - lifetime: Lifetime members are always current
        - paid:     dues recorded for the current calendar year
        - grace:    January/February, and last year's dues are paid
        - expired:  everything else
        """
        if self.is_lifetime():
            return 'lifetime'

        # CHANGED 2026-11-05: family members share the head's dues status
        head = self.get_family_head()
        if head is not None:
            return head.get_dues_status()

        today = date.today()
        paid_years = {p.year for p in DuesPayment.query.filter_by(member_id=self.id).all()}

        if today.year in paid_years:
            return 'paid'
        if today.month <= GRACE_PERIOD_LAST_MONTH and (today.year - 1) in paid_years:
            return 'grace'
        return 'expired'

    # ADDED 2026-11-05: family membership helpers
    def get_family_head(self):
        """The member who pays this member's Family dues, or None (follows one level only, so no loops)"""
        if not self.family_head_id or self.family_head_id == self.id:
            return None
        head = db.session.get(Member, self.family_head_id)
        if head is None or head.family_head_id:
            return None
        return head

    def get_family_members(self):
        """Members linked to this member as their family head"""
        return Member.query.filter_by(family_head_id=self.id).order_by(Member.first_name).all()

    def is_family_head(self):
        """True if at least one member is linked to this member"""
        return Member.query.filter_by(family_head_id=self.id).first() is not None

    def is_dues_current(self):
        """Check if dues are current (CHANGED 2026-11-04: grace period and Lifetime now work)"""
        return self.get_dues_status() in ('lifetime', 'paid', 'grace')
    
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
    created_by = db.Column(db.String(15))  # Call sign of admin who recorded it  # CHANGED 2026-11-05: 10 -> 15 for usernames
    
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
    recorded_by = db.Column(db.String(15))  # Call sign of admin who recorded it  # CHANGED 2026-11-05: 10 -> 15 for usernames
    
    def __repr__(self):
        return f'<MeetingAttendance {self.member.call_sign} - {self.meeting_date}>'


class PaymentNotice(db.Model):
    """ADDED 2026-11-05: a member started a PayPal dues payment; the treasurer confirms it against PayPal"""
    __tablename__ = 'payment_notices'

    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    dues_year = db.Column(db.Integer, nullable=False)
    membership_choice = db.Column(db.String(20), nullable=False)   # Individual / Family
    amount = db.Column(db.Float, nullable=False)
    call_sign = db.Column(db.String(15))      # as the member entered it in the form  # CHANGED 2026-11-05: 10 -> 15 for usernames
    name = db.Column(db.String(120))
    email = db.Column(db.String(120))
    family_members = db.Column(db.Text)       # Family only: other names / call signs
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending / confirmed / dismissed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    handled_by = db.Column(db.String(15))  # CHANGED 2026-11-05: 10 -> 15 for usernames
    handled_at = db.Column(db.DateTime)
    dues_payment_id = db.Column(db.Integer, db.ForeignKey('dues_payments.id'))

    member = db.relationship('Member', backref=db.backref('payment_notices', lazy=True, cascade='all, delete-orphan'))

    def __repr__(self):
        return f'<PaymentNotice {self.call_sign} {self.dues_year} {self.status}>'


class AdminLog(db.Model):
    """Audit trail for administrative actions"""
    __tablename__ = 'admin_log'
    
    id = db.Column(db.Integer, primary_key=True)
    admin_call_sign = db.Column(db.String(15), nullable=False)  # CHANGED 2026-11-05: 10 -> 15 for usernames
    action = db.Column(db.String(200), nullable=False)
    target_member_call_sign = db.Column(db.String(15))  # CHANGED 2026-11-05: 10 -> 15 for usernames
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<AdminLog {self.admin_call_sign} - {self.action}>'
