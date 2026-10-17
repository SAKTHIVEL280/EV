#!/usr/bin/env bash
# Build EV with the bundled UI, start it over an X11 backdrop and place the
# island window on that backdrop, so pointer tests work under XWayland.
#
#   bench/linux-e2e/run.sh [backdrop-color]
#   EV_TEST_DATA=/path/to/data bench/linux-e2e/run.sh   (default: ~/.cache/ev-e2e)
#   EV_TEST_HIDDEN=1 bench/linux-e2e/run.sh   (on an invisible Hyprland output, out of your way)
#
# Then drive it with xdotool (pointer and keys go through X11):
#   xdotool mousemove 1310 140      # near the drop: it opens after the delay
#   xdotool click 1                 # open the panel
#   xdotool windowfocus <EV window id>; xdotool type "hello"; xdotool key Return
# Screenshots: grim -g "1080,112 460x300" out.png
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
color="${1:-#ffffff}"
data="${EV_TEST_DATA:-$HOME/.cache/ev-e2e}"
mkdir -p "$data"

(cd "$repo/app" && pnpm -s build >/dev/null)
(cd "$repo/app/src-tauri" && cargo build --features custom-protocol --quiet)

pkill -x ev || true
pkill -f "$here/backdrop.py" || true
sleep 0.8
# Hidden mode: a headless output named EVTEST shows its own workspace; windows
# open there without focus, so the desktop in use is not disturbed.
x0=0
launch() { (setsid "$@" >/dev/null 2>&1 &); }
if [ -n "${EV_TEST_HIDDEN:-}" ]; then
  hyprctl monitors -j | grep -q '"EVTEST"' || hyprctl output create headless EVTEST >/dev/null
  sleep 0.5
  read -r ws x0 < <(hyprctl monitors -j | python3 -c '
import json, sys
m = next(m for m in json.load(sys.stdin) if m["name"] == "EVTEST")
print(m["activeWorkspace"]["id"], m["x"])')
  # Runtime-only rule (gone after `hyprctl reload`): EV's windows and the
  # backdrop open on that workspace without taking focus.
  for match in "class = '^Ev\$'" "title = '^ev-backdrop\$'"; do
    hyprctl eval "hl.window_rule({ match = { $match }, workspace = '$ws silent', no_initial_focus = true })" >/dev/null
  done
fi
launch env GDK_BACKEND=x11 python3 "$here/backdrop.py" "$color"
sleep 1
launch env EV_DATA_DIR="$data" GDK_BACKEND=x11 "$repo/app/src-tauri/target/debug/ev"
for _ in $(seq 30); do
  id=$(xdotool search --name '^EV$' 2>/dev/null | head -1 || true)
  [ -n "$id" ] && break
  sleep 0.2
done
sleep 1.5
# Hyprland tiles the backdrop on the right half; put the island over it.
for w in $(xdotool search --name '^EV$'); do xdotool windowmove "$w" $((x0 + 1100)) 120; done
xdotool mousemove $((x0 + 1500)) 700
echo "EV running (data: $data). Island centre at ($((x0 + 1310)), 120); logs in $data/logs/."
