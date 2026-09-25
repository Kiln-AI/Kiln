#!/usr/bin/env bash
# Shared helpers for the headless tray lab. Source this file.
# Starts Xvfb and a D-Bus session bus once, and writes their env to $LAB_ENV.
LAB_DIR="${LAB_DIR:-/tmp/tray-lab}"
LAB_ENV="$LAB_DIR/env.sh"
mkdir -p "$LAB_DIR"

lab_start_x() {
  if [ -f "$LAB_ENV" ] && . "$LAB_ENV" && xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
    return 0
  fi
  export DISPLAY="${LAB_DISPLAY:-:1}"
  Xvfb "$DISPLAY" -screen 0 1280x800x24 +extension GLX +extension RANDR +extension COMPOSITE >"$LAB_DIR/xvfb.log" 2>&1 &
  sleep 1
  eval "$(dbus-launch --sh-syntax)"
  export XDG_RUNTIME_DIR="$LAB_DIR/runtime"
  mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
  cat >"$LAB_ENV" <<ENV
export DISPLAY=$DISPLAY
export DBUS_SESSION_BUS_ADDRESS='$DBUS_SESSION_BUS_ADDRESS'
export DBUS_SESSION_BUS_PID=$DBUS_SESSION_BUS_PID
export XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR
export XDG_SESSION_TYPE=x11
ENV
}

lab_shot() {
  # lab_shot <out.png> [crop geometry e.g. 300x32+980+0]
  import -window root "$1.full.png"
  if [ -n "$2" ]; then
    convert "$1.full.png" -crop "$2" +repage "$1"
    rm -f "$1.full.png"
  else
    mv "$1.full.png" "$1"
  fi
}
