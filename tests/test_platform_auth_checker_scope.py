"""★★★ [G1-A02] 정적 검사 대상은 **지금 릴리스의 파일**로 좁힌다.

## 왜 좁히는가 — 느슨하게 하는 것이 아니다

`.archive` 에는 지난 릴리스의 코드가 그대로 남아 있다. 그것까지 검사하면 **이미 고친 결함이
계속 새 릴리스를 막는다.** 개발자는 「내 코드에 없는데 왜 걸리지」에서 원인을 못 찾고, 결국
검사를 끄는 쪽을 택한다 — 꺼진 검사는 없는 것과 같다.

⚠️ 지금 내보내는 파일에 자체 인증이 있으면 **그대로 걸려야 한다.** 그것이 아래 대조군이다.
"""
import os

from nodes.utils.platform_auth_checker import _iter_files, scan_paths

#: 검사에 확실히 걸리는 코드 한 줄(로그인 폼).
BAD = '<form class="login"><input type="password" /></form>\n'


def _write(path, text=BAD):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def test_아카이브의_옛_산출물은_검사하지_않는다(tmp_path):
    ws = str(tmp_path / "proj")
    _write(os.path.join(ws, ".archive", "r1", "Login.jsx"))
    r = scan_paths([ws])
    assert r["ok"] is True, f"아카이브의 옛 코드가 새 릴리스를 막았다: {r['blocking']}"
    assert r["scanned"] == 0


def test_지금_릴리스_파일의_자체인증은_그대로_걸린다(tmp_path):
    """★ 대조군 — 위 제외가 「아무것도 안 본다」가 되면 통제가 아니라 고장이다."""
    ws = str(tmp_path / "proj")
    _write(os.path.join(ws, "src", "Login.jsx"))
    r = scan_paths([ws])
    assert r["ok"] is False and r["summary"]["blocking"] >= 1


def test_임시_백업_파일은_검사하지_않는다(tmp_path):
    ws = str(tmp_path / "proj")
    _write(os.path.join(ws, "src", "Login.jsx.bak"))
    _write(os.path.join(ws, "src", "~$Login.jsx"))
    #: ⚠️ `.bak` 은 확장자 규칙(`_EXTS`)에도 안 걸리지만, `~$Login.jsx` 는 걸린다 —
    #   그래서 이름 규칙이 따로 필요하다.
    assert list(_iter_files(ws)) == []


def test_빌드_산출물도_검사하지_않는다(tmp_path):
    ws = str(tmp_path / "proj")
    _write(os.path.join(ws, "dist", "bundle.js"))
    _write(os.path.join(ws, "node_modules", "x", "index.js"))
    assert scan_paths([ws])["scanned"] == 0
