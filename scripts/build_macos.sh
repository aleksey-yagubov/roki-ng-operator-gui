#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ $(uname -s) == Darwin ]] || { echo 'macOS required'; exit 1; }
QT_PREFIX=${QT_PREFIX:-$(brew --prefix qt)}
PYTHON=${PYTHON:-python3.11}
QT_VERSION=$("$QT_PREFIX/bin/qmake" -query QT_VERSION)
mkdir -p .deps/src .deps/macos
if [[ ! -f .deps/src/KDDockWidgets/CMakeLists.txt ]]; then
  mkdir -p .deps/src/KDDockWidgets
  tar -xf native/sources/KDDockWidgets-v2.4.1.tar.gz -C .deps/src/KDDockWidgets --strip-components=1
fi
[[ -x .deps/macos/venv/bin/python ]] || "$PYTHON" -m venv .deps/macos/venv
.deps/macos/venv/bin/python -m pip install "PySide6==$QT_VERSION" 'msgpack>=1.1,<2' 'numpy>=2,<3'
cmake -S .deps/src/KDDockWidgets -B .deps/macos/build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$QT_PREFIX" \
  -DCMAKE_PROJECT_INCLUDE="$PWD/native/macos/qt_sdk_compat.cmake" \
  -DKDDockWidgets_FRONTENDS=qtquick -DKDDockWidgets_QML_MODULE=OFF \
  -DKDDockWidgets_EXAMPLES=OFF -DKDDockWidgets_TESTS=OFF \
  -DKDDockWidgets_PYTHON_BINDINGS=OFF -DKDDockWidgets_NO_SPDLOG=ON
cmake --build .deps/macos/build --parallel "${BUILD_JOBS:-6}"
cmake --install .deps/macos/build --prefix "$PWD/.deps/macos/install"
cmake -S native/macos -B .deps/macos/bootstrap -G Ninja \
  -DCMAKE_PREFIX_PATH="$PWD/.deps/macos/install;$QT_PREFIX" \
  -DCMAKE_PROJECT_INCLUDE="$PWD/native/macos/qt_sdk_compat.cmake"
cmake --build .deps/macos/bootstrap
printf '%s\n' "$QT_VERSION" > .deps/macos/qt-version.txt
