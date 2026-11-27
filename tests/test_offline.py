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


def test_pick_one_per_channel_and_fresh():
    today = date(2026, 11, 27)
    a = [v("a1", "A", 10000, date(2026, 11, 25)), v("a2", "A", 9000, date(2026, 11, 24))]
    b = [v("b1", "B", 3000, date(2026, 11, 20)), v("old", "B", 99999, date(2026, 9, 1))]
    cands = [(x, 1000.0) for x in a + b]
    got = pick(cands, today)
    assert [x[0].id for x in got] == ["a1", "b1"]


def test_baseline_is_median():
    vids = [v(str(i), "A", n, None) for i, n in enumerate([100, 200, 300, 10000])]
    assert channel_baseline(vids) == 250


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
