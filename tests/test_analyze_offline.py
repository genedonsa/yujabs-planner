"""분석 전체(engine.analyze)를 인터넷 없이 끝까지 돌려 본다: 키워드 → 검색 → 벤치마킹(전부 구독) → 레퍼런스."""
from datetime import date, timedelta

import pytest

from planner import access, collect
from planner import engine as E
from planner.surge import Video

TODAY = date(2026, 11, 28)
YT = ["유튜브 수익화 3가지 방법", "구독자 1만 만든 썸네일", "조회수 안 나올 때 알고리즘", "유튜브 수익화 현실",
      "썸네일 바꾸고 조회수 2배", "구독자 0명에서 시작하기", "알고리즘이 좋아하는 롱폼", "유튜브 편집 순서"]


def _vids(cid, name, titles, views=5000, hot=None):
    out = []
    for i in range(40):
        d = TODAY - timedelta(days=10 + i * 3)
        out.append(Video(f"{cid}{i:02d}xxxxxxxx"[:11], titles[i % len(titles)], cid, name, views, d, 600))
    if hot:
        out.insert(0, Video(f"{cid}HOTxxxxxxx"[:11], hot, cid, name, views * 6, TODAY - timedelta(days=2), 600))
    return out


TRAVEL = ["제주 캠핑 브이로그", "농막 생활 3일차", "부산 먹방 여행", "낚시 브이로그", "일본 여행 첫날"] * 7 + \
         ["구독자 1천 기념 Q&A", "구독자 감사 캠핑"]
CH = {
    "me": ({"id": "UCme", "name": "나", "subs": 88}, _vids("UCme", "나", YT, 300)),
    "role": ({"id": "UCrole", "name": "롤모델", "subs": 140_000}, _vids("UCrole", "롤모델", YT, 20_000)),
    "UCedu": ({"id": "UCedu", "name": "유튜브교육", "subs": 20_000}, _vids("UCedu", "유튜브교육", YT, 3000, hot="유튜브 수익화 구독자 1천 달성기")),
    "UCtrv": ({"id": "UCtrv", "name": "여행", "subs": 20_000}, _vids("UCtrv", "여행", TRAVEL, 3000)),
    "UCold": ({"id": "UCold", "name": "예전자동", "subs": 20_000}, _vids("UCold", "예전자동", TRAVEL, 3000)),
    "UCmine": ({"id": "UCmine", "name": "직접넣음", "subs": 20_000}, _vids("UCmine", "직접넣음", TRAVEL, 3000)),
}


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "HOME", tmp_path)
    monkeypatch.setattr(E, "_today", lambda: TODAY)
    monkeypatch.setattr(access, "check_saved", lambda s: True)

    def channel_videos(url, limit=60, original_titles=True):
        key = "me" if url.endswith("@me") else "role" if url.endswith("@role") else url.rsplit("/", 1)[-1]
        ch, v = CH[key]
        return dict(ch), list(v)
    monkeypatch.setattr(collect, "channel_videos", channel_videos)
    monkeypatch.setattr(collect, "search", lambda q, n=20, days=30: [CH["UCedu"][1][0], CH["UCtrv"][1][-1]])
    monkeypatch.setattr(collect, "video_transcript", lambda url: {"transcript": [{"text": "저는 회사를 다니며 유튜브를 했어요."}]})
    s = {"my_channel": "https://www.youtube.com/@me", "role_models": ["https://www.youtube.com/@role"],
         "formats": [], "subs": {"UCold": {"name": "예전자동", "auto": True}, "UCmine": {"name": "직접넣음"}},
         "kw_added": ["수익화"]}
    return E.analyze(s, log=lambda m: None)


def test_analyze_end_to_end(run):
    r = run
    ids = {b["id"] for b in r["bench"]}
    assert "UCedu" in ids                      # 같은 분야 → 벤치마킹 + 자동 구독
    assert "UCtrv" not in ids                  # 여행 브이로그는 '구독자' 몇 편으로 끼지 않음
    assert r["subs"]["UCedu"].get("auto")
    assert "UCold" not in r["subs"]            # 콘봇이 넣었던 채널이 기준에 안 맞으면 빠짐
    assert "UCmine" in r["subs"] and "UCmine" in ids  # 회원이 직접 넣은 채널은 그대로
    assert len(r["keywords"]) == len(set(r["keywords"]))
    assert r["criteria"] == E.DEFAULT_CRITERIA
    assert any(x["id"].startswith("UCeduHOT") for x in r["refs"])
