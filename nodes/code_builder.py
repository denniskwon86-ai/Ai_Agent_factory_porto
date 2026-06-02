import os
import re
import subprocess
from state import ProjectState

# [신규 추가] 통합 WBS 관리 유틸리티 임포트
from nodes.utils.wbs_manager import WBSManager 

def sanitize_path(base_dir: str, file_path: str) -> str:
    """Path Traversal 공격 방지를 위한 경로 검증 및 정규화"""
    full_path = os.path.realpath(os.path.join(base_dir, file_path))
    base_real_path = os.path.realpath(base_dir)
    
    if not full_path.startswith(base_real_path):
        raise ValueError(f"🚨 [보안 경고] 경로 순회(Path Traversal) 공격 감지: {file_path}")
    return full_path

def truncate_error_log(log: str, head: int = 10, tail: int = 40) -> str:
    """토큰 오버플로우 방지를 위한 Head+Tail 에러 로그 트런케이트"""
    if not log:
        return ""
    lines = log.strip().splitlines()
    if len(lines) <= head + tail:
        return log
    return "\n".join(lines[:head]) + "\n\n... [중략 (Token Overflow 방지)] ...\n\n" + "\n".join(lines[-tail:])

def parse_xml_codes(markdown_content: str) -> list:
    """마크다운 내 XML 태그 <file path="...">코드</file> 파싱"""
    pattern = re.compile(r'<file\s+path=["\'](.*?)["\']\s*>(.*?)</file>', re.DOTALL)
    matches = pattern.findall(markdown_content)
    return matches

