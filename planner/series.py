"""회원 '시리즈': 회원마다 만드는 콘텐츠 시리즈(예: 해외 유튜브 성공 사례 소개)와 시리즈별 '찾기 방식'.

- 시리즈는 회원 컴퓨터 설정(settings.json의 series)에 저장된다. 예전 '포맷'은 이름만 있는 시리즈로 옮긴다.
- 찾기 방식(기간·평소 대비 배수·최소 조회수)은 대표가 정한다. 대표 시트의 '찾기방식' 탭을 읽어 오므로
  대표가 시트를 고치면 업데이트 없이 모든 회원에게 반영된다. 못 읽으면 아래 기본값을 쓴다.
- 어떤 방식이든 '그 채널 평소 대비 배수' 조건은 꼭 들어간다(그냥 유튜브 검색과 다른 점).
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
from pathlib import Path

MODES_GID = 778
DEFAULT_MODE = "weekly"
DEFAULT_MODES = {
    "weekly": {"name": "이번 주 급상승", "days": 7, "ratio": 3.0, "min_views": 10000,
               "desc": "최근 7일, 그 채널 평소의 3배 이상, 조회 1만 이상. 이슈·트렌드 시리즈에 맞아요."},
    "hidden": {"name": "숨은 사례 발굴", "days": 30, "ratio": 2.0, "min_views": 0,
               "desc": "최근 30일, 그 채널 평소의 2배 이상. 작은 채널에서 소재를 찾는 시리즈(해외 사례 소개 등)에 맞아요."},
    "big": {"name": "검증된 큰 영상", "days": 90, "ratio": 2.0, "min_views": 100000,
            "desc": "최근 90일, 평소의 2배 이상, 조회 10만 이상. 오래 가는 주제 시리즈에 맞아요."},
}
MAX_SERIES = 6
_cache: dict = {"at": 0.0, "modes": None}


def mode_urls() -> list[str]:
    from .access import SHEET_ID
    return [f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={MODES_GID}",
            f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid={MODES_GID}"]


def _num(v, default: float) -> float:
    try:
        return float(re.sub(r"[^0-9.]", "", str(v)) or default)
    except ValueError:
        return default


def parse_modes(text: str) -> dict:
    """시트 열: key | name | days | ratio | min_views | desc. 잘못된 값은 안전한 범위로 맞춘다."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    head = [h.strip().lower() for h in rows[0]]
    if "key" not in head or "ratio" not in head:
        return {}  # 탭이 없어서 다른 탭이 왔거나 형식이 다름
    out = {}
    for r in rows[1:]:
        d = {head[i]: (r[i].strip() if i < len(r) else "") for i in range(len(head))}
        key = re.sub(r"[^a-z0-9_]", "", d.get("key", "").lower())
        if not key or not d.get("name"):
            continue
        base = DEFAULT_MODES.get(key, DEFAULT_MODES[DEFAULT_MODE])
        out[key] = {
            "name": d["name"],
            "days": int(min(max(_num(d.get("days"), base["days"]), 1), 180)),
            "ratio": round(min(max(_num(d.get("ratio"), base["ratio"]), 1.5), 20.0), 1),  # 배수 조건은 꼭 남긴다
            "min_views": int(max(_num(d.get("min_views"), base["min_views"]), 0)),
            "desc": d.get("desc") or base.get("desc", ""),
        }
    return out


def modes(home: Path | None = None, refresh: bool = False) -> dict:
    """대표 시트의 찾기 방식(10분 캐시) → 지난번 받아 둔 것 → 기본값."""
    from . import access
    from .engine import HOME
    home = home or HOME
    if not refresh and _cache["modes"] and time.time() - _cache["at"] < 600:
        return _cache["modes"]
    got = {}
    for u in mode_urls():
        try:
            got = parse_modes(access._download(u))
        except Exception:  # noqa: BLE001 — 인터넷이 안 되면 아래로
            got = {}
        if got:
            break
    f = home / "modes.json"
    if got:
        try:
            home.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    else:
        try:
            got = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            got = {}
    # 시트를 따르되, 기본 방식(이번 주 급상승)은 늘 있게 한다
    m = ({DEFAULT_MODE: DEFAULT_MODES[DEFAULT_MODE], **got} if DEFAULT_MODE not in got else got) if got else dict(DEFAULT_MODES)
    _cache.update(at=time.time(), modes=m)
    return m


def _clean_list(v, limit: int) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[\n,]", v)
    out = []
    for x in v or []:
        x = str(x).strip()
        if x and x not in out:
            out.append(x)
    return out[:limit]


def normalize(items, mode_keys=None) -> list[dict]:
    """화면·Claude에서 받은 시리즈 목록을 저장 형식으로. 이름 없는 것·중복 이름은 뺀다."""
    out, names = [], set()
    for it in items or []:
        if isinstance(it, str):
            it = {"name": it}
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()[:40]
        if not name or name in names or name == "급상승 영상":
            continue
        mode = str(it.get("mode") or DEFAULT_MODE)
        if mode_keys is not None and mode not in mode_keys:
            mode = DEFAULT_MODE
        names.add(name)
        out.append({"name": name, "desc": str(it.get("desc") or "").strip()[:200], "mode": mode,
                    "channels": _clean_list(it.get("channels"), 8),
                    "keywords": _clean_list(it.get("keywords"), 8)})
        if len(out) >= MAX_SERIES:
            break
    return out


def load(s: dict) -> list[dict]:
    """설정에서 시리즈를 읽는다. 시리즈가 없고 예전 '포맷'만 있으면 이름만 있는 시리즈로 바꿔 준다."""
    if isinstance(s.get("series"), list):
        return normalize(s["series"])
    return normalize([{"name": f} for f in s.get("formats", []) if str(f).strip()])


def criteria(mode: dict) -> dict:
    return {"days": int(mode["days"]), "min_views": int(mode["min_views"]), "ratio": float(mode["ratio"]), "region": "all"}


def mode_label(mode: dict) -> str:
    v = mode["min_views"]
    views = f" · 조회 {v // 10000}만+" if v >= 10000 else (f" · 조회 {v:,}+" if v else "")
    return f"{mode['name']} · 최근 {mode['days']}일 · 평소의 {mode['ratio']:g}배{views}"


def cached(home: Path | None = None) -> dict:
    """인터넷을 쓰지 않고 지금 아는 찾기 방식 (화면을 빨리 띄울 때)."""
    from .engine import HOME
    if _cache["modes"]:
        return _cache["modes"]
    try:
        got = json.loads(((home or HOME) / "modes.json").read_text(encoding="utf-8"))
        if isinstance(got, dict) and got:
            return got if DEFAULT_MODE in got else {DEFAULT_MODE: DEFAULT_MODES[DEFAULT_MODE], **got}
    except (OSError, ValueError):
        pass
    return dict(DEFAULT_MODES)
