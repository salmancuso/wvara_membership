# Member Import Guide

## Quick Start

### Import the Sample File

```bash
cd Desktop/WVARA_membership
python import_members.py
```

That's it! The script will import all members from `sample_import.csv`.

---

## Detailed Instructions

### Step 1: Prepare Your CSV File

Your CSV file must have these columns (in any order):

```csv
call_sign,first_name,last_name,email,phone,address,city,state,zip,fcc_class,membership_type,join_date,emergency_name,emergency_phone,emergency_relationship
```

### Step 2: Format Requirements

**Required Columns**:
- `call_sign` - Amateur radio call sign (e.g., W6SAL, K6ABC)
- `first_name` - Member's first name
- `last_name` - Member's last name
- `email` - Must be unique
- `join_date` - Format: YYYY-MM-DD (e.g., 2024-01-15)

**Optional Columns** (can be blank):
- `phone` - Phone number
- `address` - Street address
- `city` - City
- `state` - Two-letter state code (e.g., CA)
- `zip` - ZIP code
- `fcc_class` - License class (Technician, General, Amateur Extra)
- `membership_type` - Individual, Family, Lifetime, Honorary (default: Individual)
- `emergency_name` - Emergency contact name
- `emergency_phone` - Emergency contact phone
- `emergency_relationship` - Relationship (Spouse, Parent, etc.)

### Step 3: Example CSV

```csv
call_sign,first_name,last_name,email,phone,address,city,state,zip,fcc_class,membership_type,join_date,emergency_name,emergency_phone,emergency_relationship
W6ABC,John,Doe,john@example.com,(408) 555-1234,123 Main St,San Jose,CA,95120,General,Individual,2020-01-15,Jane Doe,(408) 555-5678,Spouse
K6XYZ,Alice,Smith,alice@example.com,(408) 555-2345,456 Oak Ave,Campbell,CA,95008,Technician,Family,2019-06-22,Bob Smith,(408) 555-6789,Spouse
```

### Step 4: Run Import

**Basic usage** (imports sample_import.csv):
```bash
python import_members.py
```

**Import a different file**:
```bash
python import_members.py my_members.csv
```

**Import from Excel**:
1. Open your Excel file
2. Click File → Save As
3. Choose "CSV UTF-8 (Comma delimited)"
4. Save as `my_members.csv`
5. Run: `python import_members.py my_members.csv`

### Step 5: Review Results

The script will show:
```
============================================================
WVARA Member Import
============================================================

Reading from: sample_import.csv

✓ Row 2: W6ABC - John Doe - IMPORTED
✓ Row 3: K6XYZ - Alice Smith - IMPORTED
⊘ Row 4: N6DEF - SKIPPED (already exists)

============================================================
Import Summary
============================================================
✓ Successfully imported: 2
⊘ Skipped (duplicates):  1
✗ Errors:                0
============================================================

Initial Passwords:
  All imported members have their call sign as password
  (e.g., W6ABC password is 'W6ABC')
  Members MUST change password on first login.
```

---

## What Happens During Import

### For Each Row:

1. **Check for duplicates**: 
   - If call sign exists → SKIP
   - If email exists → SKIP

2. **Validate data**:
   - Date format must be YYYY-MM-DD
   - Email must be valid format

3. **Create member**:
   - Add to database
   - Set password = call sign (temporary)
   - Mark password as temporary (forces change on first login)
   - Set is_active = True
   - Set is_admin = False

### Initial Credentials

**Every imported member**:
- Username: Their call sign (e.g., W6ABC)
- Password: Their call sign (e.g., W6ABC)
- Must change password on first login

---

## Troubleshooting

### Problem: File not found

```
✗ ERROR: File 'my_members.csv' not found!
```

**Solution**: 
- Make sure CSV file is in the same directory as import_members.py
- Check filename spelling (case-sensitive on Linux/Mac)

### Problem: Invalid date format

```
✗ Row 5: W6XYZ - ERROR (invalid date format: 01/15/2024)
```

**Solution**: 
- Dates must be YYYY-MM-DD format
- Change `01/15/2024` to `2024-01-15`

### Problem: Duplicate call sign

```
⊘ Row 3: W6SAL - SKIPPED (already exists)
```

**Solution**: 
- Member already in database
- If this is an update, delete old member first
- Or manually edit in admin interface

### Problem: Duplicate email

```
⊘ Row 4: K6ABC - SKIPPED (email john@example.com already in use)
```

**Solution**:
- Each member must have unique email
- Change email in CSV
- Or remove existing member with that email

---

