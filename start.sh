#!/bin/bash
# WVARA Membership System Startup Script

echo "=========================================="
echo "WVARA Membership Management System"
echo "=========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Check if database exists
if [ ! -f "WVARA_membership.db" ]; then
    echo ""
    echo "Database not found. Initializing database..."
    echo ""
    python init_db.py
fi

echo ""
echo "=========================================="
echo "Starting WVARA Membership System..."
echo "=========================================="
echo ""
echo "The application will be available at:"
echo "  http://localhost:1977"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the application
python app.py
