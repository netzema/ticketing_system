import os
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image
from config import EVENT, BASE_PATH

QR_DIR = os.path.join(BASE_PATH, "qr_codes")
OUTPUT_PATH = os.path.join(BASE_PATH, f"{EVENT}_qr_codes.xlsx")

# Excel layout constants
IMG_DISPLAY_SIZE = 80   # in pixels
ROW_HEIGHT = 100        # Excel row height is in points (~0.75 pixels)

# Create workbook
wb = Workbook()
ws = wb.active
ws.title = "QR Codes"
ws.append(["Ticket ID", "QR Code"])
ws.row_dimensions[1].height = 20  # Header row

# Adjust column widths
ws.column_dimensions["A"].width = 40
ws.column_dimensions["B"].width = 18

# Process each QR image
row = 2
for fname in sorted(os.listdir(QR_DIR)):
    if not fname.endswith(".png") or fname == "scan_page.png":
        continue

    ticket_id = os.path.splitext(fname)[0]
    original_path = os.path.join(QR_DIR, fname)

    # Adjust row height
    ws.row_dimensions[row].height = ROW_HEIGHT

    # Insert text and image
    ws.cell(row=row, column=1, value=ticket_id)
    qr_img = XLImage(original_path)
    qr_img.width = IMG_DISPLAY_SIZE
    qr_img.height = IMG_DISPLAY_SIZE
    qr_img.anchor = f"B{row}"
    ws.add_image(qr_img)

    row += 1

# Save workbook
wb.save(OUTPUT_PATH)
print(f"✅ Excel file created: {OUTPUT_PATH}")