## Advanced Usage

### Import Multiple Files

```bash
python import_members.py members_2024.csv
python import_members.py members_2025.csv
python import_members.py new_members.csv
```

### Test Import (Dry Run)

To see what would happen without actually importing:
```bash
# Make a copy of your database first
cp instance/WVARA_membership.db instance/backup.db

# Run import
python import_members.py test_members.csv

# If something went wrong, restore
cp instance/backup.db instance/WVARA_membership.db
```

### Create CSV from Existing Members

Want to export current members to CSV?
```bash
# In admin interface:
Admin → Reports → Member Directory → Download CSV
```

---

## CSV Template

### Minimal Template (Required Fields Only)

```csv
call_sign,first_name,last_name,email,join_date
W6ABC,John,Doe,john.doe@example.com,2024-01-15
K6XYZ,Alice,Smith,alice.smith@example.com,2024-01-20
```

### Full Template (All Fields)

```csv
call_sign,first_name,last_name,email,phone,address,city,state,zip,fcc_class,membership_type,join_date,emergency_name,emergency_phone,emergency_relationship
W6ABC,John,Doe,john@example.com,(408) 555-1234,123 Main St,San Jose,CA,95120,General,Individual,2024-01-15,Jane Doe,(408) 555-5678,Spouse
K6XYZ,Alice,Smith,alice@example.com,(408) 555-2345,456 Oak Ave,Campbell,CA,95008,Technician,Family,2024-01-20,Bob Smith,(408) 555-6789,Spouse
N6DEF,Bob,Johnson,bob@example.com,(408) 555-3456,789 Elm St,Los Gatos,CA,95030,Extra,Individual,2024-02-01,Mary Johnson,(408) 555-7890,Spouse
```

---

## Best Practices

### Before Import

1. **Backup database**:
   ```bash
   cp instance/WVARA_membership.db instance/backup_$(date +%Y%m%d).db
   ```

2. **Validate CSV**:
   - Check all dates are YYYY-MM-DD
   - Verify emails are unique
   - Confirm call signs are correct

3. **Test with small file first**:
   - Create CSV with 2-3 members
   - Run import
   - Verify in admin interface
   - Then import full file

### After Import

1. **Verify in admin**:
   ```
   Admin → Manage Members
   Check: All members imported
   ```

2. **Notify members**:
   - Send email with login instructions
   - Username = call sign
   - Password = call sign (temporary)
   - Must change on first login

3. **Record dues if needed**:
   ```
   Admin → Manage Dues Payments
   Record payments for members who paid
   ```

---

## Common Scenarios

### Scenario 1: New Club Setup

You have a spreadsheet of 50 members:

1. Export to CSV from Excel
2. Backup database
3. Run import: `python import_members.py members.csv`
4. Verify all imported
5. Record dues for paid members
6. Send login credentials to all members

### Scenario 2: Annual Renewals

You have new members from sign-up sheet:

1. Add to CSV (name, call, email, join date)
2. Run import: `python import_members.py new_members_2026.csv`
3. Record their dues payments
4. Email them credentials

### Scenario 3: Family Members

Family membership with 2 members:

```csv
call_sign,first_name,last_name,email,membership_type,join_date
W6ABC,John,Doe,john@example.com,Family,2024-01-15
K6ABC,Jane,Doe,jane@example.com,Family,2024-01-15
```

Both imported with Family membership type.

---

## FAQ

**Q: Can I update existing members with CSV?**  
A: No, import only adds new members. To update, use admin interface or delete and re-import.

**Q: What if I have different CSV columns?**  
A: You must match the column names exactly. Edit your CSV headers to match.

**Q: Can I skip optional fields?**  
A: Yes! Leave them blank in CSV. Only call_sign, first_name, last_name, email, join_date are required.

**Q: How do I import from Google Sheets?**  
A: File → Download → Comma-separated values (.csv). Then run import_members.py.

**Q: Are passwords secure?**  
A: Initial passwords (call sign) are temporary. Members MUST change on first login. Changed passwords are securely hashed.

**Q: Can I import hundreds of members?**  
A: Yes! Script handles any number. May take a few seconds for large files.

---

## Summary

**Quick Import**:
```bash
cd Desktop/WVARA_membership
python import_members.py
```

**Custom Import**:
```bash
python import_members.py your_file.csv
```

**Required CSV Format**:
- call_sign, first_name, last_name, email, join_date
- Date format: YYYY-MM-DD
- Emails must be unique

**After Import**:
- All passwords = call sign
- Must change on first login
- Record dues separately if needed

Done! 73!
