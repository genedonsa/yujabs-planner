"""콘봇 MCP 서버: 회원의 Claude 데스크톱 앱이 회원 컴퓨터의 콘봇을 '도구'로 쓰게 한다.

Claude 앱이 `CornBot --mcp`를 실행하고, 표준입출력으로 JSON-RPC(한 줄에 메시지 하나)를 주고받는다.
기획안·대본은 회원 본인의 Claude가 쓰고, 콘봇은 유튜브 수집·자료 만들기·저장·영상 편집을 맡는다.
외부 패키지 없이 표준 라이브러리만 쓴다.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]

INSTRUCTIONS = """콘봇은 유잡스 커뮤니티 회원의 컴퓨터에 깔린 유튜브 기획·편집 도우미예요. 회원은 왕초보이니 쉬운 말로, 짧게 안내하세요.

기획 흐름
1. 처음이거나 잘 모르겠으면 cornbot_status로 상태를 보세요. 암호가 안 맞으면 open_cornbot_window로 콘봇 창을 열고 '이번 달 암호를 콘봇 창에 넣어 주세요'라고 안내하세요. 암호를 대화창에 받지 마세요.
2. 학원월드 '주간 급상승 영상'(대표가 매주 고른 영상, 모든 회원 공통)으로 기획할 때: list_weekly_videos로 목록(W1, W2…)과 대표의 분석을 보여 주고 고르게 하세요. 회원이 게시글을 복사할 필요는 없어요.
3. 내 분야에서 최근 터진 영상을 찾을 때: list_references. 결과가 없거나 오래됐으면 start_analysis → analysis_status(몇 분 걸려요).
4. 영상을 고르면 회원에게 그 영상 주제에 대한 '내 이야기(경험·숫자·실패담)'를 한두 줄 물어보세요. 그다음 get_planning_material(video, my_story)를 부르고, 돌려받은 자료 맨 앞의 '기획안 작성 지시문'을 그대로 따라 기획안과 대본을 쓰세요. 주간 게시글 분석이 들어 있으면 그 분석을 기획의 출발점으로 삼으세요.
5. 다 쓰면 반드시 save_plan으로 저장하세요(콘봇 '내 기획안'에 보여요). 대화에는 기획안 요약과 훅 대본 정도만 보여 주세요.

영상 편집 흐름 (유잡스 편집 스타일)
1. 회원이 '바탕화면 촬영 폴더'처럼 말하면 find_folders로 실제 폴더를 찾아 확인하세요.
2. make_video(folder) → video_status를 30초쯤 간격으로 확인(촬영 길이에 따라 수 분~수십 분). 무음·'어·음' 추임새·'다시' NG 구간은 콘봇이 자동으로 뺍니다.
3. 끝나면 get_video_lines로 자막 줄을 읽고 다음을 한 번에 edit_video로 반영하세요.
   - 받아쓰기 오타 고치기(fix): 채널 고유명사·전문용어 위주. 말투는 바꾸지 마세요.
   - 강조 문구(emphasis): 핵심 숫자·결론 문장에만, 영상 1분당 1개 이하, 12자 이내.
   - 챕터 카드(chapters): 주제가 바뀌는 첫 줄에 2~6개, 8자 안팎의 명사형 이름.
   - 빼기(drop): 같은 말을 반복한 줄, 촬영 준비 말('녹화 되나?' 등)만.
