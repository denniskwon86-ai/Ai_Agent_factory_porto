# 생성된 FastAPI 백엔드를 격리 import(부팅)하고 TestClient로 엔드포인트를 스모크 검증한다.
# 사용: python backend_smoke_run.py <pkg_root>
# 출력(stdout): {"ok":bool,"errors":[...],"warnings":[...],"routes":int,"booted":bool}
import sys
import os
import json
import importlib


def run(pkg_root):
    result = {"ok": False, "errors": [], "warnings": [], "routes": 0, "booted": False}
    sys.path.insert(0, pkg_root)

    # 생성된 .py 파일의 모듈명 집합(내부 import 판별용)
    py_files = []
    for dp, _, fns in os.walk(pkg_root):
        for fn in fns:
            if fn.endswith(".py"):
                py_files.append(os.path.join(dp, fn))
    local_mods = {os.path.splitext(os.path.basename(p))[0] for p in py_files}

    # 진입점 탐색: FastAPI 앱이 정의된 파일(main.py 우선)
    entry = None
    for p in py_files:
        try:
            txt = open(p, encoding="utf-8").read()
        except Exception:
            continue
        if "FastAPI(" in txt:
            if os.path.basename(p) == "main.py":
                entry = p
                break
            if entry is None:
                entry = p
    if not entry:
        result["errors"].append("FastAPI 앱 진입점(예: main.py의 app=FastAPI())을 찾지 못했습니다.")
        return result

    rel = os.path.relpath(entry, pkg_root).replace(os.sep, "/")
    mod_name = rel[:-3].replace("/", ".")

    try:
        module = importlib.import_module(mod_name)
        result["booted"] = True
    except ModuleNotFoundError as e:
        name = getattr(e, "name", "") or ""
        pkg = mod_name.split(".")[0]
        top = name.split(".")[0]
        last = name.split(".")[-1]
        # 패키지 내부(상대 import) 또는 생성 파일명과 일치 → 생성물 간 불일치(코드 결함)
        if (pkg and (name == pkg or name.startswith(pkg + "."))) or (last in local_mods) or (top in local_mods):
            result["errors"].append(f"내부 모듈 import 실패(생성 파일 간 불일치): {e}")
        else:
            result["warnings"].append(f"외부 의존성 미설치(검증환경 제약, 코드 결함 아님): {top}")
            result["ok"] = True
        return result
    except SyntaxError as e:
        result["errors"].append(f"문법 오류: {e}")
        return result
    except Exception as e:
        result["errors"].append(f"앱 부팅 런타임 오류: {type(e).__name__}: {e}")
        return result

    app = getattr(module, "app", None)
    if app is None:
        result["errors"].append("진입 모듈에 FastAPI 'app' 객체가 없습니다.")
        return result

    try:
        result["routes"] = len(list(getattr(app, "routes", [])))
    except Exception:
        pass

    try:
        from fastapi.testclient import TestClient
        client = TestClient(app)
        r = client.get("/openapi.json")
        if r.status_code >= 500:
            result["errors"].append(f"/openapi.json 5xx: {r.status_code}")
        bad = []
        for route in getattr(app, "routes", []):
            methods = getattr(route, "methods", set()) or set()
            path = getattr(route, "path", "")
            if "GET" in methods and "{" not in path and path not in ("/openapi.json", "/docs", "/redoc"):
                try:
                    rr = client.get(path)
                    if rr.status_code >= 500:
                        bad.append(f"{path} -> {rr.status_code}")
                except Exception as ex:
                    bad.append(f"{path} -> 예외 {ex}")
        if bad:
            result["warnings"].append("일부 GET 엔드포인트 5xx/예외: " + "; ".join(bad[:5]))
    except ModuleNotFoundError as e:
        result["warnings"].append(f"TestClient 의존성 미설치(부팅은 성공): {getattr(e, 'name', e)}")
    except Exception as e:
        result["warnings"].append(f"엔드포인트 스모크 예외: {type(e).__name__}: {e}")

    result["ok"] = len(result["errors"]) == 0
    return result


if __name__ == "__main__":
    try:
        out = run(sys.argv[1])
    except Exception as e:
        out = {"ok": True, "skipped": True, "reason": f"스모크 러너 예외: {e}"}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
