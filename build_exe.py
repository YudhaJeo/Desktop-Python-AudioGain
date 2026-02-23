# build_exe.py
"""
build_exe.py — Generate MicFckinBoost.exe
========================================
Requirements:
    pip install pyinstaller sounddevice numpy pystray pillow

Usage:
    python build_exe.py

Output:
    dist/MicFckinBoost/MicFckinBoost.exe   (folder mode — recommended, fast startup)

Folder structure expected:
    ├── assets/
    │   ├── app-icon.ico
    │   └── app-icon.png
    ├── build_exe.py
    └── mic_booster_pro.py
"""

import subprocess
import sys
import os

# ── Config ────────────────────────────────────────────────────────────────────
APP_NAME  = "MicFckinBoost"
SCRIPT    = "mic_booster_pro.py"
ONE_FILE  = False   # False = folder mode (recommended), True = single .exe

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    here        = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(here, SCRIPT)
    assets_dir  = os.path.join(here, "assets")
    ico_path    = os.path.join(assets_dir, "app-icon.ico")
    png_path    = os.path.join(assets_dir, "app-icon.png")

    if not os.path.exists(script_path):
        print(f"[ERROR] {SCRIPT} not found in {here}")
        sys.exit(1)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconsole",
        "--clean",
        "--noconfirm",
    ]

    if ONE_FILE:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    # Bundle entire assets/ folder so resource_path("assets/...") works at runtime
    if os.path.isdir(assets_dir):
        # Syntax: src;dest_folder  (Windows semicolon)
        cmd += ["--add-data", f"{assets_dir};assets"]
        print(f"[INFO] Bundling assets/ folder")
    else:
        print(f"[WARN] assets/ folder not found — building without icons")

    # Set exe icon (requires .ico)
    if os.path.exists(ico_path):
        cmd += ["--icon", ico_path]
        print(f"[INFO] Using existing {ico_path}")
    elif os.path.exists(png_path):
        # Auto-convert PNG → ICO
        _make_ico(png_path, ico_path)
        if os.path.exists(ico_path):
            cmd += ["--icon", ico_path]
    else:
        print("[WARN] No icon file found in assets/")

    cmd.append(script_path)

    print(f"\n[BUILD] Running PyInstaller...\n")
    result = subprocess.run(cmd, cwd=here)

    if result.returncode == 0:
        out = os.path.join(here, "dist", APP_NAME)
        exe = os.path.join(out, APP_NAME + ".exe")
        print(f"\n[OK] Build complete!")
        print(f"     EXE → {exe}")
    else:
        print("\n[FAIL] PyInstaller exited with errors.")
        sys.exit(result.returncode)


def _make_ico(png_path, ico_path):
    """Convert PNG → multi-size ICO using Pillow."""
    try:
        from PIL import Image
        img   = Image.open(png_path).convert("RGBA")
        sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
        imgs  = [img.resize(s, Image.LANCZOS) for s in sizes]
        imgs[0].save(ico_path, format="ICO", sizes=sizes,
                     append_images=imgs[1:])
        print(f"[OK] Created {ico_path}")
    except Exception as e:
        print(f"[WARN] Could not create .ico: {e}")


if __name__ == "__main__":
    main()
