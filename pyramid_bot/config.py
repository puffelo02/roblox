"""All tunable values. Coordinates are for a 1920x1080 screen and get scaled
automatically to your real resolution."""

BASE_W, BASE_H = 1920, 1080

# Path to tesseract.exe (install from https://github.com/UB-Mannheim/tesseract/wiki)
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# --- Screen regions (x1, y1, x2, y2) at 1920x1080 ---
REGION_COUNTER = (660, 5, 1350, 85)       # "909 / 171,700"
REGION_CAPACITY = (60, 596, 420, 645)     # "Capacity: 1681/42705"
REGION_PROMPT = (760, 760, 1150, 890)     # "E  Block  Pick Up" box
REGION_WALKSPEED = (95, 505, 345, 535)    # "Walk Speed: 30/5501"
REGION_MENU_X = (1440, 190, 1530, 265)    # red X of the Upgrades menu
MENU_X_CLICK = (1482, 228)                # where to click to close it
# Areas covered by the HUD, ignored when looking for the signs
HUD_MASKS = [
    (0, 0, 1920, 70),        # Roblox top bar icons
    (640, 0, 1370, 152),     # block counter + robux buttons
    (1430, 55, 1920, 150),   # leaderboard
    (0, 300, 420, 1080),     # left stats
    (1700, 380, 1920, 1080), # right boosts
]

# --- Sign colors (HSV, OpenCV ranges: H 0-179, S/V 0-255) ---
# Red "BLOCKS" sign (red wraps around hue 0, so two ranges)
RED_RANGES = [((0, 150, 150), (8, 255, 255)), ((170, 150, 150), (179, 255, 255))]
# Bright green "PYRAMID" sign
GREEN_RANGES = [((45, 150, 150), (75, 255, 255))]
MIN_SIGN_PIXELS = 40
SIGN_NEAR_TOP_Y = 200     # sign last seen above this line...
SIGN_NEAR_MIN_PX = 400    # ...and this big (close, not far away)...
SIGN_GONE_CHECKS = 3      # ...then missing this many checks in a row = we're right under it
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
STEER_TOLERANCE = 0.03    # sign within +-3% of screen center = go straight
WALK_STEP_SEC = 0.25      # one walking step toward a sign
STEPS_REGION = (480, 300, 1440, 1000)  # where to count the pyramid's stacked step edges
PYRAMID_MIN_STEP_ROWS = 4  # this many stacked edges ahead = it's the pyramid (a wall has 1-2)
PYRAMID_MAX_STEP_ROWS = 15 # more than this is a menu / UI, not steps
WALL_CHECK_PLACE_SEC = 0.8 # hold E this long at a wall: counter going up = it's the pyramid
NEAR_SIGN_STEPS = 30      # steps straight ahead after a sign goes above the screen
PLOT_ENTER_SEC = 1.0      # walk forward this long after reaching the PYRAMID sign
TURN_SETTLE_SEC = 0.1     # let the character turn to face forward before comparing
BLOCKED_DIFF = 1.0        # view changes less than this after walking = blocked by a wall

# --- Placement: follow the green placement cube, E held the whole time ---
PLACE_HOLD_SEC = 0.6      # hold E this long when testing if placing works
CHAR_POS = (960, 550)     # where your character stands on screen
CHAR_BOX = (90, 110)      # half width/height around it to ignore when comparing frames
INDICATOR_HSV = ((36, 60, 90), (60, 255, 255))   # the green cube's color
INDICATOR_SEARCH = (480, 470, 1440, 1000)         # only look around the character
INDICATOR_MIN_AREA = 40
INDICATOR_MAX_AREA = 4000
BUILD_DUTY = 0.6          # share of time W is held while building (slower = blocks keep up)
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

# --- Corner anchoring + square spiral (see geometry.py) ---
# Set your Walk Speed to 30 in game (lower = more precise). If you change it,
# start once with:  python run.py --recalibrate
CALIBRATION_FILE = "calibration.json"   # measured values, kept between updates
LANE_BLOCKS = 5.0         # blocks between spiral passes (needs place range >= half of this + margin)
EDGE_INSET = 5.0          # outermost lap this far from the layer edge (room for small errors)
# corner by sight: where the step edges end on screen
CORNER_BAND = (380, 580)      # rows (1080p) where the step edges show (above the feet)
CORNER_LOW_BAND = 60          # px: edges this close to the lowest one count as the base
CORNER_MIN_ROWS = 3           # rows with a long edge needed to trust it
CORNER_MIN_LEN = 300          # an edge band must be this long to count as steps
CORNER_HUD_MASKS = [(0, 300, 430, 1080), (1740, 380, 1920, 700), (0, 0, 1920, 160),
                    (1760, 980, 1920, 1080), (0, 980, 340, 1080)]
