"""앱에 같이 묶여 가는 실행 도구 찾기 + 인터넷 연결 설정.

회원 컴퓨터에 아무것도 따로 깔지 않아도 되도록, 필요한 것은 앱 안에 넣어 두고 여기서 찾는다.
- 인증서(certifi): 맥 앱에서 https 연결이 '인증서 확인 실패'로 막히는 것을 막는다.
- deno: 유튜브 정보를 읽을 때 yt-dlp가 쓰는 자바스크립트 실행기. 앱의 bin/ 폴더에 들어 있다.
"""
from __future__ import annotations

import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def ssl_contexts() -> list[ssl.SSLContext]:
    """시도 순서: ① 컴퓨터(맥 키체인·윈도우 인증서 저장소) — 브라우저와 같은 기준이라 백신·회사 보안 프로그램이
    인증서를 바꿔 끼워도 통과 ② 앱에 든 인증서 묶음(certifi) ③ 파이썬 기본."""
    out = []
    try:
        import truststore
        out.append(truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
    except Exception:
        pass
    try:
        import certifi
        out.append(ssl.create_default_context(cafile=certifi.where()))
    except Exception:
        pass
    out.append(ssl.create_default_context())
    return out


def ssl_context() -> ssl.SSLContext:
    return ssl_contexts()[0]


def use_system_certificates() -> bool:
    """앱 시작 때 한 번: 모든 https 연결(yt-dlp 포함)이 컴퓨터 인증서 저장소를 쓰게 한다."""
    try:
        import truststore
        truststore.inject_into_ssl()
        return True
    except Exception:
        return False


def urlopen(req, timeout: int = 30):
    last = None
    for ctx in ssl_contexts():
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except urllib.error.HTTPError:
            raise
        except Exception as e:  # 인증서·연결 문제면 다음 방법으로
            last = e
    raise last


def bundled_deno() -> str | None:
    exe = "deno.exe" if os.name == "nt" else "deno"
    p = BASE / "bin" / exe
    if p.exists():
        if os.name != "nt":
            try:
                p.chmod(p.stat().st_mode | 0o111)
            except OSError:
                pass
        return str(p)
    return None


def js_runtimes() -> dict:
    """yt-dlp 옵션. 앱에 든 deno가 있으면 그것을, 없으면 yt-dlp 기본(컴퓨터에 깔린 deno)을 쓴다."""
    p = bundled_deno()
    return {"deno": {"path": p}} if p else {"deno": {}}
