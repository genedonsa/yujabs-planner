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
new made make makes making get gets got changed change changes changing watch watching actually literally finally update updates month months today tomorrow yesterday everything nothing something someone everyone people person guy guys man woman life world story stories real truth secret secrets mistake mistakes reason reasons why's here's that's it's i'm you're don't won't should could would never always rules rule if it its it's we our they them do does did don't can can't will just more most best top all every one two three first last vs not no yes so be was were been have has had from by at as or but about into out up down now here there when which who than then too very really still even also only own same other any some much many way ways things thing need want know try tried tips tip guide full free easy fast quick big little time times day days week year years video videos youtube channel channels views view subscribers subscriber youtuber youtubers shorts short live podcast episode ep part
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
            if w in STOPWORDS or len(w) < 2 or (w.isascii() and len(w) < 3):
                continue
            counter[w] += 1
    return [w for w, n in counter.most_common(top * 2) if n >= 2][:top] or [w for w, _ in counter.most_common(top)]


def shared_keywords(groups: list[list[str]], top: int = 8) -> list[str]:
    """채널별 제목 묶음에서, 두 곳 이상에 함께 나오는 낱말을 우선으로 고른다.
    한 채널에만 자주 나오는 말(그 채널만의 말버릇·시리즈 이름)은 분야 키워드가 아닐 때가 많다."""
    groups = [g for g in groups if g]
    if len(groups) < 2:
        return keywords([t for g in groups for t in g], top)
    df: Counter[str] = Counter()
    tf: Counter[str] = Counter()
    for g in groups:
        ks = keywords(g, 30)
        df.update(set(ks))
        for i, k in enumerate(ks):
            tf[k] += 30 - i
    shared = [k for k, _ in sorted(((k, (df[k], tf[k])) for k in df if df[k] >= 2), key=lambda x: x[1], reverse=True)]
    rest = [k for k, _ in tf.most_common() if k not in shared]
    return (shared + rest)[:top] if len(shared) >= 3 else (shared + rest[:max(0, 4 - len(shared))])[:top]
