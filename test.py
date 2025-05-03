import os
import csv
import sqlite3
import urllib.request
import urllib.error

# Paths
DB_PATH = "tickets.db"
QR_DIR = "qr_codes"
CSV_PATH = "ticket_urls.csv"

# 1. Check QR code folder
qr_files = [f for f in os.listdir(QR_DIR) if f.endswith(".png")]
print(f"QR folder '{QR_DIR}': {len(qr_files)} .png files found.")

# 2. Check CSV entries
with open(CSV_PATH, newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    csv_entries = list(reader)
print(f"CSV '{CSV_PATH}': {len(csv_entries)} entries (excluding header).")

# 3. Check database entries and scanned status
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT COUNT(*) FROM tickets")
total_db = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM tickets WHERE scanned_at IS NOT NULL")
scanned_db = c.fetchone()[0]
conn.close()
print(f"Database '{DB_PATH}': {total_db} tickets, {scanned_db} already scanned.")

# 4. Test a few URLs
print("\nTesting first 5 ticket validation URLs:")
for entry in csv_entries[:5]:
    tid = entry["ticket_id"]
    url = entry["url"]
    print(f"\nURL: {url}")
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            status = response.getcode()
            body = response.read(200).decode('utf-8', errors='replace')
            print(f"  Status code: {status}")
            print(f"  Response snippet: {body.strip()[:100]}...")
    except urllib.error.URLError as e:
        print(f"  Error: {e}")
    except Exception as e:
        print(f"  Unexpected error: {e}")
