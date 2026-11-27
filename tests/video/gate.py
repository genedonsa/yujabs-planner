"""새 버전을 회원에게 내보내도 되는지 판정한다 (video-test에서 사용).
영상 만들기 점검 결과와, 실제로 내려받은 앱의 자체 점검(selftest) 결과가 모두 좋아야 통과."""
import json
import sys
from pathlib import Path

res = Path(sys.argv[1])
need_app = len(sys.argv) > 2 and sys.argv[2] == "app"
bad = []
reports = list(res.glob("report_*.json"))
if not reports:
    bad.append("영상 점검 결과 파일이 없음")
for f in reports:
    r = json.loads(f.read_text(encoding="utf-8"))
    if r.get("error"):
        bad.append(f"{f.name}: 오류 {r['error'][:200]}")
    for k, v in (r.get("checks") or {}).items():
        if not v:
            bad.append(f"{f.name}: '{k}' 실패")
if need_app:
    tests = list(res.glob("selftest_*.json"))
    if not tests:
        bad.append("앱 자체 점검 결과가 없음 (앱이 안 열렸을 수 있음)")
    for f in tests:
        s = json.loads(f.read_text(encoding="utf-8"))
        for k in ("ui_exists", "sheet_ok", "system_certificates"):
            if s.get(k) is not True:
                bad.append(f"{f.name}: {k} = {s.get(k)}")
        for k in ("ffmpeg", "whisper", "deno"):
            if not s.get(k):
                bad.append(f"{f.name}: {k} 없음")
        for k in ("access_error", "tools_error", "video_error"):
            if s.get(k):
                bad.append(f"{f.name}: {s[k][:200]}")
print("\n".join(bad) or "통과")
sys.exit(1 if bad else 0)
