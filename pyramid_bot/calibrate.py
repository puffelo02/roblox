"""Quick checks before running the bot.

python -m pyramid_bot.calibrate   -> prints what the bot reads on screen every second
                                     and saves a screenshot with the regions drawn.
"""
import time

import cv2

from . import config as C
from .vision import Vision


def main():
    v = Vision()
    print("Switch to Roblox. Reading every second, Ctrl+C to quit.")
    time.sleep(3)
    img = v.grab()
    marked = img.copy()
    for r in (C.REGION_COUNTER, C.REGION_CAPACITY, C.REGION_PROMPT):
        x1, y1, x2, y2 = v._scale(r)
        cv2.rectangle(marked, (x1, y1), (x2, y2), (0, 0, 255), 3)
    cv2.imwrite("calibrate_regions.png", marked)
    print("saved calibrate_regions.png: check the red boxes surround the numbers")
    try:
        while True:
            img = v.grab()
            print(
                "counter", v.read_counter(img),
                "| capacity", v.read_capacity(img),
                "| prompt", v.pickup_prompt_visible(img),
                "| BLOCKS sign", v.find_sign(img, "blocks"),
                "| PYRAMID sign", v.find_sign(img, "pyramid"),
            )
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
