"""영상 만들기 (롱폼): 촬영 폴더 하나 → 컷 편집 + 자막 + 강조 + 음량 → 최종.mp4, 자막.srt

유잡스 편집 스킬의 브루 명령문 규칙을 코드로 옮겼다.
- 무음 구간 삭제, 추임새(어·음·아, 망설임으로 쓰인 그·이제·뭐) 삭제
- 촬영 중 "다시"(NG 신호): 그 앞에서 끊긴 문장과 "다시"를 같이 삭제하고 다시 말한 문장을 남김
- 같은 문장을 바로 다시 말한 경우 앞 테이크 삭제
- 자막 한 줄 20자, 흰 글씨 + 검은 테두리, 숫자·금액은 노란색 강조
- 목소리 -15 LUFS
회원 컴퓨터에서만 돌아간다. 음성 받아쓰기 모델은 처음 한 번 자동으로 받는다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

from . import net

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi"}
FILLERS_ALWAYS = {"어", "음", "아", "어어", "음음", "으", "에"}
FILLERS_HESITATE = {"그", "이제", "뭐", "그니까", "약간", "막"}
MODEL_DIR = Path.home() / "유잡스 기획" / "models"

STYLES = {
    "유잡스 기본": {"cut_fillers": True, "cut_ng": True, "cut_repeats": True, "max_gap": 0.25,
                 "sub_color": "&H00FFFFFF", "em_color": "&H0000D2FF", "outline": 5, "box": False,
                 "font": "Black Han Sans", "size": 64, "loudness": -15},
    "깔끔 자막": {"cut_fillers": False, "cut_ng": True, "cut_repeats": False, "max_gap": 0.45,
              "sub_color": "&H00FFFFFF", "em_color": "&H00FFFFFF", "outline": 0, "box": True,
              "font": "Black Han Sans", "size": 54, "loudness": -15},
}


@dataclass
class W:
    s: float
    e: float
    t: str
    seg: int


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: list[str], log: Callable[[str], None] | None = None) -> None:
    flags = 0x08000000 if sys.platform == "win32" else 0  # 윈도우: 검은 창 안 띄우기
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=flags)
    if p.returncode != 0:
        raise RuntimeError("영상 처리 중 오류: " + (p.stderr or "")[-400:])


def _duration(path: Path) -> float:
    p = subprocess.run([ffmpeg(), "-i", str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=0x08000000 if sys.platform == "win32" else 0)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", p.stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


# ---------- 1. 받아쓰기 ----------
def transcribe(audio: Path, model_size: str, log: Callable[[str], None]) -> list[W]:
    from faster_whisper import WhisperModel
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    log("음성 받아쓰기 모델 준비 중… (처음 한 번은 몇 분 걸려요)")
    model = WhisperModel(model_size, device="cpu", compute_type="int8", download_root=str(MODEL_DIR))
    # 소리 파일은 직접 읽어 넘긴다(받아쓰기 라이브러리의 소리 읽기 부분이 PyAV 새 버전과 맞지 않음)
    import wave
    import numpy as np
    with wave.open(str(audio), "rb") as wf:
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segs, info = model.transcribe(pcm, language="ko", word_timestamps=True, vad_filter=False,
                                  condition_on_previous_text=False)
    words: list[W] = []
    for i, sg in enumerate(segs):
        for w in sg.words or []:
            t = w.word.strip()
            if t:
                words.append(W(w.start, w.end, t, i))
        if i % 10 == 0:
            log(f"받아쓰는 중… {int(sg.end // 60)}분 {int(sg.end % 60)}초까지")
    return words


# ---------- 2. 무엇을 자를지 ----------
def _bare(t: str) -> str:
    return re.sub(r"[^\w가-힣]", "", t)


def choose(words: list[W], st: dict) -> list[W]:
    n = len(words)
    drop = [False] * n
    gap_before = [words[i].s - words[i - 1].e if i else 9.0 for i in range(n)]
    gap_after = [words[i + 1].s - words[i].e if i + 1 < n else 9.0 for i in range(n)]
    if st["cut_fillers"]:
        for i, w in enumerate(words):
            b = _bare(w.t)
            if b in FILLERS_ALWAYS:
                drop[i] = True
            elif b in FILLERS_HESITATE and (gap_after[i] > 0.3 or gap_before[i] > 0.5):
                drop[i] = True
    if st["cut_ng"]:
        for i, w in enumerate(words):
            if _bare(w.t) == "다시":
                nxt = _bare(words[i + 1].t) if i + 1 < n else ""
                if nxt in {"한번", "한", "처음", "말해", "말씀"}:
                    continue
                if gap_before[i] < 0.6 and gap_after[i] < 0.3:
                    continue  # 문장 안에서 뜻으로 쓴 '다시'
                j = i - 1  # 끊긴 문장의 시작(긴 쉼)까지 거슬러 올라감
                while j > 0 and gap_before[j] < 0.7 and i - j < 40:
                    j -= 1
                # '다시' 뒤 첫 말이 앞에서 나온 적 있으면, 그 자리부터만 지운다 (앞 인사말 등은 살림)
                restart = next((_bare(words[k].t) for k in range(i + 1, min(i + 4, n))
                                if _bare(words[k].t) not in FILLERS_ALWAYS), "")
                if restart:
                    for m in range(i - 1, max(i - 41, -1), -1):
                        if _bare(words[m].t) == restart:
                            j = m
                            break
                for k in range(max(j, 0), i + 1):
                    drop[k] = True
    if st["cut_repeats"]:
        # 쉼(0.7초 이상)으로 나눈 문장 단위로, 바로 다음 문장이 같은 말로 시작하면 앞 테이크 삭제
        sents, cur = [], []
        for i in range(n):
            if cur and gap_before[i] >= 0.7:
                sents.append(cur)
                cur = []
            cur.append(i)
        if cur:
            sents.append(cur)
        for a, b in zip(sents, sents[1:]):
            ta = "".join(_bare(words[k].t) for k in a if not drop[k])
            tb = "".join(_bare(words[k].t) for k in b if not drop[k])
            if len(ta) >= 4 and len(tb) >= len(ta) * 0.6 and SequenceMatcher(None, ta, tb[:len(ta) + 4]).ratio() > 0.75:
                for k in a:
                    drop[k] = True
    return [w for i, w in enumerate(words) if not drop[i]]


def intervals(kept: list[W], st: dict, total: float, pad: float = 0.08) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for w in kept:
        s, e = max(0.0, w.s - pad), min(total, w.e + pad)
        if out and s - out[-1][1] <= st["max_gap"]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(round(a, 3), round(b, 3)) for a, b in out if b - a > 0.05]


# ---------- 3. 자막 ----------
def _remap(t: float, ivs: list[tuple[float, float]]) -> float:
    acc = 0.0
    for a, b in ivs:
        if t < a:
            return acc
        if t <= b:
            return acc + (t - a)
        acc += b - a
    return acc


def lines(kept: list[W], ivs: list[tuple[float, float]], max_chars: int = 20) -> list[tuple[float, float, str]]:
    out, cur, cs = [], [], None
    for i, w in enumerate(kept):
        s, e = _remap(w.s, ivs), _remap(w.e, ivs)
        text = " ".join(x[2] for x in cur)
        long_pause = cur and (w.s - kept[i - 1].e) > 0.6
        if cur and (len(text) + 1 + len(w.t) > max_chars or long_pause):
            out.append((cs, cur[-1][1], text))
            cur, cs = [], None
        if cs is None:
            cs = s
        cur.append((s, e, w.t))
        if re.search(r"[.?!]$", w.t):
            out.append((cs, e, " ".join(x[2] for x in cur)))
            cur, cs = [], None
    if cur:
        out.append((cs, cur[-1][1], " ".join(x[2] for x in cur)))
    return [(a, max(b, a + 0.4), t.strip()) for a, b, t in out if t.strip()]


def _ts_srt(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _ts_ass(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def write_subs(subs, folder: Path, st: dict, w: int = 1920, h: int = 1080) -> tuple[Path, Path]:
    srt = folder / "자막.srt"
    srt.write_text("\n".join(f"{i}\n{_ts_srt(a)} --> {_ts_srt(b)}\n{t}\n" for i, (a, b, t) in enumerate(subs, 1)),
                   encoding="utf-8")
    border = "3" if st["box"] else "1"
    back = "&H99000000" if st["box"] else "&H00000000"
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{st['font']},{st['size']},{st['sub_color']},&H000000FF,&H00000000,{back},0,0,0,0,100,100,0,0,{border},{st['outline']},0,2,60,60,90,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def em(t: str) -> str:
        t = t.replace("{", "(").replace("}", ")")
        return re.sub(r"(\d[\d,.]*\s*(?:만|천|억|원|달러|명|개|배|%|퍼센트|년|개월|일|분|초|회)?)",
                      lambda m: "{\\c" + st["em_color"] + "&}" + m[1] + "{\\c" + st["sub_color"] + "&}", t)
    ass = folder / "자막.ass"
    ass.write_text(head + "\n".join(f"Dialogue: 0,{_ts_ass(a)},{_ts_ass(b)},Default,,0,0,0,,{em(t)}"
                                    for a, b, t in subs), encoding="utf-8")
    return srt, ass


# ---------- 4. 전체 ----------
def make(src_folder: str, style_name: str = "유잡스 기본", model_size: str = "small",
         log: Callable[[str], None] = print, step: Callable[[str], None] = lambda k: None) -> dict:
    src = Path(src_folder)
    clips = sorted([p for p in src.iterdir() if p.suffix.lower() in VIDEO_EXT and not p.name.startswith(".")])
    if not clips:
        raise RuntimeError("폴더에 영상 파일(mp4, mov)이 없어요.")
    st = STYLES.get(style_name, STYLES["유잡스 기본"])
    out = src / "콘봇_완성"
    work = out / "작업"
    work.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg()

    step("join"); log(f"영상 {len(clips)}개 이어 붙이는 중…")
    joined = work / "joined.mp4"
    if len(clips) == 1:
        joined = clips[0]
    else:
        inputs, fc = [], ""
        for i, c in enumerate(clips):
            inputs += ["-i", str(c)]
            fc += f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}];[{i}:a]aresample=48000[a{i}];"
        fc += "".join(f"[v{i}][a{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=1[v][a]"
        _run([ff, "-y", *inputs, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(joined)])
    total = _duration(joined)
    wav = work / "voice.wav"
    _run([ff, "-y", "-i", str(joined), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])

    step("stt")
    words = transcribe(wav, model_size, log)
    if not words:
        raise RuntimeError("말소리를 찾지 못했어요. 소리가 녹음된 영상인지 확인해 주세요.")
    step("cut"); log("무음·추임새·NG 구간 고르는 중…")
    kept = choose(words, st)
    ivs = intervals(kept, st, total)
    subs = lines(kept, ivs)
    srt, ass = write_subs(subs, out, st)
    (work / "cuts.json").write_text(json.dumps({"total": total, "intervals": ivs,
                                                 "words": len(words), "kept": len(kept)}, ensure_ascii=False), encoding="utf-8")

    step("render"); log("자막 넣고 음량 맞춰서 최종본 만드는 중…")
    sel = "+".join(f"between(t,{a},{b})" for a, b in ivs)
    fonts = net.BASE / "ui" / "fonts"
    ass_arg = str(ass).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    fonts_arg = str(fonts).replace("\\", "/").replace(":", "\\:")
    script = work / "filter.txt"
    script.write_text(
        f"[0:v]select='{sel}',setpts=N/FRAME_RATE/TB,scale=1920:1080:force_original_aspect_ratio=decrease,"
        f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,ass='{ass_arg}':fontsdir='{fonts_arg}'[v];"
        f"[0:a]aselect='{sel}',asetpts=N/SR/TB,loudnorm=I={st['loudness']}:TP=-1.5:LRA=11[a]", encoding="utf-8")
    final = out / "최종.mp4"
    _run([ff, "-y", "-i", str(joined), "-filter_complex_script", str(script), "-map", "[v]", "-map", "[a]",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)])
    step("done")
    return {"final": str(final), "srt": str(srt), "folder": str(out), "before": round(total, 1),
            "after": round(sum(b - a for a, b in ivs), 1), "cuts": len(ivs), "lines": len(subs)}
