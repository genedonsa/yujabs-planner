"""화면(ui/index.html)이 부르는 기능이 앱(desktop.Api)에 실제로 있는지 확인한다.
기능을 고치거나 이름을 바꾸다가 버튼이 조용히 고장 나는 것을 빌드 단계에서 막는 장치."""
import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.modules.setdefault("webview", types.SimpleNamespace(windows=[], FOLDER_DIALOG=0, OPEN_DIALOG=0))


def test_every_api_call_in_ui_exists():
    import desktop
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    called = set(re.findall(r"api\.([a-zA-Z_]\w*)\(", html))
    missing = sorted(n for n in called if not callable(getattr(desktop.Api, n, None)))
    assert not missing, f"화면이 부르는데 앱에 없는 기능: {missing}"


def test_every_id_used_in_script_exists_in_markup():
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    script = html.split("<script>")[-1]
    used = set(re.findall(r'\$\("([\w-]+)"\)', script))
    defined = set(re.findall(r'id="([\w-]+)"', html))
    missing = sorted(used - defined)
    assert not missing, f"스크립트가 찾는데 화면에 없는 칸: {missing}"


def test_ui_files_are_inside_ui_folder():
    """앱 창은 ui 폴더 밖 파일을 못 읽는다(글꼴·캐릭터가 안 나오던 v0.2.32 문제 재발 방지)."""
    html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8").split("<script>")[0]
    refs = re.findall(r'(?:src|href)="([^"#:$]+)"', html) + re.findall(r"url\(['\"]?([^)'\"]+)", html)
    bad = [r for r in refs if r.startswith("..") or not (ROOT / "ui" / r).exists()]
    assert not bad, f"ui 폴더에 없는 파일을 씀: {bad}"
