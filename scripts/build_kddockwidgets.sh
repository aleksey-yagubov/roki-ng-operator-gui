#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
SRC="$ROOT/.deps/src/KDDockWidgets"
BUILD="$ROOT/.deps/build/KDDockWidgets"
COMMIT=c1d28d25ef5ba077915bcb2b6fa9e14df2a361f8

if [[ $(uname -s) != Linux ]]; then
    printf 'This build recipe currently supports Linux only.\n' >&2
    exit 1
fi

for tool in git cmake ninja c++ patchelf; do
    command -v "$tool" >/dev/null
done

if [[ ! -d "$SRC/.git" ]]; then
    git_args=()
    if [[ -n ${DOWNLOAD_PROXY:-} ]]; then
        git_args=(-c "http.proxy=$DOWNLOAD_PROXY")
    fi
    git "${git_args[@]}" clone --depth 1 --branch v2.4.1 \
        https://github.com/KDAB/KDDockWidgets.git "$SRC"
fi
if [[ $(git -C "$SRC" rev-parse HEAD) != "$COMMIT" ]]; then
    printf 'Unexpected KDDockWidgets revision; refusing to overwrite source.\n' >&2
    exit 1
fi

PATCH="$ROOT/scripts/patches/kddw-wayland-drop.patch"
if git -C "$SRC" apply --reverse --check "$PATCH" 2>/dev/null; then
    printf 'Wayland drop fix already applied.\n'
else
    git -C "$SRC" apply --check "$PATCH"
    git -C "$SRC" apply "$PATCH"
fi

cmake -S "$SRC" -B "$BUILD" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$ROOT/.deps/install" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    '-DCMAKE_INSTALL_RPATH=$ORIGIN;$ORIGIN/../../../lib' \
    -DKDDockWidgets_FRONTENDS=qtquick \
    -DKDDockWidgets_QML_MODULE=ON \
    -DKDDockWidgets_EXAMPLES=OFF \
    -DKDDockWidgets_TESTS=OFF \
    -DKDDockWidgets_PYTHON_BINDINGS=OFF \
    -DKDDockWidgets_NO_SPDLOG=ON
cmake --build "$BUILD" --parallel "${JOBS:-$(nproc)}"

# This upstream release does not install the shared QML plugin with cmake --install.
# Stage the complete module ourselves, without installing anything system-wide.
MODULE="$ROOT/native/qml/com/kdab/dockwidgets"
mkdir -p "$MODULE" "$ROOT/native/licenses/KDDockWidgets"
cp -a "$BUILD/com/kdab/dockwidgets/." "$MODULE/"
cp -a "$BUILD/lib/"libkddockwidgets-qt6.so* "$MODULE/"
patchelf --set-rpath '$ORIGIN' "$MODULE/libkddockwidgetsplugin.so"
patchelf --set-rpath '$ORIGIN' "$MODULE/libkddockwidgets-qt6.so.2.4.1"
cp "$SRC/LICENSE.txt" "$SRC/3RDPARTY.md" "$ROOT/native/licenses/KDDockWidgets/"
cp -a "$SRC/LICENSES" "$ROOT/native/licenses/KDDockWidgets/"
mkdir -p "$ROOT/native/sources"
git -C "$SRC" archive --format=tar.gz --prefix=KDDockWidgets/ \
    --output="$ROOT/native/sources/KDDockWidgets-v2.4.1.tar.gz" "$COMMIT"
printf 'QML plugin staged at %s\n' "$MODULE"
du -sh "$ROOT/native"
