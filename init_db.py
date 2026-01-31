"""
Initialize WVARA Membership Database with Sample Data
Run this after first installation to populate the database with initial members
"""
from app import app, db
from models import Member, DuesPayment, RoleHistory
from datetime import date, datetime
import csv

def init_database():
    """Initialize database with initial member data"""
    with app.app_context():
        # Create all tables
        db.create_all()
        print("✓ Database tables created")
        
        # Check if data already exists
        if Member.query.first():
            print("! Database already contains data. Skipping initialization.")
            return
        
        # Create admin members
        print("\nCreating admin members...")
        
        # W6SAL - Sal (Admin)
        sal = Member(
            call_sign='W6SAL',
            first_name='Sal',
            last_name='Mancuso',
            email='W6SAL@Yahoo.com',
            phone='(408) 555-1234',
            address='123 Radio Signal Lane',
            city='San Jose',
            state='CA',
            zip_code='95125',
            fcc_license_class='General',
            membership_type='Individual',
            join_date=date(2024, 1, 1),
            is_active=True,
            is_admin=True,
            emergency_contact_name='Sarah Mancuso',
            emergency_contact_phone='(408) 555-5678',
            emergency_contact_relationship='Spouse'
        )
        sal.set_password('W6SAL')  # Initial password same as call sign
        sal.password_is_temporary = True
        db.session.add(sal)
        print(f"  ✓ Created {sal.call_sign} - Admin")
        
      
  
        # Add a few more sample members
        sample_members = [
            {
                'call_sign': 'KK6OTD',
                'first_name': 'Tim',
                'last_name': 'Allen',
                'email': 'Tim@ToolTIme.com',
                'fcc_license_class': 'Technician',
                'membership_type': 'Individual',
                'join_date': date(2018, 3, 15)
            },
            {
                'call_sign': 'WV6VLY',
                'first_name': 'Steve',
                'last_name': 'Wozniak',
                'email': 'Woz@Apple.com',
                'fcc_license_class': 'Technician',
                'membership_type': 'Family',
                'join_date': date(1998, 7, 22)
            },
            {
                'call_sign': 'WB6ACU',
                'first_name': 'Joe',
                'last_name': 'Walsh',
                'email': 'Joe@TheEagles.com',
                'fcc_license_class': 'Amateur Extra',
                'membership_type': 'Extra',
                'join_date': date(2002, 1, 10)
            }
        ]
        
        for member_data in sample_members:
            member = Member(
                call_sign=member_data['call_sign'],
                first_name=member_data['first_name'],
                last_name=member_data['last_name'],
                email=member_data['email'],
                phone=f'(408) 555-{member_data["call_sign"][-4:]}',
                address='100 Sample St',
                city='San Jose',
                state='CA',
                zip_code='95120',
                fcc_license_class=member_data['fcc_license_class'],
                membership_type=member_data['membership_type'],
                join_date=member_data['join_date'],
                is_active=True,
                is_admin=False,
                emergency_contact_name='Emergency Contact',
                emergency_contact_phone='(408) 555-9999',
                emergency_contact_relationship='Family'
            )
            member.set_password(member_data['call_sign'])
            member.password_is_temporary = True
            db.session.add(member)
            print(f"  ✓ Created {member.call_sign}")
        
        db.session.commit()
        print("\n✓ Member data created successfully")
        
        # Add current roles for leadership
        print("\nCreating leadership roles...")

        
        board_role = RoleHistory(
            member_id=sal.id,
            role_name='Board Member',
            start_date=date(2026, 1, 1),
            is_current=True
        )
        db.session.add(board_role)
        
        db.session.commit()
        print("✓ Leadership roles created")
        
        # Add sample dues payments for current year
        print("\nCreating sample dues payments...")
        current_year = datetime.now().year
        
        for member in [sal]:
            payment = DuesPayment(
                member_id=member.id,
                year=current_year,
                amount=15.00,
                payment_date=date(current_year, 1, 15),
                payment_method='PayPal',
                created_by='SYSTEM'
            )
            db.session.add(payment)
        
        db.session.commit()
        print(f"✓ Dues payments created for {current_year}")
        
        print("\n" + "="*60)
        print("DATABASE INITIALIZATION COMPLETE!")
        print("="*60)
        print("\nInitial Admin Accounts:")
        print("-" * 60)
        print(f"  W6SAL (Sal)       - Password: W6SAL")
        print("-" * 60)
        print("-" * 60)
        print("\n⚠ IMPORTANT: All passwords are temporary and must be changed")
        print("            on first login!\n")


def load_members_from_csv(csv_file):
    """
    Load members from a CSV file
    CSV format: call_sign,first_name,last_name,email,phone,address,city,state,zip,fcc_class,membership_type,join_date
    """
    with app.app_context():
        print(f"\nLoading members from {csv_file}...")
        
        with open(csv_file, 'r') as file:
            reader = csv.DictReader(file)
            count = 0
            
            for row in reader:
                # Check if member already exists
                existing = Member.query.filter_by(call_sign=row['call_sign'].upper()).first()
                if existing:
                    print(f"  ⚠ Skipping {row['call_sign']} - already exists")
                    continue
                
                # Parse join date
                try:
                    join_date = datetime.strptime(row.get('join_date', '2024-01-01'), '%Y-%m-%d').date()
                except:
                    join_date = date.today()
                
                member = Member(
                    call_sign=row['call_sign'].upper().strip(),
                    first_name=row['first_name'].strip(),
                    last_name=row['last_name'].strip(),
                    email=row['email'].strip(),
                    phone=row.get('phone', '').strip(),
                    address=row.get('address', '').strip(),
                    city=row.get('city', '').strip(),
                    state=row.get('state', '').strip().upper(),
                    zip_code=row.get('zip', '').strip(),
                    fcc_license_class=row.get('fcc_class', '').strip(),
                    membership_type=row.get('membership_type', 'Individual').strip(),
                    join_date=join_date,
                    is_active=True,
                    is_admin=False,
                    emergency_contact_name=row.get('emergency_name', 'Not Provided'),
                    emergency_contact_phone=row.get('emergency_phone', 'Not Provided'),
                    emergency_contact_relationship=row.get('emergency_relationship', '')
                )
                
                # Set initial password to call sign
                member.set_password(row['call_sign'].upper())
                member.password_is_temporary = True
                
                db.session.add(member)
                count += 1
                print(f"  ✓ Added {member.call_sign} - {member.get_full_name()}")
            
            db.session.commit()
            print(f"\n✓ Successfully imported {count} members")


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'csv':
        if len(sys.argv) < 3:
            print("Usage: python init_db.py csv <filename.csv>")
            sys.exit(1)
        load_members_from_csv(sys.argv[2])
    else:
        init_database()
