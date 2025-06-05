# Event config
EVENT = "oktoberfest2025_prd"
N_TICKETS = 1800
BASE_PATH = f"events/{EVENT}"
BACKUP_ROOT = "bkp"

# Netork config
HOST = "138.199.223.81" # Hetzner Server
# HOST = "192.168.1.4" # Internet Landstraße
# HOST = "172.20.10.8:8000" # iPhone Hotspot
PORT = "8000"
URL = "tickets.danielnetzl.com" # without www.
# URL = HOST + ":" + PORT # Hosted locally

# Page size (in mm)
PAGE_WIDTH          = 150
PAGE_HEIGHT         = 70
MERGE_PAGE_INDEX    = 1

# Coordinates for QR placement on the right side
MARGIN_RIGHT    = 10
MARGIN_BOTTOM   = 0
QR_SIZE         = 15