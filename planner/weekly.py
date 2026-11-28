"""학원월드 '주간 급상승 영상' 게시글 → 레퍼런스 목록.

모든 회원이 같은 목록을 본다: 운영자(대표·Claude)가 게시글을 읽어 암호 확인 시트의 '급상승' 탭에 올리고,
회원 콘봇은 그 탭을 읽어 레퍼런스 화면의 '급상승 영상' 포맷으로 보여 준다 (fetch_feed).
parse()는 운영자가 게시글을 시트용 행으로 바꿀 때 쓴다.

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



# ---------- 모든 회원 공통 목록 (암호 확인 시트의 '급상승' 탭) ----------
FORMAT = "급상승 영상"
FEED_GID = 777
COLUMNS = ["id", "url", "title", "channel", "views", "ratio", "note", "post_date", "post_title"]


def feed_urls() -> list[str]:
    from .access import SHEET_ID
    return [f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={FEED_GID}",
            f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid={FEED_GID}"]


def parse_feed(text: str) -> dict:
    import csv
    import io
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {"date": None, "post_title": "", "items": []}
    head = [h.strip().lower() for h in rows[0]]
    items = []
    for r in rows[1:]:
        d = {k: (r[i].strip() if i < len(r) else "") for i, k in enumerate(head)}
        vid = d.get("id") or ""
        m = re.search(YT_ID, vid) if len(vid) == 11 else (YT_URL.search(d.get("url") or "") or None)
        vid = vid if len(vid) == 11 else (m.group(1) if m else "")
        if not vid:
            continue
        def num(x, f):
            try:
                return f(str(x).replace(",", "").replace("배", "").strip())
            except ValueError:
                return None
        items.append({"id": vid, "url": f"https://www.youtube.com/watch?v={vid}",
                      "title": d.get("title") or "(제목 없음)", "channel": d.get("channel") or "",
                      "views": num(d.get("views"), int), "ratio": num(d.get("ratio"), float),
                      "note": (d.get("note") or "")[:2500], "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                      "format": FORMAT, "source": "학원월드 주간 게시글", "post_date": d.get("post_date") or "",
                      "post_title": d.get("post_title") or ""})
    for i, it in enumerate(items, 1):
        it["code"] = f"W{i}"
    first = items[0] if items else {}
    return {"date": first.get("post_date") or None, "post_title": first.get("post_title") or "", "items": items}


def fetch_feed(home: Path | None = None) -> dict:
    """시트에서 이번 주 목록을 읽는다. 못 읽으면 마지막으로 받아 둔 것을 쓴다(offline=True)."""
    from . import access
    from .engine import HOME
    home = home or HOME
    for u in feed_urls():
        try:
            d = parse_feed(access._download(u))
        except Exception:
            continue
        try:
            home.mkdir(parents=True, exist_ok=True)
            (home / "weekly.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
        return {**d, "offline": False}
    return {**load(home), "offline": True}
