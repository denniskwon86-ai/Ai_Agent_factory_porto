import hashlib
import shutil
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime, timezone

class CodeBuilder:
    def __init__(self, workspace_root: str):
        if not workspace_root:
            raise ValueError("CodeBuilder: workspace_root가 명시되어야 합니다.")
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
    
    def delete_files(self, rel_paths: List[str]) -> List[str]:
        """워크스페이스 안의 파일을 삭제한다. 삭제된 경로 목록을 돌려준다.

        ⚠️ [2026-07-27] 파이프라인에 삭제 수단이 없어 리팩터링/스택 전환이 불가능했다
          (실측 test_a1_v9 E2E-04: 같은 삭제 지시가 8회 반복되고도 파일이 남았다).
        안전장치: 워크스페이스 밖 경로·`.git` 등 내부 디렉터리는 거부한다."""
        removed = []
        root = self.workspace_root.resolve()
        for rel in rel_paths or []:
            try:
                rel_norm = str(rel).replace("\\", "/").lstrip("/")
                if not rel_norm or rel_norm.startswith("."):
                    continue
                target = (self.workspace_root / rel_norm).resolve()
                # 경로 이탈(`../`) 차단 — 워크스페이스 밖은 절대 건드리지 않는다.
                if root not in target.parents and target != root:
                    print(f"⚠️ [Deleter] 워크스페이스 밖 경로 삭제 거부: {rel}")
                    continue
                if any(seg in {".git", ".candidate", ".failures", "node_modules"} for seg in target.parts):
                    continue
                if target.is_file():
                    target.unlink()
                    removed.append(rel_norm)
            except Exception as e:
                print(f"⚠️ [Deleter] 삭제 실패 ({rel}): {e}")
        if removed:
            print(f"🗑️ [CodeBuilder] 파일 {len(removed)}건 삭제: {removed[:6]}")
        return removed

    def run(self, state: Dict[str, Any], extracted_files: List[Dict[str, str]]) -> Tuple[Dict[str, Any], List[bool]]:
        """
        [전면 재설계된 헤드리스 빌더]
        에이전트가 추출한 {"file_path": "...", "code": "..."} 배열을 받아
        원자적으로 디스크에 쓰고 file_index를 업데이트합니다.
        """
        # ══════════════════════════════════════════════════════════════════════
        # ★ [2026-07-27 C4] 후보 스테이징 → 전량 검증 → 일괄 반영 (전부 아니면 전무)
        # ══════════════════════════════════════════════════════════════════════
        # ⚠️ 두 가지 결함을 함께 고친다.
        #   ① "한 파일만 써져도 성공": 기존 판정은 `any(results)` 였다. 3개 파일 중 1개만
        #      써져도 build_status=success 가 되어, 반쯤 쓰인 워크스페이스가 커밋되고
        #      다음 태스크가 그 위에서 돌았다.
        #   ② 부분 쓰기 오염: 파일 단위 원자성은 있었지만 **프로젝트 단위 트랜잭션**이
        #      아니었다. 앞 파일들을 쓴 뒤 뒤 파일에서 실패하면 실물이 이미 오염된 상태다.
        # → 먼저 후보 영역에 전부 쓰고, 전량 성공했을 때만 실물로 승격한다.
        candidates: List[Tuple[Path, str]] = []
        skipped = []
        for file_info in extracted_files:
            file_path = file_info.get("file_path")
            code_content = file_info.get("code")
            if not file_path or not code_content:
                skipped.append(file_path or "(경로 없음)")
                continue
            candidates.append((self.workspace_root / file_path, code_content))

        if not candidates:
            state["build_status"] = "failed"
            state["build_error_log"] = (
                " CodeBuilder: 반영할 유효한 파일이 없습니다"
                + (f" (내용이 비어 건너뛴 항목: {skipped[:5]})" if skipped else "")
            )
            return state, []

        # ── 1단계: 후보 영역(.candidate)에 전량 기록 ──
        staged: List[Tuple[Path, Path, str]] = []   # (후보경로, 최종경로, 코드)
        stage_root = self.workspace_root / ".candidate"
        ok_all = True
        fail_reason = ""
        for full_path, code_content in candidates:
            try:
                rel = full_path.relative_to(self.workspace_root)
            except ValueError:
                rel = Path(full_path.name)
            cand_path = stage_root / rel
            if not self._atomic_write(cand_path, code_content):
                ok_all = False
                fail_reason = f"후보 영역 쓰기 실패: {rel}"
                break
            staged.append((cand_path, full_path, code_content))

        # ── 2단계: 전량 성공했을 때만 실물로 승격 ──
        results: List[bool] = []
        if ok_all:
            for cand_path, full_path, code_content in staged:
                success = self._atomic_write(full_path, code_content)
                results.append(success)
                if not success:
                    ok_all = False
                    fail_reason = f"실물 반영 실패: {full_path.name}"
                    break
                self._update_file_index(state, str(full_path), code_content)

        # ── 3단계: 후보 영역 정리 ──
        try:
            if stage_root.exists():
                shutil.rmtree(stage_root, ignore_errors=True)
        except Exception:
            pass

        if ok_all and results and all(results):
            state["build_status"] = "success"
            state["build_error_log"] = ""
        else:
            state["build_status"] = "failed"
            state["build_error_log"] = (
                f" CodeBuilder: 파일 반영이 완전하지 않습니다 — {fail_reason or '일부 파일 쓰기 실패'}. "
                f"(요청 {len(candidates)}건 / 반영 성공 {sum(1 for r in results if r)}건). "
                "부분 반영 상태를 남기지 않도록 실패로 처리합니다."
            )
        return state, results

    def _atomic_write(self, full_path: Path, new_code: str) -> bool:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = full_path.with_suffix(full_path.suffix + ".tmp")
        
        try:
            tmp_path.write_text(new_code, encoding="utf-8")
            tmp_path.replace(full_path)
            return True
        except Exception as e:
            print(f"⚠️ [Atomic Writer] 파일 실물 저장 실패 ({full_path.name}): {e}")
            if tmp_path.exists():
                tmp_path.unlink()
            return False

    def _update_file_index(self, state: Dict[str, Any], file_path: str, content: str):
        if "file_index" not in state:
            state["file_index"] = {}
            
        try:
            rel_path = str(Path(file_path).relative_to(self.workspace_root)).replace("\\", "/")
        except ValueError:
            rel_path = Path(file_path).name

        file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()

        if rel_path not in state["file_index"]:
            state["file_index"][rel_path] = {
                "path": rel_path,
                "last_modified_agent": "Developer",
                "last_modified_task": state.get("current_sprint_task_id", "unknown"),
                "last_modified_at": datetime.now(timezone.utc).isoformat(),
                "change_summary": "Auto-generated by pipeline",
                "purpose": "Component implementation",
                "last_hash": file_hash,
                "dependencies": []
            }
        else:
            meta = state["file_index"][rel_path]
            meta["last_modified_agent"] = "Developer"
            meta["last_modified_at"] = datetime.now(timezone.utc).isoformat()
            meta["last_modified_task"] = state.get("current_sprint_task_id", "unknown")
            meta["last_hash"] = file_hash