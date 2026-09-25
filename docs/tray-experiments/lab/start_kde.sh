#!/usr/bin/env bash
# Start a minimal Plasma 5.27 shell (X11) on Xvfb :3 with software Qt Quick rendering.
export LAB_DIR=/tmp/tray-lab-kde LAB_DISPLAY=:3
. "$(dirname "$0")/session_env.sh"
lab_start_x
. "$LAB_ENV"
echo "export XDG_CURRENT_DESKTOP=KDE KDE_FULL_SESSION=true KDE_SESSION_VERSION=5 QT_QUICK_BACKEND=software" >> "$LAB_ENV"
. "$LAB_ENV"
kwin_x11 >"$LAB_DIR/kwin.log" 2>&1 &
sleep 2
plasmashell >"$LAB_DIR/plasma.log" 2>&1 &
sleep 12