def run_code_builder(state: ProjectState) -> ProjectState:
    print("\n" + "="*50)
    print("🛠️ [CodeBuilderNode] 결정론적 빌드 및 패키징 작업을 시작합니다.")
    print("="*50)
    
    output_dir = state.get("output_dir", "")
    if not output_dir:
        state["build_status"] = "failed"
        state["build_error_log"] = "출력 디렉토리(output_dir)가 지정되지 않았습니다."
        return state

    workspace_dir = os.path.join(output_dir, "workspace")
    os.makedirs(workspace_dir, exist_ok=True)
    state["project_output_path"] = workspace_dir
    state["build_status"] = "pending"
    state["build_error_log"] = ""
    
    print("📁 1. 마크다운 내 소스코드 추출 및 파일 시스템 빌드 중...")
    combined_code_content = (state.get("frontend_code", "") + "\n" + state.get("backend_code", ""))
    files_to_create = parse_xml_codes(combined_code_content)
    
    if not files_to_create:
        print("⚠️ 생성할 물리 파일이 발견되지 않았습니다. XML 표준 태그 형식을 확인하세요.")
        state["build_status"] = "failed"
        state["build_error_log"] = "코드 산출물 내에 유효한 <file path='...'> 태그가 존재하지 않습니다. 반드시 코드를 <file path='경로'>...</file> 로 감싸야 합니다."
        return state

    try:
        for file_path, code_body in files_to_create:
            file_path = file_path.strip()
            safe_file_path = sanitize_path(workspace_dir, file_path)
            os.makedirs(os.path.dirname(safe_file_path), exist_ok=True)
            
            with open(safe_file_path, "w", encoding="utf-8") as f:
                f.write(code_body.strip())
            print(f"  └─ 파일 생성 완료: {file_path}")
    except ValueError as val_err:
        state["build_status"] = "failed"
        state["build_error_log"] = str(val_err)
        return state
    except Exception as e:
        state["build_status"] = "failed"
        state["build_error_log"] = f"파일 시스템 생성 중 예외 발생: {str(e)}"
        return state

    print("📦 2. 프로젝트 타입 감지 및 격리 빌드 환경 구성 중...")
    
    # [수정] state에 명시된 project_type 최우선 참조
    declared_type = state.get("project_type", "").lower()
    
    if declared_type:
        is_python_project = declared_type in ("python", "fullstack")
        is_node_project   = declared_type in ("node", "fullstack")
        print(f"  📋 선언된 프로젝트 타입: {declared_type}")
    else:
        # [수정] 선언값 누락 시, os.walk 대신 루트 레벨만 안전하게 폴백(Fallback) 감지
        print("  ⚠️ project_type 미선언. 최상위 루트 레벨 파일로 폴백 감지합니다.")
        is_python_project = False
        is_node_project = False
        
        try:
            root_files = os.listdir(workspace_dir)
            is_python_project = "requirements.txt" in root_files or "main.py" in root_files
            is_node_project   = "package.json" in root_files
            
            # 백엔드/프론트엔드 폴더가 분리되어 있을 경우를 대비한 추가 검사
            if not is_python_project and os.path.exists(os.path.join(workspace_dir, "backend")):
                is_python_project = True
            if not is_node_project and os.path.exists(os.path.join(workspace_dir, "frontend")):
                is_node_project = True
        except Exception as e:
            print(f"  ❌ 파일 시스템 감지 중 오류: {e}")

    # 진입점(Entry Point) 확인
    if os.path.exists(os.path.join(workspace_dir, "main.py")):
        state["executable_entry_point"] = os.path.join(workspace_dir, "main.py")
    elif os.path.exists(os.path.join(workspace_dir, "backend", "main.py")):
        state["executable_entry_point"] = os.path.join(workspace_dir, "backend", "main.py")
    else:
        state["executable_entry_point"] = "진입점 확인 필요"

    accumulated_errors = []

    if is_python_project:
        print("  🐍 Python 프로젝트 감지: 독립 가상환경(venv)을 구성합니다.")
        venv_dir = os.path.join(workspace_dir, ".venv")
        try:
            subprocess.run(["python", "-m", "venv", venv_dir], check=True, capture_output=True, encoding="utf-8",    # 👈 [신규 추가] 윈도우 인코딩 충돌 방지
    errors="replace", timeout=60)
            
            if os.name == "nt":
                pip_path = os.path.join(venv_dir, "Scripts", "pip")
                python_path = os.path.join(venv_dir, "Scripts", "python")
            else:
                pip_path = os.path.join(venv_dir, "bin", "pip")
                python_path = os.path.join(venv_dir, "bin", "python")
                
            req_path = os.path.join(workspace_dir, "requirements.txt")
            if not os.path.exists(req_path) and os.path.exists(os.path.join(workspace_dir, "backend", "requirements.txt")):
                req_path = os.path.join(workspace_dir, "backend", "requirements.txt")
                
            if os.path.exists(req_path):
                print(f"  📦 의존성 설치 중 ({req_path})... 무한 입력 대기 방지 가동")
                result = subprocess.run(
                    [pip_path, "install", "-r", req_path, "--no-input"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",    # 👈 [신규 추가] 윈도우 인코딩 충돌 방지
                    errors="replace",    # 👈 [신규 추가] 깨진 문자는 강제로 변환하여 다운 방지
                    timeout=300
                )
                if result.returncode != 0:
                    print("  ❌ Python 의존성 설치 실패!")
                    accumulated_errors.append(f"--- Python Pip Install Error ---")
                    accumulated_errors.append(result.stderr)
                else:
                    print("  ✅ Python 의존성 설치 성공!")
                    
                if state["executable_entry_point"] and os.path.exists(state["executable_entry_point"]):
                    print("  🔨 진입점 문법(Syntax) 검증 수행 중...")
                    syntax_result = subprocess.run(
                        [python_path, "-m", "py_compile", state["executable_entry_point"]],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",    # 👈 [신규 추가] 윈도우 인코딩 충돌 방지
                        errors="replace",    # 👈 [신규 추가] 깨진 문자는 강제로 변환하여 다운 방지
                        timeout=30
                    )
                    if syntax_result.returncode != 0:
                        print("  ❌ 문법 오류(Syntax Error) 감지!")
                        accumulated_errors.append(f"--- Python Syntax Error ({state['executable_entry_point']}) ---")
                        accumulated_errors.append(syntax_result.stderr)
                    else:
                        print("  ✅ 문법 검증 통과!")
        except subprocess.TimeoutExpired:
            print("  ❌ Python 빌드 타임아웃 발생 (300초 초과)")
            accumulated_errors.append("Python 가상환경 구성 또는 의존성 설치 중 300초 타임아웃이 발생했습니다.")
        except Exception as ex:
            accumulated_errors.append(f"Python 가상환경 구성 중 에러 발생: {str(ex)}")

    if is_node_project:
        print("  ⬢ Node.js 프로젝트 감지: 로컬 node_modules 패키징을 수행합니다.")
        node_target_dir = workspace_dir
        if not os.path.exists(os.path.join(workspace_dir, "package.json")) and os.path.exists(os.path.join(workspace_dir, "frontend", "package.json")):
            node_target_dir = os.path.join(workspace_dir, "frontend")
            
        try:
            print(f"  📦 npm install 실행 중 ({node_target_dir})... 인터랙티브 프롬프트 자동 응답 설정")
            npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
            
            result = subprocess.run(
                [npm_cmd, "install", "--yes"],
                cwd=node_target_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",    # 👈 [신규 추가] 윈도우 인코딩 충돌 방지
                errors="replace",    # 👈 [신규 추가] 깨진 문자는 강제로 변환하여 다운 방지
                timeout=300
            )
            if result.returncode != 0:
                print("  ❌ Node.js 의존성 설치 실패!")
                accumulated_errors.append(f"--- Node.js npm install Error ---")
                accumulated_errors.append(result.stderr)
            else:
                print("  ✅ Node.js 의존성 설치 성공!")
                
                with open(os.path.join(node_target_dir, "package.json"), "r", encoding="utf-8") as f:
                    pkg_content = f.read()
                if '"build":' in pkg_content:
                    print("  🔨 npm run build 구동 중...")
                    build_result = subprocess.run(
                        [npm_cmd, "run", "build"],
                        cwd=node_target_dir,
                        capture_output=True,
                        text=True,
                        timeout=180
                    )
                    if build_result.returncode != 0:
                        print("  ❌ 프론트엔드 정적 빌드 실패!")
                        accumulated_errors.append(f"--- Node.js npm run build Error ---")
                        accumulated_errors.append(build_result.stderr)
                    else:
                        print("  ✅ 프론트엔드 프로덕션 빌드 성공!")
                        
        except subprocess.TimeoutExpired:
            print("  ❌ Node.js 빌드 타임아웃 발생 (300초 초과)")
            accumulated_errors.append("Node.js 의존성 설치 또는 정적 빌드 중 타임아웃이 발생했습니다.")
        except Exception as ex:
            accumulated_errors.append(f"Node.js 빌드 중 에러 발생: {str(ex)}")

    if accumulated_errors:
        print("🚨 빌드 과정 중 결함이 발견되어 컴파일 실패 판정을 내립니다.")
        raw_error_log = "\n\n".join(accumulated_errors)
        truncated_log = truncate_error_log(raw_error_log, head=10, tail=40)
        state["build_status"] = "failed"
        state["build_error_log"] = truncated_log
        # 실패 시 노드 안에서 카운터를 명시적으로 +1 증가시켜 DB에 저장
        state["developer_retry_count"] = state.get("developer_retry_count", 0) + 1
    else:
        print("🎉 모든 소스코드가 컴파일 과정을 무결하게 통과하여 실제 빌드가 완성되었습니다!")
        state["build_status"] = "success"
        state["build_error_log"] = ""
        state["developer_retry_count"] = 0 # 성공 시 카운터 초기화
        
        # ---------------------------------------------------------
        # [신규 로직] QA 통과 및 빌드 성공 시 WBS 자동 체크아웃
        # ---------------------------------------------------------
        task_id = state.get("current_sprint_task_id")
        if task_id:
            print(f"✅ [CodeBuilder] 로컬 QA 테스트 통과. WBS 태스크 [{task_id}] 체크아웃 진행...")
            
            # 하드코딩 지양: state에서 경로 동적 로드 (기본값 설정)
            wbs_path = state.get("wbs_master_plan_path", "00_wbs_master_plan.json")
            
            # WBSManager 인스턴스화 및 체크아웃 시도 (FileLock 기반 원자적 처리)
            wbs_mgr = WBSManager(json_path=wbs_path)
            checkout_result = wbs_mgr.checkout_task(task_id)
            
            if checkout_result:
                print(f"🎉 [CodeBuilder] 태스크 [{task_id}] 완료! JSON 및 Excel 갱신 성공.")
            else:
                print(f"⚠️ [CodeBuilder] 태스크 완료 처리에 실패했습니다. (동시성 락 타임아웃 또는 JSON 누락)")
        
    return state