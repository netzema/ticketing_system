import os
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image
from config import EVENT, BASE_PATH

QR_DIR = os.path.join(BASE_PATH, "qr_codes")
OUTPUT_PATH = os.path.join(BASE_PATH, f"{EVENT}_qr_codes.xlsx")

# excel layout constants
IMG_DISPLAY_SIZE = 80 # in pixels
ROW_HEIGHT = 100 # Excel row height in points (~0.75 pixels)

# create workbook
wb = Workbook()
ws = wb.active
ws.title = "QR Codes"
ws.append(["Ticket ID"]) #, "QR Code"])
ws.row_dimensions[1].height = 20  # header row

# adjust column widths
ws.column_dimensions["A"].width = 40
# ws.column_dimensions["B"].width = 18

# process each QR image
row = 2
for fname in sorted(os.listdir(QR_DIR)):
    if not fname.endswith(".png") or fname == "scan_page.png":
        continue

    ticket_id = os.path.splitext(fname)[0]
    original_path = os.path.join(QR_DIR, fname)

    # adjust row height
    # ws.row_dimensions[row].height = ROW_HEIGHT

    # insert text and image
    ws.cell(row=row, column=1, value=ticket_id)
    # qr_img = XLImage(original_path)
    # qr_img.width = IMG_DISPLAY_SIZE
    # qr_img.height = IMG_DISPLAY_SIZE
    # qr_img.anchor = f"B{row}"
    # ws.add_image(qr_img)

    row += 1

# save workbook
wb.save(OUTPUT_PATH)
print(f"✅ Excel file created: {OUTPUT_PATH}")
