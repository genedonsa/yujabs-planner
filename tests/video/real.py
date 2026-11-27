"""영상 만들기 실제 점검 (CI 전용): 진짜 받아쓰기 모델로 '다시'·추임새·무음이 든 한국어 말 영상을 편집해 본다.

python tests/video/real.py make-clip OUT_DIR   (맥: say로 한국어 음성 + 시험 화면 → OUT_DIR/raw.mp4)
python tests/video/real.py run CLIP_DIR RESULT_DIR
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from planner import net, video as V  # noqa: E402

net.use_system_certificates()

SCRIPT = ("안녕하세요. 콘봇 영상 편집 점검 영상입니다. [[slnc 2500]] "
          "오늘은 유튜브 수익화 이야기를 [[slnc 900]] 다시. [[slnc 1200]] "
          "오늘은 유튜브 수익화 3가지 방법을 알려드릴게요. [[slnc 2000]] 음. [[slnc 800]] "
          "첫 번째는 꾸준함입니다. 일주일에 한 편씩 1년 동안 올리면 52편이 쌓여요. [[slnc 3000]] "
          "두 번째는 내 상품과 연결된 주제를 고르는 겁니다. 감사합니다.")


def make_clip(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    voices = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    ko = [l.split()[0] for l in voices.splitlines() if "ko_KR" in l]
    print("korean voices:", ko)
    voice = "Yuna" if "Yuna" in ko else (ko[0] if ko else None)
    if not voice:
        raise SystemExit("한국어 음성이 없는 컴퓨터예요")
    aiff = out / "voice.aiff"
    subprocess.run(["say", "-v", voice, "-r", "190", "-o", str(aiff), SCRIPT], check=True)
    ff = V.ffmpeg()
    subprocess.run([ff, "-y", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30", "-i", str(aiff),
                    "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", str(out / "raw.mp4")], check=True, capture_output=True)
    aiff.unlink()


def run(clip_dir: Path, res: Path) -> None:
    res.mkdir(parents=True, exist_ok=True)
    rep = {"platform": sys.platform}
    words_box = {}
    orig = V.transcribe

    def spy(a, m, log):
        w = orig(a, m, log)
        words_box["w"] = w
        return w
    V.transcribe = spy
    t0 = time.time()
    try:
        r = V.make(str(clip_dir), "유잡스 기본", "small", log=lambda m: print(m, flush=True))
        rep["result"] = r
    except Exception as e:
        rep["error"] = f"{type(e).__name__}: {e}"
    rep["seconds"] = round(time.time() - t0)
    rep["words"] = [[round(w.s, 2), round(w.e, 2), w.t] for w in words_box.get("w", [])]
    if "result" in rep:
        srt = Path(rep["result"]["srt"]).read_text(encoding="utf-8")
        (res / "자막.srt").write_text(srt, encoding="utf-8")
        text = " ".join(l for l in srt.splitlines() if l and not l[0].isdigit() and "-->" not in l)
        rep["checks"] = {
            "줄어듦": bool(rep["result"]["after"] < rep["result"]["before"] * 0.85),
            "인사말 남음": "안녕하세요" in text.replace(" ", ""),
            "다시 지워짐": "다시" not in text,
            "끊긴 문장 지워짐": text.count("오늘은") == 1,
            "다시 말한 문장 남음": "3가지" in text or "세 가지" in text,
            "추임새 지워짐": " 음 " not in f" {text} ",
            "끝까지 남음": "감사합니다" in text,
        }
        ff = V.ffmpeg()
        final = rep["result"]["final"]
        for i, t in enumerate([2, 8, 14]):
            subprocess.run([ff, "-y", "-ss", str(t), "-i", final, "-frames:v", "1", "-vf", "scale=960:-1",
                            str(res / f"frame{i}.jpg")], capture_output=True)
        p = subprocess.run([ff, "-i", final, "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True)
        rep["loudness"] = p.stderr[p.stderr.rfind("{"):].split('"input_i" : "')[-1].split('"')[0]
    (res / f"report_{sys.platform}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "words"}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    if sys.argv[1] == "make-clip":
        make_clip(Path(sys.argv[2]))
    else:
        run(Path(sys.argv[2]), Path(sys.argv[3]))
