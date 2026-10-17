#!/usr/bin/env bash
# Build EV with the bundled UI, start it over an X11 backdrop and place the
# island window on that backdrop, so pointer tests work under XWayland.
#
#   bench/linux-e2e/run.sh [backdrop-color]
#   EV_TEST_DATA=/path/to/data bench/linux-e2e/run.sh   (default: ~/.cache/ev-e2e)
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
(GDK_BACKEND=x11 setsid python3 "$here/backdrop.py" "$color" >/dev/null 2>&1 &)
sleep 1
(EV_DATA_DIR="$data" GDK_BACKEND=x11 setsid "$repo/app/src-tauri/target/debug/ev" \
  >"$data/ev.out" 2>&1 &)
for _ in $(seq 30); do
  id=$(xdotool search --name '^EV$' 2>/dev/null | head -1 || true)
  [ -n "$id" ] && break
  sleep 0.2
done
sleep 1.5
# Hyprland tiles the backdrop on the right half; put the island over it.
for w in $(xdotool search --name '^EV$'); do xdotool windowmove "$w" 1100 120; done
xdotool mousemove 1500 700
echo "EV running (data: $data). Drop centre at (1310, 120); logs in $data/logs/."
