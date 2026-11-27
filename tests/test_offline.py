"""유튜브 접속 없이 도는 테스트."""
from datetime import date, datetime
from pathlib import Path

from PIL import Image

from planner import access
from planner.bundle import ts, write_bundle
from planner.discover import keywords
from planner.surge import Video, channel_baseline, pick
from planner.thumbnail import compose


def v(i, ch, views, d):
    return Video(id=i, title=f"t{i}", channel_id=ch, channel_name=ch, views=views, upload_date=d, duration=600)


def test_password_fingerprint():
    fp = access.fingerprint("12월암호")
    assert len(fp) == 64
    assert access.check(" 12월암호 ", fp)
    assert not access.check("11월암호", fp)
    assert not access.check("", fp)


def test_password_from_sheet_csv(monkeypatch):
    import io
    fp = access.fingerprint("겨울")
    class R(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): pass
    fp2 = access.fingerprint("rufdnf")
    monkeypatch.setattr(access.urllib.request, "urlopen", lambda *a, **k: R(f"지문,메모\n{fp},12월\n{fp2},영문 입력\n".encode()))
    monkeypatch.setattr(access, "ACCESS_URL", "http://sheet")
    assert access.check("겨울")
    assert access.check("rufdnf")
    assert not access.check("가을")


def test_no_access_url_is_error(monkeypatch):
    import pytest
    monkeypatch.setattr(access, "ACCESS_URL", "")
    with pytest.raises(access.AccessError):
        access.check("아무거나")


def test_pick_one_per_channel_week_first_then_fill():
    today = date(2026, 11, 27)
    a = [v("a1", "A", 10000, date(2026, 11, 25)), v("a2", "A", 9000, date(2026, 11, 24))]
    b = [v("b1", "B", 3000, date(2026, 11, 22)), v("old", "B", 99999, date(2026, 9, 1))]
    c = [v("c1", "C", 5000, date(2026, 11, 16))]          # 11일 전: 1주 밖 → 보충으로만
    d = [v("d1", "D", 1500, date(2026, 11, 26))]          # 1.5배: 기준 미달
    e = [v("seen", "E", 9000, date(2026, 11, 26))]        # 지난번에 보여준 영상
    cands = [(x, 1000.0) for x in a + b + c + d + e]
    got = pick(cands, today, exclude={"seen"})
    assert [x[0].id for x in got] == ["a1", "b1", "c1"]
    assert got[2][0].extra.get("보충") and not got[0][0].extra.get("보충")


def test_baseline_is_recent30_average_without_last_week():
    today = date(2026, 11, 27)
    vids = [v("new", "A", 50000, date(2026, 11, 25))]  # 최근 1주: 평소 계산에서 뺌
    vids += [v(f"o{i}", "A", 1000 + i, date(2026, 11, 10) - __import__("datetime").timedelta(days=i)) for i in range(40)]
    vids += [v("tiny", "A", 3, date(2026, 11, 9))]       # 조회수 10 미만 무시
    base = channel_baseline(vids, today)
    # 최신 30편(new 포함) 중 new를 뺀 29편 평균
    assert base == sum(1000 + i for i in range(29)) / 29


def test_keywords():
    titles = ["주식으로 1억 모은 공무원", "주식 초보가 꼭 알아야 할 것", "공무원 월급으로 주식 투자"]
    kws = keywords(titles)
    assert "주식" in kws and "공무원" in kws


def test_bundle_and_thumbnail(tmp_path: Path):
    bg = tmp_path / "bg.jpg"
    Image.new("RGB", (1280, 720), (90, 110, 140)).save(bg)
    out = compose(bg, "구독자를 위해", "영상 만들지 마세요!", tmp_path / "o.jpg")
    assert Image.open(out).size == (1280, 720)
    ref = {"video": v("x", "C", 5000, date(2026, 11, 25)), "ratio": 5.0, "baseline": 1000,
           "detail": {"id": "x", "title": "T", "channel": "C", "duration": 61, "views": 5000, "upload_date": "20261125",
                      "description": "d", "thumbnail": "u", "comment_count": 3,
                      "comments": [{"text": "좋아요", "likes": 3}], "transcript": [{"start": 38.2, "text": "hello"}]}}
    b, p = write_bundle(tmp_path, {"name": "나", "url": "u"}, [], [ref], date(2026, 11, 27))
    txt = b.read_text(encoding="utf-8")
    assert "[0:38] hello" in txt and p.exists()
    assert ts(3817) == "1:03:37"


def test_thumbnail_lines_strip_numbers(tmp_path: Path, monkeypatch):
    import json as _j
    from planner import run as R
    (tmp_path / "원본썸네일").mkdir()
    Image.new("RGB", (1280, 720), (90, 110, 140)).save(tmp_path / "원본썸네일" / "a.jpg")
    (tmp_path / "refs.json").write_text(_j.dumps([{"id": "a"}]), encoding="utf-8")
    seen = []
    monkeypatch.setattr(R, "compose", lambda bg, l1, l2, out, tpl, style: seen.append((l1, l2)) or out)
    R.make_thumbnails(tmp_path, "1. 구독자를 위해 / 영상 만들지 마세요!", {})
    assert seen == [("구독자를 위해", "영상 만들지 마세요!")]


def test_keywords_skip_generic_words():
    kws = keywords(["유튜브 수익화 3가지", "유튜브 수익화 하지 마세요", "수익화 현실 총정리", "현실 총정리 가지"])
    assert "수익화" in kws and not {"가지", "하지", "총정리", "현실"} & set(kws)


def test_engine_criteria_and_keywords():
    from datetime import timedelta
    from planner import engine as E
    today = date(2026, 11, 27)
    old = [v(f"o{i}", "A", 4000, today - timedelta(days=10 + i * 3)) for i in range(30)]
    new = [v("hit", "A", 15000, today - timedelta(days=2)),      # 3.75배, 1만 이상 → 통과
           v("small", "A", 9000, today - timedelta(days=1)),     # 1만 미만 → 탈락
           v("late", "A", 20000, today - timedelta(days=9))]     # 7일 넘음 → 탈락
    vids = new + old
    base = E.baseline(vids, today, 7)
    # 평소 = 최근 3개월(90일) 롱폼 중 최근 7일을 뺀 평균: 4000회 27편 + 9일 전 2만 회 1편
    assert round(base) == round((27 * 4000 + 20000) / 28)
    got = E.hits({"name": "A", "id": "A"}, vids, base, today, dict(E.DEFAULT_CRITERIA))
    assert [h["id"] for h in got] == ["hit"] and got[0]["ratio"] == 3.3
    s = {"kw_removed": ["판매"], "kw_added": ["코스트코"]}
    assert E.merge_keywords(["판매", "유튜브"], s) == ["유튜브", "코스트코"]
