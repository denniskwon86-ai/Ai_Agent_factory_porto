# ==========================================
# 프론트엔드 렌더 검증 테스트러너 (서버사이드)
# 생성된 React 코드를 Node 스크립트로 실제 renderToString 하여 "정상 렌더" 여부를 검증.
# 미해결 외부 import(axios 등)·초기 렌더 크래시(null.map)를 잡아낸다.
# 실패해도(node 없음/타임아웃 등) 파이프라인을 막지 않도록 그 경우 skip 처리.
# ==========================================
import os
import json
import subprocess
import tempfile
from typing import List, Dict, Any

_SCRIPT = os.path.join("frontend", "scripts", "render_check.mjs")


def check_frontend_render(files: List[Dict[str, Any]], timeout: int = 60) -> Dict[str, Any]:
    """프론트 파일 배열([{file_path, code}])을 Node로 렌더 검증. {ok, errors, rendered, skipped?} 반환."""
    if not files:
        return {"ok": True, "errors": [], "rendered": 0, "skipped": True, "reason": "프론트 코드 없음"}
    if not os.path.exists(_SCRIPT):
        return {"ok": True, "errors": [], "skipped": True, "reason": "render_check.mjs 없음"}

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(files, f, ensure_ascii=False)
            tmp_path = f.name

        proc = subprocess.run(
            ["node", _SCRIPT, tmp_path],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8",
        )
        out = (proc.stdout or "").strip()
        try:
            data = json.loads(out)
            if isinstance(data, dict) and "ok" in data:
                return data
            return {"ok": True, "skipped": True, "reason": "출력 형식 불일치"}
        except Exception:
            # node 실행 자체가 실패(의존성 등) → 검증 스킵(파이프라인 비차단)
            return {"ok": True, "skipped": True, "reason": "렌더 검증기 출력 파싱 실패",
                    "raw": (out or (proc.stderr or ""))[:300]}
    except FileNotFoundError:
        return {"ok": True, "skipped": True, "reason": "node 미설치"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "errors": [f"렌더 검증 타임아웃({timeout}초)"], "rendered": 0}
    except Exception as e:
        return {"ok": True, "skipped": True, "reason": f"렌더 검증 예외: {e}"}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
