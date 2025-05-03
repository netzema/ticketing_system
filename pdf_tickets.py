import os
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from PyPDF2 import PdfReader, PdfWriter
from config import PAGE_WIDTH, PAGE_HEIGHT, MARGIN_RIGHT, QR_SIZE
import config
# Paths and filenames
EVENT = config.EVENT
BASE_PATH = config.BASE_PATH
TEMPLATE_PATH = f"ticket_templates/{EVENT}.pdf"     # 
QR_DIR        = f"{BASE_PATH}/qr_codes"             # Directory containing <ticket_id>.png files
OUTPUT_DIR    = f"{BASE_PATH}/tickets"              # Directory where individual ticket PDFs will be saved
OVERLAY_PDF   = f"{BASE_PATH}/overlay.pdf"          # Temporary overlay file

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Page size (in mm)
PAGE_WIDTH = PAGE_WIDTH * mm
PAGE_HEIGHT = PAGE_HEIGHT * mm

# Coordinates for QR placement on the right side
MARGIN_RIGHT = MARGIN_RIGHT * mm
QR_SIZE      = QR_SIZE * mm
# Place QR code flush to right margin, vertically centered
QR_X = PAGE_WIDTH - MARGIN_RIGHT - QR_SIZE
QR_Y = (PAGE_HEIGHT - QR_SIZE) / 2

# Generate one PDF per ticket
for fname in sorted(os.listdir(QR_DIR)):
    if not fname.lower().endswith('.png') or fname.startswith("scan_page"):
        continue
    qr_path   = os.path.join(QR_DIR, fname)

    # 1) Create a temporary overlay PDF with only the QR image
    c = canvas.Canvas(OVERLAY_PDF, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    c.drawImage(qr_path, QR_X, QR_Y, width=QR_SIZE, height=QR_SIZE)
    c.save()

    # 2) Read fresh template and overlay pages
    template = PdfReader(TEMPLATE_PATH)
    template_page = template.pages[0]
    overlay = PdfReader(OVERLAY_PDF)
    overlay_page = overlay.pages[0]

    template_page.merge_page(overlay_page)

    # 3) Write out individual ticket PDF
    writer = PdfWriter()
    writer.add_page(template_page)
    ticket_id = os.path.splitext(fname)[0]
    output_path = os.path.join(OUTPUT_DIR, f"{ticket_id}.pdf")
    with open(output_path, 'wb') as f:
        writer.write(f)

# Clean up temporary overlay file
if os.path.exists(OVERLAY_PDF):
    os.remove(OVERLAY_PDF)

print(f"Created individual ticket PDFs in '{OUTPUT_DIR}' ({len(os.listdir(OUTPUT_DIR))} files).")
