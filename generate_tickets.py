import os
import uuid
import sqlite3
import csv
import qrcode
from tqdm import tqdm, trange
import config
import shutil
import datetime
import subprocess
import sys

# Configuration
HOST = config.URL # "192.168.1.18:8000" # "oktoberfest.local:8000"  # Replace with your server host and port
N_TICKETS = config.N_TICKETS
EVENT = config.EVENT
BASE_PATH = config.BASE_PATH
DB_PATH = f"{BASE_PATH}/tickets.db"           # Path to SQLite database
QR_DIR = f"{BASE_PATH}/qr_codes"              # Directory where QR images will be saved
CSV_PATH = f"{BASE_PATH}/ticket_urls.csv"     # CSV file to map ticket IDs to URLs
BACKUP_ROOT = config.BACKUP_ROOT
PDF_SCRIPT = os.path.join(os.path.dirname(__file__), "pdf_tickets.py")

# Function to backup entire event folder
def backup_event_folder(src_folder, backup_root, event_name):
    os.makedirs(backup_root, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"{event_name}_backup_{timestamp}"
    backup_path = os.path.join(backup_root, backup_name)
    # Copy entire event directory tree
    shutil.copytree(src_folder, backup_path)
    print(f"Backup of event folder created at: {backup_path}")

# Ensure output directory exists
os.makedirs(BASE_PATH, exist_ok=True)
os.makedirs(BACKUP_ROOT, exist_ok=True)
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

# Generate SSL certificate and key for HTTPS
print("Generating SSL certificate and key...")
host_ip = HOST.split(':')[0]
key_path = os.path.join(BASE_PATH, 'key.pem')
cert_path = os.path.join(BASE_PATH, 'cert.pem')
# Call OpenSSL to create self-signed certificate
try:
    subprocess.run([
        'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
        '-keyout', key_path, '-out', cert_path,
        '-days', '365', '-subj', f"/CN={host_ip}"
    ], check=True, capture_output=True)
    print(f"Generated cert.pem and key.pem at {BASE_PATH}")
except FileNotFoundError:
    print("Error: OpenSSL not found. Please install OpenSSL to generate certificates.")
except subprocess.CalledProcessError as e:
    print(f"Error generating SSL certificate: {e}")

# Create pdf tickets
# Generate ticket PDFs by invoking pdf_tickets.py
print("Generating ticket PDF files...")
result = subprocess.run([sys.executable, PDF_SCRIPT], check=True)
if result.returncode == 0:
    print("Ticket PDFs generated successfully.")
else:
    print("Error: PDF generation script failed.")

# Backup entire event folder right after generation
backup_event_folder(BASE_PATH, BACKUP_ROOT, EVENT)