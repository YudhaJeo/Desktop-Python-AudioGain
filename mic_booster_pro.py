import sounddevice as sd
import numpy as np
import tkinter as tk
from tkinter import ttk
from threading import Thread
import math
import sys
import os
import json
import queue

import pystray
from PIL import Image, ImageDraw

# ─── State ───────────────────────────────────────────────────────────────────
gain_value      = 1.0
running         = False
monitoring      = False
audio_thread    = None
monitor_thread  = None
input_device    = None
output_device   = None
monitor_device  = None
monitor_queue   = queue.Queue(maxsize=20)
viz_queue       = queue.Queue(maxsize=10)
rage_mode       = False          # ← NEW: RAGE MODE flag

tray_icon  = None
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
RAGE_RED   = "#ff1a1a"
RAGE_DIM   = "#cc0000"
RAGE_BG    = "#1a0000"

FONT_MONO  = ("Consolas", 9)
FONT_LABEL = ("Segoe UI", 9)
FONT_BIG   = ("Consolas", 26, "bold")

# ─── Paths ───────────────────────────────────────────────────────────────────
def resource_path(relative):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative)

SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "settings.json"
)

# ─── Settings persistence ─────────────────────────────────────────────────────
def load_settings():
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings():
    try:
        data = {
            "input":   input_var.get(),
            "output":  output_var.get(),
            "monitor": monitor_var.get(),
            "gain":    slider.get(),
        }
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[settings] save error: {e}")

# ─── Devices ─────────────────────────────────────────────────────────────────
API_PRIORITY = ["WASAPI", "MME", "Windows DirectSound", "Windows WDM-KS"]
_device_index_map = {}

def _api_rank(hostapi_index):
    try:
        api_name = sd.query_hostapis(hostapi_index)["name"]
        for rank, pref in enumerate(API_PRIORITY):
            if pref.lower() in api_name.lower():
                return rank
        return len(API_PRIORITY)
    except Exception:
        return len(API_PRIORITY)

def get_clean_devices():
    global _device_index_map
    devices = sd.query_devices()
    in_candidates  = {}
    out_candidates = {}
    for idx, d in enumerate(devices):
        name = d["name"]
        if "Mapper" in name or "Primary" in name:
            continue
        rank = _api_rank(d["hostapi"])
        if d["max_input_channels"] > 0:
            if name not in in_candidates or rank < in_candidates[name][0]:
                in_candidates[name] = (rank, idx)
        if d["max_output_channels"] > 0:
            if name not in out_candidates or rank < out_candidates[name][0]:
                out_candidates[name] = (rank, idx)
    _device_index_map = {}
    for name, (_, idx) in in_candidates.items():
        _device_index_map.setdefault(name, {})["in"] = idx
    for name, (_, idx) in out_candidates.items():
        _device_index_map.setdefault(name, {})["out"] = idx
    return list(in_candidates.keys()), list(out_candidates.keys())

def resolve_input_index(name):
    return _device_index_map.get(name, {}).get("in", name)

def resolve_output_index(name):
    return _device_index_map.get(name, {}).get("out", name)

def find_vbcable(outputs):
    priorities = [
        "cable in 16ch",
        "cable in",
        "cable",
        "virtual audio cable",
        "vb-audio",
    ]
    for pat in priorities:
        for name in outputs:
            if pat in name.lower():
                return name
    return None

def find_best_output(outputs, saved_out=""):
    if saved_out and saved_out in outputs:
        return saved_out
    vb = find_vbcable(outputs)
    if vb:
        return vb
    for name in outputs:
        nl = name.lower()
        if any(k in nl for k in ["speaker", "headphone", "headset", "realtek", "audio output"]):
            return name
    return outputs[0] if outputs else None

# ─── Audio — main stream ──────────────────────────────────────────────────────
def audio_callback(indata, outdata, frames, time, status):
    global gain_value, monitoring
    if status:
        print(f"[stream] {status}")
    boosted = np.clip(indata * gain_value, -1.0, 1.0)
    outdata[:] = boosted
    if monitoring:
        try:
            monitor_queue.put_nowait(boosted.copy())
        except queue.Full:
            pass
    try:
        viz_queue.put_nowait(boosted.copy())
    except queue.Full:
        pass

