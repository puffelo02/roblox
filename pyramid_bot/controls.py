"""Keyboard input and the stop/pause hotkeys."""
import time

import pydirectinput
from pynput import keyboard

from . import config as C

pydirectinput.PAUSE = 0


class Stopped(Exception):
    pass


class Controls:
    def __init__(self):
        self.stop = False
        self.paused = False
        self.held = set()
        keyboard.Listener(on_press=self._on_key).start()

    def _on_key(self, key):
        name = getattr(key, "name", None)
        if name == C.STOP_KEY:
            self.stop = True
        elif name == C.PAUSE_KEY:
            self.paused = not self.paused
            if self.paused:
                self.release_all()
            print("PAUSED" if self.paused else "RESUMED")

    def check(self):
        while self.paused and not self.stop:
            time.sleep(0.1)
        if self.stop:
            self.release_all()
            raise Stopped()

    def sleep(self, sec):
        end = time.time() + sec
        while time.time() < end:
            self.check()
            time.sleep(min(0.05, max(0, end - time.time())))

    def down(self, key):
        pydirectinput.keyDown(key)
        self.held.add(key)

    def up(self, key):
        pydirectinput.keyUp(key)
        self.held.discard(key)

    def hold(self, key, sec):
        self.down(key)
        try:
            self.sleep(sec)
        finally:
            self.up(key)

    def release_all(self):
        for k in list(self.held):
            pydirectinput.keyUp(k)
        self.held.clear()

    # camera
    def turn_left(self, sec=C.TURN_90_SEC):
        self.hold("left", sec)

    def turn_right(self, sec=C.TURN_90_SEC):
        self.hold("right", sec)

    def jump_forward(self, landing=0.4):
        self.down("w")
        self.sleep(0.05)
        self.hold("space", C.JUMP_HOLD_SEC)
        self.sleep(landing)
        self.up("w")

    def right_drag(self, dy_px, steps=10):
        """Hold right mouse and move vertically: tilts the Roblox camera
        (positive = look further down)."""
        pydirectinput.mouseDown(button="right")
        try:
            time.sleep(0.05)
            for _ in range(steps):
                pydirectinput.moveRel(0, int(dy_px / steps), relative=True)
                time.sleep(0.02)
        finally:
            pydirectinput.mouseUp(button="right")

    def click(self, xy):
        """Roblox ignores a click that arrives together with the mouse move:
        move, wiggle so it registers the hover, then press and release slowly."""
        pydirectinput.moveTo(*xy)
        time.sleep(0.1)
        pydirectinput.moveRel(3, 0, relative=True)
        time.sleep(0.05)
        pydirectinput.moveRel(-3, 0, relative=True)
        time.sleep(0.1)
        pydirectinput.mouseDown()
        time.sleep(0.1)
        pydirectinput.mouseUp()
