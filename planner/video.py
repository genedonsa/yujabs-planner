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
    sp: bool = True  # 앞에 띄어쓰기가 있는 낱말인지 ('방법'+'을'처럼 붙는 조각은 False)


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: list[str], log: Callable[[str], None] | None = None) -> None:
    flags = 0x08000000 if sys.platform == "win32" else 0  # 윈도우: 검은 창 안 띄우기
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=flags)
    if p.returncode != 0:
        err = p.stderr or ""
        try:  # 전체 기록은 파일로 (문의할 때 보내 달라고 할 수 있게)
            (Path.home() / "유잡스 기획").mkdir(exist_ok=True)
            (Path.home() / "유잡스 기획" / "영상오류.txt").write_text(" ".join(args) + "\n\n" + err, encoding="utf-8")
        except OSError:
            pass
        lines = [l for l in err.splitlines() if ("rror" in l or "Invalid" in l or "No such" in l) and len(l) < 300]
        raise RuntimeError("영상 처리 중 오류: " + (" / ".join(lines[-3:]) or err[-300:]))


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
        for j, w in enumerate(sg.words or []):
            t = w.word.strip()
            if t:
                words.append(W(float(w.start), float(w.end), t, i, j == 0 or w.word[:1] == " "))
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
                # '다시' 뒤 첫 말이 바로 앞(15낱말 안)에 나온 적 있으면 다시 찍은 것: 그 자리부터 지운다
                restart = next((_bare(words[k].t) for k in range(i + 1, min(i + 4, n))
                                if _bare(words[k].t) not in FILLERS_ALWAYS), "")
                m_hit = next((m for m in range(i - 1, max(i - 16, -1), -1)
                              if restart and _bare(words[m].t) == restart), None)
                # 받아쓰기는 쉼을 앞 낱말 길이에 붙이므로 '다시'가 길게(0.7초+) 잡히면 쉼이 있었던 것
                paused = gap_before[i] >= 0.6 or gap_after[i] >= 0.3 or (w.e - w.s) >= 0.7 \
                    or (i and words[i - 1].e - words[i - 1].s >= 1.0)
                if m_hit is None and not paused:
                    continue  # 문장 안에서 뜻으로 쓴 '다시'
                if m_hit is not None:
                    j = m_hit
                else:
                    j = i - 1  # 끊긴 문장의 시작(긴 쉼)까지 거슬러 올라감
                    while j > 0 and gap_before[j] < 0.7 and i - j < 40:
                        j -= 1
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


