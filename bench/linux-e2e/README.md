# Linux end-to-end checks

Development runs on Linux (Hyprland); EV ships for Windows. These checks run the
real app here: the island's pointer rules, the panel, chat, model download and
Settings. Windows-only behavior (focus hand-back, fullscreen detection, IME,
Mica) still needs the Windows checklist in `bench/spikes/README.md`.

`run.sh` builds EV with the bundled UI and starts it over an X11 backdrop.
Why the backdrop: under XWayland EV only sees the pointer over X11 windows, and
Hyprland's own cursor warp does not reach X11 clients, so tests move the
pointer with `xdotool`. Keyboard input needs `xdotool windowfocus` on EV first.

Resume test without a large download: copy the first ~2.6 GB of an installed
model to `<data>/models/<file>.part`; EV then fetches only the rest from
Hugging Face and verifies the whole file.
