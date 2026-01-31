# WVARA Membership Management System

A comprehensive web-based membership management system for the West Valley Amateur Radio Association (WVARA).

## Features

### Member Features
- **User Authentication**: Secure login using call sign and password
- **Profile Management**: Update contact information, emergency contacts, and FCC license details
- **Password Management**: Change password with strength requirements
- **Dashboard**: View membership status, dues status, recent attendance, and roles
- **QRZ Integration**: Automatic profile photo retrieval from QRZ.com

### Administrator Features
- **Member Management**: View, edit, and manage all member accounts
- **Dues Tracking**: Record and track annual membership dues payments
- **Attendance Recording**: Record meeting attendance with bulk selection
- **Role Management**: Track leadership positions and board members over time
- **Admin Access Control**: Grant or revoke administrator privileges
- **Comprehensive Reports**: 
  - Member Directory (PDF & CSV)
  - Dues Status Report
  - Attendance Report
  - Email Distribution List
  - Mailing Labels

### Security Features
- Password requirements: Minimum 10 characters, uppercase, number, special character
- Temporary passwords that must be changed on first login
- Admin action logging
- Session management
- Role-based access control

## Technology Stack

- **Backend**: Python Flask
- **Database**: SQLite
- **Frontend**: HTML, Bootstrap 5, JavaScript
- **PDF Generation**: ReportLab
- **Web Scraping**: BeautifulSoup4, Requests

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Setup Instructions

1. **Clone or download the application files**

2. **Install dependencies**:
   ```bash
   cd WVARA_membership
   pip install -r requirements.txt
   ```

3. **Initialize the database**:
   ```bash
   python init_db.py
   ```
   
   This will create the database and populate it with sample data including:
   - W6SAL (Sal) - Admin
   - KK6IK (President) - Admin
   - W6HS (Eric) - Admin (Board Member)
   - KQ6OT (Tom) - Regular Member
   - Several other sample members

4. **Run the application**:
   ```bash
   python app.py
   ```
   
   The application will be available at `http://localhost:5000`

### Production Deployment

For production deployment on a cloud server:

1. **Set a secure secret key**:
   ```bash
   export SECRET_KEY='your-very-secure-random-key-here'
   ```

2. **Use a production WSGI server** (e.g., Gunicorn):
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```

3. **Set up a reverse proxy** (e.g., Nginx) for HTTPS

4. **Configure firewall rules** to allow only necessary ports

## Initial Login Credentials

All initial passwords are set to the user's call sign and must be changed on first login.

**Administrator Accounts:**
- Call Sign: `W6SAL` | Password: `W6SAL`

## Importing Existing Members

You can bulk import members from a CSV file:

```bash
python init_db.py csv members.csv
```

### CSV Format
```csv
call_sign,first_name,last_name,email,phone,address,city,state,zip,fcc_class,membership_type,join_date
W6ABC,John,Doe,john@example.com,(408)555-1234,123 Main St,San Jose,CA,95120,General,Individual,2020-01-15
```

**Required fields**: call_sign, first_name, last_name, email  
**Optional fields**: phone, address, city, state, zip, fcc_class, membership_type, join_date

## Usage Guide

### For Members

1. **Login**: Use your call sign (e.g., W6SAL) as username
2. **Update Profile**: Click "Profile" to update your contact information
3. **Change Password**: Click "Change Password" or it will prompt on first login
4. **View Dashboard**: See your membership status, dues, and attendance

### For Administrators

1. **Member Management**:
   - Navigate to Admin → Members
   - Search for members by call sign, name, or email
   - Click "View" to see detailed member information
   - Edit member details, reset passwords, or toggle admin access

2. **Recording Dues**:
   - Navigate to Admin → Dues
   - Select member, year, amount, payment date, and method
   - Click "Record Payment"

3. **Taking Attendance**:
   - Navigate to Admin → Attendance
   - Select the meeting date
   - Check boxes for members who attended
   - Click "Record Attendance"

4. **Managing Roles**:
   - Navigate to Admin → Roles
   - Add new leadership positions or end existing ones
   - Track historical leadership

5. **Generating Reports**:
   - Navigate to Admin → Reports
   - Select desired report type
   - Download as CSV or PDF

## Membership Dues Grace Period

- Dues are for calendar year (January 1 - December 31)
- Grace period extends through February 28/29 of following year
- After grace period, members should be marked inactive if dues unpaid
- Admin dashboard shows members with expired/expiring dues

## Password Requirements

Passwords must meet the following criteria:
- Minimum 10 characters
- At least one uppercase letter
- At least one number  
- At least one special character (!@#$%^&*)

## QRZ.com Integration

The system can automatically retrieve member profile photos from QRZ.com:
- Photos are fetched by call sign from https://www.qrz.com/db/CALLSIGN
- Administrators can update photos from the member detail page
- No API key required (uses web scraping)

## Database Backup

To backup the database:
```bash
cp WVARA_membership.db WVARA_membership_backup_$(date +%Y%m%d).db
```

To restore from backup:
```bash
cp WVARA_membership_backup_YYYYMMDD.db WVARA_membership.db
```

## Troubleshooting

### Database locked error
- Ensure only one instance of the app is running
- Check file permissions on the database file

### QRZ photo not loading
- Verify the call sign is correct on QRZ.com
- Check if member has a photo uploaded on QRZ
- Try manually updating from admin panel

### Cannot login
- Verify call sign is uppercase
- Contact administrator for password reset
- Check if account is marked as active

## Customization

### Changing Dues Amount
Edit the default in `templates/admin/dues.html`:
```html
<input type="number" ... value="25.00" ...>
```

### Meeting Schedule
Edit club information in `templates/dashboard.html`

### Colors and Branding
Edit CSS variables in `templates/base.html`:
```css
:root {
    --primary-color: #1a5490;
    --secondary-color: #4a90d9;
}
```

## Support

For questions or issues with this application:
- Contact: W6SAL (Sal Mancuso)
- Email: W6SAL@yahoo.com

## License

MIT License

## Development Notes

### File Structure
```
WVARA_membership/
├── app.py                 # Main Flask application
├── models.py              # Database models
├── init_db.py            # Database initialization script
├── requirements.txt       # Python dependencies
├── templates/            # HTML templates
│   ├── base.html
│   ├── login.html
│   ├── dashboard.html
│   ├── profile.html
│   ├── change_password.html
│   └── admin/
│       ├── dashboard.html
│       ├── members.html
│       ├── member_detail.html
│       ├── dues.html
│       ├── attendance.html
│       ├── roles.html
│       └── reports.html
└── static/               # CSS and JavaScript files
```

### Database Schema

**Members Table**:
- Core member information
- Contact details
- Emergency contacts
- Membership type and status
- Admin flag

**Dues Payments Table**:
- Payment tracking by year
- Amount and payment method
- Payment date

**Role History Table**:
- Leadership positions
- Start and end dates
- Current role flag

**Meeting Attendance Table**:
- Attendance records by date
- Notes field for each meeting

**Admin Log Table**:
- Audit trail of admin actions
- Action details and timestamps

## Future Enhancements

Potential features for future development:
- Email notifications for expiring dues
- Integration with club's Groups.io
- Event RSVP tracking
- Document storage
- Integration with payment gateways (PayPal API)
- Mobile app version
- Multi-club support

---

