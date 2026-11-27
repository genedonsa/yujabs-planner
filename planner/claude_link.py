"""회원의 Claude 데스크톱 앱에 콘봇을 '도구(MCP)'로 등록한다.

Claude 앱 설정 파일(claude_desktop_config.json)의 mcpServers에 cornbot 항목을 넣는다.
- 다른 항목은 그대로 둔다. 파일이 깨져 있으면 손대지 않고 알려 준다.
- 바꾸기 전 백업(.cornbot-bak)을 남기고, 임시 파일 → 바꿔치기로 저장한다.
Claude 앱은 켤 때 이 파일을 읽으므로, 등록 후 Claude 앱을 완전히 껐다 켜야 연결된다.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

KEY = "cornbot"


def config_paths() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"]
    if os.name == "nt":
        out = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            out.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
        local = os.environ.get("LOCALAPPDATA")
        if local:  # 마이크로소프트 스토어판 Claude는 설정을 이 안쪽에 둔다
            for pkg in (Path(local) / "Packages").glob("Claude_*"):
                out.append(pkg / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json")
        return out
    return [home / ".config" / "Claude" / "claude_desktop_config.json"]


def entry(exe: str | None = None) -> dict:
    return {"command": exe or sys.executable, "args": ["--mcp"]}


def _read(f: Path) -> dict:
    if not f.exists() or not f.read_text(encoding="utf-8").strip():
        return {}
    d = json.loads(f.read_text(encoding="utf-8"))
    if not isinstance(d, dict):
        raise ValueError("설정 파일 형식이 달라요")
    return d


def status(exe: str | None = None) -> dict:
    want = entry(exe)
    files = config_paths()
    res = {"linked": False, "stale": False, "claude_installed": any(f.parent.exists() for f in files), "file": str(files[0]) if files else ""}
    for f in files:
        try:
            cur = (_read(f).get("mcpServers") or {}).get(KEY)
        except (OSError, ValueError):
            res["broken"] = str(f)
            continue
        if cur == want:
            res.update(linked=True, file=str(f))
        elif cur:
            res["stale"] = True
    return res


def register(exe: str | None = None) -> dict:
    """등록(이미 같으면 그대로). 돌려주는 값: {ok, changed, files, error}"""
    want = entry(exe)
    changed, done, errors = False, [], []
    for f in config_paths():
        try:
            d = _read(f)
        except ValueError:
            errors.append(f"Claude 앱 설정 파일이 깨져 있어서 건드리지 않았어요: {f}")
            continue
        except OSError as e:
            errors.append(f"{f}: {e}")
            continue
        servers = d.get("mcpServers") if isinstance(d.get("mcpServers"), dict) else {}
        if servers.get(KEY) == want:
            done.append(str(f))
            continue
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            if f.exists():
                (f.parent / (f.name + ".cornbot-bak")).write_bytes(f.read_bytes())
            servers[KEY] = want
            d["mcpServers"] = servers
            tmp = f.with_name(f.name + ".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, f)
            changed = True
            done.append(str(f))
        except OSError as e:
            errors.append(f"{f}: {e}")
    return {"ok": bool(done) and not errors, "changed": changed, "files": done, "error": " / ".join(errors)}


def auto() -> dict | None:
    """앱을 켤 때마다: 설치본(묶음 실행 파일)일 때만 등록 상태를 맞춘다."""
    if not getattr(sys, "frozen", False):
        return None
    try:
        return register()
    except Exception as e:  # 등록 실패가 앱 실행을 막으면 안 된다
        return {"ok": False, "changed": False, "files": [], "error": str(e)[:200]}
