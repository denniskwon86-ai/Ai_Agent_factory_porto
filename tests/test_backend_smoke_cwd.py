# ==========================================
# 백엔드 스모크 하네스 회귀 테스트 (2026-07-27)
#
# 실측 결함 재현: test_a1_v3 실행 중 스모크가 반복적으로 실패했다.
#   ❌ [TestRunner] 백엔드 스모크 실패: ['앱 부팅 런타임 오류: OperationalError: unable to open database file']
#
# 원인은 생성된 앱이 아니라 **하네스**였다. `subprocess.run` 에 `cwd=` 가 없어서
# 서브프로세스가 임시 워크스페이스가 아닌 저장소 루트에서 실행됐고, 앱이 쓰는
# 상대 경로(`./data/app.db`, `data.json`)가 엉뚱한 곳으로 해석됐다.
#
# 이 테스트는 "상대 경로를 쓰는 정상 앱"이 스모크를 통과해야 한다는 계약을 고정한다.
# (하네스가 앱을 부당하게 반려하지 않을 것 — 결함 #20 렌더 하네스와 같은 종류의 문제)
# ==========================================
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.utils import backend_smoke


_APP_RELATIVE_SQLITE = '''\
import os
import sqlite3
from fastapi import FastAPI

app = FastAPI()

# 상대 경로 DB — 브라우저/서버 앱이 흔히 쓰는 형태다.
# cwd 가 쓰기 가능한 작업 폴더로 맞춰져 있으면 정상 동작해야 한다.
os.makedirs("data", exist_ok=True)
_conn = sqlite3.connect("data/app.db")
_conn.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, value TEXT)")
_conn.commit()


@app.get("/health")
def health():
    return {"status": "ok"}
'''

_APP_RELATIVE_JSONFILE = '''\
import json
from fastapi import FastAPI

app = FastAPI()

# 상대 경로 파일 쓰기 — test_a1_v4 의 main.py 가 실제로 쓰던 형태.
with open("data.json", "w", encoding="utf-8") as f:
    json.dump([], f)


@app.get("/health")
def health():
    return {"status": "ok"}
'''


def _run(code: str):
    return backend_smoke.check_backend_smoke([{"file_path": "main.py", "code": code}], timeout=60)


def test_relative_sqlite_path_app_is_not_falsely_rejected():
    """상대 경로 SQLite 를 쓰는 앱이 'unable to open database file' 로 반려되면 안 된다."""
    res = _run(_APP_RELATIVE_SQLITE)
    if res.get("skipped"):
        return  # 러너/파이썬 부재 환경에서는 비차단 skip 이 정상 동작
    errors = " ".join(res.get("errors") or [])
    assert "unable to open database file" not in errors, (
        f"하네스가 정상 앱을 거짓 반려했습니다(cwd 미지정 회귀): {errors}"
    )
    assert res.get("ok"), f"상대 경로 SQLite 앱이 스모크를 통과해야 합니다: {res}"


def test_relative_json_file_app_is_not_falsely_rejected():
    """상대 경로 파일 쓰기(test_a1_v4 main.py 형태)도 통과해야 한다."""
    res = _run(_APP_RELATIVE_JSONFILE)
    if res.get("skipped"):
        return
    assert res.get("ok"), f"상대 경로 파일 쓰기 앱이 스모크를 통과해야 합니다: {res}"


def test_smoke_subprocess_runs_in_temp_workspace():
    """작업 디렉터리가 임시 워크스페이스여야 한다 — 저장소 루트를 오염시키면 안 된다.

    앱이 cwd 에 파일을 만들고, 그 파일이 저장소 루트에 생기지 않는지로 검증한다."""
    marker = "smoke_cwd_marker_should_not_reach_repo_root.txt"
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    leaked = os.path.join(repo_root, marker)
    if os.path.exists(leaked):
        os.remove(leaked)

    code = (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        f"open({marker!r}, 'w').write('x')\n"
        "@app.get('/health')\n"
        "def health():\n"
        "    return {'status': 'ok'}\n"
    )
    res = _run(code)
    try:
        if res.get("skipped"):
            return
        assert not os.path.exists(leaked), (
            "스모크 서브프로세스가 저장소 루트에서 실행되어 파일을 남겼습니다 — cwd 가 임시 폴더여야 합니다."
        )
    finally:
        if os.path.exists(leaked):
            os.remove(leaked)


def test_real_syntax_error_is_still_rejected():
    """하네스를 관대하게 만든 결과로 **진짜 깨진 코드가 통과하면 안 된다**.

    (결함 #20 렌더 하네스 수정 때 세운 원칙과 동일 — 과잉 완화는 검증을 무의미하게 만든다.
     실제로 v4 에서 나온 `def load_data):` 형태를 그대로 쓴다.)"""
    broken = (
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "def load_data):\n"
        "    return []\n"
    )
    res = _run(broken)
    if res.get("skipped"):
        return
    assert not res.get("ok"), f"구문 오류가 있는 코드는 반드시 반려되어야 합니다: {res}"
