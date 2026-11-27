#!/bin/bash
# 콘봇 맥 설치: 받기 → 응용 프로그램에 넣기 → 열기. 회원이 따로 깔 것은 없음.
set -e
BASE="https://github.com/genedonsa/yujabs-planner/releases/latest/download"
if [ "$(uname -m)" = "arm64" ]; then FILE="CornBot-macOS.zip"; else FILE="CornBot-macOS-Intel.zip"; fi
TMP="$(mktemp -d)"
echo "콘봇 받는 중... ($FILE)"
curl -fL --progress-bar -o "$TMP/$FILE" "$BASE/$FILE"
ditto -x -k "$TMP/$FILE" "$TMP/app"
DEST="/Applications"
[ -w "$DEST" ] || DEST="$HOME/Applications"
mkdir -p "$DEST"
rm -rf "$DEST/CornBot.app"
mv "$TMP/app/CornBot.app" "$DEST/CornBot.app"
xattr -dr com.apple.quarantine "$DEST/CornBot.app" 2>/dev/null || true
rm -rf "$TMP"
echo "설치 완료: $DEST/CornBot.app"
open "$DEST/CornBot.app"
