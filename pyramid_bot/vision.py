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

    def cooldown_visible(self, img):
        """Pyramid finished: the progress bar shows a countdown like '2:39'
        instead of 'blocks / total'."""
        crop = self.crop(img, C.REGION_COUNTER)
        for prepared in (self._white_text(crop), self._bright_text(crop)):
            text = pytesseract.image_to_string(
                prepared, config="--psm 7 -c tessedit_char_whitelist=0123456789:/").replace(" ", "")
            if "/" not in text and re.search(r"\d{1,2}:\d{2}", text):
                return True
        return False

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

    def step_rows(self, img, min_len=150):
        """How many parallel near-horizontal edges are stacked in front of us.
        The pyramid's steps give several (one per layer); a plain wall gives 1-2."""
        import math
        x1, y1, x2, y2 = self._scale(C.STEPS_REGION)
        g = cv2.GaussianBlur(cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY), (5, 5), 0)
        lines = cv2.HoughLinesP(cv2.Canny(g, 30, 90), 1, np.pi / 360, 80,
                                minLineLength=int(min_len * self.sx), maxLineGap=10)
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

    def on_baseplate(self, img):
        """Normal camera: the grey stone baseplate of a new pyramid fills the
        whole ground around us (the path is only a narrow grey strip)."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h, w = hsv.shape[:2]
        band = hsv[int(h * 0.6):int(h * 0.92), int(w * 0.2):int(w * 0.95), 1]
        return float((band < C.BASEPLATE_MAX_SAT).mean()) > C.BASEPLATE_SHARE

    def stairs_ahead(self, img):
        """Normal camera: number of long horizontal step lines in front of (above
        on screen) the character. 0-1 = flat ground ahead: we're on top."""
        import math
        x1, y1, x2, y2 = self._scale(C.STAIRS_AHEAD_REGION)
        g = cv2.GaussianBlur(cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY), (5, 5), 0)
        lines = cv2.HoughLinesP(cv2.Canny(g, 30, 90), 1, np.pi / 360, 80,
                                minLineLength=int(C.STAIRS_MIN_LEN * self.sx), maxLineGap=10)
        if lines is None:
            return 0
        ys = []
        for ax, ay, bx, by in lines.reshape(-1, 4):
            a = (math.degrees(math.atan2(by - ay, bx - ax)) + 90) % 180 - 90
            if abs(a) < 15:
                ys.append((ay + by) / 2)
        rows = []
        for y in sorted(ys):
            if not rows or y - rows[-1] > 8 * self.sy:
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
        # only the LOWEST long edges count: those are the base steps next to us.
        # Higher ones can be a partly built layer whose edge ends mid-pyramid.
        long = [st[i] for i in range(1, n) if st[i][2] >= C.CORNER_MIN_LEN * self.sx]
        if not long:
            return None
        lowest = max(r[1] + r[3] for r in long)
        near = [r for r in long if r[1] + r[3] >= lowest - C.CORNER_LOW_BAND * self.sy]
        return (min(r[0] for r in near) / self.sx,
                max(r[0] + r[2] for r in near) / self.sx)

    def sign_top(self, img):
        """Top-down view: the green PYRAMID sign floating over the pyramid's
        middle. Returns (x, y) of its centre in 1080p pixels, or None."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        m = cv2.inRange(hsv, (40, 120, 120), (85, 255, 255))
        m[:int(160 * self.sy), int(600 * self.sx):int(1400 * self.sx)] = 0  # +1,000 buttons
        m = cv2.dilate(m, np.ones((9, 25), np.uint8))
        n, _, st, cen = cv2.connectedComponentsWithStats(m)
        best = None
        H, W = m.shape
        for i in range(1, n):
            x, y, w, h, area = st[i]
            if w < C.SIGN_TOP_MIN_W * self.sx or w < 3 * h:
                continue
            if x <= 2 or y <= 2 or x + w >= W - 2 or y + h >= H - 2:
                continue  # cut off by the screen edge: centre would be wrong
            if best is None or area > best[0]:
                best = (area, cen[i][0] / self.sx, cen[i][1] / self.sy)
        return None if best is None else (best[1], best[2])

    def cube_top(self, img):
        """Top-down view: the green placement cube nearest the character, as
        (dx, dy) pixels from it, or None. The PYRAMID sign (also green) and the
        HUD are ignored."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, *C.CUBE_TOP_HSV)
        for x1, y1, x2, y2 in C.STRIP_HUD_MASKS:
            mask[int(y1 * self.sy):int(y2 * self.sy), int(x1 * self.sx):int(x2 * self.sx)] = 0
        # blank the sign: big green blob of letters
        sign = cv2.dilate(cv2.inRange(hsv, (40, 120, 120), (85, 255, 255)), np.ones((9, 25), np.uint8))
        n, lab, st, _ = cv2.connectedComponentsWithStats(sign)
        for i in range(1, n):
            x, y, w, h, _a = st[i]
            if w >= C.SIGN_TOP_MIN_W * self.sx and w >= 3 * h:
                mask[max(0, y - 20):y + h + 20, max(0, x - 20):x + w + 20] = 0
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
        cx, cy = C.CHAR_POS
        best = None
        for i in range(1, n):
            area = stats[i][cv2.CC_STAT_AREA] / (self.sx * self.sy)
            if not (C.CUBE_TOP_MIN_AREA <= area <= C.INDICATOR_MAX_AREA):
                continue
            bw, bh = stats[i][cv2.CC_STAT_WIDTH], stats[i][cv2.CC_STAT_HEIGHT]
            if not (0.6 <= bw / max(bh, 1) <= 1.7) or area < 0.45 * bw * bh / (self.sx * self.sy):
                continue  # the cube is a filled square; a cactus is long and thin
            dx, dy = cents[i][0] / self.sx - cx, cents[i][1] / self.sy - cy
            d = (dx * dx + dy * dy) ** 0.5
            if d < C.CUBE_TOP_UNDER_PX:
                continue  # right under us: E is held, it gets placed anyway
            if best is None or d < best[2]:
                best = (dx, dy, d)
        return None if best is None else (best[0], best[1])

    def _side_edges_angle(self, lines):
        """No horizontal edge in view: use the pyramid's left and right edges.
        Seen from above with perspective they lean by the same amount in
        opposite directions when the camera is square; the average lean is the
        camera's turn."""
        import math
        cx = C.CHAR_POS[0] * self.sx
        left, right = [], []
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            a = math.degrees(math.atan2(x2 - x1, y2 - y1))  # lean from vertical
            a = (a + 90) % 180 - 90
            if abs(a) > 30:
                continue
            ln = math.hypot(x2 - x1, y2 - y1)
            (left if (x1 + x2) / 2 < cx else right).append((a, ln))
        if not left or not right:
            return None
        la = max(left, key=lambda t: t[1])[0]
        ra = max(right, key=lambda t: t[1])[0]
        return -(la + ra) / 2

    def top_angle(self, img):
        """Top-down view: tilt (degrees) of the pyramid's horizontal edge lines on
        screen. 0 = camera square to the pyramid. None if no long line is seen.
        (Only near-horizontal lines: the view's perspective slants the vertical
        ones even when the camera is square.)"""
        import math
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        e = cv2.Canny(cv2.GaussianBlur(g, (5, 5), 0), 40, 120)
        for x1, y1, x2, y2 in C.STRIP_HUD_MASKS:
            e[int(y1 * self.sy):int(y2 * self.sy), int(x1 * self.sx):int(x2 * self.sx)] = 0
        e[:int(160 * self.sy), :] = 0
        lines = cv2.HoughLinesP(e, 1, np.pi / 360, 120,
                                minLineLength=int(250 * self.sx), maxLineGap=20)
        if lines is None:
            return None
        angs, ws = [], []
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            a = (math.degrees(math.atan2(y2 - y1, x2 - x1)) + 90) % 180 - 90
            if abs(a) <= 40:
                angs.append(a)
                ws.append(math.hypot(x2 - x1, y2 - y1))
        if not angs:
            return self._side_edges_angle(lines)
        order = np.argsort(angs)
        a, w = np.array(angs)[order], np.array(ws)[order]
        cum = np.cumsum(w)
        return float(a[np.searchsorted(cum, cum[-1] / 2)])  # length-weighted median

    def stairs_side_top(self, img):
        """Top view: which side of the character the pyramid's stairs are on
        ("up"/"down"/"left"/"right" on screen), or None. Stairs = many long
        parallel lines; the side with the most of them near us wins."""
        import math
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        e = cv2.Canny(cv2.GaussianBlur(g, (5, 5), 0), 30, 90)
        for x1, y1, x2, y2 in C.STRIP_HUD_MASKS:
            e[int(y1 * self.sy):int(y2 * self.sy), int(x1 * self.sx):int(x2 * self.sx)] = 0
        e[:int(160 * self.sy), :] = 0
        lines = cv2.HoughLinesP(e, 1, np.pi / 360, 80, minLineLength=int(200 * self.sx), maxLineGap=10)
        if lines is None:
            return None
        cx, cy = C.CHAR_POS[0] * self.sx, C.CHAR_POS[1] * self.sy
        rows = {"up": set(), "down": set(), "left": set(), "right": set()}
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            a = (math.degrees(math.atan2(y2 - y1, x2 - x1)) + 180) % 180
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if a < 25 or a > 155:      # horizontal line: stairs above/below us
                rows["down" if my > cy else "up"].add(int(my / (8 * self.sy)))
            elif 55 < a < 125:          # vertical-ish line: stairs left/right
                rows["right" if mx > cx else "left"].add(int(mx / (8 * self.sx)))
        side, lines_n = max(((k, len(v)) for k, v in rows.items()), key=lambda kv: kv[1])
        return side if lines_n >= C.STAIRS_TOP_MIN_LINES else None

    def border_strips(self, img):
        """Top-down view: the dark strip around the pyramid's base. Returns the
        inner edge of each strip near the character, in 1080p pixels:
        {"left": x, "right": x, "top": y, "bottom": y} (only the visible ones)."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # "clearly darker than the top we stand on": the grey strip and the
        # shaded sides of the steps both qualify, the lit sand doesn't
        cx0, cy0 = int(C.CHAR_POS[0] * self.sx), int(C.CHAR_POS[1] * self.sy)
        around = hsv[max(0, cy0 - 200):cy0 + 200, max(0, cx0 - 300):cx0 + 300, 2]
        ref = float(np.median(around))
        m = (hsv[:, :, 2] < ref * C.STRIP_DARK_RATIO).astype(np.uint8) * 255
        # the green PYRAMID sign's dark letter outlines are not edges
        green = cv2.inRange(hsv, (40, 80, 80), (85, 255, 255))
        green = cv2.dilate(green, np.ones((61, 121), np.uint8))
        m[green > 0] = 0
        for r in C.STRIP_HUD_MASKS:
            x1, y1, x2, y2 = self._scale(r)
            m[y1:y2, x1:x2] = 0
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) > 0
        cx, cy = C.CHAR_POS
        band = C.STRIP_BAND
        skip = C.STRIP_SKIP_PX

        def nearest(profile_1d, center, scale):
            """Inner edge of the nearest strip on each side of center (1080p px)."""
            idx = np.flatnonzero(profile_1d)
            lo = idx[idx < center - int(skip * scale)]
            hi = idx[idx > center + int(skip * scale)]
            ok = C.STRIP_MIN_PX * scale
            return (lo.max() / scale if len(lo) >= ok else None,
                    hi.min() / scale if len(hi) >= ok else None)

        def consistent(vals):
            """A real pyramid edge is a long line: it must show up in at least two
            of the three bands, at about the same place (the jagged outline of a
            half-built layer doesn't)."""
            vals = [v for v in vals if v is not None]
            if len(vals) < 2:
                return None
            vals.sort()
            for i in range(len(vals) - 1):
                if vals[i + 1] - vals[i] < C.STRIP_AGREE_PX:
                    return (vals[i] + vals[i + 1]) / 2
            return None

        found = {}
        # vertical strips: rows above, level with and below the character
        lefts, rights = [], []
        for off in (-C.STRIP_BAND_GAP, 0, C.STRIP_BAND_GAP):
            y1 = int((cy + off - band) * self.sy)
            y2 = int((cy + off + band) * self.sy)
            if y1 < 0 or y2 > m.shape[0]:
                continue
            l, r = nearest(m[y1:y2].mean(axis=0) > C.STRIP_FILL, int(cx * self.sx), self.sx)
            lefts.append(l)
            rights.append(r)
        for side, vals in (("left", lefts), ("right", rights)):
            v = consistent(vals)
            if v is not None:
                found[side] = v
        # horizontal strips: columns left of, at and right of the character
        tops, bottoms = [], []
        for off in (-C.STRIP_BAND_GAP, 0, C.STRIP_BAND_GAP):
            x1 = int((cx + off - band) * self.sx)
            x2 = int((cx + off + band) * self.sx)
            t, b2 = nearest(m[:, x1:x2].mean(axis=1) > C.STRIP_FILL, int(cy * self.sy), self.sy)
            tops.append(t)
            bottoms.append(b2)
        for side, vals in (("top", tops), ("bottom", bottoms)):
            v = consistent(vals)
            if v is not None:
                found[side] = v
        return found

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
            tiny = which == "pyramid" and px < C.MIN_SIGN_PIXELS * self.sx * self.sy
            if tiny:
                # far away: a few pixels of thin text, its panel too small to check
                if px < C.FAR_SIGN_MIN_PIXELS * self.sx * self.sy or y < 150 * self.sy \
                        or w / max(h, 1) < 5:
                    continue
            elif px < C.MIN_SIGN_PIXELS * self.sx * self.sy:
                continue
            elif which == "pyramid" and self._panel_ratio(img, x, y, w, h) < C.PYRAMID_PANEL_MIN:
                continue  # green text without the sign's panel: gym label etc.
            if best is None or px > best[1]:
                best = (cents[i][0], px, cents[i][1] / self.sy)
        if best is None and which == "pyramid":
            best = self._far_pyramid_sign(img)
        if best is None and which == "blocks":
            best = self._far_blocks_sign(img)
        if best is None:
            return None, 0
        self.last_sign_y = best[2]  # height on screen (1080p), used to tell "right under it"
        half = img.shape[1] / 2
        return (float(best[0]) - half) / half, best[1]

    def _far_pyramid_sign(self, img):
        """The PYRAMID sign from far away: a small thin strip of green (letters
        plus their darker outline) up in the sky. Returns (x, pixels, y1080) or None."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        m = cv2.inRange(hsv, *C.FAR_SIGN_HSV)
        y0, y1 = int(C.FAR_SIGN_Y[0] * self.sy), int(C.FAR_SIGN_Y[1] * self.sy)
        m[:y0, :] = 0
        m[y1:, :] = 0
        joined = cv2.dilate(m, np.ones((3, 9), np.uint8))
        n, _, st, cen = cv2.connectedComponentsWithStats(joined)
        best = None
        for i in range(1, n):
            x, y, w, h = st[i][:4]
            if not (C.FAR_SIGN_W[0] * self.sx <= w <= C.FAR_SIGN_W[1] * self.sx):
                continue
            if w / max(h, 1) < 3.5:
                continue
            px = int(cv2.countNonZero(m[y:y + h, x:x + w]))
            if px < C.FAR_SIGN_MIN_PIXELS * self.sx * self.sy:
                continue
            if best is None or px > best[1]:
                best = (cen[i][0], px, cen[i][1] / self.sy)
        return best

    def _far_blocks_sign(self, img):
        """The red BLOCKS sign from far away / from high up (e.g. on top of the
        pyramid it shows small and below the horizon)."""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        m = cv2.inRange(hsv, (0, 175, 90), (8, 255, 255)) | cv2.inRange(hsv, (172, 175, 90), (179, 255, 255))
        m[:int(160 * self.sy), :] = 0                     # +10,000 buttons etc.
        m[int(C.FAR_BLOCKS_MAX_Y * self.sy):, :] = 0
        for x1, y1, x2, y2 in C.STRIP_HUD_MASKS:
            m[int(y1 * self.sy):int(y2 * self.sy), int(x1 * self.sx):int(x2 * self.sx)] = 0
        joined = cv2.dilate(m, np.ones((3, 9), np.uint8))
        n, _, st, cen = cv2.connectedComponentsWithStats(joined)
        best = None
        for i in range(1, n):
            x, y, w, h = st[i][:4]
            if not (C.FAR_SIGN_W[0] * self.sx <= w <= C.FAR_SIGN_W[1] * self.sx) or w / max(h, 1) < 3.5:
                continue
            px = int(cv2.countNonZero(m[y:y + h, x:x + w]))
            if px < C.FAR_SIGN_MIN_PIXELS * self.sx * self.sy:
                continue
            if best is None or px > best[1]:
                best = (cen[i][0], px, cen[i][1] / self.sy)
        return best

    def pyramid_sign_far(self, img):
        """A tiny PYRAMID sign high up near the middle of the screen = the pyramid
        is still far ahead (whatever blocks us isn't it)."""
        mask = self._sign_mask(img, C.GREEN_RANGES)
        mask[int(C.SIGN_MAX_Y * self.sy):, :] = 0
        mask[:int(C.WALL_SIGN_FAR_Y * self.sy), :] = 0  # high up = we're close to it
        joined = cv2.dilate(mask, np.ones((5, 15), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(joined)
        mid = img.shape[1] / 2
        for i in range(1, n):
            x, y, w, h = stats[i][:4]
            px = cv2.countNonZero(mask[y:y + h, x:x + w])
            if h and w / h >= C.SIGN_MIN_ASPECT and 10 * self.sx * self.sy <= px \
                    < C.WALL_SIGN_FAR_PX * self.sx * self.sy and abs(x + w / 2 - mid) < 500 * self.sx:
                return True
        return False

    # ---------- Debug ----------
    def save(self, img, tag):
        if C.SAVE_SCREENSHOTS:
            cv2.imwrite(os.path.join(C.DEBUG_DIR, f"{int(time.time()*1000)}_{tag}.png"), img)
