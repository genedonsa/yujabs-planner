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

if __name__ == "__main__" and "--mcp" in sys.argv:  # Claude 앱이 도구로 부를 때: 창 없이 대화 통로만 연다
    from planner.mcp_server import serve
    serve()
    sys.exit(0)

import webview

from planner import access, collect
from planner import engine as E
from planner import run as R
from planner import updater as U
from planner.version import VERSION

APP_NAME = "콘봇"
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
UI = BASE / "ui" / "index.html"


def _data_uri(path: Path) -> str:
    try:
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
    except OSError:
        return ""


class Api:
    def __init__(self):
        self.progress = {"running": False, "step": None, "log": [], "error": None, "result": None}
        self.window = None
        self.vprog = {"running": False, "step": None, "log": [], "error": None, "result": None}

    # ---- 시작 / 설정 ----
    def get_state(self) -> dict:
        s = R.load_settings()
        try:
            ok, access_error = access.check_saved(s), ""
        except access.AccessError as e:
            ok, access_error = False, str(e)
        last = None
        f = E.HOME / "last_result.json"
        if f.exists():
            try:
                last = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                last = None
        safe = {k: v for k, v in s.items() if k not in ("password", "password_fp")}
        return {"code_ok": ok, "access_error": access_error, "had_password": bool(s.get("password_fp") or s.get("password")),
                "settings": safe, "criteria": dict(E.DEFAULT_CRITERIA),
                "last": last, "version": VERSION, "home": str(E.HOME), "month": f"{datetime.now().year}년 {datetime.now().month}월"}

    def check_code(self, password: str) -> dict:
        try:
            ok = access.check(password)
        except access.AccessError as e:
            return {"ok": False, "error": str(e)}
        if ok:
            s = R.load_settings()
            s["password_fp"] = access.fingerprint(password)
            s.pop("password", None)
            R.save_settings(s)
        return {"ok": ok, "error": "" if ok else "암호가 맞지 않아요. 이번 달 암호인지 확인해 주세요."}

    def save_settings(self, data: dict) -> bool:
        s = R.load_settings()
        s.update({k: v for k, v in data.items() if k not in ("password", "password_fp")})
        R.save_settings(s)
        return True

    # ---- 키워드·구독 리스트·포맷 ----
    def set_keywords(self, kws: list, auto: list) -> bool:
        s = R.load_settings()
        import unicodedata
        kws = list(dict.fromkeys(unicodedata.normalize("NFC", k).strip() for k in kws if k.strip()))
        s["kw_removed"] = sorted(set(s.get("kw_removed", [])) | {a for a in auto if a not in kws})
        s["kw_removed"] = [k for k in s["kw_removed"] if k not in kws]
        s["kw_added"] = [k for k in kws if k not in auto]
        R.save_settings(s)
        return True

    def toggle_sub(self, cid: str, name: str, on: bool) -> dict:
        s = R.load_settings()
        subs = s.get("subs") if isinstance(s.get("subs"), dict) else {}
        removed = set(s.get("subs_removed", []))
        if on:
            subs[cid] = {"name": name}
            removed.discard(cid)
        else:
            subs.pop(cid, None)
            removed.add(cid)
        s["subs"], s["subs_removed"] = subs, sorted(removed)
        R.save_settings(s)
        return subs

    def add_sub_url(self, url: str) -> dict:
        try:
            ch, vids = collect.channel_videos(url, 40)
        except Exception as e:
            return {"ok": False, "error": "채널을 찾지 못했어요. 유튜브에서 채널을 열고 주소창의 주소(https://www.youtube.com/@…)를 그대로 붙여 넣어 주세요." if "does not exist" in str(e) or "Unsupported URL" in str(e) or "is not a valid URL" in str(e) else f"채널을 읽지 못했어요. 잠시 뒤 다시 해 주세요. ({E._friendly(e)})"}
        ch["avg"] = int(E.baseline(vids, datetime.now().date(), 7))
        ch["video_count"] = len(vids)
        ch["keywords"] = ["직접 추가"]
        ch["subscribed"] = True
        self.toggle_sub(ch["id"], ch["name"], True)
        return {"ok": True, "channel": ch}

    # ---- 분석 ----
    def start(self) -> bool:
        if self.progress["running"]:
            return False
        s = R.load_settings()
        self.progress = {"running": True, "step": "me", "log": [], "error": None, "result": None}

        def work():
            try:
                res = E.analyze(s, log=self.progress["log"].append,
                                step=lambda k: self.progress.__setitem__("step", k))
                st = R.load_settings()
                st["subs"] = res["subs"]
                R.save_settings(st)
                self.progress["result"] = res
            except Exception as e:  # 회원이 알아들을 말로 바꿔 화면에 보여 준다
                self.progress["error"] = E._friendly(e)
            finally:
                self.progress["running"] = False
        threading.Thread(target=work, daemon=True).start()
        return True

    def get_progress(self) -> dict:
        p = dict(self.progress)
        p["log"] = p["log"][-6:]
        return p

    # ---- 기획하기 ----
    def make_material(self, video: dict, story: str) -> dict:
        try:
            text, folder = E.plan_material(video, story, R.load_settings())
        except Exception as e:
            return {"ok": False, "error": f"영상 정보를 가져오지 못했어요. ({str(e)[:80]})"}
        self.copy_text(text)
        return {"ok": True, "folder": str(folder), "chars": len(text), "partial": "유튜브가 이번엔 영상 페이지를" in text}

    def save_plan(self, folder: str, md: str) -> bool:
        Path(folder).mkdir(parents=True, exist_ok=True)
        (Path(folder) / "기획안.md").write_text(md, encoding="utf-8")
        return True

    def list_plans(self) -> list:
        root = E.HOME / "기획"
        out = []
        if root.exists():
            for d in sorted(root.iterdir(), reverse=True):
                v, p = d / "video.json", d / "기획안.md"
                if v.exists():
                    try:
                        vid = json.loads(v.read_text(encoding="utf-8"))
                    except ValueError:
                        continue
                    out.append({"folder": str(d), "video": vid,
                                "plan": p.read_text(encoding="utf-8") if p.exists() else ""})
        return out[:30]

    def copy_text(self, text: str) -> bool:
        try:
            if sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
            elif os.name == "nt":
                subprocess.run(["clip"], input=text.encode("utf-16le"), check=True, creationflags=0x08000000)
            return True
        except Exception:
            return False

    # ---- Claude 앱 연결 (MCP) ----
    def claude_link_status(self) -> dict:
        from planner import claude_link
        try:
            st = claude_link.status() if getattr(sys, "frozen", False) else {"linked": False, "dev": True}
        except Exception as e:
            st = {"linked": False, "error": str(e)[:120]}
        st["auto"] = getattr(self, "link_result", None)
        return st

    def claude_link(self) -> dict:
        from planner import claude_link
        if not getattr(sys, "frozen", False):
            return {"ok": False, "error": "개발용 실행에서는 연결하지 않아요."}
        return claude_link.register()

    # ---- 학원월드 주간 급상승 영상 (모든 회원 공통, 운영자가 시트에 올림) ----
    def weekly_list(self) -> dict:
        from planner import weekly
        import time
        c = getattr(self, "_weekly_cache", None)
        if c and time.time() - c[0] < 600:
            return c[1]
        d = weekly.fetch_feed(E.HOME)
        self._weekly_cache = (time.time(), d)
        return d

    def reset(self, everything: bool = False) -> dict:
        """설정 → 처음 상태로. 기본은 암호·채널·구독 리스트만, everything이면 '유잡스 기획' 폴더 전체를 휴지통으로."""
        if self.progress.get("running") or self.vprog.get("running"):
            return {"ok": False, "error": "분석이나 영상 만들기가 끝난 뒤에 해 주세요."}
        try:
            return R.reset(bool(everything))
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"지우지 못했어요 ({e}). 콘봇을 껐다 켠 뒤 다시 해 주세요."}

    def open_claude(self) -> None:
        webbrowser.open("https://claude.ai/new")

    # ---- 영상 만들기 ----
    def pick_folder(self) -> str:
        try:
            win = webview.windows[0]
            res = win.create_file_dialog(webview.FOLDER_DIALOG)
        except Exception:
            return ""
        return res[0] if res else ""

    def video_styles(self) -> list:
        from planner import video as V
        return list(V.STYLES)

    def start_video(self, folder: str, style: str) -> dict:
        if self.vprog.get("running"):
            return {"ok": False, "error": "이미 영상을 만들고 있어요."}
        if not folder or not Path(folder).is_dir():
            return {"ok": False, "error": "촬영한 영상이 들어 있는 폴더를 먼저 골라 주세요."}
        self.vprog = {"running": True, "step": "join", "log": [], "error": None, "result": None}

        def work():
            try:
                from planner import video as V
                self.vprog["result"] = V.make(folder, style, log=self.vprog["log"].append,
                                              step=lambda k: self.vprog.__setitem__("step", k))
            except Exception as e:
                self.vprog["error"] = str(e)[:300]
            finally:
                self.vprog["running"] = False
        threading.Thread(target=work, daemon=True).start()
        return {"ok": True}

    def video_edit_load(self, folder: str) -> dict:
        from planner import video as V
        try:
            return {"ok": True, **V.load_edit(folder)}
        except Exception as e:
            return {"ok": False, "error": f"편집 정보를 찾지 못했어요. ({str(e)[:80]})"}

    def video_rerender(self, folder: str, items: list) -> dict:
        if self.vprog.get("running"):
            return {"ok": False, "error": "이미 영상을 만들고 있어요."}
        self.vprog = {"running": True, "step": "render", "log": [], "error": None, "result": None}

        def work():
            try:
                from planner import video as V
                self.vprog["result"] = V.rerender(folder, items, log=self.vprog["log"].append)
                self.vprog["step"] = "done"
            except Exception as e:
                self.vprog["error"] = str(e)[:300]
            finally:
                self.vprog["running"] = False
        threading.Thread(target=work, daemon=True).start()
        return {"ok": True}

    def video_progress(self) -> dict:
        p = dict(self.vprog)
        p["log"] = p["log"][-4:]
        return p

    # ---- 업데이트 ----
    def check_update(self) -> dict:
        try:
            return U.check()
        except Exception as e:
            return {"available": False, "error": str(e)[:120], "current": VERSION}

    def do_update(self) -> dict:
        try:
            U.apply()
        except Exception as e:
            return {"ok": False, "error": f"업데이트를 받지 못했어요. 인터넷 연결을 확인해 주세요. ({str(e)[:80]})"}
        threading.Timer(0.6, lambda: os._exit(0)).start()
        return {"ok": True}

    # ---- 열기 ----
    def open_folder(self, folder: str) -> None:
        Path(folder).mkdir(parents=True, exist_ok=True)
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
    rep = {"version": VERSION, "platform": platform.platform(), "python": sys.version.split()[0], "base": str(BASE),
           "ui_exists": UI.exists(), "openssl": ssl.OPENSSL_VERSION}
    try:
        import certifi
        rep["certifi"] = certifi.where()
        rep["certifi_exists"] = Path(certifi.where()).exists()
    except Exception as e:
        rep["certifi"] = f"ERR {e}"
    try:
        rep["fingerprints"] = len(access.current_fingerprints())
        rep["sheet_ok"] = rep["fingerprints"] > 0  # 암호 원문은 코드에 두지 않는다(공개 저장소)
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
    try:  # 영상 만들기 도구가 앱 안에 들어 있는지
        from planner import video as V
        ff = V.ffmpeg()
        rep["ffmpeg"] = subprocess.run([ff, "-version"], capture_output=True, text=True, timeout=30).stdout.split("\n")[0]
        import faster_whisper
        import ctranslate2
        rep["whisper"] = f"{faster_whisper.__version__} / ct2 {ctranslate2.__version__}"
    except Exception as e:
        rep["video_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    try:  # Claude 앱이 부르는 도구 통로(--mcp)가 이 앱에서 실제로 열리는지
        from planner import mcp_server
        cmd = [sys.executable, "--mcp"] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve()), "--mcp"]
        rep["mcp"] = mcp_server.probe(cmd)
        from planner import claude_link
        rep["claude_config"] = claude_link.config_paths()[0].as_posix() if claude_link.config_paths() else ""
    except Exception as e:
        rep["mcp"] = f"ERR {type(e).__name__}: {str(e)[:200]}"
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
    from planner import claude_link
    api.link_result = claude_link.auto()
    win = webview.create_window(APP_NAME, str(UI), js_api=api, width=1100, height=780, min_size=(900, 640))
    import atexit
    win.events.shown += lambda *a: R.mark_window(True)  # Claude의 '콘봇 창 열기'가 창이 떴는지 확인하는 표시
    win.events.closed += lambda *a: R.mark_window(False)
    atexit.register(R.mark_window, False)
    webview.start()


if __name__ == "__main__":
    main()
