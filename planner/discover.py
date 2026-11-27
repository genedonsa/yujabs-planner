"""영상 제목에서 버티컬 키워드를 뽑는다. 형태소 분석기 없이 단순 빈도 + 불용어."""
from __future__ import annotations

import re
from collections import Counter

STOPWORDS = set("""
영상 유튜브 채널 구독 구독자 조회수 방법 이유 진짜 정말 이거 그냥 무조건 절대 하는 하면 했던 하고 해서
있는 없는 되는 안되는 모든 지금 오늘 처음 최고 최악 공개 결과 후기 리뷰 브이로그 vlog feat ft shorts
가지 하지 마세요 총정리 정리 꿀팁 현실 추천 비밀 알려 드림 드립니다 이렇게 이것 이것만 바로 꼭 제발 단돈 무료 모르면 손해 실패담 사람 사람들 나만 우리 없이 있게 하면서 위해 대한
늘리 늘리기 만드 만들 만드는 벌기 버는 번 하기 되기 보기 알려 알려드 드리 찾기 쓰는 쓰기 파는 팔기 사는 하는법 방법들 이유 정말로 판매 강의
the a an to of and in for on with my your how why what is are you i this that
""".split())

PARTICLES = ("으로", "에서", "에게", "까지", "부터", "보다", "처럼", "이랑", "하고", "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "로", "와", "과")


def _strip_particle(word: str) -> str:
    for p in PARTICLES:
        if len(word) > len(p) + 1 and word.endswith(p):
            return word[: -len(p)]
    return word


def keywords(titles: list[str], top: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for t in titles:
        t = re.sub(r"\(.*?\)|\[.*?\]|#\S+", " ", t)
        for raw in re.findall(r"[가-힣A-Za-z]{2,}", t):
            w = _strip_particle(raw.lower())
            if w in STOPWORDS or len(w) < 2:
                continue
            counter[w] += 1
    return [w for w, n in counter.most_common(top * 2) if n >= 2][:top] or [w for w, _ in counter.most_common(top)]
