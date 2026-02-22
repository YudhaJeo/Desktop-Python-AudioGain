import sounddevice as sd
import numpy as np
import tkinter as tk
from threading import Thread

gain_value = 1.0
running = False
audio_thread = None
input_device = None
output_device = None

# ========= DEVICE FILTER =========
def get_clean_devices():
    devices = sd.query_devices()
    inputs = []
    outputs = []

    seen_in = set()
    seen_out = set()

    for d in devices:
        name = d['name']

        # skip mapper / duplicate layer
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
    global gain_value
    if status:
        print(status)

    boosted = indata * gain_value
    boosted = np.clip(boosted, -1.0, 1.0)
    outdata[:] = boosted

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
    gain_value = 1 + (slider_val / 100)
    gain_label.config(text=f"Gain: {slider_val}")

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
root.title("Discord Mic Booster")
root.geometry("420x320")
root.resizable(False, False)

inputs, outputs = get_clean_devices()

# INPUT
tk.Label(root, text="Input Mic").pack()
input_var = tk.StringVar(value=inputs[0] if inputs else "")
tk.OptionMenu(root, input_var, *inputs).pack()

# OUTPUT
tk.Label(root, text="Output (VB Cable)").pack()
output_var = tk.StringVar(value=outputs[0] if outputs else "")
tk.OptionMenu(root, output_var, *outputs).pack()

# GAIN
gain_label = tk.Label(root, text="Gain: 0", font=("Segoe UI", 12))
gain_label.pack(pady=10)

slider = tk.Scale(root, from_=-100, to=100,
                  orient="horizontal", command=update_gain)
slider.set(0)
slider.pack()

# BUTTONS
btn_frame = tk.Frame(root)
btn_frame.pack(pady=10)

tk.Button(btn_frame, text="Start", width=10, command=start_audio).grid(row=0, column=0, padx=5)
tk.Button(btn_frame, text="Stop", width=10, command=stop_audio).grid(row=0, column=1, padx=5)
tk.Button(btn_frame, text="Exit", width=10, command=exit_app).grid(row=0, column=2, padx=5)

# STATUS
status_label = tk.Label(root, text="Idle")
status_label.pack()

root.mainloop()