#!/usr/bin/env bash
# Linux-only PyInstaller build for the tray experiments (throwaway branch).
#
#   app/desktop/build_tray_experiments.sh [--gi|--no-gi] [--onedir]
#
# --gi     install PyGObject into the venv first so PyInstaller bundles gi, GTK 3 and
#          (Ayatana)AppIndicator3 typelibs + shared libs (needs libgirepository-2.0-dev,
#          libcairo2-dev, gir1.2-ayatanaappindicator3-0.1 on the build machine)
# --no-gi  uninstall PyGObject first, reproducing the current production build
#
# Output: app/desktop/build/dist-<gi|nogi>/Kiln (onefile, like production)
# Assumes app/web_ui/build exists (run the web build, or build_desktop_app.sh, first).

set -euo pipefail
cd "$(dirname "$0")/.."
APP_DIR=$PWD

GI=gi
MODE=--onefile
for arg in "$@"; do
  case $arg in
    --gi) GI=gi ;;
    --no-gi) GI=nogi ;;
    --onedir) MODE=--onedir ;;
    *) echo "unknown arg $arg"; exit 1 ;;
  esac
done

if [ "$GI" == "gi" ]; then
  uv pip install -q pygobject
  GI_OPTS="--hidden-import=gi --hidden-import=gi.repository.Gtk --hidden-import=gi.repository.AyatanaAppIndicator3"
  # AppIndicator3 (legacy libappindicator) only when its typelib is findable
  if uv run --no-sync python -c "import gi; gi.require_version('AppIndicator3','0.1')" 2>/dev/null; then
    GI_OPTS="$GI_OPTS --hidden-import=gi.repository.AppIndicator3"
  fi
else
  uv pip uninstall -q pygobject pycairo || true
  GI_OPTS="--exclude-module=gi"
fi

mkdir -p desktop/build
cp desktop/mac_taskbar.png desktop/build/taskbar.png

# shellcheck disable=SC2086
uv run --no-sync pyinstaller --windowed $MODE --splash=../win_splash.png --icon=../mac_icon.png \
  --add-data "./taskbar.png:." --add-data "../../web_ui/build:./web_ui/build" \
  --add-data "../tray_icons:./tray_icons" \
  --noconfirm --distpath="./desktop/build/dist-$GI" --workpath="./desktop/build/work-$GI" \
  -n Kiln --specpath=./desktop/build --hidden-import=tiktoken_ext.openai_public --hidden-import=tiktoken_ext \
  --hidden-import=kiln_ai.adapters.eval.eval_helpers \
  --hidden-import=litellm \
  --collect-all=litellm \
  --hidden-import=pystray._xorg --hidden-import=pystray._gtk --hidden-import=pystray._appindicator \
  $GI_OPTS \
  --paths=. ./desktop/desktop.py

ls -la "desktop/build/dist-$GI/"
du -sh "desktop/build/dist-$GI/"*
