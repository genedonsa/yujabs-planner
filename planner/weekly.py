"""학원월드 '주간 급상승 영상' 게시글 → 레퍼런스 목록.

회원이 게시글을 통째로 복사(⌘A ⌘C)해서 콘봇에 붙여 넣으면, 글 속 유튜브 영상 링크와
영상마다 달린 분석 문단(영상 요약·왜 터졌나·시청자가 얻은 가치·남은 궁금증)을 함께 뽑는다.
분석 문단은 기획 자료에 그대로 들어가 기획안의 근거가 된다.
"""
from __future__ import annotations

import html as _html
import json
import re
from datetime import date
from pathlib import Path

YT_ID = r"([A-Za-z0-9_-]{11})"
YT_URL = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:[^\s\"'<>]*&)?v=|shorts/|live/|embed/)|youtu\.be/)" + YT_ID)
IMG_ID = re.compile(r"i\.ytimg\.com/vi/" + YT_ID)
MARK = "\u2063YT:{}\u2063"
_HEAD = re.compile(r"평소의\s*[\d.]+\s*배|^\s*\d{1,2}\s*[.)위]\s")


def _html_to_text(h: str) -> str:
    """HTML을 글로 바꾸되, 유튜브 링크·썸네일 자리에 표식을 남긴다."""
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)

    def a_tag(m):
        href = m.group(1)
        vid = YT_URL.search(href)
        return (" " + MARK.format(vid.group(1)) + " ") if vid else " "
    h = re.sub(r"(?is)<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>", a_tag, h)

    def img_tag(m):
        vid = IMG_ID.search(m.group(0))
        return (" " + MARK.format(vid.group(1)) + " ") if vid else " "
    h = re.sub(r"(?is)<img\b[^>]*>", img_tag, h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return _html.unescape(h)


def parse(text: str = "", html: str = "") -> list[dict]:
    """게시글(글 또는 HTML)에서 영상 목록을 순서대로. 각 항목: id, url, note(그 영상 다음에 오는 분석 문단)."""
    body = _html_to_text(html) if html.strip() else text
    if not html.strip():  # 글로만 붙여 넣은 경우: 주소를 표식으로
        body = re.compile(YT_URL.pattern + r"[^\s<>\"]*").sub(lambda m: " " + MARK.format(m.group(1)) + " ", body)
    marks = list(re.finditer("\u2063YT:" + YT_ID + "\u2063", body))
    # 글은 보통 '2. 채널 — 평소의 3.4배' 같은 머리줄이 링크 바로 앞에 온다. 그 줄은 다음 영상 몫이다.
    segs = [body[(marks[i - 1].end() if i else 0):m.start()] for i, m in enumerate(marks)]
    segs.append(body[marks[-1].end():] if marks else "")
    heads, tails = [""] * len(marks), [""] * len(marks)
    for i in range(len(marks)):
        lines = [l for l in _clean(segs[i]).splitlines()]
        head = ""
        if lines and _HEAD.search(lines[-1]):
            head = lines.pop()
        heads[i] = head
        if i:
            tails[i - 1] = "\n".join(lines)
    if marks:
        tails[-1] = _clean(segs[-1])
    out, seen = [], set()
    for i, m in enumerate(marks):
        vid = m.group(1)
        note = "\n".join(x for x in (heads[i], tails[i]) if x)
        if vid in seen:  # 같은 영상이 썸네일·제목 링크로 두 번 나오면 분석 문단을 이어 붙인다
            for o in out:
                if o["id"] == vid:
                    o["note"] = (o["note"] + "\n" + note).strip()[:2500]
            continue
        seen.add(vid)
        out.append({"id": vid, "url": f"https://www.youtube.com/watch?v={vid}", "note": note[:2500]})
    for o in out:
        r = re.search(r"평소의\s*([\d.]+)\s*배", o["note"])
        o["ratio"] = float(r.group(1).rstrip(".")) if r else None
    return out


def _clean(t: str) -> str:
    t = re.sub(r"[ \t ]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return "\n".join(l.strip() for l in t.splitlines() if l.strip())


def enrich(items: list[dict], log=lambda m: None) -> list[dict]:
    """영상마다 제목·채널·조회수·길이·업로드일을 붙인다. 못 읽으면 게시글 내용만으로 둔다."""
    from . import collect
    for i, it in enumerate(items, 1):
        log(f"영상 정보 읽는 중 {i}/{len(items)}")
        try:
            v = collect.video_info(it["url"])
            it.update({k: v.get(k) for k in ("title", "channel", "channel_id", "views", "duration", "upload_date")})
        except Exception:
            it.setdefault("title", _guess_title(it["note"]))
        it["thumb"] = f"https://i.ytimg.com/vi/{it['id']}/mqdefault.jpg"
        it["format"] = "주간 급상승"
        it["source"] = "학원월드 주간 게시글"
    return items


def _guess_title(note: str) -> str:
    first = (note.splitlines() or [""])[0]
    return first[:80] or "(제목을 못 읽었어요)"


def save(items: list[dict], home: Path) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    f = home / "weekly.json"
    f.write_text(json.dumps({"date": date.today().isoformat(), "items": items}, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return f


def load(home: Path) -> dict:
    try:
        return json.loads((home / "weekly.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"date": None, "items": []}


def import_post(html: str = "", text: str = "", home: Path | None = None, log=lambda m: None) -> list[dict]:
    """붙여 넣은(또는 클립보드의) 게시글 → 영상 정보 붙이기 → weekly.json 저장."""
    from .engine import HOME
    items = parse(text=text, html=html)
    if not items and html and text:
        items = parse(text=text)
    if not items:
        raise ValueError("게시글에서 유튜브 영상 링크를 찾지 못했어요. 학원월드 주간 게시글을 연 뒤 "
                         "⌘A(윈도우는 Ctrl+A)로 전체 선택하고 ⌘C(Ctrl+C)로 복사해 주세요.")
    enrich(items, log)
    save(items, home or HOME)
    return items
