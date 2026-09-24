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
        """Tiny grayscale version of the 3D view (HUD cut out) to compare frames."""
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
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

    def find_sign(self, img, which):
        """Returns (offset, pixels): offset is -1 (far left) .. +1 (far right)."""
        ranges = C.RED_RANGES if which == "blocks" else C.GREEN_RANGES
        mask = self._sign_mask(img, ranges)
        pixels = int(cv2.countNonZero(mask))
        if pixels < C.MIN_SIGN_PIXELS * self.sx * self.sy:
            return None, pixels
        xs = np.nonzero(mask)[1]
        w = img.shape[1]
        return (float(np.median(xs)) - w / 2) / (w / 2), pixels

    # ---------- Debug ----------
    def save(self, img, tag):
        if C.SAVE_SCREENSHOTS:
            cv2.imwrite(os.path.join(C.DEBUG_DIR, f"{int(time.time()*1000)}_{tag}.png"), img)
