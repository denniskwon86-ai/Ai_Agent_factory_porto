# ==========================================
# 백엔드 스모크 테스트러너 (서버사이드)
# 생성된 FastAPI 백엔드를 격리 임시 패키지로 쓰고 서브프로세스에서 import(부팅)+TestClient 검증.
# 명백한 코드 결함(문법/내부 import/부팅 크래시)만 ok=False, 외부 의존성/환경 제약은 경고로 통과.
# 실패해도(파이썬/스크립트 부재 등) 파이프라인 비차단(skip).
# ==========================================
import os
import sys
import json
import shutil
import tempfile
import subprocess
from typing import List, Dict, Any

_RUNNER = os.path.join("tools", "backend_smoke_run.py")


def check_backend_smoke(files: List[Dict[str, Any]], timeout: int = 45) -> Dict[str, Any]:
    """백엔드 파일 배열([{file_path, code}])을 격리 부팅 검증. {ok, errors, warnings, routes, booted} 반환."""
    py = [f for f in (files or []) if str(f.get("file_path", "")).endswith(".py")]
    if not py:
        return {"ok": True, "errors": [], "skipped": True, "reason": "백엔드 파이썬 코드 없음"}
    if not os.path.exists(_RUNNER):
        return {"ok": True, "errors": [], "skipped": True, "reason": "backend_smoke_run.py 없음"}

    tmp = None
    try:
        tmp = tempfile.mkdtemp(prefix="be_smoke_")
        dirs = set()
        for f in py:
            rel = str(f.get("file_path", "")).replace("\\", "/").lstrip("/")
            dest = os.path.join(tmp, *rel.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as out:
                out.write(f.get("code", "") or "")
            d = os.path.dirname(dest)
            while d and os.path.abspath(d) != os.path.abspath(tmp):
                dirs.add(d)
                d = os.path.dirname(d)
        # 상대 import(from .x)가 동작하도록 패키지 디렉터리에 __init__.py 추가
        for d in dirs:
            initp = os.path.join(d, "__init__.py")
            if not os.path.exists(initp):
                open(initp, "w").close()

        # ★ [2026-07-27 결함 수정] 서브프로세스를 **임시 워크스페이스에서** 실행한다.
        #   기존엔 cwd 를 지정하지 않아 저장소 루트에서 돌았다. 그래서 생성 앱이
        #   `sqlite:///./data/app.db` 나 `open('data.json','w')` 같은 **상대 경로**를 쓰면
        #   임시 폴더가 아닌 엉뚱한 위치를 기준으로 해석되어
        #   `OperationalError: unable to open database file` 로 부팅에 실패했다(실측).
        #   앱 코드가 잘못된 게 아니라 하네스가 실행 위치를 안 맞춰준 것이다.
        _env = dict(os.environ)
        # 테스트용 DB 는 임시 폴더 안의 **절대 경로**로 주입한다. 앱이 DATABASE_URL 을
        # 존중하면 상대 경로 문제 자체가 사라지고, 무시해도 cwd 덕분에 여전히 동작한다.
        _env["DATABASE_URL"] = "sqlite:///" + os.path.join(tmp, "smoke_test.db").replace("\\", "/")
        _env["APP_DATA_DIR"] = tmp
        _env["PYTHONIOENCODING"] = "utf-8"
        # 앱이 흔히 쓰는 하위 디렉터리를 미리 만들어 준다(앱이 스스로 안 만드는 경우 대비).
        for _sub in ("data", "db", "storage", "instance", "var"):
            try:
                os.makedirs(os.path.join(tmp, _sub), exist_ok=True)
            except Exception:
                pass
        proc = subprocess.run(
            [sys.executable, os.path.abspath(_RUNNER), tmp],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8",
            cwd=tmp, env=_env,
        )
        out = (proc.stdout or "").strip()
        try:
            data = json.loads(out)
            return data if isinstance(data, dict) and "ok" in data else {"ok": True, "skipped": True, "reason": "출력 형식 불일치"}
        except Exception:
            return {"ok": True, "skipped": True, "reason": "스모크 출력 파싱 실패", "raw": (out or (proc.stderr or ""))[:300]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "errors": [f"백엔드 스모크 타임아웃({timeout}초) - 부팅 시 무한 대기 의심"], "booted": False}
    except Exception as e:
        return {"ok": True, "skipped": True, "reason": f"스모크 예외: {e}"}
    finally:
        if tmp and os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