def _find_compatible_output(in_idx):
    try:
        in_info  = sd.query_devices(in_idx)
        in_api   = in_info["hostapi"]
    except Exception:
        return None

    preferred = resolve_output_index(output_device)
    candidates = []
    if preferred is not None and preferred != in_idx:
        candidates.append(preferred)
    for name, info in _device_index_map.items():
        idx = info.get("out")
        if idx is not None and idx not in candidates and idx != in_idx:
            candidates.append(idx)

    for out_idx in candidates:
        try:
            out_info = sd.query_devices(out_idx)
            if out_info["hostapi"] == in_api:
                return out_idx
        except Exception:
            continue

    return None

def audio_loop():
    global running
    try:
        in_idx  = resolve_input_index(input_device)
        out_idx = _find_compatible_output(in_idx)
        with sd.Stream(
            device=(in_idx, out_idx),
            channels=1,
            samplerate=48000,
            blocksize=256,
            dtype="float32",
            callback=audio_callback,
        ):
            while running:
                sd.sleep(100)
    except Exception as e:
        err = str(e)
        root.after(0, lambda: show_error(err))

# ─── Audio — dedicated monitor OutputStream ───────────────────────────────────
def monitor_loop():
    global monitoring, monitor_device
    dev_name = monitor_device
    if dev_name is None:
        return
    dev = None if dev_name == "System Default" else resolve_output_index(dev_name)
    try:
        with sd.OutputStream(
            device=dev,
            channels=1,
            samplerate=48000,
            blocksize=2048,
            latency="high",
            dtype="float32",
        ) as stream:
            buf = []
            buf_frames = 0
            target_frames = 2048
            while monitoring:
                try:
                    chunk = monitor_queue.get(timeout=0.1)
                    buf.append(chunk)
                    buf_frames += len(chunk)
                    if buf_frames >= target_frames:
                        combined = np.concatenate(buf, axis=0)
                        stream.write(combined)
                        buf = []
                        buf_frames = 0
                except queue.Empty:
                    if buf:
                        combined = np.concatenate(buf, axis=0)
                        stream.write(combined)
                        buf = []
                        buf_frames = 0
    except Exception as e:
        print(f"[monitor] error: {e}")

def start_monitor():
    global monitor_thread, monitoring
    while not monitor_queue.empty():
        try:
            monitor_queue.get_nowait()
        except queue.Empty:
            break
    monitoring = True
    monitor_thread = Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

def stop_monitor():
    global monitoring
    monitoring = False

def show_error(msg):
    short = msg.replace("\n", " ").strip()
    if len(short) > 72:
        short = short[:69] + "…"
    error_label.config(text=f"⚠  {short}", fg=RED)
    root.after(8000, lambda: error_label.config(text=""))
    status_dot.config(fg=FG_DIM, text="●")
    status_label.config(text="IDLE", fg=FG_DIM)
    start_btn.config(fg=ACCENT)
    stop_btn.config(fg=FG_DIM)

# ─── Visualizer ───────────────────────────────────────────────────────────────
VIZ_W        = 420
VIZ_H        = 90
N_BARS       = 40
FFT_SIZE     = 1024
_fft_buf     = np.zeros(FFT_SIZE, dtype="float32")
_bar_smooth  = np.zeros(N_BARS, dtype="float32")
_peak_hold   = np.zeros(N_BARS, dtype="float32")
_peak_timer  = np.zeros(N_BARS, dtype="float32")
SMOOTH_ATK   = 0.85
SMOOTH_REL   = 0.55
PEAK_HOLD_FRAMES = 18
PEAK_FALL        = 0.04

_GRAD = [
    (0.00,  0,  80, 100),
    (0.45,  0, 229, 255),
    (0.75, 100, 255, 220),
    (1.00, 255,  80,  80),
]

_GRAD_RAGE = [
    (0.00, 100,   0,   0),
    (0.45, 255,  50,   0),
    (0.75, 255, 150,   0),
    (1.00, 255, 255,   0),
]

