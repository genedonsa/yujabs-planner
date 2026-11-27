"""채널 평균 대비 배수 계산과 후보 순위. 수집 없이 테스트할 수 있는 순수 함수만 둔다."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from statistics import median


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


def channel_baseline(videos: list[Video]) -> float:
    """채널 평소 조회수 = 중앙값 (한두 편 대박에 덜 흔들림). 쇼츠는 따로 본다."""
    views = [v.views for v in videos if v.views is not None and not v.is_short]
    return float(median(views)) if views else 0.0


def ratio(video: Video, baseline: float) -> float:
    return video.views / baseline if baseline > 0 else 0.0


def score(video: Video, baseline: float, today: date, fresh_days: int = 14) -> float:
    """배수 × 최신성. 오늘 올라온 영상 1.0, fresh_days 지나면 0.3까지 낮춘다."""
    r = ratio(video, baseline)
    if not video.upload_date:
        return r * 0.3
    age = max((today - video.upload_date).days, 0)
    freshness = max(0.3, 1 - 0.7 * age / fresh_days)
    return r * freshness


def pick(candidates: list[tuple[Video, float]], today: date, top: int = 4,
         min_ratio: float = 2.0, fresh_days: int = 14) -> list[tuple[Video, float, float]]:
    """candidates: (영상, 그 채널 기준선). 같은 채널은 1편만. (영상, 배수, 점수) 반환."""
    rows = []
    for v, base in candidates:
        if v.is_short or not v.upload_date:
            continue
        if (today - v.upload_date).days > fresh_days:
            continue
        r = ratio(v, base)
        if r < min_ratio:
            continue
        rows.append((v, r, score(v, base, today, fresh_days)))
    rows.sort(key=lambda x: x[2], reverse=True)
    seen, out = set(), []
    for v, r, s in rows:
        if v.channel_id in seen:
            continue
        seen.add(v.channel_id)
        out.append((v, r, s))
        if len(out) == top:
            break
    return out
