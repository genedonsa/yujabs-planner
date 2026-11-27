"""'분석 자료 묶음'과 '기획안 요청문'을 만든다. 회원은 두 파일을 Claude 앱에 넣는다."""
from __future__ import annotations

from datetime import date
from pathlib import Path

PROMPT = Path(__file__).resolve().parents[1] / "prompts" / "plan_prompt.md"


def ts(sec: float) -> str:
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _n(x) -> str:
    return f"{x:,}" if isinstance(x, int) else str(x or "-")


def write_bundle(out_dir: Path, me: dict, my_top: list, refs: list[dict], today: date | None = None) -> tuple[Path, Path]:
    """
    me: {name, url, audience(내 시청자·상품 한 줄), notes(내 경험 메모)}
    my_top: [Video] 내 채널 조회수 상위
    refs: [{video: Video, ratio: float, baseline: float, detail: collect.video_detail 결과, why_picked: str}]
    """
    today = today or date.today()
    out_dir.mkdir(parents=True, exist_ok=True)
    L: list[str] = [f"# 이번 주 기획 자료 ({today.isoformat()})", ""]
    L += ["## 내 채널", f"- 채널: {me.get('name','')} ({me.get('url','')})",
          f"- 내 시청자와 상품: {me.get('audience') or '(비어 있음)'}",
          f"- 내 경험 메모: {me.get('notes') or '(비어 있음 — 기획안에는 질문으로 남길 것)'}", "",
          "### 내 채널 조회수 상위 (썸네일 스타일 기준)"]
    for v in my_top:
        L.append(f"- {v.title} · 조회 {_n(v.views)} · {v.url}")
    L.append("")
    for i, r in enumerate(refs, 1):
        v, d = r["video"], r["detail"]
        L += [f"## 레퍼런스 {i}. {d.get('title')}",
              f"- 링크: https://youtu.be/{d.get('id')}",
              f"- 채널: {d.get('channel')} · 길이 {ts(d.get('duration') or 0)} · 조회 {_n(d.get('views'))} · 업로드 {d.get('upload_date')}",
              f"- 채널 평소(중앙값) 대비 {r['ratio']:.1f}배 (평소 {_n(int(r['baseline']))}회)",
              f"- 고른 이유: {r.get('why_picked','')}",
              f"- 썸네일: {d.get('thumbnail')}",
              "", "### 설명란", (d.get("description") or "")[:1500], "",
              f"### 댓글 상위 {len(d.get('comments') or [])}개 (총 {_n(d.get('comment_count'))}개)"]
        for c in d.get("comments") or []:
            L.append(f"- (좋아요 {c['likes']}) {c['text'].replace(chr(10),' ')[:300]}")
        L += ["", "### 자막 (시간 포함)"]
        tr = d.get("transcript") or []
        if not tr:
            L.append("(자막 없음 — 원본 대사 대신 설명란·댓글로 분석하고 그 사실을 적을 것)")
        for seg in tr:
            L.append(f"[{ts(seg['start'])}] {seg['text']}")
        L.append("")
    bundle = out_dir / f"이번주_기획자료_{today.isoformat()}.md"
    bundle.write_text("\n".join(L), encoding="utf-8")
    prompt = out_dir / "기획안_요청문.md"
    prompt.write_text(PROMPT.read_text(encoding="utf-8"), encoding="utf-8")
    return bundle, prompt
