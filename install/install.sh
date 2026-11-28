#!/bin/bash
# 콘봇 맥 설치: 받기 → 응용 프로그램에 넣기 → 열기. 회원이 따로 깔 것은 없음.
set -e
BASE="https://github.com/genedonsa/yujabs-planner/releases/latest/download"
MAJOR="$(sw_vers -productVersion 2>/dev/null | cut -d. -f1)"
if [ -n "$MAJOR" ] && [ "$MAJOR" -lt 15 ]; then
  echo "이 맥은 macOS $(sw_vers -productVersion)이에요. 콘봇은 macOS 15(Sequoia) 이상에서 돌아가요."
  echo "사과 메뉴 → 시스템 설정 → 일반 → 소프트웨어 업데이트에서 macOS를 올린 뒤 다시 해 주세요."
  exit 1
fi
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
[ -n "$CORNBOT_NO_OPEN" ] || open "$DEST/CornBot.app"
