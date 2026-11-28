"""분석 전체(engine.analyze)를 인터넷 없이 끝까지 돌려 본다: 키워드 → 검색 → 벤치마킹(전부 구독) → 레퍼런스."""
from datetime import date, timedelta

import pytest

from planner import access, collect
from planner import engine as E
from planner.surge import Video

TODAY = date(2026, 11, 28)
YT = ["유튜브 수익화 3가지 방법", "구독자 1만 만든 썸네일", "조회수 안 나올 때 알고리즘", "유튜브 수익화 현실",
      "썸네일 바꾸고 조회수 2배", "구독자 0명에서 시작하기", "알고리즘이 좋아하는 롱폼", "유튜브 편집 순서"]


def _vids(cid, name, titles, views=5000, hot=None, n_hot=1):
    out = []
    for i in range(40):
        d = TODAY - timedelta(days=10 + i * 3)
        out.append(Video(f"{cid}{i:02d}xxxxxxxx"[:11], titles[i % len(titles)], cid, name, views, d, 600))
    for j in range(n_hot if hot else 0):
        out.insert(0, Video(f"{cid}HOT{j}xxxxxx"[:11], hot, cid, name, views * 6, TODAY - timedelta(days=2), 600))
    return out


TRAVEL = ["제주 캠핑 브이로그", "농막 생활 3일차", "부산 먹방 여행", "낚시 브이로그", "일본 여행 첫날"] * 7 + \
         ["구독자 1천 기념 Q&A", "구독자 감사 캠핑"]
KOR = ["외국인 유튜버가 본 한국 음식", "한국 여행 외국인 반응", "유튜버 친구와 한국 시장", "외국인 반응 김치",
       "한국 편의점 외국인", "외국인 유튜버 서울 여행", "한국어 공부 외국인", "유튜버 한국 지하철"]
