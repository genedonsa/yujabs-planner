"""회원 전용 암호. 대표가 매달 직접 바꾼다.

동작
- 대표의 구글 시트(링크 보기 권한) A2 칸에 '암호의 지문(해시)'이 들어 있다. 암호 원문은 어디에도 저장하지 않는다.
- 앱은 시작할 때마다 그 칸을 읽어, 회원이 넣은 암호의 지문과 같은지 확인한다.
- 대표가 새 암호의 지문으로 칸을 바꾸면, 옛 암호를 쓰던 앱은 다음 실행부터 새 암호를 묻는다.

서버·비용 없음. 시트 주소(ACCESS_URL)는 빌드할 때 넣는다.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import urllib.request

from .net import ssl_context


def urlopen(req, timeout: int = 15):
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())

SALT = "yujabs-planner-v1:"
# 예: https://docs.google.com/spreadsheets/d/<시트ID>/export?format=csv&gid=0
ACCESS_URL = os.environ.get(
    "YTP_ACCESS_URL",
    "https://docs.google.com/spreadsheets/d/1j6b4rW6bva9s5KMJ9fZceuME0oqxjp4HSpMtn1osjn8/export?format=csv&gid=0",
)


class AccessError(Exception):
    """확인 자체를 못 했을 때(인터넷 끊김 등). 암호가 틀린 것과 구분한다."""


def fingerprint(password: str) -> str:
    return hashlib.sha256((SALT + password.strip()).encode("utf-8")).hexdigest()


SHEET_ID = "1j6b4rW6bva9s5KMJ9fZceuME0oqxjp4HSpMtn1osjn8"
FALLBACK_URLS = [
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid=0",
]
LAST_ERROR = ""


def _download(url: str) -> str:
    """인증서 묶음(certifi)으로 먼저, 안 되면 컴퓨터 기본 인증서로 한 번 더."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (CornBot)"})
    try:
        with urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8-sig")
    except Exception:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8-sig")


def _parse(text: str) -> set[str]:
    rows = list(csv.reader(io.StringIO(text)))[1:]
    return {row[0].strip().strip('"').lower() for row in rows if row and len(row[0].strip().strip('"')) == 64}


def current_fingerprints(url: str = "") -> set[str]:
    """시트 A열 2행부터의 지문 전부. 여러 줄이면 그중 하나만 맞아도 통과(한/영 입력 실수 대비)."""
    global LAST_ERROR
    url = url or ACCESS_URL
    if not url:
        raise AccessError("앱 설정에 암호 확인 주소가 없습니다. 운영자에게 문의해 주세요.")
    errors = []
    got_text = False
    for u in [url] + [f for f in FALLBACK_URLS if f != url]:
        try:
            text = _download(u)
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}"[:160])
            continue
        got_text = True
        fps = _parse(text)
        if fps:
            LAST_ERROR = ""
            return fps
        errors.append("시트 내용 형식 다름: " + text[:80].replace("\n", " "))
    LAST_ERROR = " | ".join(errors)
    if got_text:
        raise AccessError("암호 확인 시트의 형식이 올바르지 않습니다. 운영자에게 문의해 주세요. (자세히: " + LAST_ERROR[:120] + ")")
    raise AccessError("암호를 확인하지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요. (자세히: " + LAST_ERROR[:120] + ")")


def current_fingerprint(url: str = "") -> str:
    """하위 호환: 첫 번째 지문."""
    return sorted(current_fingerprints(url))[0]


def check(password: str, expected: str | None = None) -> bool:
    """expected를 주면 그 값과 비교(테스트용), 없으면 시트의 지문들과 비교한다."""
    if not password or not password.strip():
        return False
    allowed = {expected} if expected is not None else current_fingerprints()
    return fingerprint(password) in allowed
