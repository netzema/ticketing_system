import os
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from PyPDF2 import PdfReader, PdfWriter
import config

# Configuration
EVENT = config.EVENT
BASE_PATH = config.BASE_PATH
TEMPLATE_PATH = os.path.join("ticket_templates", f"{EVENT}.pdf")
QR_DIR = os.path.join(BASE_PATH, "qr_codes")
OUTPUT_DIR = os.path.join(BASE_PATH, "tickets")
OVERLAY_PDF = os.path.join(BASE_PATH, "overlay.pdf")

# Page size and coordinates (mm)
PAGE_WIDTH = config.PAGE_WIDTH * mm
PAGE_HEIGHT = config.PAGE_HEIGHT * mm
MARGIN_RIGHT = config.MARGIN_RIGHT * mm
QR_SIZE = config.QR_SIZE * mm
MARGIN_BOTTOM = getattr(config, "MARGIN_BOTTOM", (PAGE_HEIGHT - QR_SIZE) / 2) * mm
if not MARGIN_BOTTOM:
    MARGIN_BOTTOM = (PAGE_HEIGHT - QR_SIZE) / 2
MERGE_PAGE_INDEX = getattr(config, 'MERGE_PAGE_INDEX', 1)

# QR placement
QR_X = PAGE_WIDTH - MARGIN_RIGHT - QR_SIZE
QR_Y = MARGIN_BOTTOM

# Ensure output dir exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Helper to create overlay page
def create_overlay_page(qr_path):
    c = canvas.Canvas(OVERLAY_PDF, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
    c.drawImage(qr_path, QR_X, QR_Y, width=QR_SIZE, height=QR_SIZE)
    c.save()
    overlay = PdfReader(OVERLAY_PDF)
    return overlay.pages[0]

# Generate PDFs
writer = PdfWriter()
for fname in sorted(os.listdir(QR_DIR)):
    if not fname.lower().endswith('.png') or fname.startswith("scan_page"):
        continue
    qr_path = os.path.join(QR_DIR, fname)
    ticket_id = os.path.splitext(fname)[0]

    # Create overlay page
    overlay_page = create_overlay_page(qr_path)

    # Read template and merge
    template = PdfReader(TEMPLATE_PATH)
    for idx, page in enumerate(template.pages):
        if idx == MERGE_PAGE_INDEX:
            page.merge_page(overlay_page)
        writer.add_page(page)

# Write ticket PDF
output_file = os.path.join(OUTPUT_DIR, f"{EVENT}_tickets.pdf")
with open(output_file, 'wb') as out_f:
    writer.write(out_f)

# Cleanup overlay
if os.path.exists(OVERLAY_PDF):
    os.remove(OVERLAY_PDF)

print(f"Created individual ticket PDFs in '{OUTPUT_DIR}' ({len(os.listdir(OUTPUT_DIR))} files).")