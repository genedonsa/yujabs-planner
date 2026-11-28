"""영상 제목에서 버티컬 키워드를 뽑는다. 형태소 분석기 없이 단순 빈도 + 불용어."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

STOPWORDS = set("""
영상 유튜브 채널 구독 구독자 조회수 방법 이유 진짜 정말 이거 그냥 무조건 절대 하는 하면 했던 하고 해서
있는 없는 되는 안되는 모든 지금 오늘 처음 최고 최악 공개 결과 후기 리뷰 브이로그 vlog feat ft shorts
가지 하지 마세요 총정리 정리 꿀팁 현실 추천 비밀 알려 드림 드립니다 이렇게 이것 이것만 바로 꼭 제발 단돈 무료 모르면 손해 실패담 사람 사람들 나만 우리 없이 있게 하면서 위해 대한 맛있 맛있게 맛있는 맛있어 맛나 됩니다 됐어요 먹는 먹을 먹어 요즘 쉽게 쉬운 간단 간단한 초간단 아주 너무 많이 이제 다들 모두 가장 제일 특히 함께 같이 드세요 해보세요 보세요 넣으면 넣고 만드는법 만드는 만들기 담그 담그는 끓이 끓이는 볶는 무치 굽는 찌는 하는 쉽고 이걸 이거 이건 이렇게 진짜로 정말로 완전 엄청 대박 꼭 바로 그냥 무조건 절대
대충 어떤 어느 무슨 이런 그런 저런 모은 모아 꼴랑 난리난 난리 맛있어서 대부분 잘못 전부 같은 새로 다시 시대 법칙 목표 인생 시간 사용법 회사 유일한 유일 결국 이제는 그리고 하지만 생각 바뀌었 바뀐 시작 시작한 시작할 시작하는 다니면서 다니며 하나 여러 몇개 몇가지 얼마나 얼마 어떻게 왜냐 했는데 하는데 인데 이유는 
늘리 늘리기 만드 만들 만드는 벌기 버는 번 하기 되기 보기 알려 알려드 드리 찾기 쓰는 쓰기 파는 팔기 사는 하는법 방법들 이유 정말로 판매 강의
the a an to of and in for on with my your how why what is are you i this that
don doesn didn isn aren wasn her his him she he they their them minutes minute hours hour seconds 만든 만들었 만들어 했더니 하는법 했습니다 합니다 new made make makes making get gets got changed change changes changing watch watching actually literally finally update updates month months today tomorrow yesterday everything nothing something someone everyone people person guy guys man woman life world story stories real truth secret secrets mistake mistakes reason reasons why's here's that's it's i'm you're don't won't should could would never always rules rule if it its it's we our they them do does did don't can can't will just more most best top all every one two three first last vs not no yes so be was were been have has had from by at as or but about into out up down now here there when which who than then too very really still even also only own same other any some much many way ways things thing need want know try tried tips tip guide full free easy fast quick big little time times day days week year years video videos youtube channel channels views view subscribers subscriber youtuber youtubers shorts short live podcast episode ep part
""".split())

PARTICLES = ("으로", "에서", "에게", "까지", "부터", "보다", "처럼", "이랑", "하고", "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "로", "와", "과")


def _strip_particle(word: str) -> str:
    for p in PARTICLES:
        if len(word) > len(p) + 1 and word.endswith(p):
            return word[: -len(p)]
    return word


def _verbish(w: str) -> bool:
    """'맛있어서', '다니면서', '했는데'처럼 동사·형용사가 활용된 말은 분야 키워드가 아니다."""
    return len(w) >= 3 and not w.isascii() and w.endswith(("어서", "아서", "해서", "면서", "는데", "었던", "았던", "했던", "하던", "니까", "더니", "려고", "으면", "시키", "시켜", "시킨"))\
        or (len(w) >= 3 and not w.isascii() and w.endswith("히"))  # 영원히·꾸준히 같은 꾸밈말


# 분야가 '유튜브' 자체(유튜브 교육·성장)일 때는 평소엔 흔한 말로 빼던 유튜브 용어가 오히려 분야 키워드다
YOUTUBE_FIELD_WORDS = {"조회수", "구독자", "구독", "알고리즘", "수익화", "썸네일", "쇼츠", "롱폼", "유튜버", "채널", "편집", "떡상"}


def keywords(titles: list[str], top: int = 8, keep: set | frozenset = frozenset()) -> list[str]:
    counter: Counter[str] = Counter()
    for t in titles:
        t = unicodedata.normalize("NFC", t)
        t = re.sub(r"\(.*?\)|\[.*?\]|#\S+", " ", t)
        for raw in re.findall(r"[가-힣A-Za-z]{2,}", t):
            w = _strip_particle(raw.lower())
            if (w in STOPWORDS and w not in keep) or len(w) < 2 or (w.isascii() and len(w) < 3) or _verbish(w):
                continue
            counter[w] += 1
    return [w for w, n in counter.most_common(top * 2) if n >= 2][:top] or [w for w, _ in counter.most_common(top)]


def shared_keywords(groups: list[list[str]], top: int = 8, keep: set | frozenset = frozenset()) -> list[str]:
    """채널별 제목 묶음에서, 두 곳 이상에 함께 나오는 낱말을 우선으로 고른다.
    한 채널에만 자주 나오는 말(그 채널만의 말버릇·시리즈 이름)은 분야 키워드가 아닐 때가 많다."""
    groups = [g for g in groups if g]
    if len(groups) < 2:
        return keywords([t for g in groups for t in g], top, keep)
    df: Counter[str] = Counter()
    tf: Counter[str] = Counter()
    for g in groups:
        ks = keywords(g, 30, keep)
        df.update(set(ks))
        for i, k in enumerate(ks):
            tf[k] += 30 - i
    shared = [k for k, _ in sorted(((k, (df[k], tf[k])) for k in df if df[k] >= 2), key=lambda x: x[1], reverse=True)]
    rest = [k for k, _ in tf.most_common() if k not in shared]
    return (shared + rest)[:top] if len(shared) >= 3 else (shared + rest[:max(0, 4 - len(shared))])[:top]


DOMAIN_WORDS = {"youtube", "유튜브", "channel", "채널", "영상", "video", "videos", "shorts", "쇼츠", "youtuber", "유튜버"}


def anchor_word(groups: list[list[str]]) -> str:
    """분야를 대표하는 말 하나 (예: 유튜브·youtube). 검색어 앞에 붙여 엉뚱한 분야 결과를 줄인다.
    롤모델 여러 곳 제목에 두루 나오는 말 중 가장 흔한 것."""
    excluded = STOPWORDS - DOMAIN_WORDS
    df: Counter[str] = Counter()
    tf: Counter[str] = Counter()
    for g in groups:
        seen = set()
        for t in g:
            t = re.sub(r"\(.*?\)|\[.*?\]|#\S+", " ", t)
            for raw in re.findall(r"[가-힣A-Za-z]{2,}", t):
                w = _strip_particle(raw.lower())
                if w in excluded or len(w) < 2 or (w.isascii() and len(w) < 3):
                    continue
                tf[w] += 1
                seen.add(w)
        df.update(seen)
    if not df:
        return ""
    need = max(2, (len([g for g in groups if g]) + 1) // 2)
    cands = [w for w in df if df[w] >= need] or list(df)
    return max(cands, key=lambda w: (df[w], tf[w]))


SHORT_OK = {"ai", "pd", "it"}  # 두 글자 영어지만 분야를 나타내는 말
GENERIC_YT = {"조회수", "구독자", "구독", "유튜버", "채널", "유튜브", "youtube", "영상"}  # 유튜브 분야에선 너무 넓은 말


def _tokens(title: str, keep: set | frozenset) -> list[str | None]:
    """제목을 띄어쓰기 단위로 나눠 쓸 만한 낱말만 남긴다. 못 쓰는 자리는 None(구문이 이어지지 않게)."""
    title = unicodedata.normalize("NFC", title)
    title = re.sub(r"\(.*?\)|\[.*?\]|#\S+", " ", title)
    out: list[str | None] = []
    for raw in title.split():
        w = re.sub(r"[^가-힣A-Za-z]", "", raw).lower()
        w = _strip_particle(w)
        ok = len(w) >= 2 and not (w.isascii() and len(w) < 3 and w not in SHORT_OK) and not _verbish(w) and (w not in STOPWORDS or w in keep)
        out.append(w if ok else None)
    return out


def phrases(groups: list[list[str]], top: int = 5, keep: set | frozenset = frozenset(),
            generic: set | frozenset = frozenset()) -> list[str]:
    """롤모델 제목에서 분야를 나타내는 두 낱말 구문(예: '유튜브 수익화', '유튜브 부업')을 뽑는다.
    여러 채널에 함께 나오는 구문을 먼저, 두 낱말이 모두 넓은 말이면 뺀다."""
    df: Counter[str] = Counter()
    tf: Counter[str] = Counter()
    for g in groups:
        seen = set()
        for t in g:
            ws = _tokens(t, keep)
            for a, b in zip(ws, ws[1:]):
                if not a or not b or a == b or (a in generic and b in generic):
                    continue
                p = f"{a} {b}"
                tf[p] += 1
                seen.add(p)
        df.update(seen)
    multi = len([g for g in groups if g]) >= 2
    cand = [p for p in tf if tf[p] >= 2 and (df[p] >= 2 or not multi or tf[p] >= 3)]
    cand.sort(key=lambda p: (df[p], tf[p]), reverse=True)
    out: list[str] = []
    for p in cand:  # 이미 고른 구문들이 두 낱말을 다 덮고 있으면 건너뜀
        if not set(p.split()) <= {w for q in out for w in q.split()}:
            out.append(p)
        if len(out) >= top:
            break
    return out


def field_keywords(groups: list[list[str]], keep: set | frozenset = frozenset(), yt_field: bool = False,
                   top: int = 8) -> list[str]:
    """검색 키워드: 분야 구문(두 낱말) + 분야 낱말. 유튜브 분야면 '조회수·구독자' 같은 넓은 낱말은 홀로 쓰지 않는다."""
    generic = GENERIC_YT if yt_field else frozenset()
    ph = phrases(groups, 5, keep | ({"유튜브", "youtube"} if yt_field else set()), generic)
    used = {w for p in ph for w in p.split()}
    pool = shared_keywords(groups, 16, keep) + keywords([t for g in groups for t in g], 16, keep)
    singles: list[str] = []
    for w in pool:
        if w not in generic and w not in used and w not in singles:
            singles.append(w)
    return (ph + singles)[:top]


def topic_words(titles: list[str], keep: set | frozenset = frozenset(), top: int = 40) -> set[str]:
    """채널이 주로 다루는 낱말들(넓은 유튜브 용어 빼고). 롤모델과 겹치는지 볼 때 쓴다."""
    return set(keywords(titles, top, keep)) - GENERIC_YT - DOMAIN_WORDS
