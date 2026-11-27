"""대표용: 새 암호의 지문(해시)을 만든다. 이 값을 암호 시트 A2 칸에 붙여 넣는다.

사용:  python tools/make_password.py 새암호
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from planner.access import fingerprint  # noqa: E402

if len(sys.argv) < 2:
    sys.exit("사용법: python tools/make_password.py 새암호")
print(fingerprint(" ".join(sys.argv[1:])))
