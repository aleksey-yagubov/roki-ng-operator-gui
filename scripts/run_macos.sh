#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .deps/macos/venv/bin/python ]]; then
  echo 'Run scripts/build_macos.sh first' >&2
  exit 1
fi
QT_PREFIX=${QT_PREFIX:-$(brew --prefix qt)}
export DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib:${DYLD_FALLBACK_LIBRARY_PATH:-/usr/local/lib:/usr/lib}"
export DYLD_FRAMEWORK_PATH="$QT_PREFIX/lib"
exec .deps/macos/venv/bin/python roki_operator.py "$@"
