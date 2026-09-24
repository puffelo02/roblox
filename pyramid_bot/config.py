"""All tunable values. Coordinates are for a 1920x1080 screen and get scaled
automatically to your real resolution."""

BASE_W, BASE_H = 1920, 1080

# Path to tesseract.exe (install from https://github.com/UB-Mannheim/tesseract/wiki)
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# --- Screen regions (x1, y1, x2, y2) at 1920x1080 ---
REGION_COUNTER = (660, 5, 1350, 85)       # "909 / 171,700"
REGION_CAPACITY = (60, 590, 420, 645)     # "Capacity: 1681/42705"
REGION_PROMPT = (760, 760, 1150, 890)     # "E  Block  Pick Up" box
# Areas covered by the HUD, ignored when looking for the signs
HUD_MASKS = [
    (0, 0, 1920, 160),       # top bar + robux buttons
    (0, 300, 420, 1080),     # left stats
    (1700, 380, 1920, 1080), # right boosts
]

# --- Sign colors (HSV, OpenCV ranges: H 0-179, S/V 0-255) ---
# Red "BLOCKS" sign (red wraps around hue 0, so two ranges)
RED_RANGES = [((0, 150, 150), (8, 255, 255)), ((170, 150, 150), (179, 255, 255))]
# Bright green "PYRAMID" sign
GREEN_RANGES = [((45, 150, 150), (75, 255, 255))]
MIN_SIGN_PIXELS = 150          # fewer matching pixels = sign not visible
PYRAMID_SIGN_ARRIVED_PIXELS = 8000  # sign this big on screen = we're at the plot

# --- Movement timings (seconds) ---
# TIP: lower your Walk Speed in game (the pencil icon) to something like 100-200.
# At 1800 the character moves too far per key tap to control precisely.
TURN_90_SEC = 0.45        # how long to hold an arrow key to turn the camera 90 degrees
TURN_180_SEC = 0.90
STEER_TAP_SEC = 0.05      # small correction turn while walking to a sign
STEER_TOLERANCE = 0.08    # sign within +-8% of screen center = go straight
WALK_STEP_SEC = 0.25      # one walking step toward a sign
PLOT_ENTER_SEC = 1.0      # walk forward this long after reaching the PYRAMID sign

# --- Placement pattern ---
PLACE_HOLD_SEC = 0.6      # hold E this long at each spot
PATTERN_STEP_SEC = 0.15   # W tap between spots along a side
SIDE_STEPS_START = 40     # spots along one side for the outer ring
RING_SHRINK_STEPS = 2     # each ring inward is this many steps shorter per side
STALL_SPOTS_FOR_SKIP = 6  # this many spots in a row with no progress = skip ahead
STALL_RINGS_FOR_FALL = 2  # full ring(s) with no progress = assume we fell off

# --- Loop ---
PICKUP_TIMEOUT_SEC = 60
TRAVEL_TIMEOUT_SEC = 40
CAPACITY_FULL_RATIO = 0.98

# --- Hotkeys ---
STOP_KEY = "f8"
PAUSE_KEY = "f7"

# --- Debug ---
DEBUG_DIR = "debug"
SAVE_SCREENSHOTS = True
