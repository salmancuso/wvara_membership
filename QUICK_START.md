# WVARA Membership System - Quick Start Guide

## Installation (First Time Setup)

### Option 1: Automatic Setup (Recommended)
```bash
chmod +x start.sh
./start.sh
```

This will automatically:
- Create a virtual environment
- Install all dependencies
- Initialize the database
- Start the application

### Option 2: Manual Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python init_db.py

# Start application
python app.py
```

## Access the Application

Once started, open your web browser and go to:
```
http://localhost:5000
```

## Login Credentials

### Administrators (can manage all members and settings):
- **Call Sign**: W6SAL | **Password**: W6SAL (Sal - Full Admin)
- **Call Sign**: KK6IK | **Password**: KK6IK (President - Full Admin)
- **Call Sign**: W6HS | **Password**: W6HS (Eric - Board Member, Full Admin)

### Regular Member:
- **Call Sign**: KQ6OT | **Password**: KQ6OT (Tom - Regular Member)

⚠️ **IMPORTANT**: All initial passwords are temporary and MUST be changed on first login!

## First Steps

### As a Member:
1. Login with your call sign
2. Change your temporary password (you'll be prompted)
3. Update your profile information
4. View your membership status and dues

### As an Administrator:
1. Login with an admin account
2. Change your temporary password
3. Click "Admin" in the navigation bar
4. Explore:
   - **Dashboard**: Overview of club status, expired dues, recent activity
   - **Members**: View and manage all members
   - **Dues**: Record membership payments
   - **Attendance**: Record meeting attendance
   - **Roles**: Manage leadership positions
   - **Reports**: Generate various reports

## Key Features

### For All Members:
- ✓ View membership status and dues
- ✓ Update contact information
- ✓ View meeting attendance history
- ✓ See current roles
- ✓ Change password

### For Administrators Only:
- ✓ Manage all member accounts
- ✓ Record dues payments
- ✓ Take meeting attendance
- ✓ Assign/remove leadership roles
- ✓ Grant/revoke admin access
- ✓ Reset member passwords
- ✓ Generate reports (PDF & CSV):
  - Member Directory
  - Dues Status
  - Attendance Records
  - Email Lists
  - Mailing Labels

## Importing Existing Members

If you have a CSV file with your current members:

```bash
python init_db.py csv your_members.csv
```

See `sample_import.csv` for the required format.

## Common Tasks

### Recording Dues Payment (Admin):
1. Admin → Dues
2. Select member from dropdown
3. Enter year, amount, and payment date
4. Click "Record Payment"

### Taking Meeting Attendance (Admin):
1. Admin → Attendance
2. Select meeting date
3. Check boxes for members who attended
4. Click "Record Attendance"

### Generating Reports (Admin):
1. Admin → Reports
2. Choose report type
3. Select format (CSV or PDF)
4. Download

## Troubleshooting

**Application won't start**:
- Make sure Python 3.8+ is installed
- Check that port 5000 is not in use
- Verify all dependencies are installed

**Can't login**:
- Call sign must be UPPERCASE
- Check that account exists and is active
- Contact admin for password reset if needed

**Database error**:
- Stop the application
- Make a backup of `WVARA_membership.db`
- Try restarting

## Need Help?

For questions or technical issues:
- Contact: W6SAL (Sal Mancuso)
- Refer to the full README.md for detailed documentation

---

**WVARA - West Valley Amateur Radio Association**
