"""
Run this script once to initialize the new work_sessions table.
"""
import sys
sys.path.insert(0, '.')

from utils import work_order_db

print("Initializing work order database with new session tables...")
work_order_db.init_work_order_db()
print("Done! The work_sessions and session_samples tables have been created.")
