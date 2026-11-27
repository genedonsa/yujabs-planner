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
import urllib.request
from datetime import date, datetime
from pathlib import Path

from yt_dlp import YoutubeDL

from .surge import Video

BASE_OPTS = {"quiet": True, "no_warnings": True, "skip_download": True}


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
    is_short = "/shorts/" in url or (dur is not None and dur <= 60)
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


def channel_videos(channel_url: str, limit: int = 60) -> tuple[dict, list[Video]]:
    """채널 '동영상' 탭 최근 영상. approximate_date로 목록에서도 업로드일을 받는다."""
    url = channel_url.rstrip("/")
    if not url.endswith("/videos"):
        url += "/videos"
    opts = {**BASE_OPTS, "extract_flat": "in_playlist", "playlistend": limit,
            "extractor_args": {"youtubetab": {"approximate_date": [""]}}}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    ch = {"id": info.get("channel_id") or info.get("id"), "name": info.get("channel") or info.get("title"),
          "url": channel_url}
    vids = [_to_video(e, ch["id"], ch["name"]) for e in info.get("entries") or [] if e]
    return ch, vids


def search(query: str, n: int = 20) -> list[Video]:
    """최신순 검색."""
    opts = {**BASE_OPTS, "extract_flat": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearchdate{n}:{query}", download=False)
    return [_to_video(e) for e in info.get("entries") or [] if e]


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
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
        "comments": [{"text": c.get("text", ""), "likes": c.get("like_count") or 0} for c in comments[:max_comments]],
        "transcript": transcript(info),
    }


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
