#!/bin/bash
# Xcode か Command Line Tools の swiftc でビルドする（管理者権限不要）
set -euo pipefail
cd "$(dirname "$0")"

APP=build/ClaudeMeter.app
rm -rf "$APP" build/AppIcon.iconset
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# Apple シリコンと Intel の両方で動くユニバーサルバイナリにする
for arch in arm64 x86_64; do
  swiftc -O -swift-version 5 -target "$arch-apple-macos13.0" \
    -framework AppKit -framework ServiceManagement \
    -o "build/ClaudeMeter-$arch" Sources/*.swift
done
lipo -create -output "$APP/Contents/MacOS/ClaudeMeter" build/ClaudeMeter-arm64 build/ClaudeMeter-x86_64
rm build/ClaudeMeter-arm64 build/ClaudeMeter-x86_64
cp Info.plist "$APP/Contents/"

"$APP/Contents/MacOS/ClaudeMeter" --make-iconset build/AppIcon.iconset
iconutil -c icns -o "$APP/Contents/Resources/AppIcon.icns" build/AppIcon.iconset
rm -rf build/AppIcon.iconset

# 署名なしだと起動できないので、その場限りの署名（ad-hoc）をする
codesign --force --sign - "$APP"
echo "Built: $(pwd)/$APP"
