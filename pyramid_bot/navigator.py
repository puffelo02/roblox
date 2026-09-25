"""Corner anchoring + square spiral building.

1. Anchor: at the base wall, square the camera to the wall (step edges
   horizontal), slide right until the wall ends (= corner), step back in and
   climb straight up. Now we know where we are.
2. Build: walk a square spiral on the layer being built, corner to corner and
   tighter toward the middle; the next layer goes from the middle back out to
   the corners, and so on. Position is tracked by walking time
   (seconds per block, measured once) and 90 degree camera turns.
"""
import json
import logging
import time

from . import config as C
from . import geometry as G

log = logging.getLogger("bot")


class Navigator:
    def __init__(self, bot):
        self.b = bot
        self.v = bot.v
        self.c = bot.c
        self.cal = self._load_cal()
        self.x = self.y = 0.0
        self.heading = 0  # 0 = +y (into the pyramid), 90 = +x (right), 180, 270
        self.base = None
        self.speed_factor = 1.0
        self.top_view = False
        self.completed = 0

    # ---------- calibration ----------
    @staticmethod
    def _load_cal():
        try:
            with open(C.CALIBRATION_FILE) as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _save_cal(self):
        with open(C.CALIBRATION_FILE, "w") as f:
            json.dump(self.cal, f, indent=2)
        log.info("calibration saved: %s", self.cal)

    @property
    def turn90(self):
        return self.cal.get("turn90", C.TURN_90_SEC)

    @property
    def spb(self):
        return self.cal.get("sec_per_block")

    def calibrate_turn(self):
        """Spin the camera right and time how long until the view looks the same
        again (= 360 degrees). Then turn back to where we started."""
        log.info("measuring camera turn speed (full spin)...")
        start = self.v.scene_small(self.v.grab())
        t0 = time.time()
        maxd = 0.0
        best = None  # (diff, time)
        self.c.down("right")
        try:
            while time.time() - t0 < C.TURN_CAL_MAX_SEC:
                self.c.check()
                d = self.v.scene_diff(start, self.v.scene_small(self.v.grab()))
                t = time.time() - t0
                maxd = max(maxd, d)
                if t > 0.5 and maxd > 3 and d < 0.35 * maxd:
                    if best is None or d < best[0]:
                        best = (d, t)
                if best and d > best[0] + 0.2 * maxd:
                    break  # passed the matching point
        finally:
            self.c.up("right")
        stop = time.time() - t0
        if not best:
            log.warning("couldn't measure the camera turn, using TURN_90_SEC=%.2f", self.turn90)
            return
        t360 = best[1]
        self.c.turn_left(max(0.0, stop - t360))  # undo the overshoot
        self.cal["turn90"] = round(t360 / 4, 4)
        self._save_cal()

    # ---------- top-down view ----------
    def camera_top(self):
        """Look straight down and zoom all the way out."""
        if self.top_view:
            return
        self.c.right_drag(C.TILT_DRAG_PX)
        # full zoom-out the first time; after that it stays zoomed out
        self.c.hold("o", C.ZOOM_OUT_SEC if not getattr(self, "zoomed", False) else 0.3)
        self.zoomed = True
        self.c.sleep(0.2)
        self.top_view = True

    def leg_scale(self, key):
        return getattr(self, "leg_scales", {}).get(key, 1.0)

    def learn_leg(self, key, planned, actual):
        """planned blocks vs actual blocks walked on a leg in direction key."""
        if actual <= 0:
            return
        scales = getattr(self, "leg_scales", {})
        old = scales.get(key, 1.0)
        ratio = actual / planned  # >1 = we overshoot: walk shorter next time
        new = min(1.5, max(0.6, old / (ratio ** 0.5)))
        scales[key] = new
        self.leg_scales = scales
        if abs(new - old) > 0.03:
            log.info("legs going %s: walked %.0f of %.0f blocks, now x%.2f", key.upper(), actual, planned, new)

    def spiral_inset(self, side):
        """How far in from the edge the outer spiral lap stays: more on big
        layers (long walks out there drift further)."""
        return C.EDGE_INSET + C.EDGE_INSET_PER_BLOCK * side

    def lap_inset(self, side, i):
        return C.EDGE_LAP_INSETS[i] + C.EDGE_LAP_PER_BLOCK * side

    def reset_camera(self):
        """Known normal view whatever state the camera was left in: tilt all the
        way down (that stops at straight down), then back up the fixed amount."""
        self.c.right_drag(C.TILT_DRAG_PX + 300)
        self.c.sleep(0.1)
        self.c.right_drag(-C.UNTILT_DRAG_PX)
        self.top_view = False
        log.info("camera reset to the normal view")

    def camera_normal(self):
        if not self.top_view:
            return
        self.c.right_drag(-C.UNTILT_DRAG_PX)
        self.top_view = False

    @property
    def ppb(self):
        return self.cal.get("px_per_block", C.PX_PER_BLOCK)

    def _screen_dirs(self):
        """World direction (dx, dy) of screen right and screen up for our heading."""
        h = self.heading % 360
        up = {0: (0, 1), 90: (1, 0), 180: (0, -1), 270: (-1, 0)}[h]
        right = (up[1], -up[0])
        return right, up

    def locate(self, completed):
        """Measure our position from the top layer's edges seen from above.
        Fixes self.x / self.y for every axis an edge is visible on. Returns the
        number of axes fixed."""
        strips = self.near_strips()
        if not strips:
            return 0
        lo, hi = completed - 1, self.base - (completed - 1)  # top finished layer
        right, up = self._screen_dirs()
        cx, cy = C.CHAR_POS
        fixed = set()
        for side, pos in strips.items():
            if side == "left":
                d, dist = (-right[0], -right[1]), (cx - pos) / self.ppb
            elif side == "right":
                d, dist = right, (pos - cx) / self.ppb
            elif side == "top":
                d, dist = up, (cy - pos) / self.ppb
            else:
                d, dist = (-up[0], -up[1]), (pos - cy) / self.ppb
            if d[0]:
                self.x = hi - dist if d[0] > 0 else lo + dist
                fixed.add("x")
            else:
                self.y = hi - dist if d[1] > 0 else lo + dist
                fixed.add("y")
        if fixed:
            log.info("seen from above: %s -> at (%.1f, %.1f)",
                     ", ".join("%s %d" % kv for kv in strips.items()), self.x, self.y)
        return len(fixed)

    def near_strips(self):
        """Edges seen from above, keeping only close ones (far detections were
        often shadows / signs, not the pyramid's edge)."""
        cx, cy = C.CHAR_POS
        lim = C.EDGE_TRUST_BLOCKS * self.ppb
        out = {}
        for side, pos in self.v.border_strips(self.v.grab()).items():
            d = abs(pos - (cx if side in ("left", "right") else cy))
            if d <= lim:
                out[side] = pos
        return out

    def find_edges_from_above(self):
        """Get one edge per axis close enough to measure: bottom (we came up that
        side) for y, then walk right until the right edge shows for x."""
        step = 0.25 * self.speed_factor
        got = set()
        for key, side, axis in (("s", "bottom", "y"), ("d", "right", "x")):
            for _ in range(C.CORNER_WALK_MAX_STEPS):
                self.c.check()
                near = self.near_strips()
                if side in near or (axis == "y" and "top" in near) or \
                        (axis == "x" and "left" in near):
                    got.add(axis)
                    break
                self.c.hold(key, step)
        self.locate(self.completed)
        return len(got)

    def go_to_corner_from_above(self):
        """Walk left until the left edge is close, then down until the bottom edge
        is close: the L of the bottom-left corner."""
        step = 0.25 * self.speed_factor
        for key, side in (("a", "left"), ("s", "bottom")):
            for _ in range(C.CORNER_WALK_MAX_STEPS):
                self.c.check()
                if side in self.near_strips():
                    break
                self.c.hold(key, step)
            else:
                log.warning("no %s edge found walking %s", side, key)
                return False
        return True

    def calibrate_scale(self):
        """Pixels per block from above: slide a known distance and see how far a
        left/right edge moves on screen."""
        s1 = self.v.border_strips(self.v.grab())
        side = "left" if "left" in s1 else "right" if "right" in s1 else None
        if side is None or not self.spb:
            return
        blocks = 4
        self.c.hold("d", blocks * self.spb)
        self.c.sleep(0.15)
        s2 = self.v.border_strips(self.v.grab())
        self.c.hold("a", blocks * self.spb)
        if side in s2:
            ppb = abs(s2[side] - s1[side]) / blocks
            if 4 < ppb < 60:
                self.cal["px_per_block"] = round(ppb, 2)
                self._save_cal()

    # ---------- camera / heading ----------
    def align(self, max_deg=90):
        """Turn the camera until the step edges ahead are horizontal."""
        sign = 1
        prev = None
        for _ in range(C.ALIGN_MAX_ITER):
            a = self.v.edge_angle(self.v.grab())
            if a is None:
                return False
            if abs(a) > max_deg:
                return False
            if abs(a) < C.ALIGN_OK_DEG:
                return True
            if prev is not None and abs(a) > abs(prev):
                sign = -sign  # made it worse: the other way round
            sec = min(0.15, abs(a) / 90 * self.turn90 * C.ALIGN_GAIN)
            if a * sign > 0:
                self.c.turn_right(sec)
            else:
                self.c.turn_left(sec)
            prev = a
        return True

    def face(self, heading):
        delta = (heading - self.heading + 540) % 360 - 180
        if delta > 0:
            self.c.turn_right(delta / 90 * self.turn90)
        elif delta < 0:
            self.c.turn_left(-delta / 90 * self.turn90)
        self.heading = heading % 360
        if delta:
            self.c.sleep(0.1)
            if self.top_view:
                self.locate(self.completed)
            else:
                self.align(C.ALIGN_ON_PYRAMID_MAX_DEG)

    # ---------- anchoring ----------
    def slide_to_corner(self, key):
        """Slide along the base until the end of the step edges is right in front of
        the character (= corner), by looking at where the steps end on screen.
        Returns seconds slid, or None if the steps can't be seen (then the caller
        falls back to feeling for the wall)."""
        cx = C.CHAR_POS[0]
        target = cx + C.CORNER_TARGET_PX if key == "d" else cx - C.CORNER_TARGET_PX
        slid = 0.0
        unseen = 0
        backed = 0.0
        last_end = None
        while slid < C.WALL_MAX_SEC:
            self.c.check()
            img = self.v.grab()
            span = self.v.steps_extent(img)
            # the pyramid's steps must be in front of the character
            if span is not None and not (span[0] < cx + 100 and span[1] > cx - 100):
                span = None
            if span is None:
                unseen += 1
                self.v.save(img, "no_steps")
                if unseen >= 4:
                    log.warning("can't see the pyramid's steps to find the corner")
                    if slid:
                        self.c.hold("a" if key == "d" else "d", slid)  # back to the start
                    self.c.hold("w", backed)  # and back against the wall
                    return None
                # too close to the wall to see the steps? step back and look again
                self.c.hold("s", C.CORNER_BACKUP_SEC)
                backed += C.CORNER_BACKUP_SEC
                continue
            unseen = 0
            end = span[1] if key == "d" else span[0]
            visible = C.CORNER_VISIBLE[0] < end < C.CORNER_VISIBLE[1]
            # at or past the character counts (a slide can skip over the exact spot);
            # only an end hidden on the far side is unknown
            reached = end <= target and end < C.CORNER_VISIBLE[1] if key == "d" \
                else end >= target and end > C.CORNER_VISIBLE[0]
            if not visible and last_end is not None and abs(last_end - target) < 400:
                log.info("steps' end slipped past the character: taking that as the corner")
                reached = True
            last_end = end if visible else None
            if reached:
                log.info("corner in front of us (steps end at x=%d), slid %.2fs", end, slid)
                self.v.save(img, "corner")
                if backed:
                    self.c.hold("w", backed + 0.3)  # back against the base wall
                return slid
            # far away: bigger slides; close: small ones so we don't overshoot
            dist_px = abs(end - target) if visible else 800
            sec = (C.CORNER_SLIDE_SEC if dist_px > 250 else C.CORNER_SLIDE_SEC / 3) * self.speed_factor
            self.c.hold(key, sec)
            slid += sec
        log.warning("no corner found along the wall")
        return None

    def locate_by_overview(self):
        """Back away from the base until both ends of the side are on screen, then
        work out where we stand along it from that one picture. Returns our x in
        blocks (0 = left corner), or None. Walks back to the wall afterwards."""
        backed = 0.0
        x = None
        prev = None
        for i in range(C.OVERVIEW_MAX_BACKUPS):
            self.c.check()
            if self.b.close_menu():
                continue
            if i >= C.OVERVIEW_MIN_BACKUPS:
                img = self.v.grab()
                span = self.v.steps_extent(img)
                lo, hi = C.CORNER_VISIBLE
                ok = (span and lo + 10 < span[0] and span[1] < hi - 10
                      and span[1] - span[0] > 200)
                if ok:
                    frac = (C.CHAR_POS[0] - span[0]) / (span[1] - span[0])
                    log.info("overview try %d: side spans x=%d..%d, we're at %.0f%%",
                             i, span[0], span[1], frac * 100)
                    self.v.save(img, "overview")
                    # two pictures in a row must agree before we trust it
                    if prev is not None and abs(frac - prev) < 0.05:
                        x = (frac + prev) / 2 * self.base
                        log.info("overview agreed: block %.1f of %d", x, self.base)
                        break
                    prev = frac
                else:
                    prev = None
            self.c.hold("s", C.OVERVIEW_BACKUP_SEC * self.speed_factor)
            backed += C.OVERVIEW_BACKUP_SEC * self.speed_factor
        # back to the base wall
        self.c.hold("w", backed)
        for _ in range(20):
            if self.b.walk_step_blocked(C.CLIMB_STEP_SEC * self.speed_factor):
                break
        if x is None:
            log.warning("couldn't see both ends of the side")
        return x

    def find_corner(self, key):
        """Corner by sight first, feeling for the wall's end as a fallback."""
        slid = self.slide_to_corner(key)
        if slid is None:
            slid = self.follow_wall(key)
        return slid

    def follow_wall(self, key):
        """Slide sideways along the base wall until it ends. Returns seconds slid,
        or None if no corner was found."""
        other = "a" if key == "d" else "d"
        slid = 0.0
        while slid < C.WALL_MAX_SEC:
            self.c.hold(key, C.WALL_CHECK_SEC)
            slid += C.WALL_CHECK_SEC
            t0 = time.time()
            if self.b.walk_step_blocked(C.WALL_PROBE_SEC):
                continue
            # W moved us: past the corner, or we had drifted away from the wall
            if self.b.walk_step_blocked(0.3):
                continue  # back against the wall: it was drift
            log.info("wall ended: corner found, stepping back to its edge")
            self.c.hold("s", time.time() - t0)  # undo exactly the forward probing
            # creep back toward the wall until it's in front of us again
            back = 0.0
            for _ in range(int(C.WALL_CHECK_SEC * 2 / C.WALL_CREEP_SEC) + 2):
                self.c.hold(other, C.WALL_CREEP_SEC)
                back += C.WALL_CREEP_SEC
                t0 = time.time()
                if self.b.walk_step_blocked(C.WALL_PROBE_SEC):
                    break
                self.c.hold("s", time.time() - t0)  # undo the probe
            else:
                # never touched the wall again: go back to about where it ended
                log.warning("couldn't find the corner's exact edge, estimating")
                self.c.hold(key, back - C.WALL_CHECK_SEC / 2)
                back = C.WALL_CHECK_SEC / 2
            log.info("slid %.2fs, crept back %.2fs", slid, back)
            return slid - back
        log.warning("no corner found along the wall")
        return None

    def climb_layers(self, n):
        """Jump straight up the steps. Returns seconds moved forward since the
        last step wall (the wall of the top layer is at y = n-1)."""
        jumps = 0
        # one forward jump per finished layer, whether or not a wall was "seen"
        # (the step check can miss low steps, which left it at the bottom)
        # short jumps at high walk speed so we don't fly far past the step
        landing = max(0.2, 0.4 * self.speed_factor)
        jump_w = 0.05 + C.JUMP_HOLD_SEC + landing
        for _ in range(n):
            self.c.check()
            self.c.jump_forward(landing)
            jumps += 1
        since_wall = jump_w
        # the layer being built may already be there: one more step at most.
        # No walking on afterwards (that made the position estimate wrong).
        for _ in range(2):
            if not self.b.walk_step_blocked(0.12):
                break
            self.c.jump_forward(landing)
            jumps += 1
        self.extra_steps = jumps - n
        log.info("climbed %d layers (%d jumps)", n, jumps)
        self.jumps = jumps
        return since_wall

    def climb_to_top(self):
        """Screenshot; stairs or an obstacle in front: jump up. Nothing in front:
        we're on top, stop."""
        clear = 0
        for jumps in range(C.CLIMB_MAX_JUMPS):
            self.c.check()
            img = self.v.grab()
            if self.b.close_menu(img):
                continue
            rows = self.v.stairs_ahead(img)
            if rows >= C.STAIRS_MIN_ROWS:
                clear = 0
                self.c.jump_forward(0.25)
                continue
            if self.b.walk_step_blocked(C.CLIMB_TEST_STEP_SEC):
                clear = 0
                self.c.jump_forward(0.25)  # something in the way
                continue
            clear += 1
            if clear >= 2:  # twice in a row: really flat ahead
                log.info("on top: no stairs or obstacle ahead (%d jumps)", jumps)
                return True
        log.warning("still stairs ahead after %d jumps", C.CLIMB_MAX_JUMPS)
        return False

    def check_walkspeed(self):
        """Time per block depends on Walk Speed: rescale if it changed."""
        ws = None
        for _ in range(3):
            ws = self.v.read_walkspeed(self.v.grab())
            if ws:
                break
        if not ws:
            return
        # older calibrations didn't store it: they were measured at 30
        old = self.cal.get("walkspeed", 30 if self.spb else None)
        if self.spb and old and old != ws:
            self.cal["sec_per_block"] = round(self.spb * old / ws, 5)
            log.info("walk speed changed %s -> %s: time per block now %.4fs", old, ws, self.spb)
        self.cal["walkspeed"] = ws
        self.speed_factor = 30 / ws  # slide steps scaled to speed (tuned at 30)
        self._save_cal()

    def go_middle(self, completed, blind=0, front=False, stairs=True):
        """Look down, walk away from whatever edges are in view until we stand in
        the middle (both axes centred, or no edge in view at all). No position
        bookkeeping to go wrong: every step is decided from a fresh picture."""
        half = (self.base - 2 * (completed - 1)) / 2  # top finished layer
        cx, cy = C.CHAR_POS
        prev = None
        no_sign = 0
        centred = False
        # never walk blind further than about half the layer (the middle)
        blind_left = min(blind, max(0, int((half - 4) / 5)))
        for i in range(C.MIDDLE_MAX_STEPS):
            self.c.check()
            if self.b.close_menu():
                continue
            img = self.v.grab()
            sign = self.v.sign_top(img)
            if sign is not None:
                # the sign hangs right over the middle: get under its "A"
                tx, ty = cx + C.SIGN_MIDDLE_OFFSET[0], cy + C.SIGN_MIDDLE_OFFSET[1]
                nx, ny = (sign[0] - tx) / self.ppb, (ty - sign[1]) / self.ppb
                log.info("to the middle: sign at (%d, %d) -> move x %+.1f, y %+.1f",
                         sign[0], sign[1], nx, ny)
                if abs(nx) <= C.SIGN_TOL and abs(ny) <= C.SIGN_TOL:
                    centred = True
                    break
                ax, d = ("x", nx) if abs(nx) >= abs(ny) else ("y", ny)
                key = ("d" if d > 0 else "a") if ax == "x" else ("w" if d > 0 else "s")
                self.move_step(key, max(0.05, min(abs(d) * C.MIDDLE_GAIN, C.MIDDLE_STEP_BLOCKS) * self.spb))
                prev = None
                no_sign = 0
                continue
            no_sign += 1
            if no_sign < C.FELL_OFF_CHECKS:
                self.c.sleep(0.2)  # the sign may just flicker: look again first
                continue
            side = self.v.stairs_side_top(img) if stairs else None
            if side is not None:
                # no sign in view but stairs next to us: we fell off. The
                # pyramid is where the stairs are: go that way, jumping up them
                if front and side in ("up", "down"):
                    side = "up"  # we came up the front: the top is always ahead
                if getattr(self, "pos_known", False):
                    mid = self.base / 2
                    want = {"up": self.y < mid, "down": self.y > mid,
                            "right": self.x < mid, "left": self.x > mid}[side]
                    if not want:
                        side = None  # stairs on both sides: go by where the middle is
            if side is not None:
                key = {"up": "w", "down": "s", "left": "a", "right": "d"}[side]
                log.info("fell off? stairs %s of us: climbing back with %s", side, key.upper())
                self.step_jump(key, C.JUMP_HOLD_SEC + 4 * self.spb)
                continue
            break  # no sign, no stairs: stop here and search for the sign by sight
        if centred or not getattr(self, "pos_known", False):
            self.x = self.y = self.base / 2
        if centred:
            self.pos_known = True  # the sign confirmed it
        else:
            log.info("couldn't confirm the middle with the sign")
        return centred

    def sign_pos(self, img):
        """Our (x, y) on the layer from the sign's spot on screen, or None."""
        sign = self.v.sign_top(img)
        if sign is None:
            return None
        tx = C.CHAR_POS[0] + C.SIGN_MIDDLE_OFFSET[0]
        ty = C.CHAR_POS[1] + C.SIGN_MIDDLE_OFFSET[1]
        if abs(sign[0] - tx) > C.SIGN_TRUST_PX or abs(sign[1] - ty) > C.SIGN_TRUST_PX:
            return None
        mid = self.base / 2
        return mid - (sign[0] - tx) / self.ppb, mid + (sign[1] - ty) / self.ppb

    def locate_by_sign(self, img=None):
        """The sign hangs over the middle: where it is on screen tells exactly
        where we are. Fixes self.x / self.y. Returns True if the sign was seen."""
        if img is None:
            img = self.v.grab()
        sign = self.v.sign_top(img)
        if sign is None:
            return False
        tx = C.CHAR_POS[0] + C.SIGN_MIDDLE_OFFSET[0]
        ty = C.CHAR_POS[1] + C.SIGN_MIDDLE_OFFSET[1]
        mid = self.base / 2
        if abs(sign[0] - tx) > C.SIGN_TRUST_PX or abs(sign[1] - ty) > C.SIGN_TRUST_PX:
            return False  # far from the sign the view is too slanted to trust
        x, y = mid - (sign[0] - tx) / self.ppb, mid + (sign[1] - ty) / self.ppb
        if not (0 <= x <= self.base and 0 <= y <= self.base):
            return False  # nonsense: not a top-down view of our sign
        if abs(x - self.x) > 1 or abs(y - self.y) > 1:
            log.info("sign says (%.1f, %.1f), thought (%.1f, %.1f)", x, y, self.x, self.y)
        self.x, self.y = x, y
        return True

    def cleanup_top(self, state, lo, hi):
        """Last few blocks of a layer, still looking straight down: walk to the
        green cube whenever one is in view, else keep lapping near the edges.
        Returns "layer" when the layer is finished, or "empty"/"done"/"lost"."""
        laps = G.ring(lo, hi, self.lap_inset(hi - lo, 1), (self.x, self.y))
        li = 0
        end = time.time() + C.CLEANUP_SEC
        start_layer = G.layer_info(state["last_n"], self.base)[0]
        state["last_rise"] = time.time()
        while time.time() < end:
            self.c.check()
            if time.time() - state["last_rise"] > C.LOST_SEC_LATE:
                log.info("cleanup: nothing placed for %ds: fell off?", C.LOST_SEC_LATE)
                return "lost"
            img = self.v.grab()
            if self.b.close_menu(img):
                self.c.down("e")
                continue
            cur = self.b.counter(img)
            if cur:
                if cur[0] > state["last_n"]:
                    state["last_n"] = cur[0]
                    state["last_rise"] = time.time()
                    end = max(end, time.time() + 8)  # still placing: keep going
                if G.layer_info(cur[0], self.base)[0] > start_layer:
                    log.info("layer finished!")
                    state["layer"] = G.layer_info(cur[0], self.base)[0]
                    return "layer"
            if self.b.pyramid_done():
                return "done"
            if self.b.empty():
                return "empty"
            cube = self.v.cube_top(img)
            if cube is not None:
                dx, dy = cube[0] / self.ppb, -cube[1] / self.ppb  # blocks, +y = up
                ax, d = ("x", dx) if abs(dx) >= abs(dy) else ("y", dy)
                key = ("d" if d > 0 else "a") if ax == "x" else ("w" if d > 0 else "s")
                self.c.hold(key, max(0.3, min(abs(d), 6)) * self.spb)
                continue
            # nothing in view: next point along a lap near the edges
            tx, ty = laps[li % len(laps)]
            li += 1
            status = self.walk_to(tx, ty, state, check_lost=False, watch_edge=True)
            if status in ("empty", "done", "layer"):
                return status
        log.info("couldn't finish the layer's last blocks")
        return "lost"

    def measure_scale(self, img, completed):
        """Standing in the middle, the left and right edges of the finished layer
        below are side blocks apart: that gives pixels per block. The time per
        block is scaled along (seconds per pixel was measured right)."""
        st = self.v.border_strips(img)
        if "left" not in st or "right" not in st:
            return
        side = self.base - 2 * (completed - 1)
        cx = C.CHAR_POS[0]
        if abs((st["left"] + st["right"]) / 2 - cx) > 3 * self.ppb:
            return  # not symmetric around us: not both outer edges
        ppb = (st["right"] - st["left"]) / side
        old = self.ppb
        if abs(ppb - old) / old < 0.05:
            return
        self.cal["px_per_block"] = round(float(ppb), 2)
        if self.spb:
            self.cal["sec_per_block"] = round(float(self.spb * ppb / old), 5)
        log.info("scale from the edges: %d px for %d blocks = %.1f px/block (was %.1f), "
                 "%.4fs per block", st["right"] - st["left"], side, ppb, old, self.spb)
        self._save_cal()

    def step_jump(self, key, sec):
        """Walk `sec` seconds, jumping at the start: climbs a one-block step
        (e.g. up onto a new layer) and does nothing harmful on flat ground."""
        self.c.down(key)
        self.c.hold("space", C.JUMP_HOLD_SEC)
        self.c.sleep(max(0.0, sec - C.JUMP_HOLD_SEC))
        self.c.up(key)

    def top_align(self):
        """From above: turn the camera until the pyramid's edges are square on
        screen, so W/A/S/D really go along the pyramid's sides."""
        sign, prev = 1, None
        for _ in range(C.ALIGN_MAX_ITER):
            a = self.v.top_angle(self.v.grab())
            if a is None:
                log.info("top view: no edge line to square up on")
                return
            if abs(a) < C.TOP_ALIGN_OK_DEG:
                log.info("top view: camera square (%.1f deg)", a)
                return
            if prev is not None and abs(a) > abs(prev) + 0.5:
                sign = -sign  # made it worse: other way round
            log.info("top view: edges tilted %.1f deg, turning", a)
            sec = min(0.2, abs(a) / 90 * self.turn90)
            if a * sign > 0:
                self.c.turn_right(sec)
            else:
                self.c.turn_left(sec)
            self.c.sleep(0.15)
            prev = a

    def recover(self, completed):
        """Fell off or lost: back under the A. Stairs / sign search from where we
        are first; if that fails, walk back to the pyramid and climb it again."""
        if getattr(self, "just_finished", False):
            # a layer just got done: we're standing still near its edge. The
            # stairs we'd see lead down the outside: only look for the sign
            self.just_finished = False
            if self.go_middle(completed, stairs=False) or (
                    self.approach_sign(completed) and self.go_middle(completed, stairs=False)):
                return True
        elif self.go_middle(completed) or (self.approach_sign(completed) and self.go_middle(completed)):
            return True
        log.info("lost the pyramid: walking back to it and climbing up again")
        self.c.up("e")
        ok = self.b.go_to_pyramid() and self.anchor(completed)
        self.c.down("e")
        return ok

    def peek_sign(self):
        """Normal view for a moment: where is the PYRAMID sign ahead? Returns its
        offset (-1 left .. +1 right) or None if it's not ahead (overhead/behind)."""
        self.camera_normal()
        self.c.sleep(0.15)
        off = None
        for _ in range(2):
            off = self.v.find_sign(self.v.grab(), "pyramid")[0]
            if off is not None:
                break
            self.c.sleep(0.1)
        self.camera_top()
        return off

    def approach_sign(self, completed):
        """On top, sign not in the top view. Normal camera: walk toward the sign
        keeping it centred. When it passes over our head (it was high on screen,
        now gone), look down and walk back the opposite way, toward where it was
        last seen, until the sign shows in the top view."""
        self.c.release_all()  # stand still first
        self.c.down("e")
        self.camera_normal()
        self.c.sleep(0.15)
        if self.v.find_sign(self.v.grab(), "pyramid")[0] is None:
            log.info("on top: sign not ahead, turning to find it")
            self.b.face_sign("pyramid")
        last_off, last_y, missing = 0.0, None, 0
        for i in range(C.APPROACH_MAX_STEPS):
            self.c.check()
            img = self.v.grab()
            if self.b.close_menu(img):
                continue
            off = self.v.find_sign(img, "pyramid")[0]
            if off is not None:
                last_off, last_y, missing = off, self.v.last_sign_y, 0
                if abs(off) > C.STEER_TOLERANCE:
                    self.c.hold("d" if off > 0 else "a", min(0.2, abs(off) * 0.6))
                if i % C.JUMP_EVERY_MOVES == C.JUMP_EVERY_MOVES - 1:
                    self.c.hold("space", C.JUMP_HOLD_SEC)  # now and then: hop, unsticks us
                self.c.hold("w", 3 * self.spb)
                continue
            missing += 1
            if last_y is not None and last_y < C.APPROACH_HIGH_Y:
                log.info("on top: the sign passed over our head (last at x %+.2f)", last_off)
                break
            if missing >= 3:
                log.info("on top: sign not ahead")
                break
            self.c.sleep(0.1)
        # look down; if it isn't below us it's behind: walk back toward it
        self.camera_top()
        self.top_align()  # we may have turned the camera to find the sign
        for i in range(C.APPROACH_BACK_STEPS):
            self.c.check()
            if self.v.sign_top(self.v.grab()) is not None:
                log.info("on top: sign in the top view (%d steps back)", i)
                return True
            if i % C.JUMP_EVERY_MOVES == C.JUMP_EVERY_MOVES - 1:
                self.c.hold("space", C.JUMP_HOLD_SEC)
            self.c.hold("s", 3 * self.spb)  # opposite of the way we were going
            if abs(last_off) > C.STEER_TOLERANCE:
                self.c.hold("d" if last_off > 0 else "a", min(3, abs(last_off) * 8) * self.spb)
        log.info("on top: sign never showed in the top view")
        return False

    def move_step(self, key, sec):
        """Top view: walk `sec` seconds. Jump only if the sign was in view and
        didn't move at all (a block in the way). Plain sand from above looks the
        same everywhere, so the picture itself can't tell us we're stuck."""
        before = self.v.sign_top(self.v.grab())
        self.moves = getattr(self, "moves", 0) + 1
        if self.moves % C.JUMP_EVERY_MOVES == 0:
            self.c.hold("space", C.JUMP_HOLD_SEC)  # now and then: hop, unsticks us
        self.c.hold(key, sec)
        self.c.sleep(0.15)
        after = self.v.sign_top(self.v.grab())
        if before is not None and after is not None and sec >= 0.08:
            moved_px = abs(after[0] - before[0]) if key in ("a", "d") else abs(after[1] - before[1])
            if moved_px > 25:
                # how far that really went: keep seconds-per-block honest
                spb = sec / (moved_px / self.ppb)
                new = round(0.7 * self.spb + 0.3 * spb, 5)
                if abs(new - self.spb) / self.spb > 0.03:
                    log.info("speed check: %.4fs per block (was %.4f)", new, self.spb)
                self.cal["sec_per_block"] = new
                self.speed_samples = getattr(self, "speed_samples", 0) + 1
                if self.speed_samples % 5 == 0:
                    self._save_cal()
        if before is not None and after is not None and \
                abs(before[0] - after[0]) + abs(before[1] - after[1]) < 3 and sec > 0.1:
            log.info("didn't move: a block in the way, jumping onto it")
            self.step_jump(key, C.JUMP_HOLD_SEC + 0.1)

    def edge_close(self, img=None, only=None):
        """True if an edge of the pyramid is right next to us (from above).
        `only`: just look at the edge on that side (the way we're walking)."""
        cx, cy = C.CHAR_POS
        lim = C.EDGE_HIT_BLOCKS * self.ppb
        if img is None:
            img = self.v.grab()
        for side, pos in self.v.border_strips(img).items():
            if only and side != only:
                continue
            if abs(pos - (cx if side in ("left", "right") else cy)) <= lim:
                log.info("edge %s right next to us", side)
                return True
        return False

    def anchor(self, completed):
        """Climb where we are, look straight down and walk to the middle."""
        self.pos_known = False
        log.info("anchoring: climb, look down, walk to the middle")
        self.check_walkspeed()
        self.completed = completed
        self.align()
        self.climb_to_top()
        self.heading = 0
        self.camera_top()
        self.top_align()  # square the camera first: turning later can lose the sign
        if self.v.sign_top(self.v.grab()) is None:
            self.approach_sign(completed)  # sign not in view yet: walk toward it looking down
        if "px_per_block" not in self.cal:
            self.calibrate_scale()
        if not self.go_middle(completed, front=True):
            # lost it again while lining up: look for it again (we're on top)
            self.approach_sign(completed)
            self.go_middle(completed)
        img = self.v.grab()
        self.v.save(img, "top_view")  # picture from the middle
        self.measure_scale(img, completed)
        log.info("in the middle")
        return True

    # ---------- walking with E held ----------
    def walk(self, blocks, state, check_lost=True, key="w", edge_stop=False, goal=None):
        """Walk forward `blocks` with W (E held). Returns None, or "empty",
        "done", "lost" if building should stop."""
        duration = blocks * self.spb
        self.goal_hit = False
        moved = 0.0  # time actually moving: blocked moments don't count as distance
        last = time.time()
        prev = None
        blocked = 0
        self.c.down(key)
        try:
            while moved < duration:
                remaining = duration - moved
                self.c.sleep(min(C.BUILD_TICK_SEC, remaining))
                now = time.time()
                dt, last = now - last, now
                if remaining <= C.BUILD_TICK_SEC:
                    break  # last bit: let go of W right away (no screenshot = no overshoot)
                if C.BUILD_DUTY < 1:
                    # pause a moment so placing keeps up with walking
                    self.c.up(key)
                    self.c.sleep(C.BUILD_TICK_SEC * (1 - C.BUILD_DUTY) / C.BUILD_DUTY)
                    self.c.down(key)
                    last = time.time()
                img = self.v.grab()
                if self.b.close_menu(img):
                    self.c.down("e")
                    self.c.down(key)
                    continue
                if goal is not None and self.top_view:
                    # watch the sign: stop when we've really arrived, not on the clock
                    pos = self.sign_pos(img)
                    if pos is not None:
                        axis, target = goal
                        v = pos[0] if axis == "x" else pos[1]
                        ahead = 1 if key in ("d", "w") else -1
                        if (target - v) * ahead <= C.ARRIVE_BLOCKS:
                            self.goal_hit = True
                            return None
                        duration = max(duration, moved + abs(target - v) * self.spb * 1.5)
                if edge_stop and self.edge_close(img, {"w": "top", "s": "bottom",
                                                       "a": "left", "d": "right"}[key]):
                    return "edge"
                scene = self.v.scene_small(img)
                if prev is not None and self.v.scene_diff(prev, scene) < C.BLOCKED_DIFF:
                    blocked += 1
                    if blocked >= 2:
                        self.c.hold("space", C.JUMP_HOLD_SEC)  # step in the way
                        blocked = 0
                else:
                    blocked = 0
                    moved += dt
                prev = scene
                if self.v.find_indicator(img) is not None:
                    state["last_cube"] = now
                if now >= state["next_counter"]:
                    state["next_counter"] = now + C.COUNTER_EVERY_SEC
                    cur = self.b.counter(img)
                    if cur and cur[0] > state["last_n"]:
                        state["last_n"] = cur[0]
                        state["last_rise"] = now
                        layer = G.layer_info(cur[0], self.base)[0]
                        if layer > state.get("layer", layer):
                            log.info("layer %d finished!", layer)
                            state["layer"] = layer
                            return "layer"
                        state["layer"] = layer
                    if self.b.pyramid_done():
                        return "done"
                if now >= state["next_cap"]:
                    state["next_cap"] = now + C.CAPACITY_EVERY_SEC
                    if self.b.empty():
                        return "empty"
                late = self._layer_left() <= 0.25
                # late in a layer only the counter counts (a green cactus can
                # look like the placement cube)
                idle = now - (state["last_rise"] if late else max(state["last_rise"], state["last_cube"]))
                limit = C.LOST_SEC_LATE if late else C.LOST_SEC
                if check_lost and idle > limit:
                    log.info("nothing placed for %.0fs on a layer that isn't done: lost", idle)
                    self.v.save(img, "lost_spiral")
                    return "lost"
        finally:
            self.c.up(key)
        return None

    def _layer_left(self):
        """Share of the current layer still missing (0..1)."""
        if not self.b.last_counter:
            return 1.0
        n, side, placed = G.layer_info(self.b.last_counter[0], self.base)
        return 1.0 if side <= 0 else 1 - placed / (side * side)

    def reanchor(self, completed, state):
        """Fix our position: from above, just look at the edges again."""
        if self.top_view and self.locate(completed):
            return None
        log.info("no edge in view to fix the position, carrying on")
        return None

    def walk_to(self, tx, ty, state, check_lost=True, watch_edge=None):
        """Move to (tx, ty). On top the camera looks straight down and is never
        turned, so screen directions are pyramid directions: W = +y (up on
        screen), S = -y, D = +x, A = -x. Returns "edge" if an edge is right next to us."""
        moves = []
        if abs(tx - self.x) > 0.3:
            moves.append(("d" if tx > self.x else "a", abs(tx - self.x), "x", tx))
        if abs(ty - self.y) > 0.3:
            moves.append(("w" if ty > self.y else "s", abs(ty - self.y), "y", ty))
        for key, dist, axis, target in moves:
            # from where we really are (the sign may have corrected it)
            d = target - (self.x if axis == "x" else self.y)
            if abs(d) <= 0.3:
                continue
            dist = abs(d)
            key = ("d" if d > 0 else "a") if axis == "x" else ("w" if d > 0 else "s")
            lo, hi = self.completed - 1, self.base - (self.completed - 1)
            # only legs heading close to the outer edge watch for it (the built
            # square's own edge in the middle looks the same and must not count)
            near_edge = min(target - lo, hi - target) < self.spiral_inset(hi - lo) + C.EDGE_WATCH_BLOCKS
            start = self.x if axis == "x" else self.y
            status = self.walk(dist * self.leg_scale(key), state, check_lost=check_lost, key=key,
                               edge_stop=(check_lost if watch_edge is None else watch_edge)
                               and self.top_view and near_edge,
                               goal=(axis, target))
            if status:
                return status
            if axis == "x":
                self.x = target
            else:
                self.y = target
            if self.top_view and self.locate_by_sign() and dist >= 8 and not self.goal_hit:
                # the sign shows where we really got to: learn how far legs in
                # this direction really go, so long walks stop overshooting
                actual = abs((self.x if axis == "x" else self.y) - start)
                self.learn_leg(key, dist, actual)
        return None

    # ---------- main ----------
    def run(self, base):
        """Anchor, then spiral layer after layer until out of blocks.
        Returns "empty", "done", "lost" or "failed"."""
        self.base = base
        cur = self.b.counter()
        if not cur:
            return "failed"
        completed, side, _ = G.layer_info(cur[0], base)
        if not self.anchor(completed):
            return "failed"
        now = time.time()
        state = {"last_n": cur[0], "last_rise": now, "last_cube": now,
                 "next_counter": now, "next_cap": now + C.CAPACITY_EVERY_SEC}
        self.c.down("e")
        passes = {}  # layer -> how many passes we've done on it
        outward_done = False
        edge_fixed = set()  # layers we re-anchored for before the edge laps
        edge_walked = set()  # layers whose edge laps are done
        lost_restarts = 0
        try:
            while True:
                cur = self.b.counter() or self.b.last_counter
                completed, side, placed = G.layer_info(cur[0], base)
                self.completed = completed
                if side <= 0:
                    return "done"
                left = 1 - placed / (side * side)
                lo, hi = G.layer_bounds(completed, base)
                tries = passes.get(completed, 0)
                passes[completed] = tries + 1
                spiral = left >= C.CLEANUP_BELOW and tries < 3
                if (spiral and outward_done) or (not spiral and completed not in edge_fixed):
                    # after an inward+outward pair, or before edge laps: fix drift
                    outward_done = False
                    if not spiral:
                        edge_fixed.add(completed)
                if spiral:
                    # start from the middle and spiral outward (your method)
                    mid = (lo + hi) / 2
                    if not self.recover(completed):
                        return "lost"
                    # 2nd pass: laps shifted half a lane, over the strips the 1st one missed
                    shift = (C.LANE_BLOCKS / 2) if tries % 2 else 0
                    path, kind = G.pick_path((mid, mid), lo, hi, C.LANE_BLOCKS, self.spiral_inset(hi - lo) + shift)
                    # the middle fills first: skip laps inside the part already built
                    r0 = (1 - left) ** 0.5 * side / 2 - C.LANE_BLOCKS
                    if kind == "outward" and r0 > 0:
                        rest = [p for p in path if max(abs(p[0] - mid), abs(p[1] - mid)) >= r0]
                        if rest:
                            path = rest
                    log.info("layer %d (%dx%d, %d%% done): spiral %s from (%.0f, %.0f)",
                             completed + 1, side, side, 100 - left * 100, kind, *path[0])
                    outward_done = kind == "outward"
                elif completed not in edge_walked:
                    edge_walked.add(completed)
                    # missed blocks are mostly along the edges: two laps close to them
                    path = (G.ring(lo, hi, self.lap_inset(hi - lo, 0), (self.x, self.y))
                            + G.ring(lo, hi, self.lap_inset(hi - lo, 1), (self.x, self.y)))
                    log.info("layer %d %d%% done: laps along the edges for missed blocks",
                             completed + 1, 100 - left * 100)
                else:
                    log.info("layer %d still has %d missing: following the cube",
                             completed + 1, side * side - placed)
                    status = self.cleanup_top(state, lo, hi)
                    if status == "layer":
                        self.c.release_all()
                        self.c.down("e")
                        self.just_finished = True
                        passes.pop(completed, None)
                        edge_walked.discard(completed)
                        lost_restarts = 0
                        continue  # next layer: back under the A, new spiral
                    if status == "lost" and lost_restarts < C.MAX_MIDDLE_RESTARTS:
                        lost_restarts += 1
                        if not self.recover(completed):
                            return "lost"
                        continue  # carry on with what's missing on this layer
                    return status
                state["layer"] = completed
                for i, (tx, ty) in enumerate(path):
                    # the first leg crosses the finished middle: nothing to place there
                    status = self.walk_to(tx, ty, state, check_lost=i > 0,
                                          watch_edge=i > 0)
                    if i == 0:
                        state["last_rise"] = state["last_cube"] = time.time()
                    if status in ("lost", "edge") and self.top_view and lost_restarts < C.MAX_MIDDLE_RESTARTS:
                        # at an edge or nothing to place: start over from the middle
                        lost_restarts += 1
                        log.info("%s: back to the middle (%d)",
                                 "hit an edge" if status == "edge" else "nothing placed for a while",
                                 lost_restarts)
                        if not self.recover(completed):
                            return "lost"
                        now = time.time()
                        state["last_rise"] = state["last_cube"] = now
                        break
                    if status == "layer":
                        # next layer: stand still, find the sign, back under the A
                        self.c.release_all()
                        self.c.down("e")
                        self.just_finished = True
                        outward_done = False
                        lost_restarts = 0
                        break
                    if status:
                        return "lost" if status == "edge" else status
        finally:
            self.c.up("e")