4. 마지막에 자막 내용으로 유튜브 설명란(한 줄 요약, 챕터 시간표 00:00 형식, 관련 링크 자리)을 써 주고, 완성본 폴더 위치를 알려 주세요.
"""


def _o(props: dict, req: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": req or []}


S = {"type": "string"}
NO_REFS = ("분석은 끝났지만 최근 7일 안에 기준(조회 1만·평소의 3배)을 넘은 영상이 아직 없어요. "
           "list_weekly_videos의 급상승 영상(W1…)으로 기획하거나, 며칠 뒤 다시 분석하거나, 롤모델 채널을 더 넣어 보세요.")

TOOLS = [
    {"name": "cornbot_status", "description": "콘봇 상태: 버전, 이번 달 암호 확인 여부, 내 채널·롤모델 설정, 마지막 분석 날짜, 레퍼런스·주간 게시글·기획안 개수.",
     "inputSchema": _o({})},
    {"name": "open_cornbot_window", "description": "회원 화면에 콘봇 창을 연다. 암호 입력이나 화면 확인이 필요할 때.", "inputSchema": _o({})},
    {"name": "update_profile", "description": "내 채널·롤모델 채널·내 시청자와 상품 설정을 바꾼다. 주소는 https://www.youtube.com/@… 형식.",
     "inputSchema": _o({"my_channel": S, "role_models": {"type": "array", "items": S}, "audience": S})},
    {"name": "start_analysis", "description": "내 채널·롤모델 기준으로 같은 분야에서 최근 터진 영상(레퍼런스)과 벤치마킹 채널을 새로 찾기 시작한다. 몇 분 걸린다.",
     "inputSchema": _o({})},
    {"name": "analysis_status", "description": "start_analysis 진행 상황. 끝나면 레퍼런스 개수를 알려 준다.", "inputSchema": _o({})},
    {"name": "list_references", "description": "마지막 분석의 레퍼런스 영상 목록(R1, R2…). 평소 대비 배수가 높은 순.",
     "inputSchema": _o({"format": {"type": "string", "description": "포맷 이름으로 거르기(선택)"}, "limit": {"type": "integer"}})},
    {"name": "list_benchmark_channels", "description": "분석에서 찾은 벤치마킹 채널과 검색 키워드.", "inputSchema": _o({})},
    {"name": "change_keywords", "description": "레퍼런스 검색 키워드를 더하거나 뺀다. 다음 분석부터 적용.",
     "inputSchema": _o({"add": {"type": "array", "items": S}, "remove": {"type": "array", "items": S}})},
    {"name": "add_benchmark_channel", "description": "벤치마킹 채널을 직접 추가한다(채널 주소).", "inputSchema": _o({"url": S}, ["url"])},
    {"name": "list_weekly_videos", "description": "이번 주 학원월드 '급상승 영상' 목록(W1, W2…)과 대표가 쓴 분석. 모든 회원에게 같은 목록.", "inputSchema": _o({})},
    {"name": "get_planning_material", "description": "영상 1편의 기획 자료(기획안 작성 지시문 + 내 채널·경험 + 원본 자막·댓글 + 게시글 분석). video는 'R3', 'W2' 또는 유튜브 주소.",
     "inputSchema": _o({"video": S, "my_story": {"type": "string", "description": "이 주제에 대한 회원 본인의 이야기"}}, ["video"])},
    {"name": "save_plan", "description": "완성한 기획안·대본(마크다운)을 콘봇 '내 기획안'에 저장한다.",
     "inputSchema": _o({"video": S, "plan_markdown": S}, ["video", "plan_markdown"])},
    {"name": "list_plans", "description": "저장된 기획안 목록(최근 순).", "inputSchema": _o({"read": {"type": "integer", "description": "이 번호의 기획안 전문을 함께 돌려줌(1부터)"}})},
    {"name": "find_folders", "description": "회원 컴퓨터에서 이름으로 폴더를 찾는다(바탕화면·다운로드·문서·동영상·영상편집 등). 예: '촬영'.",
     "inputSchema": _o({"name": S}, ["name"])},
    {"name": "make_video", "description": "촬영본 폴더의 영상(mp4·mov)을 이어 붙여 받아쓰기 → 무음·추임새·NG 컷 → 자막·음량 맞춘 최종본을 만들기 시작한다. 결과는 그 폴더 안 '콘봇_완성'.",
     "inputSchema": _o({"folder": S, "style": {"type": "string", "description": "'유잡스 기본'(기본) 또는 '깔끔 자막'"}}, ["folder"])},
    {"name": "video_status", "description": "make_video / edit_video 진행 상황.", "inputSchema": _o({})},
    {"name": "get_video_lines", "description": "만든 영상의 자막 줄 목록(번호·시간·글·강조·챕터). folder는 촬영 폴더 또는 그 안 '콘봇_완성'.",
     "inputSchema": _o({"folder": S}, ["folder"])},
    {"name": "edit_video", "description": "자막 줄 번호로 한꺼번에 고쳐 다시 만든다(받아쓰기는 다시 안 해서 빠름). drop: 뺄 줄 번호들, fix/emphasis/chapters: {\"줄번호\": \"글\"}.",
     "inputSchema": _o({"folder": S, "drop": {"type": "array", "items": {"type": "integer"}},
                        "fix": {"type": "object", "additionalProperties": S},
                        "emphasis": {"type": "object", "additionalProperties": S},
                        "chapters": {"type": "object", "additionalProperties": S}}, ["folder"])},
]
FREE = {"cornbot_status", "open_cornbot_window", "analysis_status", "video_status", "find_folders"}


class Need(Exception):
    """회원에게 보여 줄 안내 (오류 표시와 함께 돌려준다)."""


class Server:
    def __init__(self):
        self.job = {"running": False, "log": [], "error": None, "done_at": None}
        self.vjob = {"running": False, "log": [], "error": None, "result": None, "folder": None}
        self._ok_at = 0.0

    # ---------- 공통 ----------
    def _settings(self) -> dict:
        from . import run as R
        return R.load_settings()

    def _check(self) -> None:
        if time.time() - self._ok_at < 600:
            return
        from . import access
        try:
            ok = access.check_saved(self._settings())
        except access.AccessError as e:
            raise Need(f"암호 시트를 확인하지 못했어요. 인터넷 연결을 확인해 주세요. ({e})")
        if not ok:
            raise Need("이번 달 콘봇 암호가 아직 확인되지 않았어요. open_cornbot_window로 콘봇 창을 열고, "
                       "회원에게 커뮤니티에서 받은 이번 달 암호를 콘봇 창에 넣어 달라고 안내하세요(대화창에 암호를 받지 마세요).")
        self._ok_at = time.time()

    def _last(self) -> dict:
        from .engine import HOME
        try:
            return json.loads((HOME / "last_result.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _weekly(self) -> dict:
        from . import weekly
        from .engine import HOME
        now = time.time()
        if getattr(self, "_wk", None) and now - self._wk[0] < 600:
            return self._wk[1]
        d = weekly.fetch_feed(HOME)
        self._wk = (now, d)
        return d

    @staticmethod
    def _short(v: dict, code: str) -> dict:
        out = {"code": code, "title": v.get("title"), "channel": v.get("channel"), "views": v.get("views"),
               "ratio_vs_usual": v.get("ratio"), "url": v.get("url") or f"https://www.youtube.com/watch?v={v.get('id')}",
               "uploaded": v.get("upload_date"), "format": v.get("format")}
        return {k: x for k, x in out.items() if x not in (None, "")}

    def _video(self, key: str) -> dict:
        key = (key or "").strip()
        k = key.upper()
        if len(k) >= 2 and k[0] in "RW" and k[1:].isdigit():
            n = int(k[1:]) - 1
            lst = (self._last().get("refs") or []) if k[0] == "R" else (self._weekly().get("items") or [])
            if not 0 <= n < len(lst):
                raise Need(f"{key}번 영상이 목록에 없어요. 먼저 {'list_references' if k[0] == 'R' else 'list_weekly_videos'}로 번호를 확인하세요.")
            return dict(lst[n])
        from . import weekly
        found = weekly.parse(text=key)
        if not found:
            raise Need("영상을 찾지 못했어요. 'R3', 'W2' 같은 번호나 유튜브 영상 주소를 주세요.")
        vid = found[0]["id"]
        for v in (self._weekly().get("items") or []) + (self._last().get("refs") or []):
            if v.get("id") == vid:
                return dict(v)
        return weekly.enrich([found[0]])[0]

    @staticmethod
    def _folder(p: str) -> Path:
        home = Path.home()
        names = {"바탕화면": "Desktop", "바탕 화면": "Desktop", "데스크톱": "Desktop", "다운로드": "Downloads",
                 "문서": "Documents", "동영상": "Movies" if sys.platform == "darwin" else "Videos", "영화": "Movies"}
        raw = (p or "").strip().strip("'\"")
        cands = [Path(os.path.expanduser(raw))]
        parts = [x for x in raw.replace("\\", "/").split("/") if x]
        if parts:
            parts = [names.get(x, x) for x in parts]
            cands += [home.joinpath(*parts), home / "Desktop" / Path(*parts)]
        for c in cands:
            if c.is_dir():
                return c.resolve()
        raise Need(f"'{raw}' 폴더를 찾지 못했어요. find_folders로 폴더 이름을 찾아보세요.")

    # ---------- 도구 ----------
    def t_cornbot_status(self, a):
        from . import access
        from .engine import HOME
        from .version import VERSION
        s = self._settings()
        try:
            ok = access.check_saved(s)
            err = ""
        except access.AccessError as e:
            ok, err = False, str(e)
        last = self._last()
        plans = len([d for d in (HOME / "기획").iterdir() if d.is_dir()]) if (HOME / "기획").exists() else 0
        return {"version": VERSION, "password_ok": ok, "password_problem": err or None,
                "my_channel": s.get("my_channel") or "(아직 없음 — update_profile로 넣기)",
                "role_models": s.get("role_models") or [], "audience": s.get("audience") or "",
                "last_analysis": last.get("date"), "references": len(last.get("refs") or []),
                "weekly_post_date": self._weekly().get("date"), "weekly_videos": len(self._weekly().get("items") or []),
                "saved_plans": plans, "data_folder": str(HOME),
                "analysis_running": self.job["running"], "video_running": self.vjob["running"]}

    def t_open_cornbot_window(self, a):
        exe = Path(sys.executable)
        if not getattr(sys, "frozen", False):
            raise Need("개발용 실행이라 창을 열 수 없어요. 콘봇 앱을 직접 열어 주세요.")
        app = next((p for p in exe.parents if p.suffix == ".app"), None)
        if sys.platform == "darwin" and app:
            subprocess.Popen(["open", str(app)])
        else:
            flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # DETACHED_PROCESS | NEW_PROCESS_GROUP
            subprocess.Popen([str(exe)], creationflags=flags, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return "콘봇 창을 열었어요. 회원에게 창을 확인해 달라고 안내하세요."

    def t_update_profile(self, a):
        from . import run as R
        s = R.load_settings()
        if a.get("my_channel"):
            s["my_channel"] = a["my_channel"].strip()
        if a.get("role_models") is not None:
            s["role_models"] = [x.strip() for x in a["role_models"] if str(x).strip()]
        if a.get("audience") is not None:
            s["audience"] = a["audience"].strip()
        R.save_settings(s)
        return {"saved": True, "my_channel": s.get("my_channel"), "role_models": s.get("role_models")}

    def t_start_analysis(self, a):
        if self.job["running"]:
            return "이미 분석 중이에요. analysis_status로 확인하세요."
        s = self._settings()
        if not s.get("my_channel") and not s.get("role_models"):
            raise Need("내 채널이나 롤모델 채널 주소가 없어요. update_profile로 먼저 넣으세요.")
        self.job = {"running": True, "log": [], "error": None, "done_at": None}

        def work():
            from . import engine as E
            from . import run as R
            try:
                res = E.analyze(s, log=self.job["log"].append)
                st = R.load_settings()
                st["subs"] = res["subs"]
                R.save_settings(st)
            except Exception as e:
                self.job["error"] = E._friendly(e) if hasattr(E, "_friendly") else str(e)
            finally:
                self.job["running"] = False
                self.job["done_at"] = datetime.now().strftime("%H:%M")
        threading.Thread(target=work, daemon=True).start()
        return "분석을 시작했어요. 보통 3~10분 걸려요. 1분쯤 뒤 analysis_status로 확인하세요."

    def t_analysis_status(self, a):
        j = self.job
        if j["running"]:
            return {"running": True, "recent_log": j["log"][-4:]}
        if j["error"]:
            return {"running": False, "error": j["error"]}
        if j["done_at"]:
            n = len(self._last().get("refs") or [])
            return {"running": False, "finished_at": j["done_at"], "references": n,
                    "next": "list_references로 목록을 보여 주세요." if n else NO_REFS}
        return {"running": False, "note": "이번 대화에서 시작한 분석이 없어요.", "last_analysis": self._last().get("date")}

    def t_list_references(self, a):
        last = self._last()
        refs = last.get("refs") or []
        if not last.get("date"):
            raise Need("아직 분석 결과가 없어요. start_analysis로 시작하세요.")
        if not refs:
            return {"analysis_date": last.get("date"), "references": [], "total": 0,
                    "note": NO_REFS}
        out = [self._short(r, f"R{i}") for i, r in enumerate(refs, 1)
               if not a.get("format") or a["format"] in (r.get("format") or "")]
        return {"analysis_date": last.get("date"), "criteria": last.get("criteria"),
                "references": out[: int(a.get("limit") or 15)], "total": len(out)}

    def t_list_benchmark_channels(self, a):
        last = self._last()
        bench = [{k: b.get(k) for k in ("name", "url", "subs", "avg", "keywords") if b.get(k) is not None}
                 for b in last.get("bench") or []]
        return {"analysis_date": last.get("date"), "keywords": last.get("keywords"), "channels": bench[:30]}

    def t_change_keywords(self, a):
        from . import run as R
        s = R.load_settings()
        add = [k.strip() for k in a.get("add") or [] if k.strip()]
        rem = [k.strip() for k in a.get("remove") or [] if k.strip()]
        s["kw_added"] = [k for k in dict.fromkeys((s.get("kw_added") or []) + add) if k not in rem]
        s["kw_removed"] = sorted((set(s.get("kw_removed") or []) | set(rem)) - set(add))
        R.save_settings(s)
        return {"added": s["kw_added"], "removed": s["kw_removed"], "note": "다음 분석(start_analysis)부터 적용돼요."}

    def t_add_benchmark_channel(self, a):
        from . import collect
        from . import engine as E
        from . import run as R
        try:
            ch, vids = collect.channel_videos(a["url"].strip(), 40)
        except Exception as e:
            raise Need(f"채널을 읽지 못했어요. 채널 주소(https://www.youtube.com/@…)를 확인해 주세요. ({E._friendly(e)})")
        s = R.load_settings()
        subs = s.get("subs") if isinstance(s.get("subs"), dict) else {}
        subs[ch["id"]] = {"name": ch["name"]}
        s["subs"] = subs
        s["subs_removed"] = [x for x in s.get("subs_removed") or [] if x != ch["id"]]
        R.save_settings(s)
        return {"added": ch["name"], "usual_views": int(E.baseline(vids, datetime.now().date(), 7))}

    def t_list_weekly_videos(self, a):
        w = self._weekly()
        if not w.get("items"):
            raise Need("이번 주 급상승 영상이 아직 올라오지 않았어요(대표가 학원월드 게시글을 올리면 자동으로 보여요). list_references로 내 분야 레퍼런스를 대신 볼 수 있어요.")
        return {"post_date": w.get("date"), "videos": [{**self._short(v, f"W{i}"), "post_analysis": (v.get("note") or "")[:600]}
                                                       for i, v in enumerate(w["items"], 1)]}

    def t_get_planning_material(self, a):
        from . import engine as E
        v = self._video(a["video"])
        text, folder = E.plan_material(v, a.get("my_story") or "", self._settings())
        return text + f"\n\n(콘봇 메모: 자료 폴더 {folder}. 기획안을 다 쓰면 save_plan(video='{a['video']}')으로 저장할 것)"

    def t_save_plan(self, a):
        from .engine import HOME, _today
        v = self._video(a["video"])
        root = HOME / "기획"
        olds = sorted(root.glob(f"*_{v['id']}")) if root.exists() else []
        folder = olds[-1] if olds else root / f"{_today().isoformat()}_{v['id']}"
        folder.mkdir(parents=True, exist_ok=True)
        if not (folder / "video.json").exists():
            (folder / "video.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
        (folder / "기획안.md").write_text(a["plan_markdown"], encoding="utf-8")
        return {"saved": str(folder / "기획안.md"), "note": "콘봇 창의 '내 기획안'에서도 볼 수 있어요."}

    def t_list_plans(self, a):
        from .engine import HOME
        root = HOME / "기획"
        out = []
        for d in sorted(root.iterdir(), reverse=True) if root.exists() else []:
            try:
                v = json.loads((d / "video.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            p = d / "기획안.md"
            out.append({"no": len(out) + 1, "date": d.name[:10], "reference": v.get("title"), "has_plan": p.exists(),
                        "folder": str(d), "_p": p})
        n = int(a.get("read") or 0)
        full = out[n - 1]["_p"].read_text(encoding="utf-8") if 0 < n <= len(out) and out[n - 1]["has_plan"] else None
        for o in out:
            o.pop("_p")
        return {"plans": out[:30], **({"plan": full} if full else {})}

    def t_find_folders(self, a):
        name = (a.get("name") or "").strip().lower()
        if not name:
            raise Need("찾을 폴더 이름을 주세요.")
        home = Path.home()
        roots = [home / x for x in ("Desktop", "Downloads", "Documents", "Movies", "Videos", "영상편집")] + [home]
        seen, out = set(), []

        def walk(d: Path, depth: int):
            if depth > 3 or len(out) >= 15:
                return
            try:
                kids = [k for k in d.iterdir() if k.is_dir() and not k.name.startswith(".")]
            except OSError:
                return
            for k in kids:
                if k.name in ("Library", "AppData", "node_modules", "콘봇_완성", "작업", "models"):
                    continue
                if name in k.name.lower() and k not in seen:
                    seen.add(k)
                    try:
                        vids = sum(1 for f in k.iterdir() if f.suffix.lower() in (".mp4", ".mov", ".m4v", ".mkv"))
                    except OSError:
                        vids = 0
                    out.append({"folder": str(k), "videos": vids, "made": (k / "콘봇_완성" / "최종.mp4").exists()})
                walk(k, depth + 1)
        for r in roots:
            if r.is_dir():
                walk(r, 1 if r != home else 3)
        return {"found": out} if out else "그 이름의 폴더를 못 찾았어요. 회원에게 폴더가 어디 있는지 물어보세요."

    def t_make_video(self, a):
        if self.vjob["running"]:
            return "이미 영상을 만들고 있어요. video_status로 확인하세요."
        folder = self._folder(a["folder"])
        style = a.get("style") or "유잡스 기본"
        self.vjob = {"running": True, "log": [], "error": None, "result": None, "folder": str(folder), "started": time.time()}

        def work():
            from . import video as V
            try:
                self.vjob["result"] = V.make(str(folder), style, log=self.vjob["log"].append)
            except Exception as e:
                self.vjob["error"] = str(e)[:400]
            finally:
                self.vjob["running"] = False
        threading.Thread(target=work, daemon=True).start()
        return f"'{folder}' 편집을 시작했어요. 촬영 길이에 따라 수 분~수십 분 걸려요(처음 한 번은 받아쓰기 모델도 받아요). 30초~1분 간격으로 video_status로 확인하세요."

    def t_video_status(self, a):
        j = self.vjob
        if j["running"]:
            return {"running": True, "folder": j["folder"], "minutes": round((time.time() - j.get("started", time.time())) / 60, 1),
                    "recent_log": j["log"][-3:]}
        if j["error"]:
            return {"running": False, "error": j["error"], "detail_log": str(Path.home() / "유잡스 기획" / "영상오류.txt")}
        if j["result"]:
            r = j["result"]
            return {"running": False, "done": True, **r,
                    "next": "get_video_lines로 자막을 읽고 오타·강조·챕터를 edit_video로 반영하세요."}
        return {"running": False, "note": "이번 대화에서 만든 영상이 없어요."}

    def _out(self, folder: str) -> Path:
        f = self._folder(folder)
        if (f / "작업" / "edit.json").exists():
            return f
        if (f / "콘봇_완성" / "작업" / "edit.json").exists():
            return f / "콘봇_완성"
        raise Need("이 폴더에서 콘봇이 만든 영상을 찾지 못했어요. 먼저 make_video로 만드세요.")

    def t_get_video_lines(self, a):
        from . import video as V
        out = self._out(a["folder"])
        d = V.load_edit(str(out))
        lines = []
        for i, it in enumerate(d["items"], 1):
            x = {"no": i, "time": f"{int(it['s'] // 60)}:{int(it['s'] % 60):02d}", "text": it["t"]}
            for k, name in (("emph", "emphasis"), ("chapter", "chapter")):
                if it.get(k):
                    x[name] = it[k]
            lines.append(x)
        return {"folder": str(out), "final": str(out / "최종.mp4"), "minutes_before": round(d["before"] / 60, 1),
                "minutes_after": round(d["after"] / 60, 1), "lines": lines,
                "note": "time은 원본 촬영 기준 시간이에요. 설명란 챕터 시간은 edit_video 결과의 chapters_at을 쓰세요."}

    def t_edit_video(self, a):
        if self.vjob["running"]:
            return "이미 영상을 만들고 있어요. video_status로 확인하세요."
        out = self._out(a["folder"])
        args = {k: a.get(k) for k in ("drop", "fix", "emphasis", "chapters")}
        self.vjob = {"running": True, "log": [], "error": None, "result": None, "folder": str(out), "started": time.time()}

        def work():
            from . import video as V
            try:
                r = V.edit_by_number(str(out), log=self.vjob["log"].append, **args)
                r["chapters_at"] = chapter_times(str(out))
                self.vjob["result"] = r
            except Exception as e:
                self.vjob["error"] = str(e)[:400]
            finally:
                self.vjob["running"] = False
        threading.Thread(target=work, daemon=True).start()
        return "고친 내용으로 다시 만들기 시작했어요(받아쓰기는 다시 안 해서 몇 분이면 돼요). video_status로 확인하세요."


def chapter_times(out_folder: str) -> list[dict]:
    """완성본 기준 챕터 시작 시간 (유튜브 설명란용)."""
    from . import video as V
    d = json.loads((Path(out_folder) / "작업" / "edit.json").read_text(encoding="utf-8"))
    ivs = [tuple(x) for x in d["intervals"]]
    res = []
    for it in d["items"]:
        if it.get("chapter"):
            t = V._remap(float(it["s"]), ivs)
            res.append({"time": f"{int(t // 60):02d}:{int(t % 60):02d}", "chapter": it["chapter"]})
    if res and res[0]["time"] != "00:00":
        res.insert(0, {"time": "00:00", "chapter": "인트로"})
    return res


# ---------- JSON-RPC ----------
def _streams():
    """표준입출력. 윈도우 창 모드 빌드는 sys.stdin/stdout이 None이라 OS 핸들에서 직접 연다."""
    if sys.stdin is not None and sys.stdout is not None:
        try:
            return sys.stdin.buffer, sys.stdout.buffer
        except AttributeError:
            pass
    if os.name != "nt":
        return os.fdopen(0, "rb", buffering=0), os.fdopen(1, "wb", buffering=0)
    import msvcrt
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.GetStdHandle.restype = ctypes.c_void_p
    fin = msvcrt.open_osfhandle(k32.GetStdHandle(-10), os.O_RDONLY | os.O_BINARY)
    fout = msvcrt.open_osfhandle(k32.GetStdHandle(-11), os.O_BINARY)
    return os.fdopen(fin, "rb", buffering=0), os.fdopen(fout, "wb", buffering=0)


def _hide_from_dock() -> None:
    """맥: Claude 앱이 띄운 도구용 콘봇이 Dock에 '두 번째 콘봇'으로 보이지 않게 한다 (창 없는 백그라운드 프로세스로)."""
    if sys.platform != "darwin":
        return
    try:
        import ctypes
        import ctypes.util
        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AppKit.framework/AppKit")
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        addr = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
        send0 = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(addr)
        send1 = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long)(addr)
        app = send0(objc.objc_getClass(b"NSApplication"), objc.sel_registerName(b"sharedApplication"))
        send1(app, objc.sel_registerName(b"setActivationPolicy:"), 2)  # NSApplicationActivationPolicyProhibited
    except Exception:
        pass  # 못 숨겨도 기능에는 지장 없다


def serve() -> None:
    _hide_from_dock()
    rin, rout = _streams()
    lock = threading.Lock()
    # 도구가 print로 남기는 글이 대화 통로를 망치지 않게 표준출력을 오류 출력(또는 버림)으로 돌린다
    if sys.stderr is None:  # 윈도우 창 모드 빌드
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    sys.stdout = sys.stderr
    try:
        from . import net
        net.use_system_certificates()
    except Exception:
        pass
    srv = Server()

    def send(msg: dict):
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with lock:
            rout.write(data)
            rout.flush()

    def handle(req: dict):
        mid, method, p = req.get("id"), req.get("method"), req.get("params") or {}
        if mid is None:  # 알림(notifications/…)은 답하지 않는다
            return
        try:
            if method == "initialize":
                from .version import VERSION
                ver = p.get("protocolVersion")
                res = {"protocolVersion": ver if ver in PROTOCOLS else PROTOCOLS[0],
                       "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "cornbot", "title": "콘봇", "version": VERSION},
                       "instructions": INSTRUCTIONS}
            elif method == "ping":
                res = {}
            elif method == "tools/list":
                res = {"tools": TOOLS}
            elif method == "tools/call":
                res = call(srv, p.get("name"), p.get("arguments") or {})
            elif method in ("resources/list", "prompts/list"):
                res = {method.split("/")[0]: []}
            else:
                send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"없는 기능: {method}"}})
                return
            send({"jsonrpc": "2.0", "id": mid, "result": res})
        except Exception as e:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)[:300]}})

    for raw in iter(rin.readline, b""):
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw.decode("utf-8"))
        except ValueError:
            send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}})
            continue
        for r in req if isinstance(req, list) else [req]:
            # 오래 걸리는 도구(자료 만들기 등)가 ping을 막지 않도록 요청마다 스레드
            threading.Thread(target=handle, args=(r,), daemon=True).start()


def call(srv: Server, name: str, args: dict) -> dict:
    fn = getattr(srv, f"t_{name}", None)
    if fn is None:
        return {"isError": True, "content": [{"type": "text", "text": f"콘봇에 '{name}' 도구가 없어요."}]}
    try:
        if name not in FREE:
            srv._check()
        out = fn(args)
        text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, indent=1)
        return {"content": [{"type": "text", "text": text}]}
    except Need as e:
        return {"isError": True, "content": [{"type": "text", "text": str(e)}]}
    except Exception as e:
        traceback.print_exc()
        return {"isError": True, "content": [{"type": "text", "text": f"콘봇 오류: {str(e)[:300]}"}]}


if __name__ == "__main__":
    serve()


def probe(cmd: list[str], timeout: float = 60) -> str:
    """점검용: 실제로 `cmd`(콘봇 --mcp)를 띄워 Claude 앱처럼 인사 → 도구 목록 → 상태 도구를 불러 본다."""
    msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "probe", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "cornbot_status", "arguments": {}}}]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    got: dict = {}

    def reader():
        for line in p.stdout:
            try:
                m = json.loads(line.decode("utf-8"))
            except ValueError:
                got.setdefault("junk", line[:80])
                continue
            got[m.get("id")] = m
    t = threading.Thread(target=reader, daemon=True)
    t.start()
    for m in msgs:
        p.stdin.write((json.dumps(m) + "\n").encode())
        p.stdin.flush()
    end = time.time() + timeout
    while time.time() < end and not all(k in got for k in (1, 2, 3)):
        time.sleep(0.2)
    p.stdin.close()
    try:
        p.wait(10)
    except subprocess.TimeoutExpired:
        p.kill()
    if not all(k in got for k in (1, 2, 3)):
        return f"ERR no answer (got {sorted(k for k in got if k)}) stderr={p.stderr.read()[-300:]!r}"
    if "junk" in got:
        return f"ERR junk on stdout: {got['junk']!r}"
    n = len(got[2]["result"]["tools"])
    st = got[3]["result"]["content"][0]["text"]
    ok = '"version"' in st
    return f"ok {got[1]['result']['serverInfo']['version']} tools={n}" if ok else f"ERR status: {st[:200]}"
