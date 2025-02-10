#!/usr/bin/env bash

set -e

# move to the root of the project
cd "$(dirname "$0")"
cd ..

if [[ $* != *--skip-web* ]]; then
  # build the web ui
  echo "Building web UI"
  cd web_ui
  npm install
  npm run build
  cd ..
fi

if [[ $* == *--build-bootloader* ]]; then
  echo "Building bootloader"
  ROOT_DIR=$PWD
  mkdir -p desktop/build/bootloader
  cd desktop/build/bootloader
  git clone https://github.com/pyinstaller/pyinstaller.git
  cd pyinstaller/bootloader
  python ./waf all
  pip install .
  which pyinstaller
  
  # Set environment variable to use custom bootloader
  #export PYTHONPATH="$PWD/../..:$PYTHONPATH"
  #export PYINSTALLER_BOOTLOADER_DIR="$PWD/../../PyInstaller/bootloader"

  # return to the root of the project
  cd $ROOT_DIR
fi

mkdir -p desktop/build

echo "Building for $(uname)"
if [ "$(uname)" == "Darwin" ]; then
  echo "Building MacOS app"
  cp desktop/mac_taskbar.png desktop/build/taskbar.png
  cp desktop/mac_icon.png desktop/build/icon.png
  # onedir launches faster, and still looks like 1 file with MacOS .app bundles
  PLATFORM_OPTS="--onedir --windowed --osx-bundle-identifier=com.kiln-ai.kiln.studio"

  PY_PLAT=$(python -c 'import platform; print(platform.machine())')
  echo "Building MacOS app for single platform ($PY_PLAT)"
elif [[ "$(uname)" =~ ^MINGW64_NT-10.0 ]] || [[ "$(uname)" =~ ^MSYS_NT-10.0 ]]; then
  echo "Building Windows App"
  cp desktop/win_taskbar.png desktop/build/taskbar.png
  cp desktop/win_icon.png desktop/build/icon.png
  PLATFORM_OPTS="--windowed --splash=../win_splash.png"
elif [ "$(uname)" == "Linux" ]; then
  echo "Building Linux App"
  cp desktop/mac_taskbar.png desktop/build/taskbar.png
  cp desktop/mac_icon.png desktop/build/icon.png
  PLATFORM_OPTS="--windowed --onefile --splash=../win_splash.png"
else
  echo "Unsupported operating system: $(uname)"
  exit 1
fi

# Builds the desktop app
# TODO: use a spec instead of long winded command line
pyinstaller $(printf %s "$PLATFORM_OPTS") --icon="./icon.png" \
  --add-data "./taskbar.png:." --add-data "../../web_ui/build:./web_ui/build" \
  --noconfirm --distpath=./desktop/build/dist --workpath=./desktop/build/work \
  -n Kiln --specpath=./desktop/build \
  --paths=. ./desktop/desktop.py

# MacOS apps have symlinks, and GitHub artifact upload zip will break them. Tar instead.
if [[ $* == *--compress-mac-app* && "$(uname)" == "Darwin" ]]; then
  echo "Compressing MacOS app"
  cd ./desktop/build/dist
  tar czpvf Kiln.app.tgz Kiln.app
  rm -r Kiln.app
  cd ../../..
fi