CORNER_VISIBLE = (440, 1730)  # step ends outside this can't be seen (HUD / screen edge)
CORNER_BACKUP_SEC = 0.3      # step back this long when the steps can't be seen
OVERVIEW_BACKUP_SEC = 0.5     # step back this long at a time until the whole side is visible
OVERVIEW_MAX_BACKUPS = 20
OVERVIEW_MIN_BACKUPS = 2      # always back away at least this many steps before looking
CORNER_SLIDE_SEC = 0.25       # slide this long between looks
CORNER_TARGET_PX = 30          # stop with the steps ending this far past the character (= just inside the corner)
WALL_CHECK_SEC = 0.4      # slide along the base wall this long between checks
WALL_PROBE_SEC = 0.15     # press W this long to check the wall is still there
WALL_CREEP_SEC = 0.04     # small steps back toward the corner to find its exact edge
WALL_MAX_SEC = 60         # give up looking for the corner after this much sliding
EDGE_REGION = (480, 440, 1440, 1000)  # where to look for step edges (below the horizon)
EDGE_MAX_DEG = 20         # only near-horizontal lines count as edges
EDGE_MIN_TOTAL_PX = 400   # total length of edge lines needed to trust the angle
ALIGN_OK_DEG = 0.7        # edges within this angle = camera is square
ALIGN_GAIN = 0.6          # how much of the measured error to correct per try
ALIGN_MAX_ITER = 8
ALIGN_ON_PYRAMID_MAX_DEG = 6  # on top, only trust small corrections
TURN_CAL_MAX_SEC = 12     # longest camera spin when measuring a full turn
REANCHOR_EXTRA = 12       # walk this many blocks past the estimated edge when going down
MAX_MIDDLE_RESTARTS = 12  # times in a row to go back to the middle before giving up the trip
LOST_SEC = 8              # nothing placed, no cube, layer far from done = lost
EDGE_LAP_INSETS = (2.5, 4.0)  # laps this far from the edge to pick up missed blocks
CLEANUP_SEC = 60          # follow the cube this long when a layer has a few missed spots
CLEANUP_BELOW = 0.12      # under 12% missing (all near the edges): edge laps + cube

# --- Top-down position (camera looking straight down on the pyramid) ---
STRIP_DARK_RATIO = 0.82   # darker than this share of the top's brightness = edge/strip
STRIP_HUD_MASKS = [(0, 330, 345, 740), (1740, 390, 1920, 680), (640, 0, 1370, 150),
                   (1420, 40, 1920, 150), (0, 0, 380, 60), (1780, 990, 1920, 1080),
                   (0, 990, 340, 1080), (1840, 0, 1920, 60)]
STRIP_BAND = 60           # px around the character's row/column to look for strips
STRIP_FILL = 0.3          # share of dark pixels for a column/row to count as strip
STRIP_BAND_GAP = 220      # check edges this far above/below (left/right) of the character too
STRIP_AGREE_PX = 90       # the checks must agree within this (a straight edge; slanted a bit)
STRIP_SKIP_PX = 160       # ignore this close to the character (its shadow)
STRIP_MIN_PX = 28         # strip must be at least this wide
PX_PER_BLOCK = 12.8       # top-down scale at full zoom-out (re-measured when possible)
TILT_DRAG_PX = 700        # right-drag this far down to look straight down
UNTILT_DRAG_PX = 420      # drag back up this far for the normal view
ZOOM_OUT_SEC = 1.5        # hold O to zoom out fully
EDGE_TRUST_BLOCKS = 8     # only trust edges seen this close (far ones were shadows/signs)
CORNER_WALK_MAX_STEPS = 120  # steps toward the left/bottom edge before giving up
BASE_OFFSET_BLOCKS = 0    # blocks between the strip's inner edge and the pyramid base

# --- Loop ---
PICKUP_STALL_SEC = 12      # capacity not rising this long = step to a fresh spot in the pit
PICKUP_TIMEOUT_SEC = 300   # absolute safety limit
TRAVEL_TIMEOUT_SEC = 40
CAPACITY_FULL_RATIO = 0.995
NEAR_FULL_RATIO = 0.95     # backup rule: above 95% and no longer rising...
FULL_FALLBACK_SEC = 4      # ...for this long = treat as full
EMPTY_BELOW = 10           # fewer blocks than this left = go refill
JUMP_HOLD_SEC = 0.15       # Roblox misses very short taps, so hold Space a bit
JUMP_FORWARD_SEC = 0.6     # W time of one forward jump (0.05 + Space + 0.4 landing)
MAX_CLIMB_JUMPS = 40
CLIMB_STEP_SEC = 0.25      # walk this long between blocked-checks while climbing
CLIMB_FREE_STEPS = 3       # this many unblocked steps in a row = we're on the flat top

# --- Hotkeys ---
STOP_KEY = "f8"
PAUSE_KEY = "f7"

