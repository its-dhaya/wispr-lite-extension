# Wispr Lite

A lightweight, personal, fully local speech-to-text tool: a Chrome extension
toggle + a local Python app running Whisper. No cloud, no server, no
subscription. Press a hotkey anywhere, speak, and paste the result into
ChatGPT, Gmail, Word, VS Code, or anywhere else.

## How it fits together

- **Chrome extension** — just an on/off switch. When you enable it, it opens
  a Native Messaging connection to the local Python app, which _spawns_ the
  process. When you disable it, the connection closes and Chrome kills the
  process automatically. That's what gives you "off = zero resource usage"
  without any extra code.
- **Python app** (`python-app/wispr_lite_host.py`) — registers a global
  hotkey, pops up a small always-on-top window when triggered, records your
  mic, transcribes locally with [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
  shows the text, and copies it to your clipboard.
- **Native host registration** (`native-host/install.ps1`) — a one-time
  PowerShell script that tells Chrome where to find the Python app.

## Setup (Windows)

1. **Install Python dependencies**

   ```powershell
   cd python-app
   pip install -r requirements.txt
   ```

   First run will download the Whisper `base` model (~140 MB) automatically.

2. **Load the extension**

   - Open `chrome://extensions`
   - Enable _Developer mode_ (top right)
   - Click _Load unpacked_ and select the `chrome-extension` folder
   - Copy the **Extension ID** shown on the card

3. **Register the native host**

   ```powershell
   cd native-host
   .\install.ps1 -ExtensionId "paste-your-extension-id-here"
   ```

4. **Use it**
   - Click the Wispr Lite icon in the toolbar and flip the toggle on
   - Press `Ctrl+Shift+Space` anywhere — a small box pops up and starts recording
   - Speak, then press `Ctrl+Shift+Space` again (or hit Enter) to stop
   - The transcribed text appears and is already on your clipboard — paste away
   - Flip the toggle off when you're done; the Python process exits automatically

## Tuning

All the knobs live at the top of `wispr_lite_host.py`:

| Setting                | Default            | Notes                                                                                 |
| ---------------------- | ------------------ | ------------------------------------------------------------------------------------- |
| `HOTKEY`               | `ctrl+shift+space` | Any combo supported by the `keyboard` library                                         |
| `WHISPER_MODEL_SIZE`   | `base`             | `tiny` is fastest/least accurate, `small`/`medium` more accurate but slower on CPU    |
| `WHISPER_DEVICE`       | `cpu`              | Set to `cuda` if you have a working NVIDIA + CUDA setup for much faster transcription |
| `WHISPER_COMPUTE_TYPE` | `int8`             | Use `float16` if running on GPU                                                       |

## Known limitations (it's meant to stay lite)

- Windows-only as written (native messaging registration + `keyboard` global
  hooks work best there; porting to macOS/Linux mainly means changing
  `install.ps1` into a shell script that edits the native host JSON path
  Chrome expects on that OS).
- The `keyboard` library's global hook occasionally needs the terminal/app
  it's launched from to have accessibility-ish permissions on some setups —
  on Windows this is normally not an issue.
- No auto-paste (by design, to avoid needing accessibility/input-injection
  permissions) — text is copied to your clipboard instead, so a manual
  `Ctrl+V` finishes the job.
