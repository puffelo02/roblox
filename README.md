# Pyramid Bot

Screen-reading bot for the Roblox pyramid game. It collects blocks, walks to the
pyramid and places them in a shrinking spiral, one layer at a time.

> Automating gameplay is against Roblox's rules, so your account could be banned. Use it at your own risk.

## Setup (Windows)

1. Install **Tesseract OCR**: https://github.com/UB-Mannheim/tesseract/wiki
   (default path `C:\Program Files\Tesseract-OCR\tesseract.exe`, change `TESSERACT_CMD` in `config.py` if different).
2. `pip install -r requirements.txt`
3. Roblox **fullscreen**, 1920x1080 recommended (other sizes are scaled).
4. In game, set your **Walk Speed to 30** (pencil icon). The bot tracks its position by walking time.
5. Roblox settings: **Camera Mode = Classic** (so the camera doesn't swing around when strafing).

## Check first

```
python -m pyramid_bot.calibrate
```
Switch to Roblox. It prints what it reads (counter, capacity, prompt, signs) every second
and saves `calibrate_regions.png`. Make sure the numbers match the screen.

## Run

Easiest: double-click `run.py` (or `python run.py`). It downloads the latest version, then starts the bot.

Manual:

Stand near the pyramid, camera looking forward and slightly down, then:
```
python -m pyramid_bot.bot
```
You have 5 seconds to click into Roblox. **F7** pauses or resumes, **F8** stops.

## How it works

1. Steers with the arrow keys toward the red **BLOCKS** sign until the "E Block Pick Up" prompt shows.
2. Holds E until Capacity is full.
3. Steers toward the green **PYRAMID** sign until it bumps into the base wall.
4. **Anchors**: squares the camera to the wall (step edges horizontal), slides right until the
   wall ends (= corner), steps back in and climbs straight up. Now it knows where it is.
5. **Spiral**: from the block counter it knows which layer is being built and how big it is
   (171,700 = 100² + 98² + … + 2²). It walks corner to corner, tighter toward the middle;
   the next layer goes from the middle back out to the corners.
6. When empty (or lost), it goes back to BLOCKS and re-anchors on the next trip.

The first run measures camera turn speed and walk speed (one full side of the base) and saves
them in `calibration.json`. After changing Walk Speed, run `python run.py --recalibrate`.

## Tuning / sending feedback

All values are in `pyramid_bot/config.py`. The most important one is `TURN_90_SEC`: how long
holding an arrow key turns the camera 90°.
When something goes wrong, send `bot.log` and the images in `debug/`.
