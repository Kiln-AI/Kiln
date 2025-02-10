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

# TODO remove this
mkdir -p web_ui/build
# write a basic index.html to the build directory
echo "<html><body><h1>Kiln Studio</h1></body></html>" > web_ui/build/index.html

# Building the bootloader ourselves helps not be falsely detected as malware by antivirus software on windows.
if [[ $* == *--build-bootloader* ]]; then
  echo "Building pyinstaller inlucding bootloader"

  ROOT_DIR=$PWD
  mkdir -p desktop/build/bootloader
  cd desktop/build/bootloader
  git clone https://github.com/pyinstaller/pyinstaller.git
  cd pyinstaller/bootloader
  python ./waf all
  cd ..
  pip install .
  echo "which pyinstaller"
  which pyinstaller

  # return to the root of the project
  cd $ROOT_DIR

  # List all directories in the .venv
  echo "Listing all directories in the .venv, nested to all levels"

  # export PYTHONPATH=$PWD/../.venv/Lib/site-packages
fi

mkdir -p desktop/build

echo "Building for $(uname)"
if [ "$(uname)" == "Darwin" ]; then
  echo "Building MacOS app"
  cp desktop/mac_taskbar.png desktop/build/taskbar.png
  # onedir launches faster, and still looks like 1 file with MacOS .app bundles
  PLATFORM_OPTS="--onedir --windowed --icon=../mac_icon.png --osx-bundle-identifier=com.kiln-ai.kiln.studio"

  PY_PLAT=$(python -c 'import platform; print(platform.machine())')
  echo "Building MacOS app for single platform ($PY_PLAT)"
elif [[ "$(uname)" =~ ^MINGW64_NT-10.0 ]] || [[ "$(uname)" =~ ^MSYS_NT-10.0 ]]; then
  echo "Building Windows App"
  cp desktop/win_taskbar.png desktop/build/taskbar.png
  PLATFORM_OPTS="--windowed --splash=../win_splash.png --icon=../win_icon.ico"
elif [ "$(uname)" == "Linux" ]; then
  echo "Building Linux App"
  cp desktop/mac_taskbar.png desktop/build/taskbar.png
  PLATFORM_OPTS="--windowed --onefile --splash=../win_splash.png --icon=../mac_icon.png"
else
  echo "Unsupported operating system: $(uname)"
  exit 1
fi

# Builds the desktop app
# TODO: use a spec instead of long winded command line
pyinstaller $(printf %s "$PLATFORM_OPTS")  \
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