def silences(wav: Path, min_len: float = 0.35) -> list[tuple[float, float]]:
    """소리에서 직접 찾은 무음 구간. 받아쓰기 시간은 쉼을 낱말에 붙여 버려서 이걸로 잘라야 한다."""
    p = subprocess.run([ffmpeg(), "-i", str(wav), "-af", f"silencedetect=noise=-35dB:d={min_len}", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=0x08000000 if sys.platform == "win32" else 0)
    st = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", p.stderr)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p.stderr)]
    return [(max(0.0, a), b) for a, b in zip(st, en)]


def intervals(kept: list[W], st: dict, total: float, pad: float = 0.08,
              sil: list[tuple[float, float]] | None = None) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for w in kept:
        s, e = max(0.0, w.s - pad), min(total, w.e + pad)
        if out and s - out[-1][1] <= st["max_gap"]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    # 남긴 구간 안의 긴 무음을 뺀다 (앞뒤로 max_gap/2 만큼은 숨 쉴 틈으로 남김)
    keep = st["max_gap"] / 2
    for a, b in sil or []:
        if b - a <= st["max_gap"] + 0.1:
            continue
        ca, cb = a + keep, b - keep
        nxt: list[list[float]] = []
        for s, e in out:
            if cb <= s or ca >= e:
                nxt.append([s, e])
                continue
            if ca > s:
                nxt.append([s, ca])
            if cb < e:
                nxt.append([cb, e])
        out = nxt
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


# 받아쓰기가 띄어 쓴 조사·어미·단위를 앞말에 붙인다 ('방법 을'→'방법을', '꾸준함 입니다'→'꾸준함입니다', '52 편이'→'52편이')
_ATTACH = re.compile(r"^(을|를|은|는|의|에|에서|에게|께|도|만|로|으로|와|과|랑|이랑|까지|부터|처럼|보다|"
                     r"입니다|이에요|예요|이다|이죠|이고|이라|이라고|인데|이란|이나)[.,?!]*$")
_UNIT = re.compile(r"^(편|개|명|원|만|천|억|년|월|일|주|시간|분|초|배|번|가지|살|위|등|퍼센트|%)")


def _attach(prev: str, cur: str) -> bool:
    return bool(_ATTACH.match(cur)) or (bool(re.search(r"\d$", prev)) and bool(_UNIT.match(cur)))


def _join(cur) -> str:
    t = "".join((" " if k and x[3] and not _attach(cur[k - 1][2], x[2]) else "") + x[2] for k, x in enumerate(cur))
    t = re.sub(r"(?<![\d])[.,]+|[.,]+(?![\d])", " ", t)  # 마침표·쉼표는 자막에서 뺀다 (3.5 같은 숫자는 둠)
    return re.sub(r"\s+", " ", t).strip()


def items(kept: list[W], max_chars: int = 20) -> list[dict]:
    """자막 한 줄 단위 묶음. s·e는 원본 영상 기준 시간 (편집 화면에서 줄을 빼면 이 구간을 잘라 낸다)."""
    out, cur = [], []

    def flush():
        if cur:
            t = _join([(0, 0, w.t, w.sp) for w in cur])
            if t:
                out.append({"s": round(float(cur[0].s), 3), "e": round(float(cur[-1].e), 3), "t": t})
    for i, w in enumerate(kept):
        text = _join([(0, 0, x.t, x.sp) for x in cur])
        long_pause = cur and (w.s - kept[i - 1].e) > 0.6
        if cur and (len(text) + 1 + len(w.t) > max_chars or long_pause):
            flush()
            cur = []
        cur.append(w)
        if re.search(r"[.?!]$", w.t):
            flush()
            cur = []
    flush()
    return out


def place(its: list[dict], ivs: list[tuple[float, float]]) -> list[tuple[float, float, str]]:
    """원본 시간의 자막 줄을 잘라 낸 뒤 영상의 시간으로 옮긴다."""
    res = []
    for it in its:
        a, b = _remap(it["s"], ivs), _remap(it["e"], ivs)
        if b - a > 0.05:
            res.append((a, max(b, a + 0.4), it["t"]))
    return res


def overlays(its: list[dict], ivs: list[tuple[float, float]]) -> list[tuple[float, float, str, str]]:
    """자막 줄에 붙은 강조 문구(emph)·챕터 카드(chapter)를 영상 시간으로. 챕터 번호는 순서대로 01, 02…"""
    out, n = [], 0
    clean = lambda x: str(x).replace("{", "(").replace("}", ")").replace("\\", "/").strip()
    for it in its:
        a, b = _remap(it["s"], ivs), _remap(it["e"], ivs)
        if it.get("chapter"):
            n += 1
            out.append((a, a + 2.6, f"{{\\c&H0000D2FF&}}{n:02d}{{\\c&H00FFFFFF&}}  {clean(it['chapter'])}", "chapter"))
        if it.get("emph"):
            out.append((a, max(b, a + 1.8), clean(it["emph"]), "emph"))
    return out


def lines(kept: list[W], ivs: list[tuple[float, float]], max_chars: int = 20) -> list[tuple[float, float, str]]:
    return place(items(kept, max_chars), ivs)


def drop_ranges(ivs: list[tuple[float, float]], cuts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out = [list(x) for x in ivs]
    for ca, cb in cuts:
        nxt = []
        for a, b in out:
            if cb <= a or ca >= b:
                nxt.append([a, b])
                continue
            if ca > a:
                nxt.append([a, ca])
            if cb < b:
                nxt.append([cb, b])
        out = nxt
    return [(round(a, 3), round(b, 3)) for a, b in out if b - a > 0.05]


def _ts_srt(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _ts_ass(t: float) -> str:
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def write_subs(subs, folder: Path, st: dict, w: int = 1920, h: int = 1080, extras=None) -> tuple[Path, Path]:
    """subs: 아래 자막 (시작, 끝, 글). extras: 위쪽 그래픽 (시작, 끝, 글, 'emph'|'chapter')."""
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
Style: Emph,{st['font']},92,&H0000D2FF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,7,0,8,80,80,150,1
Style: Chapter,{st['font']},120,&H00FFFFFF,&H000000FF,&H00000000,&HB4000000,0,0,0,0,100,100,0,0,3,24,0,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def em(t: str) -> str:
        t = t.replace("{", "(").replace("}", ")")
        return re.sub(r"(\d[\d,.]*\s*(?:만|천|억|원|달러|명|개|배|%|퍼센트|년|개월|일|분|초|회)?)",
                      lambda m: "{\\c" + st["em_color"] + "&}" + m[1] + "{\\c" + st["sub_color"] + "&}", t)
    ass = folder / "자막.ass"
    lines_ = [f"Dialogue: 0,{_ts_ass(a)},{_ts_ass(b)},Default,,0,0,0,,{em(t)}" for a, b, t in subs]
    for a, b, t, kind in extras or []:  # t는 overlays()에서 이미 { } 를 걸러 둠
        if kind == "chapter":  # 화면 가운데 위쪽 챕터 카드 (자막 자리 y 820 아래는 피함)
            lines_.append(f"Dialogue: 1,{_ts_ass(a)},{_ts_ass(b)},Chapter,,0,0,0,,{{\\fad(200,200)\\pos({w // 2},{int(h * 0.36)})}}{t}")
        else:  # 위쪽 강조 문구 (노란 글씨 + 검은 테두리)
            lines_.append(f"Dialogue: 1,{_ts_ass(a)},{_ts_ass(b)},Emph,,0,0,0,,{{\\fad(120,120)}}{t}")
    ass.write_text(head + "\n".join(lines_), encoding="utf-8")
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
    ivs = intervals(kept, st, total, sil=silences(wav))
    its = items(kept)
    (work / "edit.json").write_text(json.dumps({"source": str(joined), "style": style_name, "total": total,
                                                 "intervals": ivs, "items": its, "words": len(words),
                                                 "kept": len(kept)}, ensure_ascii=False, indent=1), encoding="utf-8")
    step("render"); log("자막 넣고 음량 맞춰서 최종본 만드는 중…")
    res = _render(joined, ivs, place(its, ivs), st, out, work, log)
    step("done")
    return {**res, "before": round(float(total), 1)}


def load_edit(out_folder: str) -> dict:
    """편집 화면용: 만든 영상의 자막 줄 목록."""
    d = json.loads((Path(out_folder) / "작업" / "edit.json").read_text(encoding="utf-8"))
    return {"items": d["items"], "style": d["style"], "before": d["total"],
            "after": round(sum(b - a for a, b in d["intervals"]), 1)}


def rerender(out_folder: str, edited: list[dict], log: Callable[[str], None] = print) -> dict:
    """편집 화면에서 고친 자막으로 다시 만든다. keep=False인 줄은 그 구간을 영상에서도 잘라 낸다.
    받아쓰기는 다시 하지 않아서 빠르다."""
    out = Path(out_folder)
    work = out / "작업"
    d = json.loads((work / "edit.json").read_text(encoding="utf-8"))
    st = STYLES.get(d["style"], STYLES["유잡스 기본"])
    keep, cuts = [], []
    for it in edited:
        if it.get("keep", True):
            t = re.sub(r"\s+", " ", str(it.get("t", ""))).strip()
            if t:
                k = {"s": float(it["s"]), "e": float(it["e"]), "t": t}
                for key in ("emph", "chapter"):
                    if str(it.get(key) or "").strip():
                        k[key] = str(it[key]).strip()[:40]
                keep.append(k)
        else:
            cuts.append((float(it["s"]) - 0.04, float(it["e"]) + 0.04))
    ivs = drop_ranges([tuple(x) for x in d["intervals"]], cuts)
    if not ivs:
        raise RuntimeError("남은 장면이 없어요. 한 줄 이상은 남겨 주세요.")
    log("고친 자막으로 다시 만드는 중…")
    res = _render(Path(d["source"]), ivs, place(keep, ivs), st, out, work, log, extras=overlays(keep, ivs))
    d["intervals"], d["items"] = ivs, keep
    (work / "edit.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return {**res, "before": round(float(d["total"]), 1)}


CHUNK = 40  # 한 번에 자르는 구간 수. 긴 영상(구간 수백 개)을 한 번에 자르면 ffmpeg가 메모리 부족으로 멈춘다.


def _fc(ff: str, args_before: list[str], script: Path, args_after: list[str]) -> None:
    """필터 스크립트 파일로 ffmpeg 실행 (ffmpeg 7.1+ 방식, 안 되면 옛 방식)."""
    try:
        _run([ff, *args_before, "-/filter_complex", str(script), *args_after])
    except RuntimeError as e:
        if "filter_complex" not in str(e) and "Option not found" not in str(e) and "Unrecognized" not in str(e):
            raise
        _run([ff, *args_before, "-filter_complex_script", str(script), *args_after])


def edit_by_number(out_folder: str, drop=None, fix=None, emphasis=None, chapters=None,
                   log: Callable[[str], None] = print) -> dict:
    """자막 줄 번호(1부터)로 한꺼번에 고쳐 다시 만든다. drop: 뺄 줄, fix: {번호: 고친 글},
    emphasis: {번호: 위쪽 강조 문구}, chapters: {번호: 챕터 이름}. 없는 번호는 알려 주고 건너뛴다."""
    d = load_edit(out_folder)
    its = [dict(x, keep=True) for x in d["items"]]
    n = len(its)
    missing = []

    def idx(k):
        try:
            i = int(str(k).strip()) - 1
        except ValueError:
            i = -1
        if 0 <= i < n:
            return i
        missing.append(str(k))
        return None
    for k in drop or []:
        i = idx(k)
        if i is not None:
            its[i]["keep"] = False
    for k, v in (fix or {}).items():
        i = idx(k)
        if i is not None and str(v).strip():
            its[i]["t"] = str(v).strip()
    for k, v in (emphasis or {}).items():
        i = idx(k)
        if i is not None:
            its[i]["emph"] = str(v).strip()
    for k, v in (chapters or {}).items():
        i = idx(k)
        if i is not None:
            its[i]["chapter"] = str(v).strip()
    res = rerender(out_folder, its, log)
    res["missing"] = sorted(set(missing))
    return res


def _render(joined: Path, ivs: list[tuple[float, float]], subs, st: dict, out: Path, work: Path,
            log: Callable[[str], None] = lambda m: None, extras=None) -> dict:
    """1) 남길 구간을 CHUNK개씩 잘라 조각 파일로 2) 조각을 이어 붙이고 3) 자막·음량을 넣어 최종본."""
    ff = ffmpeg()
    srt, ass = write_subs(subs, out, st, extras=extras)
    parts_dir = work / "조각"
    parts_dir.mkdir(parents=True, exist_ok=True)
    for old in parts_dir.glob("*.mp4"):
        old.unlink()
    chunks = [ivs[i:i + CHUNK] for i in range(0, len(ivs), CHUNK)]
    parts = []
    for n, ch in enumerate(chunks):
        log(f"자르는 중… {n + 1}/{len(chunks)}")
        a0 = max(0.0, ch[0][0] - 0.05)
        dur = ch[-1][1] - a0 + 0.1
        sel = "+".join(f"between(t,{a - a0:.3f},{b - a0:.3f})" for a, b in ch)
        script = work / "cut_filter.txt"
        script.write_text(
            f"[0:v]select='{sel}',setpts=N/FRAME_RATE/TB,scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p[v];"
            f"[0:a]aselect='{sel}',asetpts=N/SR/TB,aresample=48000[a]", encoding="utf-8")
        part = parts_dir / f"{n:04d}.mp4"
        _fc(ff, ["-y", "-ss", f"{a0:.3f}", "-t", f"{dur:.3f}", "-i", str(joined)], script,
            ["-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
             "-c:a", "aac", "-b:a", "256k", "-ar", "48000", str(part)])
        parts.append(part)
    listing = work / "조각목록.txt"
    listing.write_text("".join("file '" + p.resolve().as_posix().replace("'", "'\\''") + "'\n" for p in parts),
                       encoding="utf-8")
    cut = work / "잘린영상.mp4"
    _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(cut)])

    log("자막 넣고 음량 맞추는 중…")
    fonts = net.BASE / "ui" / "fonts"
    ass_arg = str(ass).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    fonts_arg = str(fonts).replace("\\", "/").replace(":", "\\:")
    script = work / "filter.txt"
    script.write_text(f"[0:v]ass='{ass_arg}':fontsdir='{fonts_arg}'[v];"
                      f"[0:a]loudnorm=I={st['loudness']}:TP=-1.5:LRA=11[a]", encoding="utf-8")
    final = out / "최종.mp4"
    _fc(ff, ["-y", "-i", str(cut)], script,
        ["-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)])
    for p in parts:
        p.unlink(missing_ok=True)
    return {"final": str(final), "srt": str(srt), "folder": str(out),
            "after": round(float(sum(b - a for a, b in ivs)), 1), "cuts": len(ivs), "lines": len(subs)}
