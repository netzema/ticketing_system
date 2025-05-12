import os
import sqlite3
import sys

if len(sys.argv) != 2:
    print("Usage: python reset_all_tickets.py <EVENT_NAME>")
    sys.exit(1)

EVENT = sys.argv[1]
BASE_PATH = os.path.join("events", EVENT)
DB_PATH = os.path.join(BASE_PATH, "tickets.db")

if not os.path.exists(DB_PATH):
    print(f"❌ Database not found: {DB_PATH}")
    sys.exit(1)

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("UPDATE tickets SET scanned_at = NULL")
conn.commit()
conn.close()

print(f"✅ All tickets for event '{EVENT}' have been reset (marked as unused).")
