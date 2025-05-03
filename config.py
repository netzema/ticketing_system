# Event config
EVENT = "test"
N_TICKETS = 10
BASE_PATH = f"events/{EVENT}"
BACKUP_ROOT = "bkp"

# Netork config
HOST = "192.168.1.18" # Internet Landstraße 
# HOST = "172.20.10.8:8000" # iPhone Hotspot
PORT = "8000"
URL = HOST + ":" + PORT

# Page size (in mm)
PAGE_WIDTH = 216
PAGE_HEIGHT = 70

# Coordinates for QR placement on the right side
MARGIN_RIGHT = 10
QR_SIZE      = 30