"""
Wispr Lite - local speech-to-text host.

This process is spawned by Chrome via Native Messaging when the extension
is enabled, and is killed automatically when the extension is disabled
(Chrome closes our stdin, which we watch for below).

Flow:
  1. Press HOTKEY anywhere on your system -> a small always-on-top window
     pops up and recording starts immediately.
  2. Speak. Press HOTKEY again (or Enter, while the window is focused) to
     stop recording.
  3. Audio is transcribed locally with faster-whisper. The text appears in
     the box and is copied to your clipboard automatically, ready to paste
     into ChatGPT, Gmail, Word, VS Code, etc.
"""

import sys
import os
import re
import struct
import threading
import queue

import numpy as np
import sounddevice as sd
import keyboard
import pyperclip
import tkinter as tk

from faster_whisper import WhisperModel

# ---------------------------------------------------------------------------
# Configuration - tweak these to taste
# ---------------------------------------------------------------------------
HOTKEY = "ctrl+shift+space"
WHISPER_MODEL_SIZE = "base"      # tiny / base / small / medium / large-v3
WHISPER_DEVICE = "cpu"           # "cuda" if you have a working NVIDIA + CUDA setup
WHISPER_COMPUTE_TYPE = "int8"    # int8 is fast on CPU; try "float16" on GPU
SAMPLE_RATE = 16000

event_queue = queue.Queue()


# ---------------------------------------------------------------------------
# Native messaging lifecycle: exit the moment Chrome closes our stdin
# (extension disabled, browser closed, port disconnected, etc.)
# ---------------------------------------------------------------------------
def watch_for_disconnect():
    while True:
        raw_length = sys.stdin.buffer.read(4)
        if not raw_length:
            os._exit(0)
        length = struct.unpack("<I", raw_length)[0]
        sys.stdin.buffer.read(length)  # drain payload, content unused


# ---------------------------------------------------------------------------
# Audio recording
# ---------------------------------------------------------------------------
class Recorder:
    def __init__(self):
        self.frames = []
        self.stream = None
        self.recording = False

    def start(self):
        self.frames = []
        self.recording = True

        def callback(indata, frames, time_info, status):
            if self.recording:
                self.frames.append(indata.copy())

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=callback
        )
        self.stream.start()

    def stop(self):
        self.recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if not self.frames:
            return None
        return np.concatenate(self.frames, axis=0)


recorder = Recorder()


def clean_disfluencies(text):
    """Light rule-based cleanup for simple stumbles Whisper transcribes literally.

    This only catches the easy case: the exact same word (or short phrase)
    repeated back-to-back, e.g. "the the report" -> "the report", or
    "I want I want to" -> "I want to". A genuine fumble-then-correction where
    the two attempts use DIFFERENT words (e.g. "send it to Bob, I mean Dave")
    isn't something a regex can safely resolve - that needs the model itself
    to infer intent, which is where a larger Whisper model helps more than
    any post-processing can.
    """
    # Collapse immediately repeated single words (case-insensitive, keeps the
    # casing/punctuation of the second occurrence).
    text = re.sub(r"\b(\w+)( \1\b)+", r"\1", text, flags=re.IGNORECASE)
    # Collapse immediately repeated short phrases (2-4 words), e.g.
    # "I want I want to" -> "I want to".
    for n in (4, 3, 2):
        pattern = r"\b((?:\w+ ){%d}\w+)\s+\1\b" % (n - 1)
        text = re.sub(pattern, r"\1", text, flags=re.IGNORECASE)
    return text.strip()


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class WisprWindow:
    def __init__(self, model):
        self.model = model
        self.root = tk.Tk()
        self.root.title("Wispr Lite")
        self.root.attributes("-topmost", True)
        self.root.geometry("420x220")
        self.root.protocol("WM_DELETE_WINDOW", self.cancel)

        self.status_var = tk.StringVar(value="")
        tk.Label(self.root, textvariable=self.status_var, font=("Segoe UI", 10)).pack(
            pady=(10, 5)
        )

        self.text_box = tk.Text(self.root, wrap="word", font=("Segoe UI", 11), height=6)
        self.text_box.pack(fill="both", expand=True, padx=10, pady=5)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Copy", command=self.copy_text).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Close", command=self.cancel).pack(side="left", padx=5)

        self.root.bind("<Return>", lambda e: event_queue.put("toggle"))
        self.hide()

    def show_recording(self):
        self.status_var.set("Recording... press hotkey or Enter to stop")
        self.text_box.delete("1.0", "end")
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def show_result(self, text):
        self.status_var.set("Done - copied to clipboard")
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", text)
        pyperclip.copy(text)

    def hide(self):
        self.root.withdraw()

    def cancel(self):
        """Close/X button: stop any in-progress recording (discarding it,
        no transcription) instead of leaving the mic running silently."""
        if recorder.recording:
            recorder.stop()
        self.hide()

    def copy_text(self):
        pyperclip.copy(self.text_box.get("1.0", "end").strip())

    def poll_queue(self):
        try:
            while True:
                msg = event_queue.get_nowait()
                if msg == "toggle":
                    self.handle_toggle()
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    def handle_toggle(self):
        if not recorder.recording:
            self.show_recording()
            recorder.start()
        else:
            audio = recorder.stop()
            self.status_var.set("Transcribing...")
            self.root.update()
            if audio is None or len(audio) == 0:
                self.status_var.set("No audio captured")
                return
            threading.Thread(target=self.transcribe, args=(audio,), daemon=True).start()

    def transcribe(self, audio):
        audio_float = audio.astype(np.float32) / 32768.0
        segments, _ = self.model.transcribe(
            audio_float.flatten(),
            language=None,
            beam_size=5,                    # explores more candidate wordings instead of
                                             # greedily committing to the first guess
            best_of=5,
            condition_on_previous_text=True,  # use earlier words in the sentence as context,
                                               # which helps it favor the corrected word over
                                               # a false start
            vad_filter=True,                # trims leading/trailing silence and short noise
                                             # blips that can otherwise get transcribed as junk
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        text = clean_disfluencies(text)
        self.root.after(0, lambda: self.show_result(text or "(no speech detected)"))

    def run(self):
        self.root.after(100, self.poll_queue)
        self.root.mainloop()


def main():
    threading.Thread(target=watch_for_disconnect, daemon=True).start()

    print("Loading Whisper model...", file=sys.stderr)
    model = WhisperModel(
        WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE
    )
    print("Whisper model ready.", file=sys.stderr)

    keyboard.add_hotkey(HOTKEY, lambda: event_queue.put("toggle"))

    app = WisprWindow(model)
    app.run()


if __name__ == "__main__":
    main()