#!/usr/bin/env bash
# Start GNOME Shell 46 (X11) with the Ubuntu AppIndicator extension on Xvfb :1.
# Container notes: no systemd-logind, so /run/systemd/seats must not exist (GNOME then
# uses its dummy login manager), and a system bus must be running.
export LAB_DIR=/tmp/tray-lab LAB_DISPLAY=:1
. "$(dirname "$0")/session_env.sh"
[ -d /run/systemd/seats ] && mv /run/systemd/seats /run/systemd/seats.disabled
[ -S /run/dbus/system_bus_socket ] || { mkdir -p /run/dbus; dbus-daemon --system --fork; }
lab_start_x
. "$LAB_ENV"
echo "export XDG_CURRENT_DESKTOP=GNOME XDG_SESSION_DESKTOP=gnome" >> "$LAB_ENV"
export XDG_CURRENT_DESKTOP=GNOME XDG_SESSION_DESKTOP=gnome
gsettings set org.gnome.shell disable-user-extensions false
gsettings set org.gnome.shell enabled-extensions "['ubuntu-appindicators@ubuntu.com']"
gnome-shell --x11 --replace >"$LAB_DIR/gnome.log" 2>&1 &
sleep 8
xdotool key Escape
