"""유튜브 수집. API 키 없이 yt-dlp를 쓴다.

주의: 이 파일은 유튜브 접속이 막힌 환경에서 작성되어 아직 실제로 돌려 보지 않았다.
첫 실행에서 필드 이름(view_count, upload_date 등)과 자막 형식을 확인하고 고칠 것.
유튜브가 바뀌어 깨지면 먼저 `pip install -U yt-dlp` 를 해 본다.

    python -m planner.collect --channel https://www.youtube.com/@유튜브-잡스
    python -m planner.collect --video https://youtu.be/0bO9HVfewUo
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path

from yt_dlp import YoutubeDL as _YoutubeDL

from .net import js_runtimes, urlopen
from .surge import Video

BASE_OPTS = {"quiet": True, "no_warnings": True, "skip_download": True,
             "js_runtimes": js_runtimes()}


_PLAIN = {"on": False}  # 한 번이라도 압축이 깨져 오면 그 뒤로는 압축 없이 받는다


class YoutubeDL(_YoutubeDL):
    """일부 회선·보안 프로그램에서 유튜브 응답의 압축이 깨져 오면('Error -3 while decompressing data')
    압축 없이(Accept-Encoding: identity) 다시 받는다."""

    def __init__(self, params=None, *a, **k):
        params = dict(params or {})
        self._orig_params = dict(params)
        if _PLAIN["on"]:
            params["http_headers"] = {**(params.get("http_headers") or {}), "Accept-Encoding": "identity"}
        super().__init__(params, *a, **k)

    def extract_info(self, *a, **k):
        try:
            return super().extract_info(*a, **k)
        except Exception as e:
            if "decompress" not in str(e).lower() and "compression" not in str(e).lower():
                raise
            if _PLAIN["on"] and "identity" in str(self.params.get("http_headers", {}).get("Accept-Encoding", "")):
                raise  # 이미 압축 없이 받았는데도 실패
            _PLAIN["on"] = True
            with YoutubeDL(self._orig_params) as again:  # 새 연결로 압축 없이
                return again.extract_info(*a, **k)


def _date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def _to_video(e: dict, channel_id: str = "", channel_name: str = "") -> Video:
    dur = e.get("duration")
    url = e.get("url") or ""
    is_short = "/shorts/" in url or (dur is not None and dur <= 180)  # 쇼츠는 최대 3분
    upload = _date(e.get("upload_date"))
    if not upload and e.get("timestamp"):
        upload = datetime.fromtimestamp(e["timestamp"]).date()
    return Video(
        id=e.get("id", ""),
        title=e.get("title") or "",
        channel_id=e.get("channel_id") or channel_id,
        channel_name=e.get("channel") or e.get("uploader") or channel_name,
        views=int(e.get("view_count") or 0),
        upload_date=upload,
        duration=dur,
        is_short=is_short,
    )


def channel_videos(channel_url: str, limit: int = 60, original_titles: bool = True) -> tuple[dict, list[Video]]:
    """채널 '동영상' 탭 최근 영상. approximate_date로 목록에서도 업로드일을 받는다."""
    url = channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url += "/videos"
    opts = {**BASE_OPTS, "extract_flat": "in_playlist", "playlistend": limit,
            "extractor_args": {"youtubetab": {"approximate_date": [""]}}}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    thumbs = info.get("thumbnails") or []
    avatar = next((t.get("url") for t in thumbs if (t.get("id") or "").startswith("avatar")), None) \
        or next((t.get("url") for t in thumbs if t.get("width") and t.get("width") == t.get("height")), None)
    ch = {"id": info.get("channel_id") or info.get("id"),
          "name": (info.get("channel") or info.get("title") or "").replace(" - Videos", "").replace(" - 동영상", ""),
          "url": channel_url, "handle": info.get("uploader_id") or "",
          "subs": info.get("channel_follower_count"), "desc": (info.get("description") or "")[:300],
          "avatar": avatar}
    vids = [_to_video(e, ch["id"], ch["name"]) for e in info.get("entries") or [] if e]
    if original_titles:
        _korean_titles(url, limit, ch, vids)
    return ch, vids


def _korean_titles(url: str, limit: int, ch: dict, vids: list[Video]) -> None:
    """유튜브는 기본(영어)으로 물으면 채널이 달아 둔 '영어 번역 제목'을 준다.
    한국어로 한 번 더 물어 원래 제목·채널 이름으로 바꾼다. (날짜는 한국어로 물으면 못 읽어서 첫 요청 것을 쓴다)"""
    opts = {**BASE_OPTS, "extract_flat": "in_playlist", "playlistend": limit,
            "extractor_args": {"youtube": {"lang": ["ko"]}}}
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        return  # 실패해도 영어 제목으로 계속
    ko = {e.get("id"): e.get("title") for e in info.get("entries") or [] if e and e.get("title")}
    for v in vids:
        if ko.get(v.id):
            v.title = ko[v.id]
    name = (info.get("channel") or info.get("title") or "").replace(" - Videos", "").replace(" - 동영상", "")
    if name:
        ch["name"] = name
        for v in vids:
            v.channel_name = name


def video_info(url: str) -> dict:
    """영상 한 편의 기본 정보(제목·채널·조회수·길이·업로드일). 댓글·자막은 읽지 않아 빠르다.
    영상 페이지가 막히면 oEmbed(제목·채널만)로 대신한다."""
    try:
        opts = {**BASE_OPTS, "extractor_args": {"youtube": {"lang": ["ko"]}}}
        with YoutubeDL(opts) as ydl:
            e = ydl.extract_info(url, download=False, process=False)
        return {"id": e.get("id"), "title": e.get("title"), "channel": e.get("channel") or e.get("uploader"),
                "channel_id": e.get("channel_id"), "views": e.get("view_count"), "duration": e.get("duration"),
                "upload_date": (_date(e.get("upload_date")) or date.today()).isoformat() if e.get("upload_date") else None}
    except Exception:
        q = urllib.parse.quote(url, safe="")
        with urlopen(f"https://www.youtube.com/oembed?url={q}&format=json", timeout=15) as r:
            o = json.loads(r.read().decode("utf-8"))
        return {"title": o.get("title"), "channel": o.get("author_name")}


# 유튜브 검색 '업로드 날짜' 필터 (유튜브가 최신순 정렬을 없애서 yt-dlp의 ytsearchdate도 사라졌다)
_DATE_SP = [(1, "EgIIAg%3D%3D"), (7, "EgIIAw%3D%3D"), (31, "EgIIBA%3D%3D"), (366, "EgIIBQ%3D%3D")]


def search_url(query: str, days: int = 30) -> str:
    sp = next((v for d, v in _DATE_SP if days <= d), _DATE_SP[-1][1])
    return f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}&sp={sp}"


def search(query: str, n: int = 20, days: int = 30) -> list[Video]:
    """최근 days일 안에 올라온 영상 검색 (유튜브 관련도 순)."""
    opts = {**BASE_OPTS, "extract_flat": True, "playlistend": n}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(search_url(query, days), download=False)
    return [_to_video(e) for e in (info.get("entries") or [])[:n] if e]


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as r:
        return r.read()


def _pick_caption(info: dict, langs=("ko", "en")) -> tuple[str, str, list[dict]] | None:
    """수동 자막 우선, 없으면 자동 자막. (언어, 종류, 포맷 목록)"""
    for kind in ("subtitles", "automatic_captions"):
        tracks = info.get(kind) or {}
        for lang in langs:
            for key in tracks:
                if key == lang or key.startswith(lang + "-"):
                    return key, kind, tracks[key]
    return None


def transcript(info: dict) -> list[dict]:
    """[{start: 초, text: 문장}] — json3 형식을 읽는다."""
    picked = _pick_caption(info)
    if not picked:
        return []
    _, _, formats = picked
    fmt = next((f for f in formats if f.get("ext") == "json3"), None)
    if not fmt:
        return []
    data = json.loads(_fetch(fmt["url"]))
    out = []
    for ev in data.get("events", []):
        text = "".join(s.get("utf8", "") for s in ev.get("segs") or []).strip()
        if text:
            out.append({"start": ev.get("tStartMs", 0) / 1000, "text": text})
    return out


def video_detail(video_url: str, max_comments: int = 40) -> dict:
    """제목·길이·조회수·설명란·자막·상위 댓글."""
    opts = {**BASE_OPTS, "getcomments": True,
            "extractor_args": {"youtube": {"max_comments": [str(max_comments), "all", "0"],
                                           "comment_sort": ["top"]}}}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
    comments = [c for c in info.get("comments") or [] if c.get("parent") == "root"]
    comments.sort(key=lambda c: c.get("like_count") or 0, reverse=True)
    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "channel": info.get("channel"),
        "channel_url": info.get("channel_url"),
        "duration": info.get("duration"),
        "views": info.get("view_count"),
        "upload_date": info.get("upload_date"),
        "description": info.get("description") or "",
        "thumbnail": f"https://i.ytimg.com/vi/{info.get('id')}/maxresdefault.jpg",
        "comment_count": info.get("comment_count"),
        "comments": [{"text": c.get("text", ""), "likes": c.get("like_count") or 0,
                      "pinned": bool(c.get("is_pinned")), "by_uploader": bool(c.get("author_is_uploader"))}
                     for c in comments[:max_comments]],
        "transcript": transcript(info),
    }


def video_transcript(video_url: str) -> dict:
    """댓글 없이 제목·길이·자막만 (내 경험 익히기용, 빠르게)."""
    with YoutubeDL({**BASE_OPTS}) as ydl:
        info = ydl.extract_info(video_url, download=False)
    return {"id": info.get("id"), "title": info.get("title"), "duration": info.get("duration"),
            "description": info.get("description") or "", "transcript": transcript(info)}


def save_thumbnail(video_id: str, dest: Path) -> Path:
    for name in ("maxresdefault", "hqdefault"):
        try:
            dest.write_bytes(_fetch(f"https://i.ytimg.com/vi/{video_id}/{name}.jpg"))
            return dest
        except Exception:
            continue
    raise RuntimeError(f"썸네일을 받지 못했습니다: {video_id}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel")
    ap.add_argument("--video")
    ap.add_argument("--search")
    a = ap.parse_args()
    if a.channel:
        ch, vids = channel_videos(a.channel, 15)
        print(ch)
        for v in vids:
            print(v.upload_date, v.views, v.is_short, v.title)
    if a.video:
        d = video_detail(a.video, 5)
        print({k: d[k] for k in ("title", "views", "duration", "upload_date", "comment_count")})
        print("자막 줄 수:", len(d["transcript"]), d["transcript"][:3])
        print("댓글:", d["comments"][:3])
    if a.search:
        for v in search(a.search, 10):
            print(v.upload_date, v.views, v.channel_name, v.title)
