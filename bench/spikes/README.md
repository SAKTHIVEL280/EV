# EV Phase 0 spikes — Windows 11 checklist

These three spikes prove the risky platform assumptions before any feature
work (docs/ROADMAP.md, Phase 0). They run on the Windows 11 test laptop.
Everything below takes about 30 minutes.

The kit (GitHub Actions artifact `ev-windows-spike-kit`) contains:

| File | Purpose |
|---|---|
| `EV_<version>_x64-setup.exe` | Unsigned per-user installer (no admin) |
| `SHA256SUMS.txt` | Installer checksum |
| `s3-llama.ps1` | Spike S3 benchmark |
| `llama-cpp.pins` | Pinned llama.cpp builds + SHA-256 (read by `s3-llama.ps1`) |
| `collect-results.ps1` | Zips logs and results to share back |

## 0. Before you start

1. Write down the laptop's CPU, RAM and GPU (Settings → System → About). S3
   records them automatically too.
2. Plug in the charger (battery mode changes performance).
3. Verify the installer:
   `Get-FileHash .\EV_*_x64-setup.exe -Algorithm SHA256` must match `SHA256SUMS.txt`.

## S1 — Island window

Install: run the setup file. Windows SmartScreen warns because the beta is
unsigned: **More info → Run anyway**. EV starts after install.

A small black pill appears at the top center of the main screen.

| # | Check | Pass when |
|---|---|---|
| 1 | Shadow | No shadow or border around the pill or the panel. |
| 2 | Click-through | Put a window right under the pill. Click its content 2–5 mm beside and below the pill: the window receives the click. |
| 3 | Hover | Move the mouse onto the pill: it grows and shows "Ready". Move away: it shrinks back. |
| 4 | No focus steal | Type in Notepad and move the mouse over the pill while typing: the text keeps going into Notepad. |
| 5 | Panel | Click the hovered pill: the panel opens with the cursor in the message box. It closes with **Esc** or by clicking another window. |
| 6 | Focus return | Click into Notepad, open the panel, press **Esc**, keep typing: the text goes into Notepad again. |
| 7 | Fullscreen | Play a video fullscreen (or press F11 in a browser, or start a game): the pill disappears; it returns when you leave fullscreen. |
| 8 | 60 fps | Open the panel → **Run morph test**. The result line must show `0 dropped`. Note the `worst` and `settle` values. |
| 9 | 150% scaling | Settings → Display → Scale 150%, then repeat checks 2, 3 and 8. |

Write down pass/fail for each row. The morph test results are also logged.

## S2 — Packaged core and cold start

1. Quit EV (panel → **Quit EV**), wait 10 seconds, then start EV from the Start menu.
2. Hover the pill: it must say **Ready** within a couple of seconds (core started).
3. Note the installer file size (budget: ≤ 150 MB without models).

The cold start time (`spike s2 island painted`, budget ≤ 1.5 s) is written to
`%APPDATA%\EV\logs\app.log` automatically.

## S3 — llama.cpp on this PC

Needs the Qwen3.5-4B Q4_K_M GGUF file used for the Linux baseline.

```powershell
powershell -ExecutionPolicy Bypass -File .\s3-llama.ps1 -ModelPath C:\path\to\Qwen3.5-4B-Q4_K_M.gguf
```

It downloads the pinned llama.cpp CPU and Vulkan builds (SHA-256 verified),
runs `llama-bench` and measures `llama-server` memory with and without
`-lm none`. Takes 5–15 minutes. Close other heavy apps first.

## Optional — Phase 1 chat on Windows

Only if the installer was built from the `feat/phase-1-brain` branch.

1. Copy the model file to `%APPDATA%\EV\models\Qwen3.5-4B-Q4_K_M.gguf`.
2. Open `%APPDATA%\EV\config.toml` and set, under `[llm]`:
   `model_default = "Qwen3.5-4B-Q4_K_M.gguf"`. Save; it applies without restarting.
3. Open the panel and ask "What time is it?" (instant), then "In one sentence, what is RAM?"
   and "Is it morning or evening right now?". Note the `first word` / `total` times shown.
4. Check Task Manager: `llama-server.exe` memory, and that it disappears when you quit EV.

## Optional — Phase 2 checks on Windows

Only if the installer was built from the `feat/phase-2-island` branch.

| # | Check | Pass when |
|---|---|---|
| H1 | Hotkey | In any app, press Ctrl+Space: the panel opens with the cursor in the message box. Press it again: it closes and typing goes back to the app. |
| H2 | Hotkey change | Settings → Hotkeys: set `Ctrl+Shift+Space`. The new shortcut works at once; the old one does nothing. |
| H3 | Tray | The EV icon is in the tray and visible on the taskbar (light and dark mode). Left click toggles the panel; right click shows Open EV, Settings, Quit EV and each works. |
| H4 | Settings | Panel → Settings opens the window. Change "Default effort": `%APPDATA%\EV\config.toml` shows the new value. Type 99 in "Context window": a message shows the allowed range. "Reset to default" restores it. |
| H5 | Settings live | Edit `config.toml` in Notepad and save: the open Settings window shows the new value within a second. |

## Share the results

```powershell
powershell -ExecutionPolicy Bypass -File .\collect-results.ps1
```

This creates `Desktop\ev-spike-results.zip` (EV logs + S3 results). Logs
contain timings and states only, no personal content. Send the zip together
with the S1 pass/fail list.
