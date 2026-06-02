import re
import os
import ast
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional, TypedDict
from datetime import datetime, timezone

from state import ProjectState

class PatchResult(TypedDict):
    success: bool
    file_path: str
    action: str
    target: Optional[str]
    lines_changed: int
    error: Optional[str]
    warning: Optional[str]
    match_method: Optional[str]

class CodeBuilder:
    def __init__(self, workspace_root: str = "./workspace"):
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
    
    def run(self, state: ProjectState, tech_lead_output: str) -> Tuple[ProjectState, List[PatchResult]]:
        """메인 엔트리 포인트"""
        instructions = self._parse_instructions(tech_lead_output)
        results = []
        
        for inst in instructions:
            result = self._apply_single_patch(inst)
            results.append(result)
            if result["success"]:
                self._update_file_index(state, result)
                
        state["build_status"] = "success" if all(r["success"] for r in results) else "failed"
        
        # 에러 발생 시 로그를 state에 저장하여 다음 에이전트가 복구할 수 있도록 함
        errors = [r["error"] for r in results if not r["success"] and r.get("error")]
        if errors:
            state["build_error_log"] = "\n".join(errors)
        else:
            state["build_error_log"] = ""
            
        return state, results

    def _parse_instructions(self, output: str) -> List[Dict]:
        """Tech Lead의 최신 XML 형식 파싱 (<files><file action=...>...</file></files>)"""
        instructions = []
        
        # <file ...> ... </file> 블록 추출
        file_pattern = re.compile(r'<file\s+action="([^"]+)"\s+path="([^"]+)">\s*(.*?)\s*</file>', re.DOTALL)
        
        for match in file_pattern.finditer(output):
            action, path, inner_content = match.groups()
            target = None
            replace_block = inner_content.strip()
            
            # <replace-block target="..."> 추출
            rb_match = re.search(r'<replace-block\s+target="([^"]+)">(.*?)</replace-block>', inner_content, re.DOTALL)
            if rb_match:
                target = rb_match.group(1)
                replace_block = rb_match.group(2).strip()
            else:
                # <target> 태그 탐색 (Fallback)
                t_match = re.search(r'<target>(.*?)</target>', inner_content)
                if t_match:
                    target = t_match.group(1).strip()
            
            instructions.append({
                "action": action.lower(),
                "path": path,
                "target": target,
                "replace_block": replace_block
            })
            
        return instructions

    def _apply_single_patch(self, instruction: Dict) -> PatchResult:
        action = instruction["action"]
        file_path = instruction["path"]
        target = instruction.get("target")
        new_content = instruction.get("replace_block", "")
        
        full_path = self.workspace_root / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)

        if action == "create":
            return self._atomic_write(full_path, new_content, "", target, "create")

        if not full_path.exists():
            return {"success": False, "error": f"File not found: {file_path}", "action": action, "file_path": str(full_path), "lines_changed": 0, "target": target, "warning": None, "match_method": None}

        original_code = full_path.read_text(encoding="utf-8")
        
        if action == "delete":
            full_path.unlink()
            return {"success": True, "action": "delete", "file_path": str(full_path), "lines_changed": -len(original_code.splitlines()), "target": target, "error": None, "warning": None, "match_method": None}

        # Smart Patch 적용 (4계층)
        patched_code, match_method = self._smart_patch(original_code, target, new_content, full_path.suffix)
        
        if patched_code is None:
            return {"success": False, "error": f"Target not found: {target}", "action": action, "file_path": str(full_path), "lines_changed": 0, "target": target, "warning": None, "match_method": None}

        # Atomic Write + Validation
        return self._atomic_write(full_path, patched_code, original_code, target, match_method)

    def _smart_patch(self, code: str, target: str, new_content: str, file_ext: str) -> Tuple[Optional[str], str]:
        """4계층 스마트 매칭"""
        if not target or target.lower() == "전체파일":
            return new_content, "full_replace"

        # 1. Exact Match (Python AST)
        if file_ext == ".py":
            result = self._patch_python_ast(code, target, new_content)
            if result: 
                return result, "ast_exact"
        
        # 2. Regex Function/Class Match
        result = self._patch_regex(code, target, new_content)
        if result: 
            return result, "regex"
        
        # 3. Marker Match (Fallback)
        result = self._patch_marker(code, target, new_content)
        if result: 
            return result, "marker"
        
        # 4. Last Resort
        return None, "not_found"

    def _patch_python_ast(self, code: str, target: str, new_content: str) -> Optional[str]:
        """Python AST 기반 라인 추출 및 치환 (원본 포맷팅 보존)"""
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.name == target:
                        # AST 노드의 시작/종료 라인 확보
                        start_line = node.lineno - 1
                        end_line = node.end_lineno
                        
                        lines = code.splitlines()
                        # 정확한 블록만 새 코드로 교체
                        patched = "\n".join(lines[:start_line]) + "\n" + new_content + "\n" + "\n".join(lines[end_line:])
                        return patched
        except SyntaxError:
            pass # 문법 에러가 있는 코드는 정규식으로 Fallback
        return None

    def _patch_regex(self, code: str, target: str, new_content: str) -> Optional[str]:
        """고급 정규식 패턴 탐색 (TS/JS 등 다중 언어 지원)"""
        patterns = [
            rf"(?m)^(?:export\s+)?(?:async\s+)?(?:def|class|const|function|interface)\s+{re.escape(target)}\b[\s\S]*?^(?=\S)",
            rf"(?m)^(?:export\s+)?(?:const|let|var)\s+{re.escape(target)}\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=]*)\s*=>[\s\S]*?^(?=\S)"
        ]
        for pattern in patterns:
            match = re.search(pattern, code)
            if match:
                return code[:match.start()] + new_content + "\n" + code[match.end():]
        return None

    def _patch_marker(self, code: str, target: str, new_content: str) -> Optional[str]:
        """주석 마커 기반 탐색"""
        patterns = [
            rf"//\s*@TARGET:\s*{re.escape(target)}[\s\S]*?//\s*@END",
            rf"/\*\s*@TARGET:\s*{re.escape(target)}\s*\*/[\s\S]*?/\*\s*@END\s*\*/",
            rf"#\s*@TARGET:\s*{re.escape(target)}[\s\S]*?#\s*@END"
        ]
        for pattern in patterns:
            match = re.search(pattern, code, re.IGNORECASE)
            if match:
                return code[:match.start()] + new_content + "\n" + code[match.end():]
        return None

    def _atomic_write(self, full_path: Path, new_code: str, original: str, target: str, method: str) -> PatchResult:
        """원자적 쓰기 + 언어별 컴파일 검증"""
        tmp_path = full_path.with_suffix(full_path.suffix + ".tmp")
        
        try:
            tmp_path.write_text(new_code, encoding="utf-8")
            
            # 파이썬 파일인 경우 임시 파일 문법 검증
            if full_path.suffix == ".py":
                compile(new_code, str(full_path), "exec")
            
            # 성공 시 원자적 교체
            os.replace(tmp_path, full_path)
            
            return {
                "success": True,
                "file_path": str(full_path),
                "action": "update" if original else "create",
                "target": target,
                "lines_changed": len(new_code.splitlines()) - len(original.splitlines()),
                "match_method": method,
                "error": None,
                "warning": None
            }
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink()
            return {
                "success": False, 
                "file_path": str(full_path),
                "action": "update" if original else "create",
                "target": target,
                "lines_changed": 0,
                "match_method": method,
                "error": f"Validation/Write Error: {str(e)}", 
                "warning": None
            }

    def _update_file_index(self, state: ProjectState, result: PatchResult):
        """성공한 패치에 대해 ProjectState의 SSOT(file_index) 업데이트"""
        file_path = result["file_path"]
        
        if "file_index" not in state:
            state["file_index"] = {}
            
        # 워크스페이스 루트 기준 상대 경로 추출 (안전하게)
        try:
            rel_path = str(Path(file_path).relative_to(self.workspace_root)).replace("\\", "/")
        except ValueError:
            rel_path = Path(file_path).name

        current_content = Path(file_path).read_text(encoding="utf-8")
        file_hash = hashlib.md5(current_content.encode('utf-8')).hexdigest()

        if rel_path not in state["file_index"]:
            state["file_index"][rel_path] = {
                "path": rel_path,
                "last_modified_agent": "CodeBuilder",
                "last_modified_task": state.get("current_sprint_task_id", "unknown"),
                "last_modified_at": datetime.now(timezone.utc).isoformat(),
                "last_modified_by_task": state.get("current_sprint_task_id", "unknown"),
                "change_summary": f"Target {result['target']} updated via {result['match_method']}",
                "purpose": "Updated by pipeline",
                "last_hash": file_hash,
                "dependencies": []
            }
        else:
            meta = state["file_index"][rel_path]
            meta["last_modified_agent"] = "CodeBuilder"
            meta["last_modified_at"] = datetime.now(timezone.utc).isoformat()
            meta["change_summary"] = f"Target {result['target']} updated via {result['match_method']}"
            meta["last_hash"] = file_hash

# agent_graph.py 연동용 브릿지 함수
def run_code_builder(state: ProjectState) -> ProjectState:
    print("\n[Agent] CodeBuilder 실행 중... (스마트 병합 엔진 가동)")
    
    # 워크스페이스 경로 가져오기 (기본값 설정)
    workspace_root = state.get("workspace_root", "./workspace")
    builder = CodeBuilder(workspace_root=workspace_root)
    
    # 프론트/백엔드 출력물에서 지시사항 가져오기 (가장 최근의 코드를 우선 적용)
    target_code = state.get("frontend_code", "") + "\n" + state.get("backend_code", "")
    
    updated_state, results = builder.run(state, target_code)
    
    for res in results:
        status = "✅" if res["success"] else "❌"
        target_info = f" [{res['target']}]" if res.get("target") else ""
        print(f"  {status} {res['action'].upper()} {res['file_path']}{target_info} ({res['match_method']})")
        if not res["success"] and res.get("error"):
            print(f"     └─ Error: {res['error']}")
            
    return updated_state