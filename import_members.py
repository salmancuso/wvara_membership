#!/usr/bin/env python3
"""
CSV Member Import Script
Usage: python import_members.py [csv_filename]

Imports members from a CSV file into the WVARA membership database.
CSV Format: call_sign,first_name,last_name,email,phone,address,city,state,zip,fcc_class,membership_type,join_date,emergency_name,emergency_phone,emergency_relationship
"""

import csv
import sys
from datetime import datetime
from app import app, db
from models import Member

def import_members(csv_filename='sample_import.csv'):
    """Import members from CSV file"""
    
    with app.app_context():
        imported = 0
        skipped = 0
        errors = 0
        
        print(f"\n{'='*60}")
        print(f"WVARA Member Import")
        print(f"{'='*60}\n")
        print(f"Reading from: {csv_filename}\n")
        
        try:
            with open(csv_filename, 'r') as csvfile:
                reader = csv.DictReader(csvfile)
                
                for row_num, row in enumerate(reader, start=2):  # Start at 2 (after header)
                    call_sign = row['call_sign'].strip().upper()
                    
                    # Check if member already exists
                    existing = Member.query.filter_by(call_sign=call_sign).first()
                    if existing:
                        print(f"⊘ Row {row_num}: {call_sign} - SKIPPED (already exists)")
                        skipped += 1
                        continue
                    
                    # Check if email already exists
                    email = row['email'].strip()
                    existing_email = Member.query.filter_by(email=email).first()
                    if existing_email:
                        print(f"⊘ Row {row_num}: {call_sign} - SKIPPED (email {email} already in use)")
                        skipped += 1
                        continue
                    
                    # Parse join date
                    try:
                        join_date = datetime.strptime(row['join_date'].strip(), '%Y-%m-%d').date()
                    except ValueError:
                        print(f"✗ Row {row_num}: {call_sign} - ERROR (invalid date format: {row['join_date']})")
                        errors += 1
                        continue
                    
                    # Create new member
                    try:
                        new_member = Member(
                            call_sign=call_sign,
                            first_name=row['first_name'].strip(),
                            last_name=row['last_name'].strip(),
                            email=email,
                            phone=row['phone'].strip() if row['phone'].strip() else None,
                            address=row['address'].strip() if row['address'].strip() else None,
                            city=row['city'].strip() if row['city'].strip() else None,
                            state=row['state'].strip() if row['state'].strip() else None,
                            zip_code=row['zip'].strip() if row['zip'].strip() else None,
                            fcc_license_class=row['fcc_class'].strip() if row['fcc_class'].strip() else None,
                            membership_type=row['membership_type'].strip() if row['membership_type'].strip() else 'Individual',
                            join_date=join_date,
                            emergency_contact_name=row['emergency_name'].strip() if row['emergency_name'].strip() else None,
                            emergency_contact_phone=row['emergency_phone'].strip() if row['emergency_phone'].strip() else None,
                            emergency_contact_relationship=row['emergency_relationship'].strip() if row['emergency_relationship'].strip() else None,
                            is_active=True,
                            is_admin=False
                        )
                        
                        # Set initial password to call sign (temporary)
                        new_member.set_password(call_sign)
                        new_member.password_is_temporary = True
                        
                        db.session.add(new_member)
                        db.session.commit()
                        
                        print(f"✓ Row {row_num}: {call_sign} - {row['first_name']} {row['last_name']} - IMPORTED")
                        imported += 1
                        
                    except Exception as e:
                        db.session.rollback()
                        print(f"✗ Row {row_num}: {call_sign} - ERROR ({str(e)})")
                        errors += 1
                        continue
        
        except FileNotFoundError:
            print(f"✗ ERROR: File '{csv_filename}' not found!")
            print(f"\nMake sure the CSV file is in the same directory as this script.")
            return
        
        except Exception as e:
            print(f"✗ ERROR: {str(e)}")
            return
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"Import Summary")
        print(f"{'='*60}")
        print(f"✓ Successfully imported: {imported}")
        print(f"⊘ Skipped (duplicates):  {skipped}")
        print(f"✗ Errors:                {errors}")
        print(f"{'='*60}\n")
        
        if imported > 0:
            print(f"Initial Passwords:")
            print(f"  All imported members have their call sign as password")
            print(f"  (e.g., W6ABC password is 'W6ABC')")
            print(f"  Members MUST change password on first login.\n")


if __name__ == '__main__':
    # Get CSV filename from command line or use default
    csv_file = sys.argv[1] if len(sys.argv) > 1 else 'sample_import.csv'
    
    import_members(csv_file)
