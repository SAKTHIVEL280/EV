#!/usr/bin/env bash
# A separate X display (:99) for keyboard and panel tests, out of the way of the
# desktop in use: rootful Xwayland on an invisible Hyprland output. Inside it,
# focus and key presses stay inside; the real desktop keeps its focus.
#
#   bench/linux-e2e/nested.sh            # start (idempotent), prints DISPLAY
#   bench/linux-e2e/nested.sh stop
# Then: DISPLAY=:99 WAYLAND_DISPLAY= GDK_BACKEND=x11 <app>; drive with xdotool.
set -euo pipefail
display=:99
if [ "${1:-}" = "stop" ]; then
  pkill -f "^Xwayland ${display}( |$)" || true
  hyprctl output remove EVTEST >/dev/null 2>&1 || true
  exit 0
fi
hyprctl monitors -j | grep -q '"EVTEST"' || hyprctl output create headless EVTEST >/dev/null
sleep 0.5
ws=$(hyprctl monitors -j | python3 -c '
import json, sys
print(next(m for m in json.load(sys.stdin) if m["name"] == "EVTEST")["activeWorkspace"]["id"])')
if ! pgrep -f "^Xwayland ${display}( |$)" >/dev/null; then
  # The rule must exist before the window maps, or it lands on the desktop in use.
  hyprctl eval "hl.window_rule({ match = { class = '^org.freedesktop.Xwayland\$' }, workspace = '$ws silent', no_initial_focus = true })" | grep -qx ok
  (setsid Xwayland "$display" -geometry 1600x900 -noreset >/dev/null 2>&1 &)
  sleep 2
fi
echo "DISPLAY=${display}"
