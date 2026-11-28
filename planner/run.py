"""전체 흐름: 코드 확인 → 내 채널·롤모델 수집 → 키워드 검색 → 후보 4편 → 원본 확인 → 묶음 파일."""
from __future__ import annotations

import json
import os
import sys
import re
from datetime import date
from pathlib import Path
from typing import Callable

from . import access, collect
from .bundle import write_bundle
from .discover import keywords
from .surge import Video, channel_baseline, pick
from .thumbnail import Style, compose

HOME = Path.home() / "유잡스 기획"
SETTINGS = HOME / "settings.json"


# 설정 파일 형식 번호. 저장 형식을 바꿀 때만 올리고, migrate()에 옛 형식 → 새 형식 변환을 더한다.
# (업데이트해도 회원이 넣은 채널·경험·포맷·구독 리스트가 절대 사라지지 않게 하는 장치)
SCHEMA = 2
BACKUP = HOME / "settings.bak.json"
WINDOW = HOME / "window.json"  # 콘봇 창이 떠 있는 동안만 있는 표시 (Claude가 '창 열기'가 됐는지 확인할 때 씀)


def _pid_alive(pid: int) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(int(pid), 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False


def mark_window(open_: bool) -> None:
    try:
        if open_:
            HOME.mkdir(parents=True, exist_ok=True)
            WINDOW.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        elif WINDOW.exists() and json.loads(WINDOW.read_text(encoding="utf-8")).get("pid") == os.getpid():
            WINDOW.unlink()
    except (OSError, ValueError):
        pass


def window_alive() -> bool:
    try:
        return _pid_alive(json.loads(WINDOW.read_text(encoding="utf-8")).get("pid"))
    except (OSError, ValueError):
        return False


def _to_trash(p: Path) -> None:
    """휴지통으로 옮긴다(실수로 지워도 되살릴 수 있게)."""
    import shutil
    from datetime import datetime
    if sys.platform == "darwin":
        trash = Path.home() / ".Trash"
        trash.mkdir(exist_ok=True)
        shutil.move(str(p), str(trash / f"{p.name} {datetime.now():%Y-%m-%d %H.%M.%S}"))
    elif os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", ctypes.c_void_p),
                        ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
        buf = ctypes.create_unicode_buffer(str(p) + "\0")  # 끝에 null 두 개
        op = SHFILEOPSTRUCTW(None, 3, ctypes.cast(buf, ctypes.c_void_p), None, 0x0040 | 0x0010 | 0x0004 | 0x0400, False, None, None)
        if ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) != 0:
            raise OSError("휴지통으로 옮기지 못했어요")
    else:
        shutil.rmtree(p)


def reset(everything: bool = False) -> dict:
    """처음 상태로. 기본은 설정·암호·채널·구독 리스트만 지우고 기획안·분석 자료는 남긴다.
    everything=True면 '유잡스 기획' 폴더 전체를 휴지통으로 옮긴다(받아쓰기 도구도 다시 받음)."""
    if everything:
        if HOME.exists():
            _to_trash(HOME)
        return {"ok": True, "removed": str(HOME)}
    gone = []
    for f in (SETTINGS, BACKUP, HOME / "last_result.json", HOME / "me.json"):
        if f.exists():
            f.unlink()
            gone.append(f.name)
    return {"ok": True, "removed": gone}


def migrate(s: dict) -> dict:
    """옛 버전 설정을 지금 형식으로. 값은 지우지 않고 옮기거나 채우기만 한다."""
    v = int(s.get("_schema") or 0)
    if v < 1:  # 0 → 1: 형식 번호 도입. 비어 있으면 기본값만 채움
        s.setdefault("role_models", [])
        s.setdefault("formats", [])
        s.setdefault("links", [])
    if s.get("password"):  # 1 → 2: 암호 원문 대신 지문만 저장
        s["password_fp"] = access.fingerprint(s.pop("password"))
    s["_schema"] = SCHEMA
    return s


def load_settings() -> dict:
    """설정 읽기. 파일이 깨졌으면 바로 전 저장본(백업)으로 되살린다."""
    for f in (SETTINGS, BACKUP):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                return migrate(d)
        except (OSError, ValueError):
            continue
    return {}


