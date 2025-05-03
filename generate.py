import os
import uuid
import sqlite3
import csv
import qrcode
from tqdm import tqdm, trange
import config

# Configuration
DB_PATH = "tickets.db"            # Path to SQLite database
QR_DIR = "qr_codes"              # Directory where QR images will be saved
CSV_PATH = "ticket_urls.csv"     # CSV file to map ticket IDs to URLs
HOST = config.HOST # "192.168.1.18:8000" # "oktoberfest.local:8000"  # Replace with your server host and port
N_TICKETS = config.N_TICKETS

# Ensure output directory exists
os.makedirs(QR_DIR, exist_ok=True)

# Initialize database and insert 1500 unique ticket IDs
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
# Drop table if it exists to start fresh (optional)
c.execute("DROP TABLE IF EXISTS tickets")
# Create table
c.execute("""
CREATE TABLE tickets (
    ticket_id TEXT PRIMARY KEY,
    scanned_at DATETIME
)
""")
# Generate and insert UUID4 ticket IDs
ticket_ids = []
print("Saving tickets to database...")
for _ in trange(N_TICKETS):
    tid = str(uuid.uuid4())
    ticket_ids.append(tid)
    c.execute("INSERT INTO tickets(ticket_id) VALUES(?)", (tid,))

conn.commit()
conn.close()

# Generate QR codes with embedded URLs and write mapping to CSV
with open(CSV_PATH, mode="w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["ticket_id", "url"])
    print("Writing QR codes...")
    for tid in tqdm(ticket_ids):
        url = f"https://{HOST}/validate/{tid}"
        writer.writerow([tid, url])

        # Create QR code
        img = qrcode.make(url)
        img_path = os.path.join(QR_DIR, f"{tid}.png")
        img.save(img_path)

    # Generate QR code for the continuous scan page
    scan_url = f"https://{HOST}/scan"
    writer.writerow(["scan_page", scan_url])
    scan_img = qrcode.make(scan_url)
    scan_img_path = os.path.join(QR_DIR, "scan_page.png")
    scan_img.save(scan_img_path)

print(f"Database initialized at {DB_PATH} with {N_TICKETS} tickets.")
print(f"QR codes saved in '{QR_DIR}'.")
print(f"Ticket-to-URL map written to '{CSV_PATH}'.")
