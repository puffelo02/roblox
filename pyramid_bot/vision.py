"""Reading the game from screenshots."""
import os
import re
import time

import cv2
import mss
import numpy as np
import pytesseract

from . import config as C

pytesseract.pytesseract.tesseract_cmd = C.TESSERACT_CMD


class Vision:
    def __init__(self):
        self.last_sign_y = None
        self.sct = mss.mss()
        mon = self.sct.monitors[1]
        self.monitor = mon
        self.sx = mon["width"] / C.BASE_W
        self.sy = mon["height"] / C.BASE_H
        os.makedirs(C.DEBUG_DIR, exist_ok=True)

    def grab(self):
        img = np.array(self.sct.grab(self.monitor))
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def _scale(self, r):
        x1, y1, x2, y2 = r
        return int(x1 * self.sx), int(y1 * self.sy), int(x2 * self.sx), int(y2 * self.sy)

    def crop(self, img, region):
        x1, y1, x2, y2 = self._scale(region)
        return img[y1:y2, x1:x2]

    # ---------- OCR ----------
    @staticmethod
    def _white_text(img):
        """HUD text is white with a black outline: keep only bright, unsaturated pixels."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, (0, 0, 200), (179, 60, 255))
        mask = cv2.resize(mask, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        mask = cv2.copyMakeBorder(mask, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=0)
        return 255 - mask  # black text on white for tesseract

    @staticmethod
    def _bright_text(img):
        """Fallback for colored text (e.g. capacity turning red/yellow when full):
        keep bright pixels of any color that sit next to the black outline and
        don't look like the background (the most common color in the box)."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        dark = cv2.inRange(hsv, (0, 0, 0), (179, 255, 60))
        near_outline = cv2.dilate(dark, np.ones((5, 5), np.uint8))
        bright = cv2.inRange(hsv, (0, 0, 130), (179, 255, 255))
        bg = np.median(img[bright > 0].reshape(-1, 3), axis=0) if bright.any() else np.zeros(3)
        not_bg = (np.linalg.norm(img.astype(np.float32) - bg, axis=2) > 60).astype(np.uint8) * 255
        mask = bright & near_outline & not_bg
        mask = cv2.resize(mask, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        mask = cv2.copyMakeBorder(mask, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=0)
        return 255 - mask

    def _read_pair(self, img, region):
        """Reads 'a / b' and returns (a, b) or None."""
        crop = self.crop(img, region)
        attempts = [
            (prep, cfg)
            for prep in (self._white_text(crop), self._bright_text(crop))
            for cfg in ("--psm 7", "--psm 7 -c tessedit_char_whitelist=0123456789/,")
        ]
        for prepared, cfg in attempts:
            text = pytesseract.image_to_string(prepared, config=cfg).replace(" ", "")
            m = re.search(r"([\d,.]+)/([\d,.]+)", text)
            if m:
                try:
                    return int(re.sub(r"\D", "", m.group(1))), int(re.sub(r"\D", "", m.group(2)))
                except ValueError:
                    pass
        return None

    def read_counter(self, img):
        return self._read_pair(img, C.REGION_COUNTER)

    def read_capacity(self, img):
        return self._read_pair(img, C.REGION_CAPACITY)

    def read_walkspeed(self, img):
        pair = self._read_pair(img, C.REGION_WALKSPEED)
        return pair[0] if pair and 0 < pair[0] <= pair[1] else None

    def pickup_prompt_visible(self, img):
        crop = self.crop(img, C.REGION_PROMPT)
        text = pytesseract.image_to_string(crop, config="--psm 6").lower()
        return "block" in text or "pick" in text

    def menu_open(self, img):
        """The Upgrades menu is open if its big red X (with white cross) is there."""
        hsv = cv2.cvtColor(self.crop(img, C.REGION_MENU_X), cv2.COLOR_BGR2HSV)
        red = cv2.inRange(hsv, (0, 150, 150), (8, 255, 255)) | cv2.inRange(
            hsv, (170, 150, 150), (179, 255, 255)
        )
        white = cv2.inRange(hsv, (0, 0, 220), (179, 40, 255))
        return red.mean() / 255 > 0.12 and white.mean() / 255 > 0.05

    def scene_small(self, img):
        """Tiny grayscale version of the 3D view (HUD cut out) to compare frames.
        The character is blanked out: it turning around (e.g. from facing right
        to facing the wall) must not look like the world moving."""
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cx, cy = C.CHAR_POS
        bw, bh = C.CHAR_BOX
        g[int((cy - bh) * self.sy):int((cy + bh) * self.sy),
          int((cx - bw) * self.sx):int((cx + bw) * self.sx)] = 0
        h, w = g.shape
        g = g[int(h * 0.15):int(h * 0.9), int(w * 0.22):int(w * 0.88)]
        return cv2.resize(g, (96, 54), interpolation=cv2.INTER_AREA).astype(np.float32)

    @staticmethod
    def scene_diff(a, b):
        return float(np.mean(np.abs(a - b)))

    def find_indicator(self, img):
        """Green placement cube. Returns (dx, dy) in 1080p pixels relative to the
        character (screen center), or None if it isn't visible."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, *C.INDICATOR_HSV)
        keep = np.zeros_like(mask)
        x1, y1, x2, y2 = self._scale(C.INDICATOR_SEARCH)
        keep[y1:y2, x1:x2] = 255
        mask &= keep
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
        area_scale = self.sx * self.sy
        cx, cy = C.CHAR_POS
        best = None
        for i in range(1, n):
            area = stats[i][cv2.CC_STAT_AREA] / area_scale
            if not (C.INDICATOR_MIN_AREA <= area <= C.INDICATOR_MAX_AREA):
                continue  # specks, or big green things like menu buttons
            dx = cents[i][0] / self.sx - cx
            dy = cents[i][1] / self.sy - cy
            d = (dx * dx + dy * dy) ** 0.5
            if best is None or d < best[2]:
                best = (dx, dy, d)
        return None if best is None else (best[0], best[1])

    def edge_angle(self, img):
        """Angle (degrees) of the long step edges in front of the character.
        0 = edges perfectly horizontal = camera square to the pyramid side.
        Positive = right end lower on screen. None if no clear edges."""
        import math
        x1, y1, x2, y2 = self._scale(C.EDGE_REGION)
        g = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        g = cv2.GaussianBlur(g, (5, 5), 0)
        edges = cv2.Canny(g, 30, 90)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 360, 80,
                                minLineLength=int(150 * self.sx), maxLineGap=10)
        if lines is None:
            return None
        found = []
        for l in lines.reshape(-1, 4):
            ax, ay, bx, by = (int(v) for v in l)
            a = math.degrees(math.atan2(by - ay, bx - ax))
            a = (a + 90) % 180 - 90
            if abs(a) < C.EDGE_MAX_DEG:
                found.append((a, math.hypot(bx - ax, by - ay)))
        total = sum(w for _, w in found)
        if total < C.EDGE_MIN_TOTAL_PX * self.sx:
            return None
        found.sort()
        acc = 0
        for a, w in found:  # length-weighted median
            acc += w
            if acc >= total / 2:
                median = a
                break
        agree = sum(w for a, w in found if abs(a - median) < 2)
        if agree < total * 0.6:
            return None  # lines disagree: not a clean edge
        return median

    def step_rows(self, img):
        """How many parallel near-horizontal edges are stacked in front of us.
        The pyramid's steps give several (one per layer); a plain wall gives 1-2."""
        import math
        x1, y1, x2, y2 = self._scale(C.STEPS_REGION)
        g = cv2.GaussianBlur(cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY), (5, 5), 0)
        lines = cv2.HoughLinesP(cv2.Canny(g, 30, 90), 1, np.pi / 360, 80,
                                minLineLength=int(150 * self.sx), maxLineGap=10)
        if lines is None:
            return 0
        found = []
        for l in lines.reshape(-1, 4):
            ax, ay, bx, by = (int(v) for v in l)
            a = (math.degrees(math.atan2(by - ay, bx - ax)) + 90) % 180 - 90
            if abs(a) < 20:
                found.append((a, (ay + by) / 2))
        median = sorted(a for a, _ in found)[len(found) // 2] if found else 0
        rows = []
        for y in sorted(y for a, y in found if abs(a - median) < 3):
            if not rows or y - rows[-1] > 10 * self.sy:
                rows.append(y)
        return len(rows)

    def steps_extent(self, img):
        """Horizontal span (left, right) of the pyramid's step edges in 1080p x,
        or None if no steps are visible. The steps are long horizontal edge bands;
        where they end is the corner of the pyramid. Ends inside the HUD areas
        can't be seen, so a value at the visible border means "further than that"."""
        g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (5, 5), 0).astype(np.float32)
        gy = np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
        gx = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3))
        m = ((gy > 40) & (gy > 2 * gx)).astype(np.uint8) * 255
        for r in C.CORNER_HUD_MASKS:
            x1, y1, x2, y2 = self._scale(r)
            m[y1:y2, x1:x2] = 0
        _, top, _, bottom = self._scale((0, C.CORNER_BAND[0], 0, C.CORNER_BAND[1]))
        m[:top] = 0
        m[bottom:] = 0
        m = cv2.dilate(m, np.ones((3, 41), np.uint8))  # join the pieces of each edge
        n, _, st, _ = cv2.connectedComponentsWithStats(m)
        spans = []
        for i in range(1, n):
            x, y, w, h = st[i][:4]
            if w >= C.CORNER_MIN_LEN * self.sx:
                spans.append((x / self.sx, (x + w) / self.sx))
        if not spans:
            return None
        return min(a for a, _ in spans), max(b for _, b in spans)

    def screen_point(self, xy):
        return (
            self.monitor["left"] + int(xy[0] * self.sx),
            self.monitor["top"] + int(xy[1] * self.sy),
        )

    # ---------- Signs ----------
    def _sign_mask(self, img, ranges):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = np.zeros(hsv.shape[:2], np.uint8)
        for lo, hi in ranges:
            mask |= cv2.inRange(hsv, lo, hi)
        for r in C.HUD_MASKS:
            x1, y1, x2, y2 = self._scale(r)
            mask[y1:y2, x1:x2] = 0
        return mask

    @staticmethod
    def _panel_ratio(img, x, y, w, h):
        """The real PYRAMID sign has a muted green see-through panel around the
        text. Returns the share of panel-colored pixels just around the text."""
        H, W = img.shape[:2]
        x1, x2 = max(0, int(x - w * 0.25)), min(W, int(x + w * 1.25))
        y1, y2 = max(0, int(y - h * 0.4)), min(H, int(y + h * 1.4))
        hsv = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
        panel = cv2.inRange(hsv, *C.PYRAMID_PANEL_HSV)
        # only count the ring around the text, not the text itself
        ring = np.ones(panel.shape, np.uint8)
        ring[y - y1:y - y1 + h, x - x1:x - x1 + w] = 0
        total = int(ring.sum())
        return cv2.countNonZero(panel & (ring * 255)) / total if total else 0.0

    def find_sign(self, img, which):
        """Returns (offset, pixels): offset is -1 (far left) .. +1 (far right).

        Signs are wide, thin text floating above the horizon. Red/green gym gear
        is chunkier and sits lower, so blobs are filtered by shape and height."""
        ranges = C.RED_RANGES if which == "blocks" else C.GREEN_RANGES
        mask = self._sign_mask(img, ranges)
        max_y = C.SIGN_MAX_Y * self.sy
        mask[int(max_y):, :] = 0
        # join the letters into one blob per sign
        joined = cv2.dilate(mask, np.ones((5, 15), np.uint8))
        n, _, stats, cents = cv2.connectedComponentsWithStats(joined)
        best = None
        for i in range(1, n):
            x, y, w, h = stats[i][:4]
            if h == 0 or w / h < C.SIGN_MIN_ASPECT:
                continue
            px = int(cv2.countNonZero(mask[y:y + h, x:x + w]))
            if px < C.MIN_SIGN_PIXELS * self.sx * self.sy:
                continue
            if which == "pyramid" and self._panel_ratio(img, x, y, w, h) < C.PYRAMID_PANEL_MIN:
                continue  # green text without the sign's panel: gym label etc.
            if best is None or px > best[1]:
                best = (cents[i][0], px, cents[i][1] / self.sy)
        if best is None:
            return None, 0
        self.last_sign_y = best[2]  # height on screen (1080p), used to tell "right under it"
        half = img.shape[1] / 2
        return (float(best[0]) - half) / half, best[1]

    # ---------- Debug ----------
    def save(self, img, tag):
        if C.SAVE_SCREENSHOTS:
            cv2.imwrite(os.path.join(C.DEBUG_DIR, f"{int(time.time()*1000)}_{tag}.png"), img)