def save_settings(s: dict) -> None:
    """임시 파일에 다 쓴 뒤 바꿔치기해서, 쓰다가 꺼져도 설정이 반쯤 깨지지 않게 한다. 직전 저장본은 백업으로 남긴다."""
    import os
    HOME.mkdir(parents=True, exist_ok=True)
    s = migrate(dict(s))
    tmp = SETTINGS.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    if SETTINGS.exists():
        try:  # 멀쩡한 직전 저장본만, 지금 형식으로 바꿔서 백업 (옛 암호 원문이 백업에 남지 않게)
            prev = migrate(json.loads(SETTINGS.read_text(encoding="utf-8")))
            BACKUP.write_text(json.dumps(prev, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, ValueError, AttributeError):
            pass
    os.replace(tmp, SETTINGS)


def run(s: dict, log: Callable[[str], None] = print, max_search_channels: int = 25,
        step: Callable[[str], None] = lambda k: None) -> dict:
    if not access.check_saved(s):
        raise PermissionError("이번 달 암호가 바뀌었어요. 커뮤니티 회원 게시판에서 새 암호를 확인해 주세요.")
    today = date.today()
    out_dir = HOME / today.isoformat()

    step("me"); log("내 채널을 읽는 중…")
    me_ch, me_vids = collect.channel_videos(s["my_channel"], 60)
    my_top = sorted([v for v in me_vids if not v.is_short], key=lambda v: v.views, reverse=True)[:6]

    candidates: list[tuple[Video, float]] = []
    titles = [v.title for v in me_vids]
    baselines: dict[str, float] = {}
    step("models")
    for url in s["role_models"]:
        log(f"롤모델 채널 읽는 중: {url}")
        try:
            ch, vids = collect.channel_videos(url, 60)
        except Exception as e:  # 채널 하나가 실패해도 계속
            log(f"  건너뜀 ({e})")
            continue
        base = channel_baseline(vids, today)
        baselines[ch["id"]] = base
        candidates += [(v, base) for v in vids]
        titles += [v.title for v in vids]

    kws = keywords(titles) + [k for k in s.get("extra_keywords", []) if k]
    step("search"); log(f"키워드: {', '.join(kws)}")
    checked = 0
    for kw in kws:
        log(f"검색 중: {kw}")
        try:
            results = collect.search(kw, 20)
        except Exception as e:
            log(f"  검색 실패 ({e})")
            continue
        for v in results:
            if v.is_short or v.channel_id in baselines or not v.channel_id or checked >= max_search_channels:
                continue
            try:
                _, cvids = collect.channel_videos(f"https://www.youtube.com/channel/{v.channel_id}", 30)
            except Exception:
                continue
            checked += 1
            baselines[v.channel_id] = channel_baseline(cvids, today)
            candidates += [(cv, baselines[v.channel_id]) for cv in cvids]

    step("pick")
    shown = set()  # 지난주까지 이미 보여준 영상은 빼기(주간 기록 중복 제외와 같음)
    if HOME.exists():
        for d in HOME.iterdir():
            f = d / "refs.json"
            if d.is_dir() and d.name != today.isoformat() and f.exists():
                try:
                    shown |= {r["id"] for r in json.loads(f.read_text(encoding="utf-8"))}
                except (OSError, ValueError, KeyError):
                    pass
    picked = pick(candidates, today, top=4, min_ratio=float(s.get("min_ratio", 2)), exclude=shown)
    if not picked:
        raise RuntimeError("최근 1~2주 안에 평소보다 2배 이상 나온 영상을 찾지 못했습니다. 롤모델 채널을 더 넣거나 기준 배수를 낮춰 보세요.")

    step("detail")
    refs = []
    thumbs = out_dir / "원본썸네일"
    thumbs.mkdir(parents=True, exist_ok=True)
    for v, r, _ in picked:
        log(f"원본 확인 중: {v.title}")
        detail = collect.video_detail(v.url, 40)
        try:
            collect.save_thumbnail(v.id, thumbs / f"{v.id}.jpg")
        except Exception as e:
            log(f"  썸네일 저장 실패 ({e})")
        refs.append({"video": v, "ratio": r, "baseline": baselines.get(v.channel_id, 0),
                     "detail": detail, "why_picked": f"평소 대비 {r:.1f}배, {(today - v.upload_date).days}일 전 업로드"
                     + (" (1주 안에 4편이 안 돼 2주 안에서 보충)" if v.extra.get("보충") else "")})

    step("bundle")
    me = {"name": me_ch.get("name"), "url": s["my_channel"], "audience": s.get("audience", ""), "notes": s.get("notes", "")}
    bundle, prompt = write_bundle(out_dir, me, my_top, refs, today)
    (out_dir / "refs.json").write_text(json.dumps([{
        "id": r["video"].id, "title": r["video"].title, "channel": r["video"].channel_name,
        "views": r["detail"].get("views") or r["video"].views, "ratio": round(r["ratio"], 1),
        "upload_date": r["video"].upload_date.isoformat() if r["video"].upload_date else "",
        "duration": r["detail"].get("duration"), "comments": r["detail"].get("comment_count"),
        "has_transcript": bool(r["detail"].get("transcript")), "url": r["video"].url,
        "baseline": int(r["baseline"]), "filled": bool(r["video"].extra.get("보충"))} for r in refs],
        ensure_ascii=False, indent=2), encoding="utf-8")
    step("done"); log("완료!")
    return {"folder": str(out_dir), "bundle": str(bundle), "prompt": str(prompt)}


def make_thumbnails(folder: Path, lines_text: str, s: dict) -> list[Path]:
    """lines_text: 편마다 한 줄 '줄1 / 줄2' (refs.json 순서)."""
    refs = json.loads((folder / "refs.json").read_text(encoding="utf-8"))
    style = Style(position=s.get("text_position", "bottom"), color1=s.get("color1", "#FFFFFF"),
                  color2=s.get("color2", "#FFD21F"))
    tpl = Path(s["template"]) if s.get("template") else None
    out = []
    rows = [l for l in lines_text.splitlines() if l.strip()]
    for ref, row in zip(refs, rows):
        row = re.sub(r"^\s*\d+\s*[.):\-]\s*", "", row)  # 앞 번호(1. / 1) / 1:) 떼기
        l1, _, l2 = row.partition("/")
        bg = folder / "원본썸네일" / f"{ref['id']}.jpg"
        out.append(compose(bg, l1.strip(), l2.strip(), folder / "썸네일시안" / f"{ref['id']}.jpg", tpl, style))
    return out
