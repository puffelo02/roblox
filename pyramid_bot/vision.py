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

    def _read_pair(self, img, region):
        """Reads 'a / b' and returns (a, b) or None."""
        prepared = self._white_text(self.crop(img, region))
        for cfg in ("--psm 7", "--psm 7 -c tessedit_char_whitelist=0123456789/,"):
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
