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

# Configuration from config.py
HOST = config.URL           # e.g., "192.168.1.18:8000"
N_TICKETS = config.N_TICKETS
EVENT = config.EVENT
BASE_PATH = config.BASE_PATH
DB_PATH = os.path.join(BASE_PATH, 'tickets.db')
QR_DIR = os.path.join(BASE_PATH, 'qr_codes')
CSV_PATH = os.path.join(BASE_PATH, 'ticket_urls.csv')
BACKUP_ROOT = config.BACKUP_ROOT
PDF_SCRIPT = os.path.join(os.path.dirname(__file__), 'pdf_tickets.py')

# Ensure output directories exist
os.makedirs(BASE_PATH, exist_ok=True)
os.makedirs(BACKUP_ROOT, exist_ok=True)
os.makedirs(QR_DIR, exist_ok=True)

# Initialize database
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("DROP TABLE IF EXISTS tickets")
c.execute(
    """
    CREATE TABLE tickets (
        ticket_id TEXT PRIMARY KEY,
        scanned_at DATETIME
    )
    """
)

# Generate and store ticket IDs
ticket_ids = []
print("Saving tickets to database...")
for _ in trange(N_TICKETS):
    tid = str(uuid.uuid4())
    ticket_ids.append(tid)
    c.execute("INSERT INTO tickets(ticket_id) VALUES(?)", (tid,))
conn.commit()
conn.close()

# Generate QR codes and CSV mapping
with open(CSV_PATH, mode='w', newline='', encoding='utf-8') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(['ticket_id', 'url'])
    print("Writing QR codes and URLs...")

    for tid in tqdm(ticket_ids):
        url = f"https://{HOST}/validate/{tid}"
        writer.writerow([tid, url])

        # Create a QRCode object without border
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=0
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        img_path = os.path.join(QR_DIR, f"{tid}.png")
        img.save(img_path)

    # Add scan page QR code
    scan_url = f"https://{HOST}/scan"
    writer.writerow(['scan_page', scan_url])
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=0
    )
    qr.add_data(scan_url)
    qr.make(fit=True)
    scan_img = qr.make_image(fill_color='black', back_color='white')
    scan_img_path = os.path.join(QR_DIR, 'scan_page.png')
    scan_img.save(scan_img_path)

print(f"Database initialized at {DB_PATH} with {len(ticket_ids)} tickets.")
print(f"QR codes saved in '{QR_DIR}'. CSV written to '{CSV_PATH}'.")

# Generate SSL certificate and key
print("Generating SSL certificate and key...")
host_ip = HOST.split(':')[0]
key_path = os.path.join(BASE_PATH, 'key.pem')
cert_path = os.path.join(BASE_PATH, 'cert.pem')
try:
    subprocess.run([
        'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
        '-keyout', key_path, '-out', cert_path,
        '-days', '365', '-subj', f"/CN={host_ip}"
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Generated cert.pem and key.pem at {BASE_PATH}")
except FileNotFoundError:
    print("Error: OpenSSL not found. Please install OpenSSL.")
except subprocess.CalledProcessError as e:
    print(f"Error generating SSL certificate: {e}")

# Generate ticket PDFs
def run_pdf_script():
    print("Generating ticket PDF files...")
    result = subprocess.run([sys.executable, PDF_SCRIPT], check=False)
    if result.returncode == 0:
        print("Ticket PDFs generated successfully.")
    else:
        print("Error: PDF generation script failed.")

run_pdf_script()

# Backup entire event folder
def backup_event_folder(src_folder, backup_root, event_name):
    os.makedirs(backup_root, exist_ok=True)
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"{event_name}_backup_{timestamp}"
    backup_path = os.path.join(backup_root, backup_name)
    shutil.copytree(src_folder, backup_path)
    print(f"Backup created at: {backup_path}")

backup_event_folder(BASE_PATH, BACKUP_ROOT, EVENT)
