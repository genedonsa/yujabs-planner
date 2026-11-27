"""Claude 앱이 콘봇을 쓰는 흐름 그대로 점검 (CI 전용, 실제 유튜브·실제 받아쓰기).

python tests/e2e/mcp_flow.py CLIP_MP4 OUT_DIR

1) 진짜 표준입출력 통로(desktop.py --mcp)로 인사·도구 목록 확인
2) 같은 도구들을 차례로 불러 기획부터 영상 편집까지: 상태 → 내 채널·롤모델(=내 채널) → 분석 → 레퍼런스 →
   주간 게시글 가져오기(분석에서 찾은 실제 영상으로 만든 게시글) → 기획 자료 → 기획안 저장 → 폴더 찾기 →
   영상 만들기 → 자막 줄 → 오타·강조·챕터·빼기 → 다시 만들기 → 챕터 시간
암호만 건너뛴다(암호는 앱 selftest에서 따로 점검).
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from planner import access, mcp_server, net  # noqa: E402

net.use_system_certificates()
clip, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
rep = {"steps": [], "errors": []}
t0 = time.time()


def save():
    (out / "mcp_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")


rep["stdio_probe"] = mcp_server.probe([sys.executable, str(ROOT / "desktop.py"), "--mcp"])
if not rep["stdio_probe"].startswith("ok"):
    rep["errors"].append("stdio: " + rep["stdio_probe"])

access.check_saved = lambda s: True
srv = mcp_server.Server()


def call(tool, **a):
    r = mcp_server.call(srv, tool, a)
    text = r["content"][0]["text"]
    rep["steps"].append({"t": round(time.time() - t0), "tool": tool, "args": {k: (str(v)[:120]) for k, v in a.items()},
                         "error": r.get("isError", False), "out": text[:1500]})
    save()
    if r.get("isError"):
        rep["errors"].append(f"{tool}: {text[:300]}")
    try:
        return json.loads(text)
    except ValueError:
        return text


def wait(tool, key="running", limit=2400, every=15):
    end = time.time() + limit
    while time.time() < end:
        st = mcp_server.call(srv, tool, {})["content"][0]["text"]
        d = json.loads(st)
        if not d.get(key):
            return call(tool)
        time.sleep(every)
    rep["errors"].append(f"{tool}: {limit}초 안에 안 끝남")
    return {}


ME = "https://www.youtube.com/@유튜브-잡스"
call("cornbot_status")
call("update_profile", my_channel=ME, role_models=[ME], audience="유튜브로 지식 상품을 팔고 싶은 30~50대 / 유튜브 운영 강의")
call("start_analysis")
an = wait("analysis_status", every=20)
rep["analysis"] = an
refs = call("list_references", limit=10)
bench = call("list_benchmark_channels")
rep["keywords"] = bench.get("keywords") if isinstance(bench, dict) else None

# 주간 게시글: 분석에서 찾은 실제 영상(없으면 내 채널 인기 영상)으로 학원월드 글 모양을 만든다
ids = []
if isinstance(refs, dict):
    ids = [r["url"] for r in refs.get("references", [])[:3]]
if len(ids) < 2:
    try:
        me = json.loads((Path.home() / "유잡스 기획" / "me.json").read_text(encoding="utf-8"))
        ids += [f"https://youtu.be/{t['id']}" for t in me.get("top", [])[:3 - len(ids)]]
    except (OSError, ValueError):
        pass
post = "11월 4주차 주간 급상승 영상\n\n" + "\n".join(
    f"{i}. 점검채널 — 평소의 {4.5 - i}배\n{u}\n영상 요약: 점검용 요약 {i}\n왜 터졌나: 제목에 숫자와 결과를 먼저 보여 줌\n"
    f"시청자가 얻은 가치: 바로 따라 할 순서\n남은 궁금증: 작은 채널도 되나\n" for i, u in enumerate(ids, 1))
rep["post"] = post
w = call("import_weekly_post", text=post)
call("list_weekly_videos")
mat = call("get_planning_material", video="W1",
           my_story="나도 회사 다니며 유튜브를 시작해서 6개월 동안 수익이 0원이었다. 조회수보다 내 상품을 살 사람을 모으는 게 중요하다는 걸 늦게 알았다.")
mat_text = mat if isinstance(mat, str) else json.dumps(mat, ensure_ascii=False)
(out / "mcp_material.md").write_text(mat_text, encoding="utf-8")
rep["material"] = {"chars": len(mat_text), "지시문": "기획안" in mat_text[:3000],
                   "게시글분석": "학원월드 주간 게시글 분석" in mat_text, "내이야기": "수익이 0원" in mat_text,
                   "자막": "### 자막" in mat_text, "댓글": "### 댓글" in mat_text}
call("save_plan", video="W1", plan_markdown="# 점검용 기획안\n\n## 대본\n### 훅 · 0:00\n저도 처음 6개월은 수익이 0원이었어요.\n")
plans = call("list_plans", read=1)
rep["plan_saved"] = isinstance(plans, dict) and "점검용 기획안" in (plans.get("plan") or "")
if isinstance(refs, dict) and refs.get("references"):
    call("get_planning_material", video="R1", my_story="점검")

# 영상 편집: 바탕화면/콘봇점검촬영 폴더에 촬영본을 두고 Claude처럼 찾게 한다
shoot = Path.home() / "Desktop" / "콘봇점검촬영"
shoot.mkdir(parents=True, exist_ok=True)
shutil.copy(clip, shoot / "01.mp4")
call("find_folders", name="콘봇점검")
call("make_video", folder="바탕화면/콘봇점검촬영")
vs = wait("video_status", limit=3000)
rep["video"] = vs
lines = call("get_video_lines", folder="바탕화면/콘봇점검촬영")
if isinstance(lines, dict) and lines.get("lines"):
    L = lines["lines"]
    n = len(L)
    fix = {"1": L[0]["text"].replace("콘봇", "콘봇")}
    for x in L:
        if "콤보" in x["text"] or "곤봇" in x["text"]:
            fix[str(x["no"])] = x["text"].replace("콤보", "콘봇").replace("곤봇", "콘봇")
    emph = {str(x["no"]): "수익화 3가지" for x in L if "3가지" in x["text"] or "세 가지" in x["text"]}
    chap = {"1": "인사"}
    for x in L:
        if "첫 번째" in x["text"] or "첫번째" in x["text"]:
            chap[str(x["no"])] = "꾸준함"
        if "두 번째" in x["text"] or "두번째" in x["text"]:
            chap[str(x["no"])] = "주제 고르기"
    call("edit_video", folder="바탕화면/콘봇점검촬영", fix=fix, emphasis=emph or {"2": "핵심"}, chapters=chap,
         drop=[n] if n > 4 else [])
    ve = wait("video_status", limit=1500)
    rep["edited"] = ve
    after = call("get_video_lines", folder="바탕화면/콘봇점검촬영")
    rep["checks"] = {
        "편집 줄 수 줄어듦": isinstance(after, dict) and (n <= 4 or len(after.get("lines", [])) == n - 1),
        "강조 저장": isinstance(after, dict) and any(x.get("emphasis") for x in after.get("lines", [])),
        "챕터 저장": isinstance(after, dict) and sum(1 for x in after.get("lines", []) if x.get("chapter")) >= 1,
        "챕터 시간": bool(isinstance(ve, dict) and ve.get("chapters_at")),
        "완성본": isinstance(ve, dict) and Path(str(ve.get("final", ""))).exists(),
    }
    final = str(ve.get("final", "")) if isinstance(ve, dict) else ""
    if final and Path(final).exists():
        from planner import video as V
        for i, t in enumerate([1, 4, 8, 12]):
            subprocess.run([V.ffmpeg(), "-y", "-ss", str(t), "-i", final, "-frames:v", "1", "-vf", "scale=960:-1",
                            str(out / f"mcp_frame{i}.jpg")], capture_output=True)
        if ve.get("srt") and Path(ve["srt"]).exists():
            shutil.copy(ve["srt"], out / "mcp_subs.srt")
rep["seconds"] = round(time.time() - t0)
rep["ok"] = not rep["errors"] and all((rep.get("checks") or {"없음": False}).values())
save()
print(json.dumps({k: rep[k] for k in ("ok", "errors", "checks", "material", "plan_saved", "seconds") if k in rep}, ensure_ascii=False, indent=1))
