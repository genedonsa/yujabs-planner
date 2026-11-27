"""Claude 앱 연결(MCP)·주간 게시글·Claude 설정 등록 테스트 (인터넷 없이)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from planner import access, claude_link, mcp_server, weekly
from planner import engine as E
from planner import run as R

ROOT = Path(__file__).resolve().parents[1]

POST_TEXT = """이번 주 급상승 영상
1. 엄마의손맛 — 평소의 5.2배
https://youtu.be/abcdefghijk
영상 요약: 김치 담그는 법
왜 터졌나: 댓글 반응 좋음
2. 전국집밥자랑 — 평소의 3.4배
https://www.youtube.com/watch?v=ZYXWVUTSRQP&t=3
영상 요약: 반찬 10가지
"""
POST_HTML = ('<p>1. 엄마의손맛 — 평소의 5.2배</p><a href="https://youtu.be/abcdefghijk">'
             '<img src="https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg"></a><p>초롱무 김치</p><p>왜 터졌나: 계절</p>'
             '<p>2. 전국 — 평소의 3.4배</p><a href="https://www.youtube.com/shorts/ZYXWVUTSRQP">반찬</a><p>왜 터졌나: 좋음</p>')


def test_weekly_parse_text_and_html():
    for items in (weekly.parse(text=POST_TEXT), weekly.parse(html=POST_HTML)):
        assert [i["id"] for i in items] == ["abcdefghijk", "ZYXWVUTSRQP"]
        assert [i["ratio"] for i in items] == [5.2, 3.4]
        assert "왜 터졌나" in items[0]["note"] and "3.4" not in items[0]["note"]
        assert items[1]["note"].startswith("2.")


def test_mcp_handshake_subprocess():
    out = mcp_server.probe([sys.executable, str(ROOT / "desktop.py"), "--mcp"])
    assert out.startswith("ok") and "tools=" in out, out


@pytest.fixture
def srv(tmp_path, monkeypatch):
    for mod in (E, R):
        monkeypatch.setattr(mod, "HOME", tmp_path)
    monkeypatch.setattr(R, "SETTINGS", tmp_path / "settings.json")
    monkeypatch.setattr(R, "BACKUP", tmp_path / "settings.bak.json")
    monkeypatch.setattr(access, "check_saved", lambda s: True)
    monkeypatch.setattr(weekly, "enrich", lambda items, log=None: [i.update(title=f"제목 {i['id']}") for i in items] and items)
    monkeypatch.setattr(mcp_server.Server, "_ok_at", 0.0, raising=False)
    return mcp_server.Server()


def _call(srv, tool, **a):
    r = mcp_server.call(srv, tool, a)
    return r.get("isError", False), r["content"][0]["text"]


def test_tools_weekly_flow_and_plan(srv, tmp_path, monkeypatch):
    err, t = _call(srv, "import_weekly_post", text=POST_TEXT)
    assert not err, t
    assert "W2" in t and "제목 ZYXWVUTSRQP" in t
    err, t = _call(srv, "list_weekly_videos")
    assert not err and "평소의 5.2배" in t
    seen = {}

    def fake_material(video, story, s):
        seen["v"] = video
        folder = tmp_path / "기획" / f"2026-11-28_{video['id']}"
        folder.mkdir(parents=True)
        (folder / "video.json").write_text(json.dumps(video, ensure_ascii=False), encoding="utf-8")
        return "자료", folder
    monkeypatch.setattr(E, "plan_material", fake_material)
    err, t = _call(srv, "get_planning_material", video="w2", my_story="나도 해 봤다")
    assert not err and t.startswith("자료")
    assert seen["v"]["id"] == "ZYXWVUTSRQP" and "반찬" in seen["v"]["note"]
    err, t = _call(srv, "save_plan", video="W2", plan_markdown="# 기획안")
    assert not err
    assert (tmp_path / "기획" / "2026-11-28_ZYXWVUTSRQP" / "기획안.md").read_text(encoding="utf-8") == "# 기획안"
    err, t = _call(srv, "list_plans", read=1)
    assert not err and "# 기획안" in t
    err, t = _call(srv, "get_planning_material", video="W9")
    assert err and "목록에 없어요" in t


def test_plan_material_includes_post_note(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "HOME", tmp_path)
    monkeypatch.setattr(E.collect, "video_detail", lambda url, n: (_ for _ in ()).throw(RuntimeError("blocked")))
    v = {"id": "abcdefghijk", "url": "https://www.youtube.com/watch?v=abcdefghijk", "title": "김치", "ratio": None,
         "note": "왜 터졌나: 계절 김치"}
    text, folder = E.plan_material(v, "", {})
    assert "학원월드 주간 게시글 분석" in text and "계절 김치" in text and "배수: (모름)" in text


def test_password_gate(srv, monkeypatch):
    monkeypatch.setattr(access, "check_saved", lambda s: False)
    err, t = _call(srv, "list_references")
    assert err and "암호" in t
    err, t = _call(srv, "cornbot_status")
    assert not err and '"password_ok": false' in t


def test_profile_keywords_and_unknown(srv):
    assert not _call(srv, "update_profile", my_channel="https://www.youtube.com/@a", role_models=["https://www.youtube.com/@b"])[0]
    assert R.load_settings()["role_models"] == ["https://www.youtube.com/@b"]
    _call(srv, "change_keywords", add=["김치"], remove=["맛있"])
    s = R.load_settings()
    assert s["kw_added"] == ["김치"] and "맛있" in s["kw_removed"]
    assert _call(srv, "no_such_tool")[0]


def test_video_lines_and_folder(srv, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    shoot = tmp_path / "Desktop" / "촬영"
    work = shoot / "콘봇_완성" / "작업"
    work.mkdir(parents=True)
    (work / "edit.json").write_text(json.dumps({"source": "x", "style": "유잡스 기본", "total": 100.0,
                                                 "intervals": [[0, 10], [20, 30]],
                                                 "items": [{"s": 1, "e": 3, "t": "안녕하세요"},
                                                           {"s": 21, "e": 24, "t": "수익화 방법", "chapter": "수익화"}]}),
                                     encoding="utf-8")
    err, t = _call(srv, "find_folders", name="촬영")
    assert not err and "촬영" in t
    err, t = _call(srv, "get_video_lines", folder="바탕화면/촬영")
    assert not err, t
    d = json.loads(t)
    assert [x["no"] for x in d["lines"]] == [1, 2] and d["lines"][1]["chapter"] == "수익화"
    assert mcp_server.chapter_times(str(shoot / "콘봇_완성")) == [{"time": "00:00", "chapter": "인트로"},
                                                                {"time": "00:11", "chapter": "수익화"}]


def test_claude_config_register_keeps_others(tmp_path, monkeypatch):
    f = tmp_path / "Claude" / "claude_desktop_config.json"
    f.parent.mkdir()
    f.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}), encoding="utf-8")
    monkeypatch.setattr(claude_link, "config_paths", lambda: [f])
    r = claude_link.register("/Apps/CornBot")
    assert r["ok"] and r["changed"]
    d = json.loads(f.read_text(encoding="utf-8"))
    assert d["mcpServers"]["other"] == {"command": "x"} and d["theme"] == "dark"
    assert d["mcpServers"]["cornbot"] == {"command": "/Apps/CornBot", "args": ["--mcp"]}
    assert (f.parent / "claude_desktop_config.json.cornbot-bak").exists()
    assert claude_link.status("/Apps/CornBot")["linked"]
    assert not claude_link.register("/Apps/CornBot")["changed"]
    f.write_text("{broken", encoding="utf-8")
    r = claude_link.register("/Apps/CornBot")
    assert not r["ok"] and "깨져" in r["error"] and f.read_text(encoding="utf-8") == "{broken"
