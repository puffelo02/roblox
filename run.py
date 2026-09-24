"""Update to the latest bot version from GitHub, then start it.

Double-click this file, or run:   python run.py
Add --no-update to start without downloading:   python run.py --no-update
Add --recalibrate after changing your Walk Speed: python run.py --recalibrate
"""
import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

URL = "https://codeload.github.com/puffelo02/roblox/zip/refs/heads/claude/roblox-pyramid-game-dqk1s7"
HERE = os.path.dirname(os.path.abspath(__file__))


def update():
    print("Downloading the latest version...")
    data = urllib.request.urlopen(URL, timeout=30).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = z.namelist()[0].split("/")[0]
        # keep a copy of your config in case you changed values in it
        cfg = os.path.join(HERE, "pyramid_bot", "config.py")
        if os.path.exists(cfg):
            shutil.copy(cfg, os.path.join(HERE, "config_backup.py"))
        for name in z.namelist():
            rel = name[len(root) + 1:]
            if not rel or name.endswith("/"):
                continue
            dest = os.path.join(HERE, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(name) as src, open(dest, "wb") as out:
                out.write(src.read())
    print("Updated. (Your previous config is saved as config_backup.py)")
    subprocess.call([sys.executable, "-m", "pip", "install", "-q", "-r",
                     os.path.join(HERE, "requirements.txt")])


def main():
    os.chdir(HERE)
    if "--no-update" not in sys.argv:
        try:
            update()
        except Exception as e:
            print("Update failed, starting the version already here:", e)
    if "--recalibrate" in sys.argv and os.path.exists("calibration.json"):
        os.remove("calibration.json")
        print("Calibration reset: the bot will measure walk and turn speed again.")
    subprocess.call([sys.executable, "-m", "pyramid_bot.bot"])
    input("Bot stopped. Press Enter to close.")


if __name__ == "__main__":
    main()
