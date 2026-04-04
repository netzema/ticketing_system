# event config
EVENT = "oktoberfest2026_prd"
N_TICKETS = 1500
BASE_PATH = f"events/{EVENT}"
BACKUP_ROOT = "bkp"

# netork config
HOST = "91.98.87.80" # Hetzner Server
# HOST = "192.168.1.4" # Internet home
# HOST = "172.20.10.8:8000" # iPhone Hotspot
PORT = "8000"
URL = "jugend.netzldatasolutions.at" # without www.
# URL = HOST + ":" + PORT # Hosted locally

# page size (in mm)
PAGE_WIDTH          = 150
PAGE_HEIGHT         = 70
MERGE_PAGE_INDEX    = 1

# coordinates for QR placement on the right side
MARGIN_RIGHT    = 10
MARGIN_BOTTOM   = 0
QR_SIZE         = 15