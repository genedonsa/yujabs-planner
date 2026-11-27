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


def current_fingerprint(url: str = "") -> str:
    url = url or ACCESS_URL
    if not url:
        raise AccessError("앱 설정에 암호 확인 주소가 없습니다. 운영자에게 문의해 주세요.")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "yujabs-planner"})
        with urllib.request.urlopen(req, timeout=15) as r:
            text = r.read().decode("utf-8-sig")
    except Exception as e:
        raise AccessError("암호를 확인하지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.") from e
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2 or not rows[1] or len(rows[1][0].strip()) != 64:
        raise AccessError("암호 확인 시트의 형식이 올바르지 않습니다. 운영자에게 문의해 주세요.")
    return rows[1][0].strip().lower()


def check(password: str, expected: str | None = None) -> bool:
    """expected를 주면 그 값과 비교(테스트용), 없으면 시트에서 읽어 온다."""
    if not password or not password.strip():
        return False
    expected = expected if expected is not None else current_fingerprint()
    return fingerprint(password) == expected
