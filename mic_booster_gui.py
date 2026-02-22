import sounddevice as sd
import numpy as np
import tkinter as tk
from tkinter import ttk
from threading import Thread
import math

# ─── State ───────────────────────────────────────────────────────────────────
gain_value = 1.0
running = False
monitoring = False
audio_thread = None
input_device = None
output_device = None
monitor_device = None

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
        status_label.config(text=f"ERR: {e}", fg=RED)

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
    input_device = input_var.get()
    output_device = output_var.get()
    running = True
    audio_thread = Thread(target=audio_loop, daemon=True)
    audio_thread.start()
    status_dot.config(fg=GREEN, text="●")
    status_label.config(text="LIVE", fg=GREEN)
    start_btn.config(fg=FG_DIM)
    stop_btn.config(fg=RED)

def stop_audio():
    global running
    running = False
    status_dot.config(fg=FG_DIM, text="●")
    status_label.config(text="IDLE", fg=FG_DIM)
    start_btn.config(fg=ACCENT)
    stop_btn.config(fg=FG_DIM)

def exit_app():
    global running
    running = False
    root.destroy()

# ─── UI ───────────────────────────────────────────────────────────────────────
root = tk.Tk()
root.title("MIC BOOST")
root.geometry("460x520")
root.resizable(False, False)
root.configure(bg=BG)

def mk_label(parent, text, fg=FG_DIM, font=FONT_LABEL, **kw):
    return tk.Label(parent, text=text, fg=fg, bg=parent["bg"], font=font, **kw)

def mk_divider(parent, pad=(8,8)):
    f = tk.Frame(parent, bg=BORDER, height=1)
    f.pack(fill="x", padx=20, pady=pad)

def styled_dropdown(parent, var, options):
    frame = tk.Frame(parent, bg=SURFACE2, highlightbackground=BORDER,
                     highlightthickness=1)
    frame.pack(fill="x", padx=20, pady=3)
    # truncate long names
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
mk_label(header, "BOOST", fg=FG, font=("Consolas", 18, "bold")).pack(side="left", padx=(2,0))

# status badge right side
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

mk_label(section, "OUTPUT", fg=FG_DIM, font=FONT_MONO).pack(anchor="w", padx=20)
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

# Big gain number
gain_val_label = tk.Label(gain_sec, text="000", fg=ACCENT,
                           bg=BG, font=FONT_BIG)
gain_val_label.pack(pady=(2, 6))

# Custom slider style
style = ttk.Style()
style.theme_use("clam")
style.configure("Gain.Horizontal.TScale",
                background=BG,
                troughcolor=SURFACE2,
                sliderthickness=18,
                sliderrelief="flat")

slider = ttk.Scale(gain_sec, from_=0, to=200, orient="horizontal",
                   command=update_gain, style="Gain.Horizontal.TScale")
slider.set(0)
slider.pack(fill="x")

# tick marks
tick_row = tk.Frame(gain_sec, bg=BG)
tick_row.pack(fill="x")
for t in ["0", "50", "100", "150", "200"]:
    mk_label(tick_row, t, fg=FG_DIM, font=("Consolas", 7)).pack(side="left",
             expand=True)

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
          
# Monitor toggle — full width below
monitor_btn = tk.Button(root, text="○ MON OFF",
                         command=toggle_monitor,
                         fg=FG_DIM, bg=SURFACE,
                         activeforeground=GREEN,
                         activebackground=SURFACE2,
                         relief="flat", bd=0,
                         highlightbackground=BORDER, highlightthickness=1,
                         font=FONT_MONO, padx=14, pady=8, cursor="hand2")
monitor_btn.pack(fill="x", padx=24, pady=(2, 4))

# Exit
tk.Button(root, text="EXIT", command=exit_app,
          fg=FG_DIM, bg=BG, activeforeground=RED,
          activebackground=BG, relief="flat", bd=0,
          highlightthickness=0, font=FONT_MONO,
          padx=8, pady=6, cursor="hand2").pack(pady=(2, 12))

root.mainloop()