def _lerp_color(frac, grad=None):
    if grad is None:
        grad = _GRAD_RAGE if rage_mode else _GRAD
    frac = max(0.0, min(1.0, frac))
    for i in range(len(grad) - 1):
        f0, r0, g0, b0 = grad[i]
        f1, r1, g1, b1 = grad[i + 1]
        if frac <= f1:
            t = (frac - f0) / (f1 - f0 + 1e-9)
            r = int(r0 + t * (r1 - r0))
            g = int(g0 + t * (g1 - g0))
            b = int(b0 + t * (b1 - b0))
            return f"#{r:02x}{g:02x}{b:02x}"
    return "#ff5050"

_rage_blink_state = False

def _draw_visualizer():
    global _fft_buf, _bar_smooth, _peak_hold, _peak_timer, _rage_blink_state

    new_samples = []
    while True:
        try:
            chunk = viz_queue.get_nowait()
            new_samples.append(chunk.flatten())
        except queue.Empty:
            break

    if new_samples:
        combined = np.concatenate(new_samples)
        if len(combined) >= FFT_SIZE:
            _fft_buf = combined[-FFT_SIZE:]
        else:
            _fft_buf = np.roll(_fft_buf, -len(combined))
            _fft_buf[-len(combined):] = combined

    windowed  = _fft_buf * np.hanning(FFT_SIZE)
    spectrum  = np.abs(np.fft.rfft(windowed))
    spectrum  = spectrum[:FFT_SIZE // 2]
    log_bins  = np.logspace(np.log10(2), np.log10(len(spectrum) - 1), N_BARS + 1).astype(int)
    log_bins  = np.clip(log_bins, 0, len(spectrum) - 1)
    bar_raw   = np.array([
        np.mean(spectrum[log_bins[i]:log_bins[i + 1] + 1])
        for i in range(N_BARS)
    ], dtype="float32")

    ref = max(bar_raw.max(), 0.01)
    bar_norm = np.clip(bar_raw / ref * 0.9, 0.0, 1.0)

    rms = float(np.sqrt(np.mean(_fft_buf ** 2))) * 8.0
    rms = min(rms, 1.0)
    bar_norm *= rms

    rising  = bar_norm > _bar_smooth
    _bar_smooth = np.where(rising,
                           _bar_smooth * (1 - SMOOTH_ATK) + bar_norm * SMOOTH_ATK,
                           _bar_smooth * (1 - SMOOTH_REL) + bar_norm * SMOOTH_REL)

    new_peak = _bar_smooth > _peak_hold
    _peak_hold  = np.where(new_peak, _bar_smooth, _peak_hold)
    _peak_timer = np.where(new_peak, PEAK_HOLD_FRAMES, _peak_timer - 1)
    falling = _peak_timer <= 0
    _peak_hold  = np.where(falling, np.maximum(_peak_hold - PEAK_FALL, _bar_smooth), _peak_hold)

    canvas = viz_canvas

    # Rage mode: blink canvas background
    if rage_mode:
        _rage_blink_state = not _rage_blink_state
        canvas_bg = "#1a0000" if _rage_blink_state else "#0d0000"
        canvas.config(bg=canvas_bg)
    else:
        canvas.config(bg=SURFACE2)

    canvas.delete("viz")

    bar_area_h = VIZ_H - 6
    gap        = 2
    bar_w      = (VIZ_W - gap * (N_BARS - 1)) / N_BARS
    x          = 0

    for i in range(N_BARS):
        h    = max(2, int(_bar_smooth[i] * bar_area_h))
        frac = _bar_smooth[i]
        col  = _lerp_color(frac)

        x0 = x
        y0 = VIZ_H - h
        x1 = x + bar_w - 1
        y1 = VIZ_H

        canvas.create_rectangle(x0, y0, x1, y1,
                                 fill=col, outline="", tags="viz")
        if h > 4:
            inner_col = _lerp_color(min(frac + 0.15, 1.0))
            canvas.create_rectangle(x0 + 1, y0, x1 - 1, y0 + 2,
                                     fill=inner_col, outline="", tags="viz")

        ph = max(2, int(_peak_hold[i] * bar_area_h))
        py = VIZ_H - ph - 2
        if py > 0:
            pcol = _lerp_color(_peak_hold[i] + 0.1)
            canvas.create_rectangle(x0, py, x1, py + 2,
                                     fill=pcol, outline="", tags="viz")

        x += bar_w + gap

    canvas.create_rectangle(0, VIZ_H - 3, VIZ_W, VIZ_H,
                             fill=canvas.cget("bg"), outline="", tags="viz")

    root.after(33, _draw_visualizer)


# ─── Gain calculation ─────────────────────────────────────────────────────────
# NEW RANGE:
#   Slider  0   → gain 0.0  (mute / volume 0)
#   Slider  100 → gain 1.0  (unity / normal volume)
#   Slider  250 → gain 6.0  (max boost, ~+15.6 dB)
#
# Formula: gain = (slider_value / 100) ** 1.5  — but we want 0→0, 100→1, 250→6
# Simpler piecewise:
#   0..100  : gain = slider / 100           (linear 0→1)
#   100..250: gain = 1 + ((slider-100)/150) * 5  (linear 1→6)

def slider_to_gain(v):
    """Convert slider value (0-250) to gain multiplier."""
    v = float(v)
    if v <= 0:
        return 0.0
    elif v <= 100:
        return v / 100.0
    else:
        # 100→1.0 .. 250→6.0
        return 1.0 + ((v - 100.0) / 150.0) * 5.0


# ─── Logic ────────────────────────────────────────────────────────────────────
def update_gain(val):
    global gain_value
    v = float(val)
    gain_value = slider_to_gain(v)

    v_int = int(v)
    gain_val_label.config(text=f"{v_int:03d}")

    if gain_value <= 0:
        db_str = "-∞ dB"
        gain_val_label.config(fg=FG_DIM)
    elif gain_value < 1.0:
        db = round(20 * math.log10(gain_value), 1)
        db_str = f"{db} dB"
        gain_val_label.config(fg=FG_DIM)
    elif gain_value == 1.0:
        db_str = "±0.0 dB"
        gain_val_label.config(fg=GREEN)
    else:
        db = round(20 * math.log10(gain_value), 1)
        db_str = f"+{db} dB"
        gain_val_label.config(fg=ACCENT)

    db_label.config(text=db_str)

def toggle_monitor():
    global monitor_device
    if monitoring:
        stop_monitor()
        monitor_btn.config(text="○ MON OFF", fg=FG_DIM, bg=SURFACE,
                           highlightbackground=BORDER)
    else:
        monitor_device = monitor_var.get()
        start_monitor()
        monitor_btn.config(text="● MON  ON", fg=GREEN, bg=SURFACE2,
                           highlightbackground=GREEN)

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
    stop_monitor()
    monitor_btn.config(text="○ MON OFF", fg=FG_DIM, bg=SURFACE,
                       highlightbackground=BORDER)
    status_dot.config(fg=FG_DIM, text="●")
    status_label.config(text="IDLE", fg=FG_DIM)
    start_btn.config(fg=ACCENT)
    stop_btn.config(fg=FG_DIM)
    update_tray_tooltip()

def exit_app(icon=None, item=None):
    global running, tray_icon
    save_settings()
    running = False
    stop_monitor()
    if tray_icon:
        tray_icon.stop()
    root.destroy()

# ─── RAGE MODE ────────────────────────────────────────────────────────────────
RAGE_GAIN = 800.0   # absurd gain for prank

_rage_blink_job = None

def _rage_blink_ui():
    """Blink the rage button itself while rage mode is active."""
    global _rage_blink_job
    if not rage_mode:
        return
    cur = rage_btn.cget("bg")
    next_bg = RAGE_RED if cur == RAGE_BG else RAGE_BG
    rage_btn.config(bg=next_bg)
    _rage_blink_job = root.after(400, _rage_blink_ui)

def toggle_rage():
    global rage_mode, gain_value, _rage_blink_job
    rage_mode = not rage_mode

    if rage_mode:
        # Store current gain and switch to RAGE gain
        gain_value = RAGE_GAIN
        # Update UI
        rage_btn.config(
            text="💀 RAGE MODE  ●  ON",
            fg="#ffff00",
            bg=RAGE_RED,
            highlightbackground=RAGE_RED,
        )
        gain_val_label.config(text="☠☠☠", fg=RAGE_RED)
        db_label.config(text="+∞ RAGE", fg=RAGE_RED)
        slider.state(["disabled"])   # lock slider during rage
        _rage_blink_ui()
        root.configure(bg=RAGE_BG)
        for w in [header, section, gain_sec, viz_outer, ctrl, autorun_frame]:
            try:
                w.config(bg=RAGE_BG)
            except Exception:
                pass
        for lbl in [status_dot, status_label, db_label, gain_val_label]:
            try:
                lbl.config(bg=RAGE_BG)
            except Exception:
                pass
        for child in gain_hdr.winfo_children():
            try:
                child.config(bg=RAGE_BG)
            except Exception:
                pass
        for child in header.winfo_children():
            try:
                child.config(bg=RAGE_BG)
            except Exception:
                pass
        for child in badge.winfo_children():
            try:
                child.config(bg=RAGE_BG)
            except Exception:
                pass
        for child in autorun_frame.winfo_children():
            try:
                child.config(bg=RAGE_BG)
            except Exception:
                pass
    else:
        # Cancel blink job
        if _rage_blink_job:
            root.after_cancel(_rage_blink_job)
            _rage_blink_job = None
        # Restore slider-based gain
        v = slider.get()
        gain_value = slider_to_gain(v)
        update_gain(v)
        slider.state(["!disabled"])
        # Restore button style
        rage_btn.config(
            text="☠  RAGE MODE  ○  OFF",
            fg=FG_DIM,
            bg=SURFACE,
            highlightbackground=BORDER,
        )
        # Restore background
        root.configure(bg=BG)
        for w in [header, section, gain_sec, viz_outer, ctrl, autorun_frame]:
            try:
                w.config(bg=BG)
            except Exception:
                pass
        for lbl in [status_dot, status_label]:
            try:
                lbl.config(bg=BG)
            except Exception:
                pass
        for child in gain_hdr.winfo_children():
            try:
                child.config(bg=BG)
            except Exception:
                pass
        for child in header.winfo_children():
            try:
                child.config(bg=BG)
            except Exception:
                pass
        for child in badge.winfo_children():
            try:
                child.config(bg=BG)
            except Exception:
                pass
        for child in autorun_frame.winfo_children():
            try:
                child.config(bg=BG)
            except Exception:
                pass


# ─── Autorun ─────────────────────────────────────────────────────────────────
def set_autorun(enable=True):
    try:
        import winreg
        app_name = "MicFckinBoost"
        exe_path = (f'"{sys.executable}"' if getattr(sys, "frozen", False)
                    else f'"{sys.executable}" "{os.path.abspath(__file__)}"')
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
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
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ,
        )
        winreg.QueryValueEx(key, "MicFckinBoost")
        winreg.CloseKey(key)
        return True
    except Exception:
        return False

