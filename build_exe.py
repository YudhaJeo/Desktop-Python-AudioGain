"""
build_exe.py — Generate mic_booster_pro.exe
============================================
Requirements:
    pip install pyinstaller sounddevice numpy pystray pillow

Usage:
    python build_exe.py

Output:
    dist/MicBoostPro/MicBoostPro.exe   (folder mode, recommended)
    — OR —
    dist/MicBoostPro.exe               (single-file mode, slower cold start)

Place app-icon.png in the same folder as this script before building.
"""

import subprocess
import sys
import os

# ── Config ────────────────────────────────────────────────────────────────────
APP_NAME   = "MicBoostPro"
SCRIPT     = "mic_booster_pro.py"
ICON_FILE  = "app-icon.png"     # used as window & tray icon
ONE_FILE   = False              # True = single .exe (slower), False = folder (faster)

# ── Build ─────────────────────────────────────────────────────────────────────
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(here, SCRIPT)
    icon_path   = os.path.join(here, ICON_FILE)

    if not os.path.exists(script_path):
        print(f"[ERROR] {SCRIPT} not found in {here}")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconsole",                     # no black terminal window
        "--clean",
        "--noconfirm",
    ]

    if ONE_FILE:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    # Bundle the icon so resource_path() finds it at runtime
    if os.path.exists(icon_path):
        # --add-data src;dest  (Windows uses semicolon)
        cmd += ["--add-data", f"{icon_path};."]
        # also set .ico for the exe itself (needs .ico format; PIL converts it)
        ico_path = os.path.join(here, "app-icon.ico")
        _make_ico(icon_path, ico_path)
        if os.path.exists(ico_path):
            cmd += ["--icon", ico_path]
    else:
        print(f"[WARN] {ICON_FILE} not found — building without custom icon")

    cmd.append(script_path)

    print("\n[BUILD] Running PyInstaller...\n")
    print(" ".join(cmd), "\n")
    result = subprocess.run(cmd, cwd=here)

    if result.returncode == 0:
        out = os.path.join(here, "dist", APP_NAME)
        print(f"\n[OK] Build complete → {out}")
        if not ONE_FILE:
            print(f"     Run: {os.path.join(out, APP_NAME + '.exe')}")
    else:
        print("\n[FAIL] PyInstaller returned non-zero exit code.")
        sys.exit(result.returncode)


def _make_ico(png_path, ico_path):
    """Convert PNG → ICO using Pillow (required by PyInstaller --icon)."""
    try:
        from PIL import Image
        img = Image.open(png_path).convert("RGBA")
        sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
        imgs  = [img.resize(s, Image.LANCZOS) for s in sizes]
        imgs[0].save(ico_path, format="ICO", sizes=sizes, append_images=imgs[1:])
        print(f"[OK] Created {ico_path}")
    except Exception as e:
        print(f"[WARN] Could not create .ico: {e}")


if __name__ == "__main__":
    main()
