"""컴퓨터 클립보드 읽기. 회원이 학원월드 주간 게시글을 ⌘A ⌘C(Ctrl+A Ctrl+C)로 복사해 두면
콘봇이 링크가 살아 있는 HTML 그대로 읽는다 (글자로만 붙여 넣으면 영상 링크가 사라지는 경우가 많다)."""
from __future__ import annotations

import os
import re
import subprocess
import sys


def _mac_html() -> str:
    js = ("ObjC.import('AppKit');var p=$.NSPasteboard.generalPasteboard;"
          "var s=p.stringForType('public.html');s.isNil()?'':s.js")
    try:
        r = subprocess.run(["osascript", "-l", "JavaScript", "-e", js], capture_output=True, timeout=10)
        h = r.stdout.decode("utf-8", "replace").strip()
        if h:
            return h
    except Exception:
        pass
    try:  # 예전 방식: «data HTML3C68…» 꼴의 16진수
        r = subprocess.run(["osascript", "-e", "the clipboard as «class HTML»"], capture_output=True, timeout=10)
        m = re.search(r"«data HTML([0-9A-Fa-f]+)»", r.stdout.decode("utf-8", "replace"))
        return bytes.fromhex(m.group(1)).decode("utf-8", "replace") if m else ""
    except Exception:
        return ""


def _win_html() -> str:
    import ctypes
    from ctypes import wintypes
    u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
    u32.RegisterClipboardFormatW.restype = wintypes.UINT
    u32.GetClipboardData.restype = ctypes.c_void_p
    u32.GetClipboardData.argtypes = [wintypes.UINT]
    k32.GlobalLock.restype = ctypes.c_void_p
    k32.GlobalLock.argtypes = [ctypes.c_void_p]
    k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    k32.GlobalSize.restype = ctypes.c_size_t
    k32.GlobalSize.argtypes = [ctypes.c_void_p]
    fmt = u32.RegisterClipboardFormatW("HTML Format")
    if not u32.OpenClipboard(None):
        return ""
    try:
        h = u32.GetClipboardData(fmt)
        if not h:
            return ""
        p = k32.GlobalLock(h)
        try:
            raw = ctypes.string_at(p, k32.GlobalSize(h))
        finally:
            k32.GlobalUnlock(h)
    finally:
        u32.CloseClipboard()
    raw = raw.split(b"\0", 1)[0]
    m = re.search(rb"StartHTML:(\d+)", raw)
    return raw[int(m.group(1)):].decode("utf-8", "replace") if m else raw.decode("utf-8", "replace")


def _text() -> str:
    try:
        if sys.platform == "darwin":
            return subprocess.run(["pbpaste"], capture_output=True, timeout=10).stdout.decode("utf-8", "replace")
        if os.name == "nt":
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"],
                               capture_output=True, timeout=15, creationflags=0x08000000)
            return r.stdout.decode("utf-8", "replace")
    except Exception:
        pass
    return ""


def read() -> tuple[str, str]:
    """(html, text). 둘 다 비어 있을 수 있다."""
    html = ""
    try:
        if sys.platform == "darwin":
            html = _mac_html()
        elif os.name == "nt":
            html = _win_html()
    except Exception:
        html = ""
    return html, _text()
