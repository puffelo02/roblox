"""All tunable values. Coordinates are for a 1920x1080 screen and get scaled
automatically to your real resolution."""

BASE_W, BASE_H = 1920, 1080

# Path to tesseract.exe (install from https://github.com/UB-Mannheim/tesseract/wiki)
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# --- Screen regions (x1, y1, x2, y2) at 1920x1080 ---
REGION_COUNTER = (660, 5, 1350, 85)       # "909 / 171,700"
REGION_CAPACITY = (60, 596, 420, 645)     # "Capacity: 1681/42705"
REGION_PROMPT = (760, 760, 1150, 890)     # "E  Block  Pick Up" box
REGION_MENU_X = (1440, 190, 1530, 265)    # red X of the Upgrades menu
MENU_X_CLICK = (1482, 228)                # where to click to close it
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
MIN_SIGN_PIXELS = 40
SIGN_MAX_Y = 360               # signs float above the horizon; ignore anything lower
SIGN_MIN_ASPECT = 3.5          # sign text is wide and thin (gym gear is chunky)
PYRAMID_PANEL_HSV = ((30, 25, 100), (75, 150, 230))  # muted green panel behind PYRAMID
PYRAMID_PANEL_MIN = 0.25       # share of panel color around the text to count as the real sign          # fewer matching pixels = sign not visible
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
BLOCKED_DIFF = 1.0        # view changes less than this after walking = blocked by a wall

# --- Placement: follow the green placement cube, E held the whole time ---
PLACE_HOLD_SEC = 0.6      # hold E this long when testing if placing works
CHAR_POS = (960, 550)     # where your character stands on screen
INDICATOR_HSV = ((36, 60, 90), (60, 255, 255))   # the green cube's color
INDICATOR_SEARCH = (480, 470, 1440, 1000)         # only look around the character
INDICATOR_MIN_AREA = 40
INDICATOR_MAX_AREA = 4000
BUILD_TICK_SEC = 0.1      # how often the screen is checked while building
COUNTER_EVERY_SEC = 1.0   # counter OCR is slow: only read it this often
CAPACITY_EVERY_SEC = 3.0
STEER_DEADZONE_DEG = 15   # cube this close to straight ahead = don't turn
STEER_MAX_SEC = 0.12      # longest camera turn per check (keeps turns smooth)
SPIRAL_TURN_START = 0.02  # camera turn per check with no cube (big circle)...
SPIRAL_TURN_GROW = 0.0005 # ...getting a bit tighter every check
SPIRAL_TURN_MAX = 0.06
FALL_SEC = 3.0            # no cube and nothing placed this long = fell off, turn back
MAX_RECOVERIES = 3        # turn-back attempts before walking to the PYRAMID sign

# --- Loop ---
PICKUP_STALL_SEC = 12      # capacity not rising this long = step to a fresh spot in the pit
PICKUP_TIMEOUT_SEC = 300   # absolute safety limit
TRAVEL_TIMEOUT_SEC = 40
CAPACITY_FULL_RATIO = 0.995
NEAR_FULL_RATIO = 0.95     # backup rule: above 95% and no longer rising...
FULL_FALLBACK_SEC = 4      # ...for this long = treat as full
EMPTY_BELOW = 10           # fewer blocks than this left = go refill
JUMP_HOLD_SEC = 0.15       # Roblox misses very short taps, so hold Space a bit
MAX_CLIMB_JUMPS = 40
CLIMB_STEP_SEC = 0.25      # walk this long between blocked-checks while climbing
CLIMB_FREE_STEPS = 3       # this many unblocked steps in a row = we're on the flat top

# --- Hotkeys ---
STOP_KEY = "f8"
PAUSE_KEY = "f7"

# --- Debug ---
DEBUG_DIR = "debug"
SAVE_SCREENSHOTS = True
