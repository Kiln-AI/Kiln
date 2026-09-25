#!/usr/bin/env bash
# Run every variant of the frozen builds on one desktop/panel and screenshot the tray.
# Usage: run_matrix.sh <gnome|xfce> <panel-label e.g. dark|light>
set -u
cd "$(dirname "$0")/../../.."
desk=$1; panel=$2
if [ "$desk" == "gnome" ]; then
  export LAB_DIR=/tmp/tray-lab; CROP=90x32+1180+0
else
  export LAB_DIR=/tmp/tray-lab-xfce; CROP=100x26+1095+0
fi
export OUT="$LAB_DIR/matrix-$panel" SETTLE=${SETTLE:-3}
mkdir -p "$OUT"
NOGI=app/desktop/build/dist-nogi/Kiln
GI=app/desktop/build/dist-gi/Kiln
R=docs/tray-experiments/lab/run_variant.sh
run() { label=$1; shift; case "$label" in ${ONLY:-}*) ;; *) return ;; esac; $R "$desk-$panel-$label" "$CROP" "$@" >/dev/null 2>&1; echo "done $label"; }

run nogi-default          $NOGI
run nogi-pr1814           $NOGI --tray-variant pr1814
run nogi-xorg-color       $NOGI --tray-variant color
run nogi-xorg-color-argb  $NOGI --tray-variant color --tray-xorg argb
run nogi-xorg-mono-auto-argb $NOGI --tray-variant mono-auto --tray-xorg argb
run nogi-xorg-bg-auto     $NOGI --tray-variant color --tray-xorg bg:auto
run nogi-sni-baseline     $NOGI --tray-backend sni
run nogi-sni-color        $NOGI --tray-backend sni --tray-variant color
run nogi-sni-tile         $NOGI --tray-backend sni --tray-variant tile
run nogi-sni-mono-auto    $NOGI --tray-backend sni --tray-variant mono-auto
run nogi-sni-mono-white-edge $NOGI --tray-backend sni --tray-variant mono-white-edge
run nogi-sni-mono-black-edge $NOGI --tray-backend sni --tray-variant mono-black-edge
run nogi-sni-symbolic     $NOGI --tray-backend sni --tray-variant symbolic
run gi-default-noglib     $GI --tray-glib-thread off
run gi-default            $GI
run gi-pr1814             $GI --tray-variant pr1814
run gi-color              $GI --tray-variant color
run gi-color-22           $GI --tray-variant color --tray-size 22
run gi-tile               $GI --tray-variant tile
run gi-mono-auto          $GI --tray-variant mono-auto
run gi-symbolic           $GI --tray-variant symbolic
run gi-themed             $GI --tray-variant themed
run gi-gtk-color          $GI --tray-backend gtk --tray-variant color
run gi-xorg-default       $GI --tray-backend xorg
