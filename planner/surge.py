"""채널 평균 대비 배수 계산과 후보 순위. 수집 없이 테스트할 수 있는 순수 함수만 둔다."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Video:
    id: str
    title: str
    channel_id: str
    channel_name: str
    views: int
    upload_date: date | None
    duration: int | None = None  # 초
    is_short: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"https://youtu.be/{self.id}"


RECENT_DAYS = 7        # '최근 1주' — 주간 급상승 기준과 같음
MIN_RATIO = 2.0        # 채널 평소의 2배 이상
BASELINE_COUNT = 30    # 평소 = 최근 30편 평균(최근 1주 영상은 뺌)
MIN_VIEWS = 10         # 회원 전용 등 조회수가 안 보이는 영상은 무시


def channel_baseline(videos: list[Video], today: date | None = None) -> float:
    """채널 평소 조회수 = 최근 30편 중 '최근 1주' 영상을 뺀 나머지의 평균 (주간 급상승 기준과 같음).
    롱폼만 본다. today가 없으면 최근 1주를 빼지 않는다."""
    vids = [v for v in videos if not v.is_short and v.views is not None and v.views >= MIN_VIEWS]
    vids.sort(key=lambda v: v.upload_date or date.min, reverse=True)
    vids = vids[:BASELINE_COUNT]
    if today:
        vids = [v for v in vids if not v.upload_date or (today - v.upload_date).days > RECENT_DAYS]
    views = [v.views for v in vids]
    return sum(views) / len(views) if views else 0.0


def ratio(video: Video, baseline: float) -> float:
    return video.views / baseline if baseline > 0 else 0.0


def score(video: Video, baseline: float, today: date, fresh_days: int = RECENT_DAYS) -> float:
    """배수 × 최신성. 오늘 올라온 영상 1.0, fresh_days가 되면 0.3까지 낮춘다."""
    r = ratio(video, baseline)
    if not video.upload_date:
        return r * 0.3
    age = max((today - video.upload_date).days, 0)
    freshness = max(0.3, 1 - 0.7 * age / max(fresh_days, 1))
    return r * freshness


def pick(candidates: list[tuple[Video, float]], today: date, top: int = 4,
         min_ratio: float = MIN_RATIO, fresh_days: int = RECENT_DAYS,
         exclude: set[str] | None = None, fill_days: int = 14) -> list[tuple[Video, float, float]]:
    """candidates: (영상, 그 채널 평소). 기준: 최근 1주 + 평소 2배 이상 + 롱폼 + 지난번에 보여준 영상 제외.
    같은 채널은 1편만. 1주 안에서 top편이 안 채워지면 2주(fill_days)까지 넓혀 채운다(보충 표시).
    (영상, 배수, 점수) 반환. 보충된 영상은 v.extra['보충']=True."""
    exclude = exclude or set()

    def rows_for(days):
        rows = []
        for v, base in candidates:
            if v.is_short or not v.upload_date or v.id in exclude or (v.views or 0) < MIN_VIEWS:
                continue
            if (today - v.upload_date).days > days:
                continue
            r = ratio(v, base)
            if r < min_ratio:
                continue
            rows.append((v, r, score(v, base, today, days)))
        rows.sort(key=lambda x: x[2], reverse=True)
        return rows

    seen, out = set(), []
    for days, extra in ((fresh_days, False), (fill_days, True)):
        for v, r, s in rows_for(days):
            if v.channel_id in seen or len(out) == top:
                continue
            seen.add(v.channel_id)
            if extra:
                v.extra["보충"] = True
            out.append((v, r, s))
        if len(out) == top:
            break
    return out
