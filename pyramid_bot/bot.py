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

    # ---------- helpers ----------
    def counter(self, img=None):
        img = self.v.grab() if img is None else img
        val = self.v.read_counter(img)
        if val:
            self.last_counter = val
        return val

    def capacity(self, img=None):
        img = self.v.grab() if img is None else img
        return self.v.read_capacity(img)

    def pyramid_done(self):
        return self.last_counter is not None and self.last_counter[0] >= self.last_counter[1]

    def walk_to_sign(self, which, arrived):
        """Steer toward a sign with the arrow keys until arrived(img, pixels) is true."""
        start = time.time()
        searched = 0.0
        while time.time() - start < C.TRAVEL_TIMEOUT_SEC:
            self.c.check()
            img = self.v.grab()
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
        log.info("picking up")
        self.c.down("e")
        start = time.time()
        try:
            while time.time() - start < C.PICKUP_TIMEOUT_SEC:
                self.c.sleep(0.5)
                cap = self.capacity()
                if cap:
                    log.info("capacity %s/%s", *cap)
                    if cap[0] >= cap[1] * C.CAPACITY_FULL_RATIO:
                        return True
        finally:
            self.c.up("e")
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
        after = self.counter()
        if before and after:
            return max(0, after[0] - before[0])
        return 0

    def climb(self, max_jumps=12):
        """Jump forward until placing works again (we're back on the top layer)."""
        log.info("climbing")
        for _ in range(max_jumps):
            if self.place_here() > 0:
                return True
            self.c.jump_forward()
        return False

    def empty(self):
        cap = self.capacity()
        return cap is not None and cap[0] <= 0

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
                self.pick_up()
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
