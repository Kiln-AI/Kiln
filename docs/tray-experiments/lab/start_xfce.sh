#!/usr/bin/env bash
# Start an XFCE panel session on its own Xvfb display + D-Bus session.
# Usage: start_xfce.sh   (then: . /tmp/tray-lab-xfce/env.sh)
export LAB_DIR=/tmp/tray-lab-xfce LAB_DISPLAY=:2
. "$(dirname "$0")/session_env.sh"
lab_start_x
. "$LAB_ENV"
echo "export XDG_CURRENT_DESKTOP=XFCE" >> "$LAB_ENV"
export XDG_CURRENT_DESKTOP=XFCE
xfconfd >/dev/null 2>&1 &
xfsettingsd --no-daemon >"$LAB_DIR/xfsettingsd.log" 2>&1 &
xfwm4 --compositor=on >"$LAB_DIR/xfwm4.log" 2>&1 &
sleep 1
xfce4-panel >"$LAB_DIR/panel.log" 2>&1 &
sleep 3
