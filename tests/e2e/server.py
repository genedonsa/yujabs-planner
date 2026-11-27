"""실사용 점검용 서버: 실제 콘봇 화면(ui/)과 실제 Api(실제 유튜브)를 브라우저로 연결한다.
암호 확인만 건너뛴다(암호 자체는 selftest에서 따로 점검). 앱에는 들어가지 않는 파일."""
import json, sys, types
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.modules["webview"] = types.SimpleNamespace(windows=[], OPEN_DIALOG=0)
from planner import access, net  # noqa: E402
net.use_system_certificates()
access.check = lambda pw, expected=None: True
access.check_saved = lambda s: True
import desktop  # noqa: E402
API = desktop.Api()
API.copy_text = lambda text: (Path("e2e_out") / "copied.md").write_text(text, encoding="utf-8") or True
API.open_url = lambda url: None
API.open_claude = lambda: None
API.open_folder = lambda f: None
import os  # noqa: E402
API.pick_folder = lambda: os.environ.get("CLIP_DIR", "")


def _sample_ids():  # 점검용 주간 게시글을 만들 실제 영상 주소 (분석 결과 → 내 채널 인기 영상 순)
    from planner import engine as E
    out = []
    try:
        out += [r["url"] for r in json.loads((E.HOME / "last_result.json").read_text(encoding="utf-8"))["refs"][:3]]
    except Exception:
        pass
    try:
        out += [f"https://youtu.be/{t['id']}" for t in json.loads((E.HOME / "me.json").read_text(encoding="utf-8"))["top"][:3]]
    except Exception:
        pass
    return out[:3]


API.sample_ids = _sample_ids

class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(REPO / "ui"), **k)
    def log_message(self, *a):
        pass
    def do_POST(self):
        name = self.path.rsplit("/", 1)[-1]
        args = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"[]")
        try:
            body = json.dumps({"ok": True, "res": getattr(API, name)(*args)}, ensure_ascii=False, default=str)
        except Exception as e:
            body = json.dumps({"ok": False, "err": f"{type(e).__name__}: {e}"}, ensure_ascii=False)
        self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.end_headers()
        self.wfile.write(body.encode("utf-8"))

if __name__ == "__main__":
    Path("e2e_out").mkdir(exist_ok=True)
    from planner import engine as E, collect
    _orig = E.analyze
    def _logged(s, log, step):  # 분석 진행 기록을 파일로도 남긴다
        f = open("e2e_out/analyze.log", "a", encoding="utf-8")
        def l(m):
            log(m); f.write(m + "\n"); f.flush()
        try:
            return _orig(s, l, step)
        except Exception as e:
            l(f"분석 오류: {type(e).__name__}: {e}"); raise
    E.analyze = _logged
    with open("e2e_out/probe.txt", "w", encoding="utf-8") as f:  # 검색이 되는지 바로 확인
        for q in ["유튜브 수익화", "youtube growth"]:
            try:
                r = collect.search(q, 8)
                f.write(f"{q}: {len(r)}개\n" + "".join(f"  {v.channel_id} {v.channel_name} {v.duration} {v.is_short} {v.upload_date} {v.title[:40]}\n" for v in r))
            except Exception as e:
                f.write(f"{q}: 실패 {type(e).__name__}: {str(e)[:300]}\n")
    ThreadingHTTPServer(("127.0.0.1", 8765), H).serve_forever()
