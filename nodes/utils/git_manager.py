import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

class GitManager:
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self._init_if_needed()

    def _run_cmd(self, cmd: list) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                cmd,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                encoding="utf-8", 
                check=False
            )
        except FileNotFoundError:
            print(" [GitManager] 시스템에 'git'이 설치되어 있지 않거나 PATH에 없습니다.")
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="Git not found")

    def _init_if_needed(self):
        git_dir = self.workspace_root / ".git"
        if not git_dir.exists():
            self._run_cmd(["git", "init"])
            self._run_cmd(["git", "config", "user.name", "AI Factory Agent"])
            self._run_cmd(["git", "config", "user.email", "agent@aifactory.local"])
            
            readme = self.workspace_root / "README.md"
            if not readme.exists():
                readme.write_text("# AI Factory Unified Workspace\n자동 생성된 워크스페이스입니다.", encoding="utf-8")
                
            self._run_cmd(["git", "add", "."])
            self._run_cmd(["git", "commit", "-m", "chore: Initialize unified workspace"])
            print(" [GitManager] 통합 워크스페이스 Git 저장소 초기화 완료")

    def commit_sprint_changes(self, task_id: str, state: Dict[str, Any]) -> Optional[str]:
        status = self._run_cmd(["git", "status", "--porcelain"])
        if not status.stdout.strip():
            print("ℹ️ [GitManager] 변경된 파일이 없어 커밋을 건너뜁니다.")
            return None

        self._run_cmd(["git", "add", "."])

        file_index = state.get("file_index", {})
        change_summaries = []
        for path, meta in file_index.items():
            if meta.get("last_modified_task") == task_id and meta.get("change_summary"):
                change_summaries.append(f"- {path}: {meta['change_summary']}")

        if change_summaries:
            body = "\n".join(change_summaries)
            summary_title = "워크스페이스 코드 병합 및 업데이트"
        else:
            body = "- 자동 병합된 코드 업데이트"
            summary_title = "코드 자동 병합 완료"

        commit_msg = f"feat({task_id}): {summary_title}\n\n[AI Factory Auto Commit]\n{body}"

        res = self._run_cmd(["git", "commit", "-m", commit_msg])
        if res.returncode == 0:
            log_res = self._run_cmd(["git", "rev-parse", "HEAD"])
            commit_hash = log_res.stdout.strip()
            print(f" [GitManager] Git 커밋 완료 (Hash: {commit_hash[:7]})")
            return commit_hash
        else:
            print(f"⚠️ [GitManager] 커밋 실패: {res.stderr}")
            return None

    def read_file_at_commit(self, commit: Optional[str], rel_path: str) -> Optional[str]:
        """지정 커밋 시점의 파일 내용을 반환(회귀 게이트의 baseline용). 없으면 None.
        git 미설치/경로 부재/커밋 부재 시 None(=비교 생략, 비차단)."""
        if not commit or not rel_path:
            return None
        rel = str(rel_path).replace("\\", "/")
        res = self._run_cmd(["git", "show", f"{commit}:{rel}"])
        if res.returncode == 0:
            return res.stdout
        return None

    #  누락되었던 롤백 복구 엔진 추가 (서킷 브레이커 크래시 원천 차단)
    #: ★★★ 롤백이 **지우면 안 되는 것** — 산출물이 아니라 «진행 기록» 이다.
    #:
    #: ⚠️⚠️ [2026-08-26 실측] `git clean -fd` 가 추적되지 않은 파일을 전부 지우면서
    #:   파이프라인 자신의 기록까지 날렸다. 실제로 이렇게 됐다:
    #:
    #:     · `00_wbs_master_plan.json` — 완료 표시가 사라져 **끝난 태스크가 다시 돌았다**
    #:       (E2E-01 이 두 번, TASK-02 가 두 번. 그때마다 LLM 비용을 다시 썼다).
    #:     · `contracts/` — 승인 도장과 초안이 사라졌다. 승인이 없어지니 재승인을 다시
    #:       받아야 했고, 초안이 없어지니 「계약 대상인데 초안이 없다」로 **다른 태스크까지
    #:       영영 막혔다**(TASK-02 가 그렇게 죽었다).
    #:
    #: ★ 같은 판단을 이 저장소가 이미 한 번 했다 — 실패 번들을 워크스페이스 **밖**으로
    #:   옮긴 이유가 「진단 자료는 롤백 대상이 되면 안 된다」였다(`nodes/execution.py`).
    #:   WBS·계약은 밖으로 옮길 수 없으므로(프로젝트의 것이다) **롤백을 넘겨** 보존한다.
    #: ⚠️ 생성 «코드» 는 그대로 되돌린다. 되돌리는 목적이 그것이다.
    PRESERVE = (
        "00_wbs_master_plan.json",   # 무엇이 끝났나
        "project_meta.json",         # 템플릿 바인딩(잃으면 전 태스크가 'default' 로 강등)
        "config_snapshot.json",      # 무엇으로 돌았나
        "contracts",                 # 계약 정본·승인 도장·초안
    )

    def _read_preserved(self) -> Dict[str, bytes]:
        """보존 대상을 메모리로 뜬다. 없으면 조용히 건너뛴다."""
        saved: Dict[str, bytes] = {}
        for rel in self.PRESERVE:
            p = self.workspace_root / rel
            if p.is_file():
                try:
                    saved[rel] = p.read_bytes()
                except OSError:
                    pass
            elif p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file():
                        try:
                            saved[str(f.relative_to(self.workspace_root)).replace("\\", "/")] = f.read_bytes()
                        except OSError:
                            pass
        return saved

    def _restore_preserved(self, saved: Dict[str, bytes]) -> None:
        """롤백 뒤 되돌려 놓는다. ⚠️ 실패해도 던지지 않는다 — 복원 실패가 종결 처리를
        막으면 파이프라인이 그 자리에서 멎는다. 대신 **말한다.**"""
        for rel, data in saved.items():
            p = self.workspace_root / rel
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            except OSError as e:
                print(f"⚠️ [GitManager] 진행 기록 복원 실패({rel}): {e}")

    def rollback_to_safe_state(self, target_commit: Optional[str] = None):
        print(f" [GitManager] 안전 지대(Safe State)로 강제 롤백을 시작합니다.")

        #: ★ 지우기 **전에** 뜬다. 뒤에 뜨면 이미 없다.
        saved = self._read_preserved()

        self._run_cmd(["git", "reset", "--hard"])
        self._run_cmd(["git", "clean", "-fd"])

        if target_commit:
            res = self._run_cmd(["git", "checkout", target_commit])
            if res.returncode == 0:
                print(f"[OK] [GitManager] 지정된 커밋({target_commit[:7]})으로 롤백 성공.")
                self._restore_preserved(saved)
                return
            else:
                print(f"⚠️ [GitManager] 커밋 이동 실패. HEAD 기준으로 롤백을 대체합니다.")

        self._run_cmd(["git", "checkout", "dev"]) # 또는 주 브랜치
        #: ★ 성공·대체 두 경로 **모두**에서 되돌린다. 한쪽만 복원하면 그 갈래에서만
        #:   기록이 사라지고, 그런 결함은 재현이 어렵다.
        self._restore_preserved(saved)
        print("[OK] [GitManager] 최종 커밋(HEAD) 상태로 작업 공간 복원 완료"
              + (f" (진행 기록 {len(saved)}개 보존)" if saved else "") + ".")