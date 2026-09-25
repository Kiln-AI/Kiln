#!/usr/bin/env bash
# Usage: run_variant.sh <label> <crop-geometry> <kiln command...>
# Runs Kiln with the given command, waits for the tray to be created, screenshots,
# crops the tray area, saves the log, and kills the app.
set -u
LAB_DIR="${LAB_DIR:-/tmp/tray-lab}"
OUT="${OUT:-$LAB_DIR/shots}"
label="$1"; crop="$2"; shift 2
mkdir -p "$OUT"
. "$LAB_DIR/env.sh"
export KILN_TRAY_LOG="$OUT/$label.log"
rm -f "$KILN_TRAY_LOG"
setsid "$@" > "$OUT/$label.stdout" 2>&1 &
pid=$!
for _ in $(seq 1 120); do
  grep -q "run_detached done\|Error running tray" "$KILN_TRAY_LOG" 2>/dev/null && break
  sleep 0.5
done
sleep "${SETTLE:-3}"
import -window root "$OUT/$label.full.png"
convert "$OUT/$label.full.png" -crop "$crop" +repage "$OUT/$label.png"
convert "$OUT/$label.png" -filter point -resize 400% "$OUT/$label.x4.png"
kill -TERM -- -$pid 2>/dev/null
sleep 1
kill -KILL -- -$pid 2>/dev/null
wait $pid 2>/dev/null
grep -E "LOADED|argb|pseudo|mono-auto: panel|tray: variant|glib|appindicator: icon|FAILED|draw failed" "$KILN_TRAY_LOG" | sed 's/^[0-9-]* [0-9:,]* //' | sort -u
