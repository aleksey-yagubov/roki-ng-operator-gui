#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $(uname -s) == Darwin ]] || { echo 'macOS required'; exit 1; }
[[ -x .deps/macos/venv/bin/python ]] || { echo 'Run scripts/build_macos.sh first'; exit 1; }
HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1 HOMEBREW_NO_INSTALL_CLEANUP=1 \
  brew install gstreamer gobject-introspection
.deps/macos/venv/bin/python -m pip install 'PyGObject>=3.50,<4'
QT_PREFIX=${QT_PREFIX:-$(brew --prefix qt)}
export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib:${DYLD_FALLBACK_LIBRARY_PATH:-/usr/local/lib:/usr/lib}"
DYLD_FRAMEWORK_PATH="$QT_PREFIX/lib" .deps/macos/venv/bin/python scripts/check_gstreamer.py
