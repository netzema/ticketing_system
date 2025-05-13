import os
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image
from config import EVENT, BASE_PATH

QR_DIR = os.path.join(BASE_PATH, "qr_codes")
CSV_PATH = os.path.join(BASE_PATH, "ticket_urls.csv")
OUTPUT_PATH = os.path.join(BASE_PATH, f"{EVENT}_qr_codes.xlsx")

# Set up workbook
wb = Workbook()
ws = wb.active
ws.title = "QR Codes"

# Set column widths
ws.column_dimensions["A"].width = 40
ws.column_dimensions["B"].width = 20

# Add QR codes
row = 1
for fname in sorted(os.listdir(QR_DIR)):
    if not fname.endswith(".png") or fname == "scan_page.png":
        continue

    ticket_id = os.path.splitext(fname)[0]
    img_path = os.path.join(QR_DIR, fname)

    # Resize image if necessary
    img = Image.open(img_path)
    img.thumbnail((150, 150))  # Resize in memory
    # img.save(img_path)  # Optional: update file with smaller version

    # Add ticket ID
    ws.cell(row=row, column=1, value=ticket_id)

    # Add image to cell
    qr_img = XLImage(img_path)
    qr_img.anchor = f"B{row}"
    ws.add_image(qr_img)

    row += 1

# Save workbook
wb.save(OUTPUT_PATH)
print(f"✅ Excel file created: {OUTPUT_PATH}")