CH = {
    "me": ({"id": "UCme", "name": "나", "subs": 88}, _vids("UCme", "나", YT, 300)),
    "role": ({"id": "UCrole", "name": "롤모델", "subs": 140_000}, _vids("UCrole", "롤모델", YT, 20_000)),
    "role2": ({"id": "UCrole2", "name": "큰롤모델", "subs": 900_000}, _vids("UCrole2", "큰롤모델", YT, 200_000)),
    "UCedu": ({"id": "UCedu", "name": "유튜브교육", "subs": 20_000}, _vids("UCedu", "유튜브교육", YT, 3000, hot="유튜브 수익화 구독자 1천 달성기", n_hot=4)),
    "UCmid": ({"id": "UCmid", "name": "중간교육", "subs": 300_000}, _vids("UCmid", "중간교육", YT, 30_000)),
    "UCkor": ({"id": "UCkor", "name": "한국어때", "subs": 20_000}, _vids("UCkor", "한국어때", KOR, 3000, hot="외국인 유튜버 한국 반응", n_hot=4)),
    "UCtrv": ({"id": "UCtrv", "name": "여행", "subs": 20_000}, _vids("UCtrv", "여행", TRAVEL, 3000)),
    "UCold": ({"id": "UCold", "name": "예전자동", "subs": 20_000}, _vids("UCold", "예전자동", TRAVEL, 3000)),
    "UCmine": ({"id": "UCmine", "name": "직접넣음", "subs": 20_000}, _vids("UCmine", "직접넣음", TRAVEL, 3000)),
}


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "HOME", tmp_path)
    monkeypatch.setattr(E, "_today", lambda: TODAY)
    monkeypatch.setattr(access, "check_saved", lambda s: True)
    from planner import series as SR
    monkeypatch.setattr(SR, "modes", lambda home=None, refresh=False: dict(SR.DEFAULT_MODES))

    def channel_videos(url, limit=60, original_titles=True):
        key = "me" if url.endswith("@me") else "role2" if url.endswith("@role2") else "role" if url.endswith("@role") else url.rsplit("/", 1)[-1]
        ch, v = CH[key]
        return dict(ch), list(v)
    monkeypatch.setattr(collect, "channel_videos", channel_videos)
    monkeypatch.setattr(collect, "search", lambda q, n=20, days=30: [CH["UCedu"][1][0], CH["UCtrv"][1][-1], CH["UCkor"][1][0], CH["UCmid"][1][0]])
    monkeypatch.setattr(collect, "video_transcript", lambda url: {"transcript": [{"text": "저는 회사를 다니며 유튜브를 했어요."}]})
    s = {"my_channel": "https://www.youtube.com/@me", "role_models": ["https://www.youtube.com/@role", "https://www.youtube.com/@role2"],
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
    assert sum(1 for x in r["refs"] if x["id"].startswith("UCeduHOT")) == 2  # 한 채널은 2편까지
    assert "UCkor" not in ids and not any(x["id"].startswith("UCkorHOT") for x in r["refs"])  # '유튜버' 하나만 걸린 다른 분야
    assert "UCmid" in ids  # 롤모델을 늘리면(큰 롤모델) 그 규모까지 찾는다
    assert any(" " in k for k in r["auto_keywords"]) and not {"조회수", "구독자", "채널"} & set(r["auto_keywords"])


def test_series_modes_and_channels(tmp_path, monkeypatch):
    """회원 시리즈: 시리즈 채널은 그 시리즈의 찾기 방식(숨은 사례 발굴=30일·2배)으로 고른다."""
    from planner import series as SR
    monkeypatch.setattr(E, "HOME", tmp_path)
    monkeypatch.setattr(E, "_today", lambda: TODAY)
    monkeypatch.setattr(access, "check_saved", lambda s: True)
    monkeypatch.setattr(SR, "modes", lambda home=None, refresh=False: dict(SR.DEFAULT_MODES))
    vids = _vids("UCcase", "사례채널", ["How I grew my YouTube channel"] * 8, 4000)
    vids.insert(0, Video("UCcaseOLD20", "He Got 6 Million Subscribers", "UCcase", "사례채널", 10000, TODAY - timedelta(days=20), 900))
    chans = dict(CH, **{"UCcase": ({"id": "UCcase", "name": "사례채널", "subs": 50_000}, vids)})

    def channel_videos(url, limit=60, original_titles=True):
        key = "me" if url.endswith("@me") else "role" if url.endswith("@role") else "UCcase" if url.endswith("@case") else url.rsplit("/", 1)[-1]
        ch, v = chans[key]
        return dict(ch), list(v)
    monkeypatch.setattr(collect, "channel_videos", channel_videos)
    monkeypatch.setattr(collect, "search", lambda q, n=20, days=30: [])
    monkeypatch.setattr(collect, "video_transcript", lambda url: {"transcript": []})
    base = {"my_channel": "https://www.youtube.com/@me", "role_models": ["https://www.youtube.com/@role"], "formats": ["옛 포맷"]}
    s = dict(base, series=[{"name": "해외 성공 사례", "desc": "해외 유튜브 성공 사례 소개", "mode": "hidden",
                            "channels": ["https://www.youtube.com/@case"]}])
    r = E.analyze(s, log=lambda m: None)
    got = [x for x in r["refs"] if x["id"] == "UCcaseOLD20"]
    assert got and got[0]["format"] == "해외 성공 사례" and got[0]["source"] == "시리즈 채널"
    assert r["series"][0]["mode_label"].startswith("숨은 사례 발굴")
    s2 = dict(base, series=[dict(s["series"][0], mode="weekly")])  # 같은 영상도 '이번 주 급상승'이면 20일 전이라 빠짐
    assert not [x for x in E.analyze(s2, log=lambda m: None)["refs"] if x["id"] == "UCcaseOLD20"]
    assert [x["name"] for x in SR.load(base)] == ["옛 포맷"]  # 예전 포맷은 시리즈로 옮겨짐


def test_parse_modes_guards():
    from planner import series as SR
    m = SR.parse_modes("key,name,days,ratio,min_views,desc\nhidden,숨은 사례,999,1,0,x\nweekly,급상승,7,3배,\"10,000\",\n,빈줄,1,1,1,\n")
    assert m["hidden"]["days"] == 180 and m["hidden"]["ratio"] == 1.5  # 배수 조건은 최소 1.5배로 지킴
    assert m["weekly"]["min_views"] == 10000 and "" not in m
    assert SR.parse_modes("id,title\nabc,영상\n") == {}  # 다른 탭이 오면 무시
