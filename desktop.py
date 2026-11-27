"""데스크톱 앱 진입점. pywebview로 창을 띄우고 ui/index.html을 보여 준다.

화면(JS)은 window.pywebview.api.<함수> 로 아래 Api 메서드를 부른다.
PyInstaller로 묶으면 아이콘 더블클릭으로 이 창이 열린다.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

import webview

from planner import access
from planner import run as R

APP_NAME = "콘봇"
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
UI = BASE / "ui" / "index.html"
STEPS = ["me", "models", "search", "pick", "detail", "bundle", "done"]


def _data_uri(path: Path) -> str:
    try:
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
    except OSError:
        return ""


class Api:
    def __init__(self):
        self.progress = {"running": False, "step": None, "log": [], "error": None, "result": None}

    # ---- 시작 / 설정 ----
    def get_state(self) -> dict:
        s = R.load_settings()
        try:
            ok, access_error = access.check(s.get("password", "")), ""
        except access.AccessError as e:
            ok, access_error = False, str(e)
        return {
            "code_ok": ok,
            "access_error": access_error,
            "had_password": bool(s.get("password")),
            "settings": {k: s.get(k) for k in ("my_channel", "role_models", "audience", "notes", "extra_keywords",
                                                 "template", "text_position", "color1", "color2")},
            "template_preview": _data_uri(Path(s["template"])) if s.get("template") else "",
            "history": self.history(),
            "month": f"{datetime.now().year}년 {datetime.now().month}월",
        }

    def check_code(self, password: str) -> dict:
        try:
            ok = access.check(password)
        except access.AccessError as e:
            return {"ok": False, "error": str(e)}
        if ok:
            s = R.load_settings()
            s["password"] = password.strip()
            R.save_settings(s)
        return {"ok": ok, "error": "" if ok else "암호가 맞지 않아요. 이번 달 암호인지 확인해 주세요."}

    def save_settings(self, data: dict) -> bool:
        s = R.load_settings()
        s.update({k: v for k, v in data.items() if k != "password"})
        R.save_settings(s)
        return True

    def pick_template(self) -> dict:
        win = webview.windows[0]
        res = win.create_file_dialog(webview.OPEN_DIALOG, file_types=("이미지 (*.png;*.jpg;*.jpeg)",))
        if not res:
            return {}
        path = Path(res[0])
        return {"path": str(path), "preview": _data_uri(path)}

    # ---- 실행 ----
    def start(self) -> bool:
        if self.progress["running"]:
            return False
        s = R.load_settings()
        self.progress = {"running": True, "step": "me", "log": [], "error": None, "result": None}

        def work():
            try:
                res = R.run(s, log=self.progress["log"].append,
                            step=lambda k: self.progress.__setitem__("step", k))
                self.progress["result"] = self.load_result(res["folder"])
            except Exception as e:  # 화면에 그대로 보여 준다
                self.progress["error"] = str(e)
            finally:
                self.progress["running"] = False
        threading.Thread(target=work, daemon=True).start()
        return True

    def get_progress(self) -> dict:
        p = dict(self.progress)
        p["log"] = p["log"][-8:]
        return p

    # ---- 결과 ----
    def load_result(self, folder: str) -> dict:
        f = Path(folder)
        refs = json.loads((f / "refs.json").read_text(encoding="utf-8"))
        for r in refs:
            r["thumb"] = _data_uri(f / "원본썸네일" / f"{r['id']}.jpg")
            mine = f / "썸네일시안" / f"{r['id']}.jpg"
            r["mine"] = _data_uri(mine) if mine.exists() else ""
        lines_file = f / "썸네일문구.txt"
        return {"folder": str(f), "date": f.name, "refs": refs,
                "lines": lines_file.read_text(encoding="utf-8") if lines_file.exists() else ""}

    def history(self) -> list[dict]:
        if not R.HOME.exists():
            return []
        out = []
        for d in sorted(R.HOME.iterdir(), reverse=True):
            if d.is_dir() and (d / "refs.json").exists():
                n = len(json.loads((d / "refs.json").read_text(encoding="utf-8")))
                out.append({"folder": str(d), "date": d.name, "count": n})
        return out[:12]

    def make_thumbs(self, folder: str, lines: str) -> dict:
        f = Path(folder)
        (f / "썸네일문구.txt").write_text(lines, encoding="utf-8")
        R.make_thumbnails(f, lines, R.load_settings())
        return self.load_result(folder)

    # ---- 열기 ----
    def open_folder(self, folder: str) -> None:
        if sys.platform == "darwin":
            subprocess.run(["open", folder])
        elif os.name == "nt":
            os.startfile(folder)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", folder])

    def open_url(self, url: str) -> None:
        webbrowser.open(url)


WEBVIEW2_ID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def _has_webview2() -> bool:
    import winreg  # type: ignore
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_ID}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_ID}"),
        (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_ID}"),
    ]
    for root, key in keys:
        try:
            with winreg.OpenKey(root, key) as k:
                v, _ = winreg.QueryValueEx(k, "pv")
                if v and v != "0.0.0.0":
                    return True
        except OSError:
            pass
    return False


def ensure_webview2() -> None:
    """윈도우: 화면을 그리는 WebView2가 없으면 앱에 든 설치기로 조용히 깔아 둔다(회원이 따로 할 일 없음)."""
    if os.name != "nt":
        return
    try:
        if _has_webview2():
            return
        setup = BASE / "bin" / "MicrosoftEdgeWebview2Setup.exe"
        if setup.exists():
            subprocess.run([str(setup), "/silent", "/install"], timeout=600)
    except Exception:
        pass


def selftest(out: str) -> None:
    """빌드 서버에서 실제 앱으로 돌려 보는 점검. 결과를 파일로 남긴다."""
    import platform
    import ssl
    rep = {"platform": platform.platform(), "python": sys.version.split()[0], "base": str(BASE),
           "ui_exists": UI.exists(), "openssl": ssl.OPENSSL_VERSION}
    try:
        import certifi
        rep["certifi"] = certifi.where()
        rep["certifi_exists"] = Path(certifi.where()).exists()
    except Exception as e:
        rep["certifi"] = f"ERR {e}"
    try:
        rep["fingerprints"] = len(access.current_fingerprints())
        rep["password_유잡스02"] = access.check("유잡스02")
        rep["password_dbwkqtm02"] = access.check("dbwkqtm02")
    except Exception as e:
        rep["access_error"] = f"{type(e).__name__}: {e}"
    try:
        from planner import net
        rep["deno"] = net.bundled_deno()
        if rep["deno"]:
            rep["deno_version"] = subprocess.run([rep["deno"], "--version"], capture_output=True, text=True,
                                                 timeout=30).stdout.splitlines()[0]
        import yt_dlp
        rep["yt_dlp"] = yt_dlp.version.__version__
    except Exception as e:
        rep["tools_error"] = f"{type(e).__name__}: {e}"
    try:
        import truststore  # noqa: F401
        rep["system_certificates"] = True
    except Exception as e:
        rep["system_certificates"] = f"ERR {e}"
    try:  # 유튜브 채널 목록 읽기(실제 수집 경로). 서버 컴퓨터는 유튜브가 막을 수 있어 참고용.
        from planner import collect
        ch, vids = collect.channel_videos("https://www.youtube.com/@유튜브-잡스", 5)
        rep["youtube_channel"] = f"ok {ch.get('name')} {len(vids)}편, 첫 영상 업로드일 {vids[0].upload_date if vids else None}"
    except Exception as e:
        rep["youtube_channel"] = f"ERR {type(e).__name__}: {str(e)[:200]}"
    Path(out).write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    from planner import net
    net.use_system_certificates()
    for a in sys.argv[1:]:
        if a.startswith("--selftest="):
            selftest(a.split("=", 1)[1])
            return
    ensure_webview2()
    api = Api()
    webview.create_window(APP_NAME, str(UI), js_api=api, width=1100, height=780, min_size=(900, 640))
    webview.start()


if __name__ == "__main__":
    main()
