"""자동 업데이트. 새 버전이 GitHub 릴리스에 올라오면, 회원이 버튼 하나로 받아서 바꾸고 다시 연다.

- 앱이 직접 받으므로 브라우저 다운로드와 달리 맥 보안 경고(격리 표시)가 붙지 않는다.
- 설정·경험·지난 기록은 '문서'가 아니라 홈의 '유잡스 기획' 폴더에 있어서 그대로 남는다.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import net
from .version import VERSION

REPO = "genedonsa/yujabs-planner"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
DL = f"https://github.com/{REPO}/releases/latest/download/"


def _vt(v: str) -> tuple:
    return tuple(int(x) for x in v.lstrip("v").split(".") if x.isdigit())


def check() -> dict:
    req = urllib.request.Request(API, headers={"User-Agent": "CornBot", "Accept": "application/vnd.github+json"})
    with net.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    latest = data.get("tag_name", "")
    return {"current": VERSION, "latest": latest.lstrip("v"), "notes": data.get("body") or "",
            "available": bool(latest) and _vt(latest) > _vt(VERSION) and getattr(sys, "frozen", False)}


def _asset() -> str:
    if sys.platform == "darwin":
        return "CornBot-macOS.zip" if platform.machine() == "arm64" else "CornBot-macOS-Intel.zip"
    return "CornBot-windows.zip"


def apply() -> None:
    """새 버전을 받아 풀고, 이 앱이 꺼지면 바꿔 끼운 뒤 다시 여는 작은 스크립트를 띄운다."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("개발 모드에서는 업데이트하지 않아요.")
    tmp = Path(tempfile.mkdtemp(prefix="cornbot-upd-"))
    zpath = tmp / _asset()
    req = urllib.request.Request(DL + _asset(), headers={"User-Agent": "CornBot"})
    with net.urlopen(req, timeout=300) as r, open(zpath, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    new = tmp / "new"
    pid = os.getpid()
    if sys.platform == "darwin":
        subprocess.run(["ditto", "-x", "-k", str(zpath), str(new)], check=True)
        app = Path(sys.executable).resolve().parents[2]  # …/CornBot.app/Contents/MacOS/CornBot
        script = tmp / "swap.sh"
        script.write_text(f"""#!/bin/bash
while kill -0 {pid} 2>/dev/null; do sleep 0.5; done
rm -rf "{app}"
mv "{new}/CornBot.app" "{app}"
xattr -dr com.apple.quarantine "{app}" 2>/dev/null
open "{app}"
""", encoding="utf-8")
        subprocess.Popen(["/bin/bash", str(script)], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        with zipfile.ZipFile(zpath) as z:
            z.extractall(new)
        home = Path(sys.executable).resolve().parent
        exe = Path(sys.executable).resolve()
        script = tmp / "swap.bat"
        script.write_text(f"""@echo off
:wait
tasklist /FI "PID eq {pid}" | find "{pid}" >nul && (timeout /t 1 /nobreak >nul & goto wait)
robocopy "{new}" "{home}" /MIR /NFL /NDL /NJH /NJS >nul
start "" "{exe}"
""", encoding="mbcs")
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags, close_fds=True)