# ─── Tray ────────────────────────────────────────────────────────────────────
def load_tray_image():
    icon_path = resource_path(os.path.join("assets", "app-icon.png"))
    if os.path.exists(icon_path):
        return Image.open(icon_path).convert("RGBA").resize((64, 64))
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
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
        tray_icon.title = f"MicFckinBoost — {'LIVE' if running else 'IDLE'}"

def build_tray():
    global tray_icon
    menu = pystray.Menu(
        pystray.MenuItem("Show / Hide", show_window, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("▶  Start", lambda i, it: root.after(0, start_audio)),
        pystray.MenuItem("■  Stop",  lambda i, it: root.after(0, stop_audio)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Run at Startup",
            lambda i, it: (set_autorun(not is_autorun_enabled()),),
            checked=lambda item: is_autorun_enabled(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", exit_app),
    )
    tray_icon = pystray.Icon("MicFckinBoost", load_tray_image(),
                             "MicFckinBoost — IDLE", menu)
    Thread(target=tray_icon.run, daemon=True).start()

def on_close():
    save_settings()
    hide_window()

# ─── UI ───────────────────────────────────────────────────────────────────────
root = tk.Tk()
root.title("MIC FCKIN BOOST")
root.geometry("460x400")
root.resizable(False, False)
root.configure(bg=BG)
root.protocol("WM_DELETE_WINDOW", on_close)

_icon_png = resource_path(os.path.join("assets", "app-icon.png"))
if os.path.exists(_icon_png):
    try:
        root.iconphoto(True, tk.PhotoImage(file=_icon_png))
    except Exception:
        pass

def mk_label(parent, text, fg=FG_DIM, font=FONT_LABEL, **kw):
    return tk.Label(parent, text=text, fg=fg, bg=parent["bg"], font=font, **kw)

def mk_divider(parent, pad=(8, 8)):
    tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=20, pady=pad)

def styled_dropdown(parent, var, options):
    frame = tk.Frame(parent, bg=SURFACE2, highlightbackground=BORDER,
                     highlightthickness=1)
    frame.pack(fill="x", padx=20, pady=3)
    short     = [o[:42] + "…" if len(o) > 42 else o for o in options]
    name_map  = dict(zip(short, options))
    short_var = tk.StringVar(value=short[0] if short else "")
    def on_change(*_):
        var.set(name_map.get(short_var.get(), short_var.get()))
    short_var.trace_add("write", on_change)
    var.set(options[0] if options else "")
    def set_by_full(full_name):
        for s, f in name_map.items():
            if f == full_name:
                short_var.set(s)
                return
    frame._set_by_full = set_by_full
    frame._options     = options
    menu = tk.OptionMenu(frame, short_var, *short)
    menu.config(bg=SURFACE2, fg=FG, activebackground=SURFACE,
                activeforeground=ACCENT, relief="flat", bd=0,
                highlightthickness=0, font=FONT_LABEL,
                indicatoron=True, anchor="w", width=46)
    menu["menu"].config(bg=SURFACE2, fg=FG, activebackground=ACCENT_DIM,
                        activeforeground=ACCENT, relief="flat", bd=0,
                        font=FONT_LABEL)
    menu.pack(fill="x", padx=6, pady=4)
    return frame

# ── Header ───────────────────────────────────────────────────────────────────
header = tk.Frame(root, bg=BG)
header.pack(fill="x", padx=20, pady=(20, 4))
mk_label(header, "MIC",   fg=FG, font=("Consolas", 18, "bold")).pack(side="left")
mk_label(header, "FCKIN",   fg=FG, font=("Consolas", 18, "bold")).pack(side="left")
mk_label(header, "BOOST", fg=ACCENT,     font=("Consolas", 18, "bold")).pack(side="left", padx=(2, 0))

badge = tk.Frame(header, bg=BG)
badge.pack(side="right", pady=4)
status_dot   = tk.Label(badge, text="●", fg=FG_DIM, bg=BG, font=("Consolas", 10))
status_label = tk.Label(badge, text="IDLE", fg=FG_DIM, bg=BG, font=FONT_MONO)
status_dot.pack(side="left")
status_label.pack(side="left", padx=(3, 0))

mk_divider(root, (4, 12))

# ── Devices ──────────────────────────────────────────────────────────────────
inputs, outputs = get_clean_devices()
section = tk.Frame(root, bg=BG)
section.pack(fill="x")

mk_label(section, "INPUT", fg=FG_DIM, font=FONT_MONO).pack(anchor="w", padx=20)
input_var = tk.StringVar()
in_frame  = styled_dropdown(section, input_var, inputs or ["No input found"])

tk.Frame(section, bg=BG, height=6).pack()

mk_label(section, "OUTPUT (VB‑CABLE Recommended)", fg=FG_DIM, font=FONT_MONO).pack(anchor="w", padx=20)
output_var = tk.StringVar()
out_frame  = styled_dropdown(section, output_var, outputs or ["No output found"])

tk.Frame(section, bg=BG, height=6).pack()

mk_label(section, "MONITOR", fg=FG_DIM, font=FONT_MONO).pack(anchor="w", padx=20)
monitor_var = tk.StringVar()
monitor_options = ["System Default"] + (outputs or ["No output found"])
mon_frame   = styled_dropdown(section, monitor_var, monitor_options)

mk_divider(root, (14, 8))

# ── Gain ─────────────────────────────────────────────────────────────────────
gain_sec = tk.Frame(root, bg=BG)
gain_sec.pack(fill="x", padx=20)

gain_hdr = tk.Frame(gain_sec, bg=BG)
gain_hdr.pack(fill="x")
mk_label(gain_hdr, "GAIN", fg=FG_DIM, font=FONT_MONO).pack(side="left")

# NEW: range labels
mk_label(gain_hdr, "0=MUTE  ·  100=UNITY  ·  250=MAX BOOST",
         fg="#3a3a48", font=("Consolas", 7)).pack(side="left", padx=8)

db_label = tk.Label(gain_hdr, text="±0.0 dB", fg=FG_DIM, bg=BG, font=FONT_MONO)
db_label.pack(side="right")

gain_val_label = tk.Label(gain_sec, text="100", fg=GREEN, bg=BG, font=FONT_BIG)
gain_val_label.pack(pady=(2, 6))

_sty = ttk.Style()
_sty.theme_use("clam")
_sty.configure("Gain.Horizontal.TScale",
               background=BG, troughcolor=SURFACE2,
               sliderthickness=18, sliderrelief="flat")

# NEW: slider range 0-250
slider = ttk.Scale(gain_sec, from_=0, to=250, orient="horizontal",
                   command=update_gain, style="Gain.Horizontal.TScale")
slider.set(100)   # default = unity gain
slider.pack(fill="x")

tick_row = tk.Frame(gain_sec, bg=BG)
tick_row.pack(fill="x")
for t in ["0", "50", "100", "150", "200", "250"]:
    mk_label(tick_row, t, fg=FG_DIM, font=("Consolas", 7)).pack(side="left", expand=True)

# NEW: tick marker labels
hint_row = tk.Frame(gain_sec, bg=BG)
hint_row.pack(fill="x")
mk_label(hint_row, "MUTE", fg="#3a3a48", font=("Consolas", 7)).pack(side="left")
mk_label(hint_row, "UNITY", fg="#3a3a48", font=("Consolas", 7)).pack(side="left", padx=(80, 0))
mk_label(hint_row, "MAX", fg="#3a3a48", font=("Consolas", 7)).pack(side="right")

mk_divider(root, (12, 6))

# ── Audio Visualizer ─────────────────────────────────────────────────────────
viz_outer = tk.Frame(root, bg=BG)
viz_outer.pack(fill="x", padx=20, pady=(0, 4))

viz_header = tk.Frame(viz_outer, bg=BG)
viz_header.pack(fill="x", pady=(0, 4))
mk_label(viz_header, "SPECTRUM", fg=FG_DIM, font=FONT_MONO).pack(side="left")
mk_label(viz_header, "FFT · 40‑BAND", fg="#3a3a48", font=("Consolas", 7)).pack(side="right", pady=1)

viz_border = tk.Frame(viz_outer, bg=BORDER, padx=1, pady=1)
viz_border.pack(fill="x")

viz_canvas = tk.Canvas(
    viz_border,
    width=VIZ_W, height=VIZ_H,
    bg=SURFACE2, highlightthickness=0,
)
viz_canvas.pack(fill="x")

_grid_ys = [VIZ_H // 4, VIZ_H // 2, 3 * VIZ_H // 4]
for gy in _grid_ys:
    viz_canvas.create_line(0, gy, VIZ_W, gy,
                           fill=BORDER, width=1, tags="grid")

mk_divider(root, (6, 8))

# ── Controls ─────────────────────────────────────────────────────────────────
ctrl = tk.Frame(root, bg=BG)
ctrl.pack(fill="x", padx=20, pady=4)

def mk_btn(parent, text, cmd, fg=ACCENT):
    b = tk.Button(parent, text=text, command=cmd,
                  fg=fg, bg=SURFACE, activeforeground=FG,
                  activebackground=SURFACE2, relief="flat", bd=0,
                  highlightbackground=BORDER, highlightthickness=1,
                  font=FONT_MONO, padx=14, pady=8, cursor="hand2")
    b.pack(side="left", padx=4, expand=True, fill="x")
    return b

start_btn = mk_btn(ctrl, "▶  START", start_audio, fg=ACCENT)
stop_btn  = mk_btn(ctrl, "■  STOP",  stop_audio,  fg=FG_DIM)

monitor_btn = tk.Button(root, text="○ MON OFF", command=toggle_monitor,
                        fg=FG_DIM, bg=SURFACE, activeforeground=GREEN,
                        activebackground=SURFACE2, relief="flat", bd=0,
                        highlightbackground=BORDER, highlightthickness=1,
                        font=FONT_MONO, padx=14, pady=8, cursor="hand2")
monitor_btn.pack(fill="x", padx=24, pady=(2, 4))

# ── RAGE MODE button ──────────────────────────────────────────────────────────
mk_divider(root, (4, 4))

rage_btn = tk.Button(
    root,
    text="☠  RAGE MODE  ○  OFF",
    command=toggle_rage,
    fg=FG_DIM,
    bg=SURFACE,
    activeforeground=RAGE_RED,
    activebackground=RAGE_BG,
    relief="flat",
    bd=0,
    highlightbackground="#550000",
    highlightthickness=1,
    font=("Consolas", 10, "bold"),
    padx=14,
    pady=10,
    cursor="hand2",
)
rage_btn.pack(fill="x", padx=24, pady=(0, 6))

# ── Autorun ──────────────────────────────────────────────────────────────────
autorun_frame = tk.Frame(root, bg=BG)
autorun_frame.pack(fill="x", padx=24, pady=(0, 2))
autorun_var = tk.BooleanVar(value=is_autorun_enabled())

def toggle_autorun_ui():
    set_autorun(autorun_var.get())

tk.Checkbutton(
    autorun_frame, text="Run at Windows startup",
    variable=autorun_var, command=toggle_autorun_ui,
    fg=FG_DIM, bg=BG, activeforeground=ACCENT_DIM, activebackground=BG,
    selectcolor=SURFACE2, relief="flat", bd=0, highlightthickness=0, pady=8,
    font=FONT_MONO, cursor="hand2",
).pack(side="left")

# ── Exit ─────────────────────────────────────────────────────────────────────
tk.Button(root,
          text="EXIT",
          command=exit_app,
          fg=FG_DIM,
          bg=SURFACE,
          activeforeground=RED,
          activebackground=BG,
          relief="flat",
          bd=0,
          highlightthickness=0,
          font=FONT_MONO,
          padx=14,
          pady=8,
          cursor="hand2"
).pack(fill="x", padx=24, pady=(2, 8))

mk_label(root, "✕ close = minimize to tray", fg="#3a3a48",
         font=("Consolas", 7)).pack(pady=(0, 2))

# ── Error label ───────────────────────────────────────────────────────────────
error_label = tk.Label(root, text="", fg=RED, bg=BG,
                       font=("Consolas", 8), wraplength=420, justify="left")
error_label.pack(fill="x", padx=20, pady=(0, 8))

# ─── Apply saved / default settings ──────────────────────────────────────────
def apply_initial_settings():
    cfg = load_settings()
    saved_in = cfg.get("input", "")
    if saved_in and saved_in in inputs:
        in_frame._set_by_full(saved_in)
    saved_out = cfg.get("output", "")
    best_out = find_best_output(outputs, saved_out)
    if best_out:
        out_frame._set_by_full(best_out)
    saved_mon = cfg.get("monitor", "")
    if saved_mon and (saved_mon == "System Default" or saved_mon in outputs):
        mon_frame._set_by_full(saved_mon)
    else:
        mon_frame._set_by_full("System Default")
    try:
        g = cfg.get("gain", 100)   # default now 100 = unity
        slider.set(float(g))
        update_gain(g)
    except Exception:
        pass

root.after(50, apply_initial_settings)

# ─── Boot ────────────────────────────────────────────────────────────────────
build_tray()

def _fit_window():
    root.update_idletasks()
    h = root.winfo_reqheight() + 16
    root.geometry(f"460x{h}")

root.after(80, _fit_window)
root.after(100, _draw_visualizer)
root.after(200, start_audio)
root.mainloop()