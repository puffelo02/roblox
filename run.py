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

BRANCH = "claude/roblox-pyramid-game-dqk1s7"
URL = "https://codeload.github.com/puffelo02/roblox/zip/refs/heads/" + BRANCH
API = "https://api.github.com/repos/puffelo02/roblox/commits/" + BRANCH
HERE = os.path.dirname(os.path.abspath(__file__))


def update():
    print("Downloading the latest version...")
    # ask for the newest commit first and download exactly that one: the
    # branch zip can be cached by GitHub for a few minutes after a push
    url, sha = URL, None
    try:
        req = urllib.request.Request(API, headers={"Accept": "application/vnd.github.sha"})
        sha = urllib.request.urlopen(req, timeout=15).read().decode().strip()
        url = "https://codeload.github.com/puffelo02/roblox/zip/" + sha
    except Exception as e:
        print("(couldn't ask GitHub for the newest commit, using the branch zip:", e, ")")
    data = urllib.request.urlopen(url, timeout=30).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = z.namelist()[0].split("/")[0]
        # GitHub stores the commit id in the zip itself
        sha = z.comment.decode(errors="ignore").strip() or sha
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
    with open(os.path.join(HERE, "VERSION.txt"), "w") as f:
        f.write((sha[:7] if sha else "latest") + "\n")
    print("Updated to version", sha[:7] if sha else "(latest)",
          "\n(Put your own settings in my_settings.py: updates never overwrite it)")
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
