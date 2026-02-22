import sounddevice as sd
import numpy as np
import tkinter as tk
from threading import Thread

gain_value = 1.0
running = False
monitoring = False
audio_thread = None

input_device = None
output_device = None
monitor_device = None

# ========= DEVICE FILTER =========
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

# ========= AUDIO =========
def audio_callback(indata, outdata, frames, time, status):
    global gain_value, monitoring

    if status:
        print(status)

    boosted = np.clip(indata * gain_value, -1.0, 1.0)

    # Output utama ke VB Cable
    outdata[:] = boosted

    # Monitoring optional
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
            channels=1,
            samplerate=48000,
            blocksize=256,
            callback=audio_callback
        ):
            while running:
                sd.sleep(100)
    except Exception as e:
        status_label.config(text=f"Error: {e}")

# ========= CONTROL =========
def update_gain(val):
    global gain_value
    slider_val = int(val)

    # Gain brutal mode 😈
    gain_value = 1 + (slider_val / 50)

    gain_label.config(text=f"Gain: {slider_val}")

def toggle_monitor():
    global monitoring, monitor_device
    monitoring = not monitoring
    monitor_device = monitor_var.get()

    monitor_btn.config(text=f"Monitoring: {'ON' if monitoring else 'OFF'}")

def start_audio():
    global running, audio_thread, input_device, output_device

    if running:
        return

    input_device = input_var.get()
    output_device = output_var.get()

    running = True
    audio_thread = Thread(target=audio_loop, daemon=True)
    audio_thread.start()
    status_label.config(text="Running ✔")

def stop_audio():
    global running
    running = False
    status_label.config(text="Stopped")

def exit_app():
    global running
    running = False
    root.destroy()

# ========= UI =========
root = tk.Tk()
root.title("Discord Mic Booster Pro")
root.geometry("460x380")
root.resizable(False, False)

inputs, outputs = get_clean_devices()

# INPUT
tk.Label(root, text="Input Mic").pack()
input_var = tk.StringVar(value=inputs[0] if inputs else "")
tk.OptionMenu(root, input_var, *inputs).pack()

# OUTPUT VB CABLE
tk.Label(root, text="Output (VB Cable)").pack()
output_var = tk.StringVar(value=outputs[0] if outputs else "")
tk.OptionMenu(root, output_var, *outputs).pack()

# MONITOR DEVICE
tk.Label(root, text="Monitoring Device").pack()
monitor_var = tk.StringVar(value=outputs[0] if outputs else "")
tk.OptionMenu(root, monitor_var, *outputs).pack()

# GAIN
gain_label = tk.Label(root, text="Gain: 0", font=("Segoe UI", 12))
gain_label.pack(pady=10)

slider = tk.Scale(root, from_=0, to=200,
                  orient="horizontal", command=update_gain)
slider.set(0)
slider.pack()

# BUTTONS
btn_frame = tk.Frame(root)
btn_frame.pack(pady=10)

tk.Button(btn_frame, text="Start", width=10, command=start_audio).grid(row=0, column=0, padx=5)
tk.Button(btn_frame, text="Stop", width=10, command=stop_audio).grid(row=0, column=1, padx=5)
tk.Button(btn_frame, text="Exit", width=10, command=exit_app).grid(row=0, column=2, padx=5)

# MONITOR BUTTON
monitor_btn = tk.Button(root, text="Monitoring: OFF", command=toggle_monitor)
monitor_btn.pack(pady=5)

# STATUS
status_label = tk.Label(root, text="Idle")
status_label.pack()

root.mainloop()