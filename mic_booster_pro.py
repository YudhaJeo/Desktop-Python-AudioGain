import sounddevice as sd
import numpy as np
import tkinter as tk
from tkinter import ttk
from threading import Thread
import math
import sys
import os

# ─── Tray (pystray + PIL) ─────────────────────────────────────────────────────
import pystray
from PIL import Image, ImageDraw

# ─── State ───────────────────────────────────────────────────────────────────
gain_value = 1.0
running    = False
monitoring = False
audio_thread = None
input_device  = None
output_device = None
monitor_device = None

tray_icon = None   # pystray.Icon instance
app_hidden = False

# ─── Colors ──────────────────────────────────────────────────────────────────
BG         = "#0d0d0f"
SURFACE    = "#141418"
SURFACE2   = "#1c1c22"
BORDER     = "#2a2a35"
ACCENT     = "#00e5ff"
ACCENT_DIM = "#00bcd4"
FG         = "#e8e8f0"
FG_DIM     = "#6b6b80"
RED        = "#ff4466"
GREEN      = "#00ff88"

FONT_MONO  = ("Consolas", 9)
FONT_LABEL = ("Segoe UI", 9)
FONT_TITLE = ("Segoe UI Semibold", 11)
FONT_BIG   = ("Consolas", 26, "bold")

# ─── Resource path (works for both dev & PyInstaller) ────────────────────────
def resource_path(filename):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

# ─── Devices ─────────────────────────────────────────────────────────────────
def get_clean_devices():
    devices = sd.query_devices()
    inputs, outputs = [], []
    seen_in, seen_out = set(), set()
    for d in devices:
        name = d['name']
        if "Mapper" in name or "Primary" in name:
            continue
        if d['max_input_channels'] > 0 and name not in seen_in:
            inputs.append(name)
            seen_in.add(name)
        if d['max_output_channels'] > 0 and name not in seen_out:
            outputs.append(name)
            seen_out.add(name)
    return inputs, outputs

# ─── Audio ────────────────────────────────────────────────────────────────────
def audio_callback(indata, outdata, frames, time, status):
    global gain_value, monitoring
    if status:
        print(status)
    boosted = np.clip(indata * gain_value, -1.0, 1.0)
    outdata[:] = boosted
    if monitoring and monitor_device is not None:
        try:
            sd.play(boosted, device=monitor_device, samplerate=48000, blocking=False)
        except:
            pass

def audio_loop():
    global running
    try:
        with sd.Stream(
            device=(input_device, output_device),
            channels=1, samplerate=48000,
            blocksize=256, callback=audio_callback
        ):
            while running:
                sd.sleep(100)
    except Exception as e:
        root.after(0, lambda: status_label.config(text=f"ERR: {e}", fg=RED))

# ─── Logic ────────────────────────────────────────────────────────────────────
def update_gain(val):
    global gain_value
    v = int(float(val))
    gain_value = 1 + (v / 50)
    db = round(20 * math.log10(gain_value), 1) if gain_value > 0 else 0
    gain_val_label.config(text=f"{v:03d}")
    db_label.config(text=f"+{db} dB")

def toggle_monitor():
    global monitoring, monitor_device
    monitoring = not monitoring
    monitor_device = monitor_var.get()
    if monitoring:
        monitor_btn.config(text="● MON  ON", fg=GREEN, bg=SURFACE2,
                           highlightbackground=GREEN)
    else:
        monitor_btn.config(text="○ MON OFF", fg=FG_DIM, bg=SURFACE,
                           highlightbackground=BORDER)

def start_audio():
    global running, audio_thread, input_device, output_device
    if running:
        return
    input_device  = input_var.get()
    output_device = output_var.get()
    running = True
    audio_thread = Thread(target=audio_loop, daemon=True)
    audio_thread.start()
    status_dot.config(fg=GREEN, text="●")
    status_label.config(text="LIVE", fg=GREEN)
    start_btn.config(fg=FG_DIM)
    stop_btn.config(fg=RED)
    update_tray_tooltip()

def stop_audio():
    global running
    running = False
    status_dot.config(fg=FG_DIM, text="●")
    status_label.config(text="IDLE", fg=FG_DIM)
    start_btn.config(fg=ACCENT)
    stop_btn.config(fg=FG_DIM)
    update_tray_tooltip()

def exit_app(icon=None, item=None):
    global running, tray_icon
    running = False
    if tray_icon:
        tray_icon.stop()
    root.destroy()

# ─── Autorun Registry ─────────────────────────────────────────────────────────
def set_autorun(enable=True):
    """Add/remove app from Windows startup via registry."""
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "MicBoostPro"
        exe_path = sys.executable if getattr(sys, "frozen", False) else \
                   f'"{sys.executable}" "{os.path.abspath(__file__)}"'

        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path,
                             0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Autorun error: {e}")

def is_autorun_enabled():
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path,
                             0, winreg.KEY_READ)
        winreg.QueryValueEx(key, "MicBoostPro")
        winreg.CloseKey(key)
        return True
    except:
        return False

