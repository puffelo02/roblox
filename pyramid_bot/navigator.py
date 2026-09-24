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
            self.c.sleep(0.05)
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
        free = 0
        since_wall = 0.0
        # one forward jump per finished layer, whether or not a wall was "seen"
        # (the step check can miss low steps, which left it at the bottom)
        for _ in range(n):
            self.c.check()
            self.c.jump_forward()
            jumps += 1
        since_wall = C.JUMP_FORWARD_SEC
        for _ in range(C.MAX_CLIMB_JUMPS):
            self.c.check()
            t0 = time.time()
            if self.b.walk_step_blocked(C.CLIMB_STEP_SEC):
                self.c.jump_forward()  # still a step in front: keep going up
                jumps += 1
                free = 0
                since_wall = C.JUMP_FORWARD_SEC
            else:
                free += 1
                since_wall += time.time() - t0  # real time W was held
                if free >= 2:
                    break
        log.info("climbed %d layers (%d jumps)", n, jumps)
        self.jumps = jumps
        return since_wall

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

    def anchor(self, completed):
        """From the base wall: square up, find the right corner, climb at a known
        spot. Sets self.x / self.y / self.heading."""
        log.info("anchoring at a corner")
        self.check_walkspeed()
        self.align()
        if "turn90" not in self.cal:
            self.calibrate_turn()
            self.align()
        slid = self.find_corner("d")
        if slid is None:
            return False
        at_left = False
        if self.spb is None:
            log.info("measuring walk speed: sliding to the other corner (%d blocks)", self.base)
            self.align()
            slid = self.find_corner("a")
            if slid is None:
                return False
            self.cal["sec_per_block"] = round(slid / self.base, 5)
            self._save_cal()
            at_left = True
        # climb two blocks inside the layer being built (not too close to the edge)
        offset = completed + 2
        self.align()
        if at_left:
            self.c.hold("d", offset * self.spb)
            self.x = offset
        else:
            self.c.hold("a", offset * self.spb)
            self.x = self.base - offset
        since_wall = self.climb_layers(completed)
        # each jump went up one step; the last step's edge is at y = jumps - 1
        self.y = max(0, self.jumps - 1) + since_wall / self.spb
        self.heading = 0
        log.info("anchored at (%.1f, %.1f)", self.x, self.y)
        return True

    # ---------- walking with E held ----------
    def walk(self, blocks, state, check_lost=True):
        """Walk forward `blocks` with W (E held). Returns None, or "empty",
        "done", "lost" if building should stop."""
        duration = blocks * self.spb
        moved = 0.0  # time actually moving: blocked moments don't count as distance
        last = time.time()
        prev = None
        blocked = 0
        self.c.down("w")
        try:
            while moved < duration:
                remaining = duration - moved
                self.c.sleep(min(C.BUILD_TICK_SEC, remaining))
                now = time.time()
                dt, last = now - last, now
                if remaining <= C.BUILD_TICK_SEC:
                    break  # last bit: let go of W right away (no screenshot = no overshoot)
                img = self.v.grab()
                if self.b.close_menu(img):
                    self.c.down("e")
                    self.c.down("w")
                    continue
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
                idle = now - max(state["last_rise"], state["last_cube"])
                if check_lost and idle > C.LOST_SEC and self._layer_left() > 0.25:
                    log.info("nothing placed for %.0fs on a layer that isn't done: lost", idle)
                    self.v.save(img, "lost_spiral")
                    return "lost"
        finally:
            self.c.up("w")
        return None

    def _layer_left(self):
        """Share of the current layer still missing (0..1)."""
        if not self.b.last_counter:
            return 1.0
        n, side, placed = G.layer_info(self.b.last_counter[0], self.base)
        return 1.0 if side <= 0 else 1 - placed / (side * side)

    def reanchor(self, completed, state):
        """Walk down the near side of the pyramid and anchor at the corner again,
        which wipes out the small errors that add up while walking."""
        log.info("re-anchoring: walking down to the base wall")
        self.c.up("e")
        # stay away from the side edges so we come down in front of the base wall
        margin = min(10, self.base / 4)
        status = self.walk_to(min(max(self.x, margin), self.base - margin), self.y, state)
        if status:
            return status
        self.face(180)
        # plenty extra: the estimate may be off after a long spiral, and a few
        # blocks out into the desert don't hurt
        self.walk(self.y + C.REANCHOR_EXTRA, state, check_lost=False)
        self.face(0)
        for _ in range(80):  # back toward the pyramid until the base wall stops us
            if self.b.walk_step_blocked(C.CLIMB_STEP_SEC):
                break
        if not self.anchor(completed):
            return "failed"
        self.c.down("e")
        return None

    def walk_to(self, tx, ty, state):
        moves = []
        if abs(tx - self.x) > 0.3:
            moves.append((90 if tx > self.x else 270, abs(tx - self.x), "x", tx))
        if abs(ty - self.y) > 0.3:
            moves.append((0 if ty > self.y else 180, abs(ty - self.y), "y", ty))
        moves.sort(key=lambda m: m[0] != self.heading)  # no turn first
        for heading, dist, axis, target in moves:
            self.face(heading)
            status = self.walk(dist, state)
            if status:
                return status
            if axis == "x":
                self.x = target
            else:
                self.y = target
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
        if completed == 0:
            return "failed"  # no base wall yet to anchor on: caller follows the cube
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
        try:
            while True:
                cur = self.b.counter() or self.b.last_counter
                completed, side, placed = G.layer_info(cur[0], base)
                if side <= 0:
                    return "done"
                left = 1 - placed / (side * side)
                lo, hi = G.layer_bounds(completed, base)
                tries = passes.get(completed, 0)
                passes[completed] = tries + 1
                spiral = tries == 0 or (left >= C.CLEANUP_BELOW and tries < 3)
                if (spiral and outward_done) or (not spiral and completed not in edge_fixed):
                    # after an inward+outward pair, or before edge laps: fix drift
                    status = self.reanchor(completed, state)
                    if status:
                        return status
                    outward_done = False
                    if not spiral:
                        edge_fixed.add(completed)
                if spiral:
                    path, kind = G.pick_path((self.x, self.y), lo, hi, C.LANE_BLOCKS, C.EDGE_INSET)
                    log.info("layer %d (%dx%d, %d%% done): spiral %s from (%.0f, %.0f)",
                             completed + 1, side, side, 100 - left * 100, kind, *path[0])
                    outward_done = kind == "outward"
                elif completed not in edge_walked:
                    edge_walked.add(completed)
                    # missed blocks are mostly along the edges: two laps close to them
                    path = (G.ring(lo, hi, C.EDGE_LAP_INSETS[0], (self.x, self.y))
                            + G.ring(lo, hi, C.EDGE_LAP_INSETS[1], (self.x, self.y)))
                    log.info("layer %d %d%% done: laps along the edges for missed blocks",
                             completed + 1, 100 - left * 100)
                else:
                    log.info("layer %d still has %d missing: following the cube",
                             completed + 1, side * side - placed)
                    self.c.up("e")
                    self.b.build(max_sec=C.CLEANUP_SEC, climb_first=False)
                    return "lost"  # position unknown now: re-anchor on the next trip
                state["layer"] = completed
                for tx, ty in path:
                    status = self.walk_to(tx, ty, state)
                    if status == "layer":
                        # next layer: hop up onto it and plan a new, smaller spiral
                        self.c.hold("space", C.JUMP_HOLD_SEC)
                        outward_done = False
                        break
                    if status:
                        return status
        finally:
            self.c.up("e")
