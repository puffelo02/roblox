"""Pyramid builder bot.

Loop:  walk to BLOCKS sign -> hold E until full -> walk to PYRAMID sign ->
climb on top -> place along a shrinking clockwise spiral -> repeat.

Run from the repo root:   python -m pyramid_bot.bot
F7 = pause/resume, F8 = stop.
"""
import logging
import time

from . import config as C
from .controls import Controls, Stopped
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

    def walk_to_sign(self, which, arrived, stop_when_blocked=False):
        """Steer toward a sign with the arrow keys until arrived(img, pixels) is true.
        If W stops moving us (view doesn't change), we're blocked by something:
        with stop_when_blocked that counts as arrived (used for the pyramid wall),
        otherwise jump over it."""
        start = time.time()
        searched = 0.0
        blocked = 0
        while time.time() - start < C.TRAVEL_TIMEOUT_SEC:
            self.c.check()
            img = self.v.grab()
            if self.close_menu(img):
                continue
            offset, pixels = self.v.find_sign(img, which)
            if arrived(img, pixels):
                log.info("arrived at %s", which)
                return True
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
            if offset < -C.STEER_TOLERANCE:
                self.c.turn_left(C.STEER_TAP_SEC)
            elif offset > C.STEER_TOLERANCE:
                self.c.turn_right(C.STEER_TAP_SEC)
            before = self.v.scene_small(self.v.grab())
            self.c.hold("w", C.WALK_STEP_SEC)
            diff = self.v.scene_diff(before, self.v.scene_small(self.v.grab()))
            if diff < C.BLOCKED_DIFF:
                blocked += 1
                if blocked >= 2:
                    if stop_when_blocked:
                        log.info("blocked by a wall on the way to %s: arrived", which)
                        return True
                    log.info("blocked on the way to %s, jumping", which)
                    self.c.jump_forward()
            else:
                blocked = 0
        self.v.save(self.v.grab(), f"timeout_{which}")
        log.warning("timed out walking to %s", which)
        return False

    # ---------- phases ----------
    def go_to_blocks(self):
        log.info("-> BLOCKS")
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
        ok = self.walk_to_sign(
            "pyramid",
            lambda img, px: px > C.PYRAMID_SIGN_ARRIVED_PIXELS * self.v.sx * self.v.sy,
            stop_when_blocked=True,
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
        """Walk forward for sec seconds; True if the view barely changed (blocked)."""
        before = self.v.scene_small(self.v.grab())
        self.c.hold("w", sec)
        return self.v.scene_diff(before, self.v.scene_small(self.v.grab())) < C.BLOCKED_DIFF

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

    def build(self):
        """Follow the green placement cube with E held until out of blocks.

        cube next to us   -> stand still, blocks go down
        cube further away -> walk to it (W/A/S/D by where it is on screen)
        no cube in view   -> turn the camera to look around; if still nothing,
                             take a small step (jumping if blocked) and look again
        """
        log.info("building")
        self.climb()
        searches = 0
        turns = 0
        last_n = None
        last_rise = time.time()
        ticks = 0
        self.c.down("e")
        try:
            while True:
                self.c.sleep(C.BUILD_TICK_SEC)
                img = self.v.grab()
                if self.close_menu(img):
                    self.c.down("e")
                    continue
                cur = self.counter(img)
                if cur and (last_n is None or cur[0] > last_n):
                    last_n = cur[0]
                    last_rise = time.time()
                if self.pyramid_done():
                    return
                ticks += 1
                if ticks % 5 == 0 and self.empty():
                    return
                rising = time.time() - last_rise < 1.0

                ind = self.v.find_indicator(img)
                if ind is None:
                    if rising:
                        continue  # blocks are going down, stay
                    turns += 1
                    if turns <= C.SEARCH_TURNS:
                        self.c.turn_right(C.SEARCH_TURN_SEC)
                        continue
                    turns = 0
                    searches += 1
                    log.info("no placement cube around, stepping forward (%d)", searches)
                    if searches >= C.LOST_SEARCHES:
                        log.info("lost, heading back to the pyramid")
                        self.v.save(img, "no_cube")
                        self.c.up("e")
                        self.go_to_pyramid()
                        self.climb()
                        self.c.down("e")
                        searches = 0
                        continue
                    if self.walk_step_blocked(C.SEARCH_STEP_SEC):
                        self.c.jump_forward()
                    continue

                searches = 0
                turns = 0
                dx, dy = ind
                dist = (dx * dx + dy * dy) ** 0.5
                if dist < C.INDICATOR_NEAR_PX and (rising or time.time() - last_rise < C.NEAR_STALL_SEC):
                    continue  # on the spot: let E do its work
                self.move_toward(dx, dy, dist)
        finally:
            self.c.up("e")

    def move_toward(self, dx, dy, dist):
        """Short key press toward a point on screen (up = forward)."""
        keys = []
        if abs(dy) > dist * 0.35:
            keys.append("w" if dy < 0 else "s")
        if abs(dx) > dist * 0.35:
            keys.append("d" if dx > 0 else "a")
        pulse = min(C.MOVE_PULSE_MAX, max(0.05, dist * C.MOVE_PULSE_PER_PX))
        for k in keys:
            self.c.down(k)
        try:
            self.c.sleep(pulse)
        finally:
            for k in keys:
                self.c.up(k)

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
                self.build()
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
