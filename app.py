"""로컬 화면. 127.0.0.1에서만 열리는 작은 웹 페이지를 띄우고 브라우저로 연다.

v1은 표준 라이브러리만 쓴다(설치 파일 크기를 줄이려고). 화면 디자인은 Claude Code에서 다듬는다.
"""
from __future__ import annotations

import html
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from planner import run as R

PORT = 8765
STATE = {"log": [], "result": None, "error": None, "busy": False}


def page(body: str) -> bytes:
    return f"""<!doctype html><meta charset="utf-8"><title>유잡스 주간 기획</title>
<style>body{{font-family:system-ui,-apple-system,'Noto Sans KR',sans-serif;max-width:760px;margin:32px auto;padding:0 16px;line-height:1.6}}
label{{display:block;font-weight:600;margin-top:14px}}input,textarea{{width:100%;padding:8px;font-size:15px}}
button{{margin-top:18px;padding:10px 18px;font-size:16px;background:#2a5bd7;color:#fff;border:0;border-radius:8px}}
pre{{background:#f3f4f7;padding:12px;white-space:pre-wrap}}small{{color:#667}}</style>{body}""".encode()


def form() -> str:
    s = R.load_settings()
    v = lambda k, d="": html.escape(s.get(k, d) if isinstance(s.get(k, d), str) else "\n".join(s.get(k, [])))
    return f"""<h1>유잡스 주간 기획</h1>
<form method="post" action="/run">
<label>이번 달 실행 코드 <small>커뮤니티 회원 게시판에서 확인</small></label><input name="code" value="{v('code')}">
<label>내 채널 주소</label><input name="my_channel" value="{v('my_channel')}" placeholder="https://www.youtube.com/@내채널">
<label>롤모델 채널 주소 <small>한 줄에 하나</small></label><textarea name="role_models" rows="4">{v('role_models')}</textarea>
<label>내 시청자와 내가 팔 상품 (한 줄)</label><input name="audience" value="{v('audience')}">
<label>추가 키워드 (선택, 한 줄에 하나)</label><textarea name="extra_keywords" rows="2">{v('extra_keywords')}</textarea>
<label>내 썸네일 템플릿 PNG 경로 (선택)</label><input name="template" value="{v('template')}">
<button>이번 주 레퍼런스 찾기</button></form>"""


def status() -> str:
    log = html.escape("\n".join(STATE["log"][-30:]))
    if STATE["busy"]:
        return f'<meta http-equiv="refresh" content="3"><h2>찾는 중…</h2><pre>{log}</pre>'
    if STATE["error"]:
        return f'<h2>멈췄어요</h2><p>{html.escape(STATE["error"])}</p><pre>{log}</pre><p><a href="/">처음으로</a></p>'
    r = STATE["result"]
    refs = "".join(f"<li>{html.escape(t)}</li>" for t in r["refs"])
    return f"""<h2>준비됐어요</h2><ol>{refs}</ol>
<p>폴더: <code>{html.escape(r['folder'])}</code></p>
<p><b>다음 단계</b>: Claude 앱을 열고 폴더 안의 두 파일(<code>이번주_기획자료_….md</code>, <code>기획안_요청문.md</code>)을 넣은 뒤 "기획안 만들어 줘"라고 하세요.</p>
<form method="post" action="/thumbs"><label>썸네일 시안 만들기 <small>Claude가 준 문구를 편마다 한 줄씩: 줄1 / 줄2</small></label>
<textarea name="lines" rows="4"></textarea><button>썸네일 시안 만들기</button></form>"""


class H(BaseHTTPRequestHandler):
    def _send(self, body: str, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page(body))

    def do_GET(self):
        self._send(status() if (STATE["busy"] or STATE["result"] or STATE["error"]) and self.path == "/status" else form())

    def do_POST(self):
        data = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
        get = lambda k: (data.get(k) or [""])[0].strip()
        lines = lambda k: [l.strip() for l in get(k).splitlines() if l.strip()]
        if self.path == "/run":
            s = R.load_settings()
            s.update({"code": get("code"), "my_channel": get("my_channel"), "role_models": lines("role_models"),
                      "audience": get("audience"), "extra_keywords": lines("extra_keywords"), "template": get("template")})
            R.save_settings(s)
            STATE.update(log=[], result=None, error=None, busy=True)

            def work():
                try:
                    STATE["result"] = R.run(s, log=STATE["log"].append)
                except Exception as e:
                    STATE["error"] = str(e)
                finally:
                    STATE["busy"] = False
            threading.Thread(target=work, daemon=True).start()
        elif self.path == "/thumbs" and STATE["result"]:
            try:
                made = R.make_thumbnails(Path(STATE["result"]["folder"]), get("lines"), R.load_settings())
                STATE["log"].append(f"썸네일 시안 {len(made)}장을 만들었어요: {made[0].parent if made else ''}")
            except Exception as e:
                STATE["log"].append(f"썸네일 시안 실패: {e}")
        self.send_response(303)
        self.send_header("Location", "/status")
        self.end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    webbrowser.open(f"http://127.0.0.1:{PORT}/")
    print(f"열림: http://127.0.0.1:{PORT}/  (창을 닫으려면 Ctrl+C)")
    srv.serve_forever()
