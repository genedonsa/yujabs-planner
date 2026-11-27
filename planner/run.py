"""전체 흐름: 코드 확인 → 내 채널·롤모델 수집 → 키워드 검색 → 후보 4편 → 원본 확인 → 묶음 파일."""
from __future__ import annotations

import json
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


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(s: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


def run(s: dict, log: Callable[[str], None] = print, max_search_channels: int = 25,
        step: Callable[[str], None] = lambda k: None) -> dict:
    if not access.check(s.get("password", "")):
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
        base = channel_baseline(vids)
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
            baselines[v.channel_id] = channel_baseline(cvids)
            candidates += [(cv, baselines[v.channel_id]) for cv in cvids]

    step("pick")
    picked = pick(candidates, today, top=4, min_ratio=float(s.get("min_ratio", 2)))
    if not picked:
        raise RuntimeError("최근 2주 안에 평소보다 2배 이상 나온 영상을 찾지 못했습니다. 롤모델 채널을 더 넣거나 기준 배수를 낮춰 보세요.")

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
                     "detail": detail, "why_picked": f"평소 대비 {r:.1f}배, {(today - v.upload_date).days}일 전 업로드"})

    step("bundle")
    me = {"name": me_ch.get("name"), "url": s["my_channel"], "audience": s.get("audience", ""), "notes": s.get("notes", "")}
    bundle, prompt = write_bundle(out_dir, me, my_top, refs, today)
    (out_dir / "refs.json").write_text(json.dumps([{
        "id": r["video"].id, "title": r["video"].title, "channel": r["video"].channel_name,
        "views": r["detail"].get("views") or r["video"].views, "ratio": round(r["ratio"], 1),
        "upload_date": r["video"].upload_date.isoformat() if r["video"].upload_date else "",
        "duration": r["detail"].get("duration"), "comments": r["detail"].get("comment_count"),
        "has_transcript": bool(r["detail"].get("transcript")), "url": r["video"].url} for r in refs],
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
