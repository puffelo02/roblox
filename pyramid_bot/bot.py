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
        self.ring = 0
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

    def walk_to_sign(self, which, arrived):
        """Steer toward a sign with the arrow keys until arrived(img, pixels) is true."""
        start = time.time()
        searched = 0.0
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
            self.c.hold("w", C.WALK_STEP_SEC)
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
            "pyramid", lambda img, px: px > C.PYRAMID_SIGN_ARRIVED_PIXELS * self.v.sx * self.v.sy
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

    def climb(self):
        """Jump forward (W + Space) until placing works, i.e. we're on the top layer."""
        log.info("climbing")
        for i in range(C.MAX_CLIMB_JUMPS):
            if self.place_here() > 0:
                log.info("on top after %d jumps", i)
                return True
            self.c.jump_forward()
        self.v.save(self.v.grab(), "climb_failed")
        return False

    def empty(self):
        """Out of blocks: capacity reads (almost) 0, i.e. less than one placement."""
        cap = self.capacity()
        if cap is not None and cap[0] < C.EMPTY_BELOW:
            log.info("capacity empty (%s/%s), back to BLOCKS", *cap)
            return True
        return False

    def build(self):
        """Walk a clockwise spiral holding E at each spot until capacity is empty."""
        log.info("building, ring %d", self.ring)
        self.climb()
        dead_rings = 0
        while True:
            side_steps = C.SIDE_STEPS_START - self.ring * C.RING_SHRINK_STEPS
            if side_steps < 2:
                log.info("reached the middle, starting from the outside again")
                self.ring = 0
                self.c.turn_right(C.TURN_180_SEC)
                continue
            ring_progress = 0
            for side in range(4):
                stalled = 0
                step = 0
                while step < side_steps:
                    self.c.check()
                    placed = self.place_here()
                    ring_progress += placed
                    stalled = 0 if placed else stalled + 1
                    if self.empty():
                        return
                    if self.pyramid_done():
                        return
                    if stalled == 3:
                        # probably standing below a step: jump up
                        self.c.jump_forward()
                    # skip over already filled stretches faster
                    mult = 2 if stalled >= C.STALL_SPOTS_FOR_SKIP else 1
                    self.c.hold("w", C.PATTERN_STEP_SEC * mult)
                    step += mult
                self.c.turn_right()
            self.ring += 1
            if ring_progress == 0:
                dead_rings += 1
                if dead_rings >= C.STALL_RINGS_FOR_FALL:
                    log.info("no progress for a while, probably fell off")
                    self.v.save(self.v.grab(), "fell")
                    self.c.turn_right()  # center of a clockwise spiral is to the right
                    self.climb()
                    dead_rings = 0
            else:
                dead_rings = 0

    # ---------- main loop ----------
    def run(self):
        log.info("starting in 5 seconds: click on the Roblox window now")
        time.sleep(5)
        try:
            while True:
                self.counter()
                if self.pyramid_done():
                    log.info("pyramid complete: %s", self.last_counter)
                    self.ring = 0
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
