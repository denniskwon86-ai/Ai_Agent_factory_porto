import subprocess
from pathlib import Path
from typing import Dict, Any

def run_background_tests_and_scans(workspace_root: str) -> Dict[str, Any]:
    """
    백그라운드에서 단위 테스트(pytest/jest) 및 보안 취약점 스캔(bandit 등)을
    실행하고 그 결과를 수집하여 반환합니다.
    (Phase 2: LLM 주관적 QA의 한계를 보완하기 위한 결정론적 지표 제공)
    """
    root = Path(workspace_root)
    results = {
        "pytest": {"run": False, "ok": False, "output": ""},
        "bandit": {"run": False, "ok": False, "output": ""},
        "py_compile": {"run": False, "ok": False, "output": ""},
        "frontend_check": {"run": False, "ok": False, "output": ""}
    }

    # 1. Pytest 실행 (backend 폴더나 tests 폴더 존재 시)
    if (root / "backend").exists() or (root / "tests").exists():
        try:
            results["pytest"]["run"] = True
            proc = subprocess.run(
                ["pytest", "--disable-warnings", "-q"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=10
            )
            results["pytest"]["ok"] = (proc.returncode == 0)
            results["pytest"]["output"] = proc.stdout[-1000:] + "\n" + proc.stderr[-500:]
        except Exception as e:
            results["pytest"]["output"] = f"Error running pytest: {e}"

    # 2. Bandit 보안 스캔 실행 (Python 코드 대상)
    if (root / "backend").exists() or list(root.glob("*.py")):
        try:
            results["bandit"]["run"] = True
            target = "backend" if (root / "backend").exists() else "."
            proc = subprocess.run(
                ["bandit", "-r", target, "-lll", "-ii"],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=10
            )
            results["bandit"]["ok"] = (proc.returncode == 0)
            results["bandit"]["output"] = proc.stdout[-1000:]
        except Exception as e:
            results["bandit"]["output"] = f"Error running bandit: {e}"

    # 3. 파이썬 기본 구문(Syntax) 검증
    if list(root.rglob("*.py")):
        try:
            results["py_compile"]["run"] = True
            proc = subprocess.run(
                ["python", "-m", "compileall", "-q", "."],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=10
            )
            results["py_compile"]["ok"] = (proc.returncode == 0)
            if not results["py_compile"]["ok"]:
                results["py_compile"]["output"] = proc.stderr[-1000:] + "\n" + proc.stdout[-1000:]
        except Exception as e:
            results["py_compile"]["output"] = f"Error running py_compile: {e}"

    # 4. 프론트엔드 빌드/구문 검증 (package.json 기반)
    if (root / "package.json").exists() or (root / "frontend" / "package.json").exists():
        try:
            results["frontend_check"]["run"] = True
            target_dir = root / "frontend" if (root / "frontend" / "package.json").exists() else root
            # 빌드가 없으면 설치 후 빌드 시도
            if not (target_dir / "node_modules").exists():
                subprocess.run(["npm", "install"], cwd=str(target_dir), capture_output=True, timeout=60)
                
            proc = subprocess.run(
                ["npm", "run", "build"],
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                timeout=45
            )
            results["frontend_check"]["ok"] = (proc.returncode == 0)
            if not results["frontend_check"]["ok"]:
                results["frontend_check"]["output"] = proc.stderr[-1000:] + "\n" + proc.stdout[-1000:]
        except Exception as e:
            results["frontend_check"]["output"] = f"Error running frontend check: {e}"

    return results

def format_test_results_for_qa(results: Dict[str, Any]) -> str:
    """QA 노드에 주입하기 위한 마크다운 포맷팅"""
    lines = ["\n[자동화 테스트 및 스캔 결과 (결정론적 지표)]"]
    
    if not any(v.get("run", False) for v in results.values()):
        return ""

    if results.get("py_compile", {}).get("run"):
        status = "✅ PASS" if results["py_compile"]["ok"] else "❌ FAIL (Syntax Error 발견)"
        lines.append(f"- 파이썬 구문 검증: {status}")
        if not results["py_compile"]["ok"]:
            lines.append(f"  ```\n  {results['py_compile']['output'].strip()}\n  ```")

    if results.get("frontend_check", {}).get("run"):
        status = "✅ PASS" if results["frontend_check"]["ok"] else "❌ FAIL (프론트엔드 빌드 에러)"
        lines.append(f"- 프론트엔드 빌드 검증: {status}")
        if not results["frontend_check"]["ok"]:
            lines.append(f"  ```\n  {results['frontend_check']['output'].strip()}\n  ```")

    if results.get("pytest", {}).get("run"):
        status = "✅ PASS" if results["pytest"]["ok"] else "❌ FAIL"
        lines.append(f"- Pytest 단위 테스트: {status}")
        if not results["pytest"]["ok"]:
            lines.append(f"  ```\n  {results['pytest']['output'].strip()}\n  ```")

    if results.get("bandit", {}).get("run"):
        status = "✅ PASS (취약점 없음)" if results["bandit"]["ok"] else "⚠️ WARNING (보안 취약점 발견)"
        lines.append(f"- Bandit 보안 스캔: {status}")
        if not results["bandit"]["ok"]:
            lines.append(f"  ```\n  {results['bandit']['output'].strip()}\n  ```")

    return "\n".join(lines)
