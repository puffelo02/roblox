# Pyramid Bot

Screen-reading bot for the Roblox pyramid game. It collects blocks, walks to the
pyramid and places them in a shrinking spiral, one layer at a time.

> Automating gameplay is against Roblox's rules, so your account could be banned. Use it at your own risk.

## Setup (Windows)

1. Install **Tesseract OCR**: https://github.com/UB-Mannheim/tesseract/wiki
   (default path `C:\Program Files\Tesseract-OCR\tesseract.exe`, change `TESSERACT_CMD` in `config.py` if different).
2. `pip install -r requirements.txt`
3. Roblox **fullscreen**, 1920x1080 recommended (other sizes are scaled).
4. In game, **lower your Walk Speed** (pencil icon) to ~100-200 so key taps are controllable.

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
3. Steers toward the green **PYRAMID** sign, walks onto the plot, and jumps up until placing works.
4. Walks a clockwise spiral, holding E at each spot. The block counter tells it whether a spot
   still takes blocks. It skips quickly over full stretches, and if a whole ring does nothing
   it assumes it fell off and climbs back up.
5. Repeats until the counter reaches the target.

## Tuning / sending feedback

All values are in `pyramid_bot/config.py`. The most important one is `TURN_90_SEC`: how long
holding an arrow key turns the camera 90°.
When something goes wrong, send `bot.log` and the images in `debug/`.
