"""Pyramid builder bot.

Loop:  walk to BLOCKS sign -> hold E until full -> walk to PYRAMID sign ->
climb on top -> place along a shrinking clockwise spiral -> repeat.

Run from the repo root:   python -m pyramid_bot.bot
F7 = pause/resume, F8 = stop.
"""
import logging
import time

from . import config as C
from . import geometry as G
from .controls import Controls, Stopped
from .navigator import Navigator
from .vision import Vision

log = logging.getLogger("bot")


class Bot:
    def __init__(self):
        self.v = Vision()
        self.c = Controls()
        self.last_counter = None
        self.cap_max = None
        self.cap_candidate = None
        self.cap_votes = 0
        self.nav = Navigator(self)

    # ---------- helpers ----------
    def counter(self, img=None):
        """Block counter, ignoring OCR glitches (wrong total, going backwards, huge jumps)."""
        img = self.v.grab() if img is None else img
        val = self.v.read_counter(img)
        last = self.last_counter
        if val and last:
            new_pyramid = val[0] < 1000 and last[0] >= last[1]
            glitch = val[1] != last[1] or val[0] < last[0] or val[0] - last[0] > 20000
            if glitch and not new_pyramid:
                return last
        if val:
            self.last_counter = val
        return val or last

    def capacity(self, img=None):
        """Capacity, ignoring readings whose max doesn't match the usual max."""
        img = self.v.grab() if img is None else img
        val = self.v.read_capacity(img)
        if not val or val[0] > val[1]:
            return None
        if val[1] != self.cap_max:
            # only trust a new max once it's been read the same way 3 times in a row
            self.cap_votes = self.cap_votes + 1 if val[1] == self.cap_candidate else 1
            self.cap_candidate = val[1]
            if self.cap_votes < 3:
                return None
            self.cap_max = val[1]
        return val

    def close_menu(self, img=None):
        """If the Upgrades menu popped up, click its X and step off the platform."""
        img = self.v.grab() if img is None else img
        if not self.v.menu_open(img):
            return False
        log.info("upgrades menu open, closing it")
        self.v.save(img, "menu")
        self.c.release_all()
        for _ in range(5):
            self.c.click(self.v.screen_point(C.MENU_X_CLICK))
            self.c.sleep(0.4)
            if not self.v.menu_open(self.v.grab()):
                break
        # back off the platform so it doesn't open again
        self.c.hold("s", 0.8)
        self.c.hold("d", 0.5)
        return True

    def pyramid_done(self):
        return self.last_counter is not None and self.last_counter[0] >= self.last_counter[1]

    def at_pyramid_wall(self):
        """Is the wall in front of us really the pyramid? Placing works from its
        base (counter goes up), and its steps show as several stacked edges."""
        img = self.v.grab()
        # the pyramid's shape: a stack of long, wide step lines in front of us
        rows = self.v.step_rows(img, C.WALL_STEP_MIN_LEN)
        far = self.v.pyramid_sign_far(img)
        if C.WALL_MIN_STEP_ROWS <= rows <= C.WALL_MAX_STEP_ROWS:
            # the pyramid's shape: stacked step lines in front of us
            log.info("wall check: %d step edges ahead, it's the pyramid", rows)
            return True
        if far:
            # the PYRAMID sign still a tiny speck near the horizon: something else
            log.info("wall check: pyramid sign still far ahead: not the pyramid")
            return False
        before = self.counter()
        self.c.hold("e", C.WALL_CHECK_PLACE_SEC)
        after = self.counter()
        if before and after and after[0] > before[0]:
            log.info("wall check: blocks were placed, it's the pyramid")
            return True
        log.info("wall check: %d step edges, nothing placed: not the pyramid", rows)
        self.v.save(img, "not_pyramid")
        return False

    def get_around(self, attempt):
        """First try jumping over it (a sand block); then back off and sidestep
        (alternating sides, wider each time)."""
        if attempt == 1:
            self.c.jump_forward()
            return
        self.c.hold("s", 0.5)
        self.c.hold("d" if attempt % 2 == 0 else "a", 0.6 + 0.4 * attempt)

    def face_sign(self, which, max_turns=1.0):
        """Turn the camera (standing still) until the sign is in view. True if found."""
        step = C.TURN_90_SEC / 4
        turned = 0.0
        while turned < C.TURN_90_SEC * 4 * max_turns:
            self.c.check()
            img = self.v.grab()
            if self.close_menu(img):
                continue
            off = self.v.find_sign(img, which)[0]
            if off is not None:
                if abs(off) < C.FACE_SIGN_OK:
                    return True
                # in view but off to the side: small turn toward it
                (self.c.turn_left if off < 0 else self.c.turn_right)(
                    min(step, abs(off) * C.TURN_90_SEC * 0.5))
                turned += step / 4
                self.c.sleep(0.1)
                continue
            self.c.turn_right(step)
            turned += step
            self.c.sleep(0.1)
        log.warning("can't see the %s sign anywhere", which)
        return False

    def walk_to_sign(self, which, arrived, stop_when_blocked=False, strafe=False):
        """Steer toward a sign with the arrow keys until arrived(img, pixels) is true.
        If W stops moving us (view doesn't change), we're blocked by something:
        with stop_when_blocked that counts as arrived (used for the pyramid wall),
        otherwise jump over it."""
        start = time.time()
        searched = 0.0
        blocked = 0
        last_y = None
        missing = 0
        detours = 0
        while time.time() - start < C.TRAVEL_TIMEOUT_SEC:
            self.c.check()
            img = self.v.grab()
            if self.close_menu(img):
                continue
            offset, pixels = self.v.find_sign(img, which)
            if arrived(img, pixels):
                log.info("arrived at %s", which)
                return True
            if offset is not None:
                missing = 0
                near = (self.v.last_sign_y < C.SIGN_NEAR_TOP_Y
                        and pixels > C.SIGN_NEAR_MIN_PX * self.v.sx * self.v.sy)
                last_y = self.v.last_sign_y if near else None
            else:
                missing += 1
            if offset is None and last_y is not None and missing >= C.SIGN_GONE_CHECKS:
                # it went off the top of the screen: we're right next to it, keep going
                log.info("%s sign went above the screen: walking straight ahead", which)
                last_y = None
                for _ in range(C.NEAR_SIGN_STEPS):
                    if self.walk_step_blocked(C.WALK_STEP_SEC):
                        if stop_when_blocked:
                            if self.at_pyramid_wall():
                                log.info("blocked by the pyramid right under the %s sign: arrived", which)
                                return True
                            detours += 1
                            self.get_around(detours)
                            continue
                        self.c.jump_forward()
                    if arrived(self.v.grab(), 0):
                        log.info("arrived at %s", which)
                        return True
                continue
            if offset is None and last_y is not None:
                self.c.hold("w", C.WALK_STEP_SEC)  # close sign just went out of view: keep going
                continue
            if offset is None and strafe:
                if missing >= C.SIGN_GONE_CHECKS:
                    self.face_sign(which)  # lost it: look around standing still
                    missing = 0
                else:
                    self.c.hold("w", C.WALK_STEP_SEC)
                continue
            if offset is None:
                # not in view: spin the camera to look for it
                self.c.turn_right(C.TURN_90_SEC / 3)
                searched += C.TURN_90_SEC / 3
                if searched > C.TURN_180_SEC * 2.5:
                    self.v.save(img, f"lost_{which}")
                    log.warning("can't find %s sign", which)
                    searched = 0.0
                    self.c.hold("w", C.WALK_STEP_SEC * 2)
                continue
            searched = 0.0
            if strafe:
                # keep the camera still: sidestep to keep the sign in the middle
                if abs(offset) > C.STEER_TOLERANCE:
                    self.c.down("w")
                    self.c.hold("a" if offset < 0 else "d",
                                min(C.STRAFE_MAX_SEC, abs(offset) * C.STRAFE_GAIN))
                    self.c.up("w")
            elif offset < -C.STEER_TOLERANCE:
                self.c.turn_left(C.STEER_TAP_SEC)
            elif offset > C.STEER_TOLERANCE:
                self.c.turn_right(C.STEER_TAP_SEC)
            before = self.v.scene_small(self.v.grab())
            self.c.hold("w", C.WALK_STEP_SEC)
            diff = self.v.scene_diff(before, self.v.scene_small(self.v.grab()))
            if diff < C.BLOCKED_DIFF:
                blocked += 1
                if blocked >= 2:
                    blocked = 0
                    if stop_when_blocked:
                        if self.at_pyramid_wall():
                            log.info("blocked by the pyramid wall: arrived")
                            return True
                        detours += 1
                        log.info("blocked by something that isn't the pyramid: going around (%d)", detours)
                        self.get_around(detours)
                        continue
                    log.info("blocked on the way to %s, jumping", which)
                    self.c.jump_forward()
            else:
                blocked = 0
        self.v.save(self.v.grab(), f"timeout_{which}")
        log.warning("timed out walking to %s", which)
        return False

    # ---------- phases ----------
    def find_sign_any_pitch(self, which):
        """Turn around looking for the sign; if it's nowhere, the camera is
        probably still tilted down (top view): tilt up a bit and look again."""
        for tilt in range(C.PITCH_SEARCH_TRIES + 1):
            if self.face_sign(which):
                return True
            if tilt < C.PITCH_SEARCH_TRIES:
                log.info("no %s sign all around: tilting the camera up", which)
                self.c.right_drag(-C.PITCH_SEARCH_PX)
        return False

    def go_to_blocks(self):
        log.info("-> BLOCKS (capacity empty: refilling)")
        if not self.v.pickup_prompt_visible(self.v.grab()):
            self.find_sign_any_pitch("blocks")  # find the red BLOCKS sign, standing still
        return self.walk_to_sign(
            "blocks", lambda img, px: self.v.pickup_prompt_visible(img)
        )

    def pick_up(self):
        """Hold E until capacity is completely full. If it stops rising, shuffle to a new spot."""
        log.info("picking up")
        start = time.time()
        best = -1
        last_rise = time.time()
        last_log = 0
        shuffle = 0
        self.c.down("e")
        try:
            while time.time() - start < C.PICKUP_TIMEOUT_SEC:
                self.c.sleep(0.5)
                img = self.v.grab()
                if self.close_menu(img):
                    self.go_to_blocks()
                    self.c.down("e")
                    last_rise = time.time()
                    continue
                cap = self.capacity(img)
                near_full = self.cap_max and best >= self.cap_max * C.NEAR_FULL_RATIO
                if not cap:
                    # text may change look when full: if we were close and it's unreadable, go
                    if near_full and time.time() - last_rise > C.FULL_FALLBACK_SEC:
                        log.info("capacity unreadable after reaching %s, treating as full", best)
                        self.v.save(img, "full_unreadable")
                        return True
                    continue
                if time.time() - last_log > 3:
                    log.info("capacity %s/%s", *cap)
                    last_log = time.time()
                if cap[0] >= cap[1] * C.CAPACITY_FULL_RATIO:
                    log.info("capacity full %s/%s", *cap)
                    return True
                if near_full and cap[0] <= best and time.time() - last_rise > C.FULL_FALLBACK_SEC:
                    log.info("capacity stopped at %s/%s, treating as full", *cap)
                    self.v.save(img, "full_stalled")
                    return True
                if cap[0] > best:
                    best = cap[0]
                    last_rise = time.time()
                elif time.time() - last_rise > C.PICKUP_STALL_SEC:
                    log.info("capacity stuck at %s/%s, moving a bit", *cap)
                    self.v.save(img, "pickup_stuck")
                    self.c.up("e")
                    # small moves around inside the pit, cycling direction
                    self.c.hold("wasd"[shuffle % 4], 0.3)
                    shuffle += 1
                    if not self.v.pickup_prompt_visible(self.v.grab()):
                        self.go_to_blocks()
                    self.c.down("e")
                    last_rise = time.time()
        finally:
            self.c.up("e")
        log.warning("pickup timed out")
        return False

    def go_to_pyramid(self):
        log.info("-> PYRAMID")
        self.find_sign_any_pitch("pyramid")  # find the word first, standing still
        ok = self.walk_to_sign(
            "pyramid",
            lambda img, px: px > C.PYRAMID_SIGN_ARRIVED_PIXELS * self.v.sx * self.v.sy,
            stop_when_blocked=True, strafe=True,
        )
        if ok:
            self.c.hold("w", C.PLOT_ENTER_SEC)
        return ok

    def place_here(self):
        """Hold E at the current spot. Returns how many blocks went down."""
        before = self.counter()
        self.c.hold("e", C.PLACE_HOLD_SEC)
        img = self.v.grab()
        if self.close_menu(img):
            return 0
        after = self.counter(img)
        if before and after:
            return max(0, after[0] - before[0])
        return 0

    def walk_step_blocked(self, sec):
        """Walk forward for sec seconds; True if the view barely changed (blocked).
        W goes down first and the "before" picture is taken a moment later, so the
        character turning to face forward doesn't count as moving."""
        self.c.down("w")
        try:
            self.c.sleep(C.TURN_SETTLE_SEC)
            before = self.v.scene_small(self.v.grab())
            self.c.sleep(sec)
            after = self.v.scene_small(self.v.grab())
        finally:
            self.c.up("w")
        return self.v.scene_diff(before, after) < C.BLOCKED_DIFF

    def climb(self):
        """Walk forward, jumping whenever a step blocks us. We're on top once we can
        walk freely several steps in a row (the steps are narrow, the top is wide).
        Placing blocks is NOT used here: from the ground the place range can reach
        the pyramid too, which made it think it was on top."""
        log.info("climbing")
        free = 0
        jumps = 0
        for _ in range(C.MAX_CLIMB_JUMPS * 2):
            self.c.check()
            if self.close_menu():
                free = 0
                continue
            if self.walk_step_blocked(C.CLIMB_STEP_SEC):
                free = 0
                self.c.jump_forward()
                jumps += 1
            else:
                free += 1
                if free >= C.CLIMB_FREE_STEPS:
                    log.info("on top after %d jumps", jumps)
                    return True
        self.v.save(self.v.grab(), "climb_failed")
        log.warning("climb failed")
        return False

    def empty(self):
        """Out of blocks: capacity reads (almost) 0, i.e. less than one placement."""
        cap = self.capacity()
        if cap is not None and cap[0] < C.EMPTY_BELOW:
            log.info("capacity empty (%s/%s), back to BLOCKS", *cap)
            return True
        return False

    def build_pyramid(self):
        """Corner anchor + square spiral when the pyramid size is known,
        otherwise fall back to following the cube."""
        cur = self.counter()
        base = G.base_size(cur[1]) if cur else None
        if base is None:
            log.info("pyramid size unknown (%s), following the cube instead", cur)
            self.build()
            return
        try:
            status = self.nav.run(base)
        finally:
            self.nav.camera_normal()  # back to the normal view for walking to BLOCKS
        log.info("building stopped: %s", status)
        if status == "failed":
            log.info("couldn't anchor, following the cube this trip")
            self.build()

    def build(self, max_sec=None, climb_first=True):
        """Keep walking (W + E held) and steer with the camera, never stopping.

        cube visible -> turn the camera toward it while walking over it
        no cube      -> walk a circle that slowly tightens (spiral toward the center)
        fell off     -> nothing placed and no cube for a while: the pyramid is behind
                        us, so turn around and climb back up
        """
        log.info("following the cube")
        if climb_first:
            self.climb()
        started = time.time()
        last_n = self.counter()[0] if self.counter() else None
        last_rise = last_ind = time.time()
        next_counter = next_cap = time.time()
        spiral_turn = C.SPIRAL_TURN_START
        prev_scene = None
        blocked = 0
        failed_recoveries = 0
        self.c.down("e")
        self.c.down("w")
        try:
            while max_sec is None or time.time() - started < max_sec:
                self.c.sleep(C.BUILD_TICK_SEC)
                now = time.time()
                img = self.v.grab()
                if self.close_menu(img):
                    self.c.down("e")
                    self.c.down("w")
                    continue

                # slow OCR only once in a while
                if now >= next_counter:
                    next_counter = now + C.COUNTER_EVERY_SEC
                    cur = self.counter(img)
                    if cur and (last_n is None or cur[0] > last_n):
                        last_n = cur[0]
                        last_rise = now
                        failed_recoveries = 0
                    if self.pyramid_done():
                        return
                if now >= next_cap:
                    next_cap = now + C.CAPACITY_EVERY_SEC
                    if self.empty():
                        return

                # hop when a step blocks us
                scene = self.v.scene_small(img)
                if prev_scene is not None and self.v.scene_diff(prev_scene, scene) < C.BLOCKED_DIFF:
                    blocked += 1
                    if blocked >= 3:
                        self.c.hold("space", C.JUMP_HOLD_SEC)
                        blocked = 0
                else:
                    blocked = 0
                prev_scene = scene

                ind = self.v.find_indicator(img)
                if ind is not None:
                    last_ind = now
                    spiral_turn = C.SPIRAL_TURN_START
                    self.steer_toward(*ind)
                    continue

                # no cube: fell off the edge?
                if now - last_ind > C.FALL_SEC and now - last_rise > C.FALL_SEC:
                    failed_recoveries += 1
                    log.info("nothing to place for %.0fs, probably fell off: turning back (%d)",
                             now - last_ind, failed_recoveries)
                    self.v.save(img, "fell")
                    self.c.up("w")
                    if failed_recoveries >= C.MAX_RECOVERIES:
                        log.info("still lost, walking back to the PYRAMID sign")
                        self.c.up("e")
                        self.go_to_pyramid()
                        failed_recoveries = 0
                    else:
                        self.c.turn_right(C.TURN_180_SEC)
                    self.climb()
                    self.c.down("e")
                    self.c.down("w")
                    last_ind = last_rise = time.time()
                    spiral_turn = C.SPIRAL_TURN_START
                    continue

                # spiral: keep turning a little, a bit more each time (tighter circle)
                self.c.turn_right(spiral_turn)
                spiral_turn = min(C.SPIRAL_TURN_MAX, spiral_turn + C.SPIRAL_TURN_GROW)
        finally:
            self.c.up("w")
            self.c.up("e")

    def steer_toward(self, dx, dy):
        """Turn the camera toward a point on screen while walking (up = ahead)."""
        import math
        angle = math.degrees(math.atan2(dx, -dy))  # 0 = straight ahead, +90 = right
        if abs(angle) < C.STEER_DEADZONE_DEG:
            return
        sec = min(C.STEER_MAX_SEC, abs(angle) / 90 * C.TURN_90_SEC)
        if angle > 0:
            self.c.turn_right(sec)
        else:
            self.c.turn_left(sec)

    # ---------- main loop ----------
    def run(self):
        log.info("starting in 5 seconds: click on the Roblox window now")
        time.sleep(5)
        try:
            while True:
                self.counter()
                if self.pyramid_done():
                    log.info("pyramid complete: %s", self.last_counter)
                    self.c.sleep(5)
                    continue
                if not self.go_to_blocks():
                    continue
                if not self.pick_up():
                    continue
                if not self.go_to_pyramid():
                    continue
                self.build_pyramid()
        except Stopped:
            log.info("stopped by user")
        finally:
            self.c.release_all()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("bot.log")],
    )
    Bot().run()


if __name__ == "__main__":
    main()