# --- Debug ---
DEBUG_DIR = "debug"
SAVE_SCREENSHOTS = True

# walking to the middle from above
MIDDLE_MAX_STEPS = 25     # pictures/steps at most
MIDDLE_TOL = 2.0          # blocks: close enough to the middle
MIDDLE_STEP_BLOCKS = 12   # longest step between two pictures
EDGE_HIT_BLOCKS = 7.0     # an edge this close = "hit the edge": back to the middle
EDGE_WATCH_BLOCKS = 15   # spiral legs ending this close to the edge watch for it
# the PYRAMID sign seen from above hangs over the middle: standing right under
# its "A" = standing in the middle. Sign centre relative to the character:
SIGN_MIDDLE_OFFSET = (2, -50)
SIGN_TOL = 0.6            # blocks
SIGN_TOP_MIN_W = 120      # px: narrower green things are not the sign
SIGN_TRUST_PX = 330       # only fix the position from the sign when it's this close to its spot
CUBE_TOP_MIN_AREA = 25    # px: the green cube looks small from above
CUBE_TOP_UNDER_PX = 18   # a cube this close is the one under our feet
ARRIVE_BLOCKS = 0.5       # a leg is done this close to its end (seen from the sign)
WALL_SIGN_FAR_PX = 400   # pyramid sign smaller than this (and low on screen) = still far away
WALL_SIGN_FAR_Y = 200
MIDDLE_BLIND_STEPS = 8    # after climbing: walk ahead (5 blocks) up to this many times until the sign shows
TOP_ALIGN_OK_DEG = 1.5   # top view: edges this close to level = camera square
FAR_SIGN_MIN_PIXELS = 12  # the PYRAMID sign from far away (tiny thin text in the sky)
STRAFE_GAIN = 1.2         # sidestep seconds per unit of sign offset (-1..1) on the way to the pyramid
STRAFE_MAX_SEC = 0.3
FACE_SIGN_OK = 0.12       # sign this close to the screen centre = facing it
FAR_SIGN_HSV = ((40, 60, 45), (80, 255, 255))  # sign green incl. the dark letter outline
FAR_SIGN_Y = (160, 380)   # far away the sign floats just above the horizon
FAR_SIGN_W = (25, 160)    # px wide
WALL_STEP_MIN_LEN = 300   # px: step lines at least this long (the leaderboard/sand block have short ones)
WALL_MIN_STEP_ROWS = 3    # this many long stacked step lines ahead = the pyramid
WALL_MAX_STEP_ROWS = 40   # a tall pyramid close up shows many steps
APPROACH_MAX_STEPS = 60   # on top: walking steps toward the sign at most
APPROACH_STEP_SEC = 0.15  # one step (normal camera)
APPROACH_HIGH_Y = 260     # sign seen above this line = close; then it leaves the screen
APPROACH_MAX_MISSING = 6
APPROACH_SHORT_BLOCKS = 8  # stop this many blocks before the middle (then line up from the top view)
APPROACH_STEP_BLOCKS = 5  # on top: one step toward the sign between top-view looks
APPROACH_MAX_LOOKS = 10
STAIRS_AHEAD_REGION = (300, 250, 1620, 540)  # above the character's feet = in front of it
STAIRS_MIN_LEN = 300
STAIRS_MIN_ROWS = 2       # this many long step lines ahead = stairs, keep jumping
CLIMB_MAX_JUMPS = 80
STAIRS_TOP_MIN_LINES = 5  # top view: this many stair lines on one side = the pyramid is that way
PITCH_SEARCH_TRIES = 4    # tilt the camera up this many times looking for a sign
PITCH_SEARCH_PX = 120     # right-drag per tilt step
CLIMB_TEST_STEP_SEC = 0.25  # walk test while climbing: on stairs this always hits the next step
MIDDLE_GAIN = 0.6         # move this share of the way to the A per step (no overshooting)
FELL_OFF_CHECKS = 3       # sign missing this many checks in a row before looking for stairs
PYRAMID_AHEAD_ROWS = 6    # stair lines straight ahead = the pyramid is right there
WALK_INTO_MAX_STEPS = 20
BASEPLATE_MAX_SAT = 100   # grey stone: low colour saturation
BASEPLATE_SHARE = 0.75    # this much of the ground around us is grey stone = on the baseplate
EDGE_INSET_PER_BLOCK = 0.10  # outer lap: + this x layer width further from the edge (126 wide: +10)
EDGE_LAP_PER_BLOCK = 0.12   # edge-cleanup laps likewise (126 wide: +8)
JUMP_EVERY_MOVES = 3      # hop every this many moves while searching/centring (gets unstuck)
APPROACH_BACK_STEPS = 12  # looking down: steps back toward a sign that went over our head
LOST_SEC_LATE = 20        # late in a layer (edge laps / cleanup): nothing placed this long = fell off
