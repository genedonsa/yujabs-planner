"""v0.2 분석 흐름.

1. 내 경험 익히기: 내 채널 영상 대본 + 내가 쓴 소개 + 정보 링크 → '내가 나에 대해 말한 문장'만 모아 둔다.
2. 키워드: 롤모델·내 영상 제목에서 자동으로 뽑고, 회원이 뺀 것은 다시 넣지 않고 더한 것은 유지한다.
3. 벤치마킹 채널: 키워드·내 포맷으로 검색해 롤모델보다 작은 같은 분야 채널을 찾는다.
4. 레퍼런스: 롤모델 + 구독 리스트 + 검색에서 본 채널의 영상 중
   최근 N일(기본 7) · 조회수 M 이상(기본 1만) · 그 채널 평소(최근 3개월 롱폼 평균, 최근 N일 제외)의 K배 이상(기본 3).
   구독자 수는 보지 않는다. 지난번에 보여 준 영상은 뺀다.
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
import urllib.request
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from . import access, collect, net
from .discover import anchor_word, keywords as auto_keywords, shared_keywords
from .surge import Video

HOME = Path.home() / "유잡스 기획"
DEFAULT_CRITERIA = {"days": 7, "min_views": 10000, "ratio": 3.0, "region": "all"}
BASELINE_DAYS = 90
SELF_MARK = re.compile(r"(저는|제가|저도|저희|제\s|나는|내가|우리\s?회사|저한테|제\s?채널|저 같은|저처럼|제 경험|해\s?봤|했었|했는데|였는데)")


def _friendly(e: Exception) -> str:
    """유튜브 오류를 회원이 알아들을 말로."""
    m = str(e)
    if "does not exist" in m or "404" in m:
        return "이 주소로 채널을 찾지 못했어요"
    if "confirm you" in m or "bot" in m:
        return "유튜브가 잠깐 막았어요. 조금 뒤 다시 해 주세요"
    if "timed out" in m or "Connection" in m or "Network" in m or "urlopen error" in m:
        return "인터넷 연결이 불안정해요"
    if "decompress" in m or "compression" in m:
        return "유튜브에서 받은 내용이 깨져서 왔어요. 잠시 뒤 다시 해 주세요"
    if re.search(r"[가-힣]", m):
        return m[:300]  # 이미 회원용 문장
    return "알 수 없는 오류가 났어요 (" + m[:80] + ")"


def _today() -> date:
    return date.today()


# ---------- 1. 내 경험 ----------
def _page_text(url: str, limit: int = 6000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (CornBot)"})
    with net.urlopen(req, timeout=20) as r:
        raw = r.read(800_000).decode("utf-8", "ignore")
    raw = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
    meta = " ".join(re.findall(r'(?i)<meta[^>]+(?:name|property)="(?:description|og:description|og:title)"[^>]+content="([^"]*)"', raw))
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", raw))
    text = re.sub(r"\s+", " ", meta + " " + text).strip()
    return text[:limit]


def _self_sentences(text: str, cap: int) -> list[str]:
    sents = re.split(r"(?<=[.!?요다])\s+", text)
    out = [s.strip() for s in sents if 12 <= len(s.strip()) <= 220 and SELF_MARK.search(s)]
    return out[:cap]


def learn_me(s: dict, log: Callable[[str], None], max_videos: int = 12) -> dict:
    me_ch, vids = collect.channel_videos(s["my_channel"], 60)
    longs = [v for v in vids if not v.is_short]
    top = sorted(longs, key=lambda v: v.views, reverse=True)[:6]
    exp: list[dict] = []
    intro = (s.get("intro") or "").strip()
    if intro:
        exp.append({"src": "내가 쓴 소개", "text": intro})
    for v in longs[:max_videos]:
        log(f"내 영상 대본 읽는 중: {v.title[:30]}")
        try:
            d = collect.video_transcript(v.url)
        except Exception as e:
            log("  건너뜀 (" + _friendly(e) + ")")
            continue
        text = " ".join(x["text"] for x in d.get("transcript") or [])
        for sent in _self_sentences(text, 12):
            exp.append({"src": f"내 영상 · {v.title[:40]}", "text": sent})
    for url in [u for u in s.get("links", []) if u.strip()]:
        log(f"링크 읽는 중: {url[:50]}")
        try:
            t = _page_text(url)
            picked = _self_sentences(t, 15) or ([t[:600]] if t else [])
            exp += [{"src": url, "text": x} for x in picked]
        except Exception as e:
            log(f"  못 읽었어요 ({str(e)[:60]})")
    me = {"name": me_ch.get("name"), "url": s["my_channel"], "handle": me_ch.get("handle"),
          "subs": me_ch.get("subs"), "avatar": me_ch.get("avatar"), "video_count": len(vids),
          "long_count": len(longs), "titles": [v.title for v in vids],
          "top": [{"id": v.id, "title": v.title, "views": v.views} for v in top],
          "experience": exp}
    HOME.mkdir(parents=True, exist_ok=True)
    (HOME / "me.json").write_text(json.dumps(me, ensure_ascii=False, indent=2), encoding="utf-8")
    return me


def experience_text(me: dict, limit: int = 9000) -> str:
    lines, n = [], 0
    for e in me.get("experience", []):
        line = f"- ({e['src']}) {e['text']}"
        if n + len(line) > limit:
            break
        lines.append(line)
        n += len(line)
    return "\n".join(lines) or "(아직 익힌 경험이 없어요)"


# ---------- 2. 키워드 ----------
def merge_keywords(auto: list[str], s: dict) -> list[str]:
    nf = lambda k: unicodedata.normalize("NFC", str(k)).strip()
    removed = {nf(k) for k in s.get("kw_removed", [])}
    out: list[str] = []
    for k in [nf(k) for k in auto if nf(k) not in removed] + [nf(k) for k in s.get("kw_added", [])]:
        if k and k not in out:
            out.append(k)
    return out


# ---------- 3·4. 채널 평소, 벤치마킹, 레퍼런스 ----------
def baseline(vids: list[Video], today: date, recent_days: int) -> float:
    lo = today - timedelta(days=BASELINE_DAYS)
    pool = [v.views for v in vids if not v.is_short and v.views >= 10 and v.upload_date
            and lo <= v.upload_date and (today - v.upload_date).days > recent_days]
    if len(pool) < 3:  # 3개월 안 영상이 적으면 최근 30편으로 대신
        pool = [v.views for v in vids if not v.is_short and v.views >= 10 and v.upload_date
                and (today - v.upload_date).days > recent_days][:30]
    return sum(pool) / len(pool) if pool else 0.0


def hits(ch: dict, vids: list[Video], base: float, today: date, c: dict) -> list[dict]:
    out = []
    for v in vids:
        if v.is_short or not v.upload_date or base <= 0:
            continue
        age = (today - v.upload_date).days
        if age > c["days"] or v.views < c["min_views"]:
            continue
        r = v.views / base
        if base < 1000:  # 평소 조회수가 너무 적은 채널은 배수가 부풀어서 뺀다 (평소 288회 → 287배 같은 경우)
            continue
        if r >= c["ratio"]:
            out.append({"id": v.id, "title": v.title, "channel": ch.get("name") or v.channel_name,
                        "channel_id": ch.get("id"), "views": v.views, "ratio": round(r, 1),
                        "baseline": int(base), "upload_date": v.upload_date.isoformat(), "age": age,
                        "duration": v.duration, "url": f"https://youtu.be/{v.id}",
                        "thumb": f"https://i.ytimg.com/vi/{v.id}/mqdefault.jpg"})
    return out


def _tag_format(ref: dict, formats: list[str], found_by: dict) -> str:
    if ref["id"] in found_by:
        return found_by[ref["id"]]
    title = ref["title"].lower()
    best, score = "", 0
    for f in formats:
        words = [w for w in re.findall(r"[가-힣A-Za-z]{2,}", f.lower())]
        sc = sum(1 for w in words if w in title)
        if sc > score:
            best, score = f, sc
    return best


def _same_channel(a: str, b: str) -> bool:
    import urllib.parse as up
    norm = lambda u: up.unquote((u or "").strip().lower()).split("?")[0].rstrip("/").replace("https://", "").replace("http://", "").replace("m.youtube", "www.youtube").replace("www.", "").removesuffix("/videos").removesuffix("/featured")
    return bool(a and b) and norm(a) == norm(b)


def analyze(s: dict, log: Callable[[str], None] = print, step: Callable[[str], None] = lambda k: None) -> dict:
    if not access.check_saved(s):
        raise PermissionError("이번 달 암호가 바뀌었어요. 커뮤니티 회원 게시판에서 새 암호를 확인해 주세요.")
    today = _today()
    c = dict(DEFAULT_CRITERIA)  # 유잡스 기준은 고정 (회원이 바꿀 수 없음)
    formats = [f for f in s.get("formats", []) if f.strip()]

    step("me"); log("내 채널과 내 경험을 읽는 중…")
    me = learn_me(s, log)

    step("models")
    roles, channel_vids, titles = [], {}, list(me["titles"])
    groups = [list(me["titles"])]
    failed_roles = []
    for url in s.get("role_models", []):
        log(f"롤모델 채널 읽는 중: {url}")
        try:
            ch, vids = collect.channel_videos(url, 60)
        except Exception as e:
            log("  건너뜀 (" + _friendly(e) + ")")
            failed_roles.append(url)
            continue
        ch["avg"] = int(baseline(vids, today, c["days"]))
        ch["video_count"] = len(vids)
        ch["is_me"] = _same_channel(url, s.get("my_channel", ""))
        roles.append(ch)
        channel_vids[ch["id"]] = (ch, vids)
        titles += [v.title for v in vids]
        groups.append([v.title for v in vids])

    if not roles and failed_roles:
        raise RuntimeError("롤모델 채널을 하나도 읽지 못했어요. 주소가 맞는지 확인해 주세요: " + ", ".join(failed_roles[:3]))
    anchor = anchor_word(groups[1:] or groups)  # 롤모델 제목 기준 분야 대표 말
    from .discover import YOUTUBE_FIELD_WORDS
    yt_field = anchor in ("유튜브", "youtube", "유튜버")
    if yt_field:  # 유튜브 교육 분야면 '유튜브' 대신 더 좁은 말을 검색어 앞에 붙이지 않는다(키워드가 이미 유튜브 용어)
        anchor = "유튜브"
    auto = shared_keywords(groups, keep=YOUTUBE_FIELD_WORDS if yt_field else frozenset())
    kws = merge_keywords(auto, s)
    role_ids = {r["id"] for r in roles}
    # 롤모델 칸에 내 채널을 넣었으면 '나보다 작은 채널'만 찾으면 거의 없다 → 나와 비슷한 규모(5배까지)로 찾는다
    # 내 채널이 아직 작으면(구독자 수백 명) 5배로도 거의 없으니, 최소 구독자 10만·평소 조회 5만까지는 본보기로 삼는다
    role_subs = [max(r["subs"] * 5, 100_000) if r.get("is_me") else r["subs"] for r in roles if r.get("subs")]
    role_avg = [max(r["avg"] * 5, 50_000) if r.get("is_me") else r["avg"] for r in roles if r.get("avg")]
    max_subs = min(role_subs) if role_subs else None
    max_avg = min(role_avg) if role_avg else None

    step("search"); log(f"키워드: {', '.join(kws)} (분야: {anchor or '-'})")
    found_count: Counter = Counter()
    found_kw: dict[str, set] = {}
    found_by_format: dict[str, str] = {}
    found_vids: set[str] = set()
    def q(k: str) -> str:  # '비즈니스' 대신 '유튜브 비즈니스'처럼 분야 말을 붙여 검색
        return f"{anchor} {k}" if anchor and anchor not in k.lower() and not k.startswith(anchor[:2]) else k
    search_terms = [(q(k), k, None) for k in kws] + [(f, f, f) for f in formats]
    for term, label, fmt in search_terms:
        log(f"검색 중: {term}")
        try:
            res = collect.search(term, 20)
        except Exception as e:
            log(f"  검색 실패 ({str(e)[:60]})")
            continue
        for v in res:
            if not v.channel_id or v.channel_id in role_ids or v.is_short:
                continue
            found_count[v.channel_id] += 1
            found_vids.add(v.id)
            found_kw.setdefault(v.channel_id, set()).add(label)
            if fmt:
                found_by_format[v.id] = fmt

    subs = s.get("subs")  # 회원이 고른 구독 리스트 (채널 id → 정보)
    subs = dict(subs) if isinstance(subs, dict) else {}
    removed_subs = set(s.get("subs_removed", []))
    step("bench")
    bench = []
    check_ids = [cid for cid, _ in found_count.most_common(25)]
    why: Counter = Counter()
    check_ids += [cid for cid in subs if cid not in check_ids]
    for cid in check_ids:
        try:
            ch, vids = collect.channel_videos(f"https://www.youtube.com/channel/{cid}", 40)
        except Exception:
            continue
        ch["avg"] = int(baseline(vids, today, c["days"]))
        ch["video_count"] = len(vids)
        ch["keywords"] = sorted(found_kw.get(cid, set()))[:4]
        channel_vids[cid] = (ch, vids)
        smaller = (ch.get("subs") is not None and max_subs and ch["subs"] < max_subs) or \
                  (ch.get("subs") is None and max_avg and ch["avg"] and ch["avg"] < max_avg)
        recent_long = sum(1 for v in vids if not v.is_short and v.upload_date and (today - v.upload_date).days <= 30)
        ch["recent_30"] = recent_long
        # 같은 분야인지: 그 채널 영상 제목 2개 이상에 분야 말이나 키워드가 들어 있어야 한다
        terms = [t.lower() for t in ([anchor] if anchor else []) + kws + formats if t]
        if yt_field:  # 유튜브 교육 분야는 제목에 유튜브 이야기가 있어야 같은 분야 ('회사'·'시대' 같은 말로는 부족)
            terms = sorted(YOUTUBE_FIELD_WORDS | {"유튜브", "youtube"} | {f.lower() for f in formats})
        on_topic = sum(1 for v in vids if any(t in v.title.lower() for t in terms)) >= 2
        # 너무 작은 채널(구독자 1천 미만이거나 평소 조회수 1천 미만)은 참고가 어려워 뺀다
        big_enough = (ch.get("subs") or 0) >= 1000 and (ch["avg"] or 0) >= 1000
        if cid in subs or (smaller and big_enough and recent_long >= 1 and on_topic and cid not in removed_subs):
            bench.append(ch)
        else:
            why[("롤모델보다 큼" if not smaller else "너무 작음" if not big_enough else
                 "최근 30일 롱폼 없음" if recent_long < 1 else "분야 다름" if not on_topic else "직접 뺀 채널")] += 1
    log(f"벤치마킹 후보 {len(check_ids)}곳 → {len(bench)}곳" + (" (빠진 이유: " + ", ".join(f"{k} {n}" for k, n in why.most_common()) + ")" if why else "")
        + (f" · 기준 구독자 {max_subs:,}명 미만" if max_subs else ""))
    # 롤모델과 같은 분야로 찾은 채널은 전부 구독 리스트에 (회원이 직접 뺀 채널은 다시 넣지 않음)
    for ch in bench:
        if ch["id"] not in removed_subs:
            subs.setdefault(ch["id"], {"name": ch["name"]})
    for ch in bench:
        ch["subscribed"] = ch["id"] in subs

    step("pick")
    shown = set()
    if HOME.exists():
        for d in HOME.iterdir():
            f = d / "refs.json"
            if d.is_dir() and d.name != today.isoformat() and f.exists():
                try:
                    shown |= {r["id"] for r in json.loads(f.read_text(encoding="utf-8"))}
                except (OSError, ValueError, KeyError):
                    pass
    refs, seen = [], set()
    for cid, (ch, vids) in channel_vids.items():
        source = "롤모델" if cid in role_ids else ("구독 리스트" if cid in subs else "키워드 검색")
        for h in hits(ch, vids, baseline(vids, today, c["days"]), today, c):
            if h["id"] in shown or h["id"] in seen:
                continue
            if source == "키워드 검색" and h["id"] not in found_vids:
                continue  # 검색으로만 알게 된 채널은 검색에 걸린 그 영상만 (채널의 다른 주제 영상은 뺌)
            if source == "키워드 검색" and yt_field and h["id"] not in found_by_format and \
                    not any(w in h["title"].lower() for w in YOUTUBE_FIELD_WORDS | {"유튜브", "youtube"}):
                continue  # 유튜브 교육 분야인데 제목에 유튜브 얘기가 없는 영상(퇴직·여행 등)은 뺀다
            seen.add(h["id"])
            h["source"] = source
            h["format"] = _tag_format(h, formats, found_by_format)
            refs.append(h)
    refs.sort(key=lambda r: (-r["ratio"], r["age"]))

    out_dir = HOME / today.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "refs.json").write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {"date": today.isoformat(), "folder": str(out_dir), "me": {k: me[k] for k in ("name", "handle", "subs", "avatar", "video_count", "long_count")},
              "exp_count": len(me["experience"]), "keywords": kws, "auto_keywords": auto,
              "roles": roles, "failed_roles": failed_roles, "bench": bench, "bench_why": dict(why), "bench_checked": len(check_ids), "subs": subs, "refs": refs, "criteria": c, "formats": formats}
    (HOME / "last_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    step("done"); log("완료!")
    return result


# ---------- 기획하기: 영상 1편 자료 ----------
def plan_material(video: dict, story: str, s: dict) -> tuple[str, Path]:
    from .bundle import ts
    try:
        d = collect.video_detail(video["url"], 40)
        partial = ""
    except Exception as e:  # 유튜브가 영상 페이지 읽기를 막는 경우: 아는 정보만으로 자료를 만든다
        d = {"id": video.get("id"), "title": video.get("title"), "channel": video.get("channel"),
             "duration": video.get("duration"), "views": video.get("views"),
             "thumbnail": f"https://i.ytimg.com/vi/{video.get('id')}/hqdefault.jpg", "description": "",
             "comments": [], "comment_count": 0, "transcript": []}
        partial = f"(유튜브가 이번엔 영상 페이지를 읽지 못하게 막아서 설명란·댓글·자막을 못 가져왔어요: {str(e)[:80]})"
    me = json.loads((HOME / "me.json").read_text(encoding="utf-8")) if (HOME / "me.json").exists() else {}
    prompt = (net.BASE / "prompts" / "plan_prompt.md").read_text(encoding="utf-8")
    L = [prompt, "", "---", "", "# 기획 자료", "",
         "## 내 채널", f"- 채널: {me.get('name','')} ({s.get('my_channel','')})",
         f"- 내 시청자와 상품: {s.get('audience') or '(비어 있음)'}", "",
         "### 내 채널 조회수 상위 (썸네일 스타일 기준)"]
    for t in me.get("top", []):
        L.append(f"- {t['title']} · 조회 {t['views']:,} · https://youtu.be/{t['id']} · 썸네일 https://i.ytimg.com/vi/{t['id']}/hqdefault.jpg")
    L += ["", "## 내 경험 노트 (콘봇이 내 영상 대본·소개·링크에서 익힌 것. 여기 있는 건 질문하지 말고 바로 쓸 것)",
          experience_text(me), "",
          "## 이 영상에 대한 내 이야기 (회원이 직접 쓴 것. 반드시 대본에 녹일 것)", story.strip() or "(비어 있음)", "",
          f"## 레퍼런스: {d.get('title')}",
          f"- 링크: https://youtu.be/{d.get('id')}",
          f"- 채널: {d.get('channel')} · 길이 {ts(d.get('duration') or 0)} · 조회 {d.get('views') or 0:,} · 업로드 {video.get('upload_date') or '(모름)'}",
          (f"- 채널 평소 대비 {video.get('ratio')}배" + (f" (평소 {video['baseline']:,}회 = 최근 3개월 롱폼 평균)" if video.get("baseline") else ""))
          if video.get("ratio") else "- 채널 평소 대비 배수: (모름)",
          f"- 포맷: {video.get('format') or '(미정)'}",
          f"- 썸네일: {d.get('thumbnail')}", ""]
    if video.get("note"):
        L += ["### 학원월드 주간 게시글 분석 (대표가 쓴 분석. 기획의 출발점으로 삼고, 이 분석이 짚은 '왜 터졌나'를 내 영상에서 살릴 것)",
              video["note"][:2500], ""]
    L += ["### 설명란", (d.get("description") or "")[:1500], "",
          f"### 댓글 상위 {len(d.get('comments') or [])}개 (총 {d.get('comment_count') or 0:,}개)"]
    for cm in d.get("comments") or []:
        tag = ("고정 댓글 · " if cm.get("pinned") else "") + ("채널 주인 · " if cm.get("by_uploader") else "")
        L.append(f"- ({tag}좋아요 {cm['likes']}) {cm['text'].replace(chr(10), ' ')[:300]}")
    L += ["", "### 자막 (시간 포함)"]
    tr = d.get("transcript") or []
    if not tr:
        L.append(partial or "(자막 없음 — 설명란·댓글로 분석하고 그 사실을 적을 것)")
        if partial:
            L.append("(원본 대사를 지어내지 말 것. 제목·썸네일·내 이야기로 기획하고, 원본 대사가 필요한 곳은 '원본 확인 필요'로 표시할 것)")
    L += [f"[{ts(x['start'])}] {x['text']}" for x in tr]
    text = "\n".join(L)
    folder = HOME / "기획" / f"{_today().isoformat()}_{video['id']}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "기획자료.md").write_text(text, encoding="utf-8")
    (folder / "video.json").write_text(json.dumps(video, ensure_ascii=False, indent=2), encoding="utf-8")
    return text, folder
