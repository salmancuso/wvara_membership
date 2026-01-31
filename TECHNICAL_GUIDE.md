# WVARA Membership System - Technical Overview

## System Architecture

### Technology Stack
- **Backend**: Python Flask (lightweight web framework)
- **Database**: SQLite (file-based, no separate server needed)
- **Frontend**: HTML5, Bootstrap 5, JavaScript
- **PDF Generation**: ReportLab
- **Web Scraping**: BeautifulSoup4 (for QRZ.com photos)

### Why These Technologies?

**Flask**: 
- Lightweight and easy to deploy
- Perfect for small to medium applications
- Minimal configuration required

**SQLite**:
- No separate database server to manage
- Single file database (easy to backup)
- Handles 100-200 concurrent users easily
- Perfect for club size (100-200 members)

**Bootstrap 5**:
- Professional, responsive design
- Works on desktop, tablet, and mobile
- Consistent UI components

## Application Structure

```
WVARA_membership/
├── app.py                    # Main application (routes, business logic)
├── models.py                 # Database models (tables structure)
├── init_db.py               # Database initialization script
├── requirements.txt          # Python dependencies
├── start.sh                  # Easy startup script
├── templates/               # HTML templates
│   ├── base.html            # Base template (navigation, footer)
│   ├── login.html           # Login page
│   ├── dashboard.html       # Member dashboard
│   ├── profile.html         # Profile editing
│   ├── change_password.html # Password change
│   └── admin/               # Admin templates
│       ├── dashboard.html   # Admin dashboard
│       ├── members.html     # Member list
│       ├── member_detail.html # Member details/edit
│       ├── dues.html        # Dues management
│       ├── attendance.html  # Attendance tracking
│       ├── roles.html       # Role management
│       └── reports.html     # Reports page
└── static/                  # CSS, JavaScript, images
```

## Database Schema

### Members Table
- Personal information (name, call sign, email, phone, address)
- Emergency contact information
- FCC license details
- Membership type (Individual, Family, Lifetime)
- Admin flag (controls access rights)
- Active/inactive status
- QRZ photo URL
- Password hash (encrypted)

### Dues Payments Table
- Links to member
- Year and amount
- Payment date and method
- Who recorded the payment

### Role History Table
- Tracks leadership positions
- Start and end dates
- Current vs. past roles

### Meeting Attendance Table
- Meeting date
- Member attendance
- Notes about the meeting

### Admin Log Table
- Audit trail of all admin actions
- Timestamp and IP address

## Security Considerations

### Password Security
- Passwords are hashed using Werkzeug's security functions (PBKDF2)
- Never stored in plain text
- Minimum complexity requirements enforced

### Session Management
- Flask secure sessions with secret key
- Session expires on browser close (no persistent login)

### Admin Access
- Two-factor authorization (admin flag + valid session)
- All admin actions are logged

### For Production Deployment
1. **Set a strong SECRET_KEY**: Don't use default
2. **Use HTTPS**: Set up SSL certificate
3. **Firewall**: Restrict access to necessary ports only
4. **Regular Backups**: Automate database backups
5. **Update Dependencies**: Keep packages up to date

## Deployment Options

### Option 1: Simple Cloud Server (Recommended for Small Clubs)
- DigitalOcean Droplet ($6/month)
- AWS Lightsail ($3.50/month)
- Linode Nanode ($5/month)

Steps:
1. Create Ubuntu 22.04 server
2. Install Python and dependencies
3. Copy application files
4. Set up Gunicorn as WSGI server
5. Configure Nginx as reverse proxy
6. Set up SSL with Let's Encrypt (free)
7. Configure firewall

### Option 2: Platform as a Service (Easiest)
- PythonAnywhere (free tier available, paid from $5/month)
- Heroku (paid plans from $7/month)
- Railway.app (free tier available)

These handle most configuration automatically.

### Option 3: Local/On-Premises Server
- Old computer or Raspberry Pi
- Dynamic DNS service for internet access
- Port forwarding on router
- Good for testing, harder to maintain for production

## Maintenance Tasks

### Daily
- Monitor for failed login attempts
- Check admin log for suspicious activity

### Weekly
- Backup database file
- Review expired dues list

### Monthly
- Update expired member status (after grace period)
- Review and update as needed

### Yearly
- Review and update dues amounts if needed
- Archive old attendance records if desired
- Update copyright year in footer

## Backup Strategy

### Automated Backup Script
Create a cron job to backup daily:

```bash
#!/bin/bash
# Save as backup.sh
DATE=$(date +%Y%m%d)
cp /path/to/WVARA_membership.db /backups/WVARA_$DATE.db
# Keep only last 30 days
find /backups -name "WVARA_*.db" -mtime +30 -delete
```

Add to crontab:
```bash
0 2 * * * /path/to/backup.sh
```

## Customization Guide

### Changing Club Information
Edit `templates/dashboard.html` for club info display

### Changing Default Dues Amount
Edit `templates/admin/dues.html` - change default value

### Modifying Email Templates
(If adding email functionality in future)

### Adding Custom Fields
1. Add column to `models.py`
2. Create database migration
3. Update relevant templates
4. Update forms to accept new field

### Changing Colors/Branding
Edit CSS in `templates/base.html`:
```css
:root {
    --primary-color: #1a5490;    /* Main blue */
    --secondary-color: #4a90d9;  /* Lighter blue */
    --success-color: #28a745;    /* Green */
    --danger-color: #dc3545;     /* Red */
    --warning-color: #ffc107;    /* Yellow */
}
```

## Performance Optimization

For Larger Clubs (500+ members):
1. Consider PostgreSQL instead of SQLite
2. Add database indexes for frequently queried fields
3. Implement caching (Flask-Caching)
4. Use CDN for static files

## Future Enhancement Ideas

### Phase 2 Features
- Email notifications (dues reminders, meeting announcements)
- Calendar view of meetings and events
- Event RSVP system
- Document repository (meeting minutes, bylaws)
- Newsletter management

### Phase 3 Features
- Integration with groups.io or Google Groups
- Payment gateway integration (PayPal API, Stripe)
- Mobile app (React Native or Flutter)
- SMS notifications
- Net participation tracking

### Advanced Features
- Equipment checkout system
- Repeater maintenance logs
- Member skills/capabilities database
- Volunteer hour tracking
- Certificate generation (for awards, training)

## Troubleshooting Common Issues

### Issue: Port 1977 already in use
Solution: Change port in app.py or kill the process using the port

### Issue: Database locked
Solution: Ensure only one instance is running, check file permissions

### Issue: QRZ photos not loading
Solution: Check internet connection, verify call sign on QRZ.com

### Issue: Can't create admin user
Solution: Use init_db.py or directly update database

### Issue: Forgot admin password
Solution: Reset via database or create new admin account

## Support and Updates

### Getting Help
- Review documentation (README.md, QUICK_START.md)
- Check error messages in terminal
- Review Flask logs
- Contact developer (W6SAL)

### Updating the Application
1. Backup database first!
2. Pull/download new version
3. Check for database migrations
4. Update dependencies: `pip install -r requirements.txt`
5. Test on development server
6. Deploy to production

## License and Credits

Developed for WVARA (West Valley Amateur Radio Association)
By: Sal Mancuso (W6SAL)
Date: January 2026

This system is provided as-is for use by WVARA and its members.

## Additional Resources

- Flask Documentation: https://flask.palletsprojects.com/
- Bootstrap Documentation: https://getbootstrap.com/docs/
- SQLite Documentation: https://sqlite.org/docs.html
- Python Security Best Practices: https://python.org/dev/security/

---

For technical support or feature requests, contact W6SAL.