# ─── System Tray ──────────────────────────────────────────────────────────────
def load_tray_image():
    icon_path = resource_path("app-icon.png")
    if os.path.exists(icon_path):
        img = Image.open(icon_path).convert("RGBA").resize((64, 64))
        return img
    # fallback: generate simple cyan circle
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(0, 229, 255, 255))
    draw.ellipse([20, 16, 44, 48], fill=(13, 13, 15, 255))
    return img

def show_window(icon=None, item=None):
    global app_hidden
    app_hidden = False
    root.after(0, _do_show)

def _do_show():
    root.deiconify()
    root.lift()
    root.focus_force()

def hide_window():
    global app_hidden
    app_hidden = True
    root.withdraw()

def update_tray_tooltip():
    if tray_icon:
        state = "LIVE" if running else "IDLE"
        tray_icon.title = f"MicBoost — {state}"

def on_tray_click(icon, button, time):
    """Double-click tray icon to toggle window."""
    if button == pystray.mouse.Button.left:
        if app_hidden:
            show_window()
        else:
            hide_window()

def toggle_autorun_menu(icon, item):
    current = is_autorun_enabled()
    set_autorun(not current)

def build_tray():
    global tray_icon

    def autorun_checked(item):
        return is_autorun_enabled()

    menu = pystray.Menu(
        pystray.MenuItem("Show / Hide", show_window, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("▶  Start",  lambda i, it: root.after(0, start_audio)),
        pystray.MenuItem("■  Stop",   lambda i, it: root.after(0, stop_audio)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Run at Startup", toggle_autorun_menu,
                         checked=autorun_checked),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", exit_app),
    )

    tray_icon = pystray.Icon(
        "MicBoostPro",
        load_tray_image(),
        "MicBoost — IDLE",
        menu
    )
    # pystray runs its own loop in a thread
    tray_thread = Thread(target=tray_icon.run, daemon=True)
    tray_thread.start()

# ─── Window close → hide to tray ─────────────────────────────────────────────
def on_close():
    hide_window()

# ─── UI ───────────────────────────────────────────────────────────────────────
root = tk.Tk()
root.title("MIC BOOST")
root.geometry("460x560")
root.resizable(False, False)
root.configure(bg=BG)
root.protocol("WM_DELETE_WINDOW", on_close)

# Set window icon
icon_path = resource_path("app-icon.png")
if os.path.exists(icon_path):
    try:
        icon_img = tk.PhotoImage(file=icon_path)
        root.iconphoto(True, icon_img)
    except:
        pass

def mk_label(parent, text, fg=FG_DIM, font=FONT_LABEL, **kw):
    return tk.Label(parent, text=text, fg=fg, bg=parent["bg"], font=font, **kw)

def mk_divider(parent, pad=(8, 8)):
    f = tk.Frame(parent, bg=BORDER, height=1)
    f.pack(fill="x", padx=20, pady=pad)

def styled_dropdown(parent, var, options):
    frame = tk.Frame(parent, bg=SURFACE2, highlightbackground=BORDER,
                     highlightthickness=1)
    frame.pack(fill="x", padx=20, pady=3)
    short = [o[:42] + "…" if len(o) > 42 else o for o in options]
    name_map = dict(zip(short, options))
    short_var = tk.StringVar(value=short[0] if short else "")

    def on_change(*a):
        full = name_map.get(short_var.get(), short_var.get())
        var.set(full)

    short_var.trace_add("write", on_change)
    var.set(options[0] if options else "")

    menu = tk.OptionMenu(frame, short_var, *short)
    menu.config(bg=SURFACE2, fg=FG, activebackground=SURFACE,
                activeforeground=ACCENT, relief="flat", bd=0,
                highlightthickness=0, font=FONT_LABEL, indicatoron=True,
                anchor="w", width=46)
    menu["menu"].config(bg=SURFACE2, fg=FG, activebackground=ACCENT_DIM,
                        activeforeground=ACCENT, relief="flat", bd=0,
                        font=FONT_LABEL)
    menu.pack(fill="x", padx=6, pady=4)
    return frame

# ══ Header ══
header = tk.Frame(root, bg=BG)
header.pack(fill="x", padx=20, pady=(20, 4))

mk_label(header, "MIC", fg=ACCENT, font=("Consolas", 18, "bold")).pack(side="left")
mk_label(header, "BOOST", fg=FG, font=("Consolas", 18, "bold")).pack(side="left", padx=(2, 0))

badge = tk.Frame(header, bg=BG)
badge.pack(side="right", pady=4)
status_dot = tk.Label(badge, text="●", fg=FG_DIM, bg=BG, font=("Consolas", 10))
status_dot.pack(side="left")
status_label = tk.Label(badge, text="IDLE", fg=FG_DIM, bg=BG, font=FONT_MONO)
status_label.pack(side="left", padx=(3, 0))

mk_divider(root, (4, 12))

# ══ Device Section ══
inputs, outputs = get_clean_devices()
section = tk.Frame(root, bg=BG)
section.pack(fill="x")

mk_label(section, "INPUT", fg=FG_DIM, font=FONT_MONO).pack(anchor="w", padx=20)
input_var = tk.StringVar()
styled_dropdown(section, input_var, inputs if inputs else ["No input found"])

tk.Frame(section, bg=BG, height=6).pack()

mk_label(section, "OUTPUT  /  VB‑CABLE", fg=FG_DIM, font=FONT_MONO).pack(anchor="w", padx=20)
output_var = tk.StringVar()
styled_dropdown(section, output_var, outputs if outputs else ["No output found"])

tk.Frame(section, bg=BG, height=6).pack()

mk_label(section, "MONITOR", fg=FG_DIM, font=FONT_MONO).pack(anchor="w", padx=20)
monitor_var = tk.StringVar()
styled_dropdown(section, monitor_var, outputs if outputs else ["No output found"])

mk_divider(root, (14, 8))

# ══ Gain Section ══
gain_sec = tk.Frame(root, bg=BG)
gain_sec.pack(fill="x", padx=20)

gain_hdr = tk.Frame(gain_sec, bg=BG)
gain_hdr.pack(fill="x")
mk_label(gain_hdr, "GAIN", fg=FG_DIM, font=FONT_MONO).pack(side="left")
db_label = tk.Label(gain_hdr, text="+0.0 dB", fg=FG_DIM, bg=BG, font=FONT_MONO)
db_label.pack(side="right")

gain_val_label = tk.Label(gain_sec, text="000", fg=ACCENT, bg=BG, font=FONT_BIG)
gain_val_label.pack(pady=(2, 6))

style = ttk.Style()
style.theme_use("clam")
style.configure("Gain.Horizontal.TScale",
                background=BG, troughcolor=SURFACE2,
                sliderthickness=18, sliderrelief="flat")

slider = ttk.Scale(gain_sec, from_=0, to=200, orient="horizontal",
                   command=update_gain, style="Gain.Horizontal.TScale")
slider.set(0)
slider.pack(fill="x")

tick_row = tk.Frame(gain_sec, bg=BG)
tick_row.pack(fill="x")
for t in ["0", "50", "100", "150", "200"]:
    mk_label(tick_row, t, fg=FG_DIM, font=("Consolas", 7)).pack(side="left", expand=True)

mk_divider(root, (12, 10))

# ══ Controls ══
ctrl = tk.Frame(root, bg=BG)
ctrl.pack(fill="x", padx=20, pady=4)

def mk_btn(parent, text, cmd, fg=ACCENT, side="left"):
    b = tk.Button(parent, text=text, command=cmd,
                  fg=fg, bg=SURFACE, activeforeground=FG,
                  activebackground=SURFACE2, relief="flat", bd=0,
                  highlightbackground=BORDER, highlightthickness=1,
                  font=FONT_MONO, padx=14, pady=8, cursor="hand2")
    b.pack(side=side, padx=4, expand=True, fill="x")
    return b

start_btn = mk_btn(ctrl, "▶  START", start_audio, fg=ACCENT)
stop_btn  = mk_btn(ctrl, "■  STOP",  stop_audio,  fg=FG_DIM)

monitor_btn = tk.Button(root, text="○ MON OFF",
                         command=toggle_monitor,
                         fg=FG_DIM, bg=SURFACE,
                         activeforeground=GREEN,
                         activebackground=SURFACE2,
                         relief="flat", bd=0,
                         highlightbackground=BORDER, highlightthickness=1,
                         font=FONT_MONO, padx=14, pady=8, cursor="hand2")
monitor_btn.pack(fill="x", padx=24, pady=(2, 4))

# ══ Autorun toggle in UI ══
autorun_frame = tk.Frame(root, bg=BG)
autorun_frame.pack(fill="x", padx=24, pady=(0, 2))

autorun_var = tk.BooleanVar(value=is_autorun_enabled())

def toggle_autorun_ui():
    set_autorun(autorun_var.get())

autorun_check = tk.Checkbutton(
    autorun_frame, text="Run at Windows startup",
    variable=autorun_var, command=toggle_autorun_ui,
    fg=FG_DIM, bg=BG, activeforeground=ACCENT_DIM,
    activebackground=BG, selectcolor=SURFACE2,
    relief="flat", bd=0, highlightthickness=0,
    font=FONT_MONO, cursor="hand2"
)
autorun_check.pack(side="left")

# Exit
tk.Button(root, text="EXIT", command=exit_app,
          fg=FG_DIM, bg=BG, activeforeground=RED,
          activebackground=BG, relief="flat", bd=0,
          highlightthickness=0, font=FONT_MONO,
          padx=8, pady=6, cursor="hand2").pack(pady=(2, 12))

# ─── Tray hint label ──────────────────────────────────────────────────────────
mk_label(root, "✕ close = minimize to tray", fg="#3a3a48", font=("Consolas", 7)).pack(pady=(0,6))

# ─── Start tray & main loop ───────────────────────────────────────────────────
build_tray()
root.mainloop()
